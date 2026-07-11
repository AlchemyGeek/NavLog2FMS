import re

import fitz
import pytesseract
from PIL import Image

from navlog2fms.models import CommonRoute, RoutePoint
from navlog2fms.parsers import register

FORMAT_KEY = "garmin_pilot"
_FINGERPRINT = "GARMIN"

_AIRWAY_PAT = re.compile(r'^[VJQT]\d+')
_IDENT_PAT = re.compile(r'^[A-Z]{2,5}\d{0,2}$')
_TABLE_HDR_WORDS = {
    # Column headers (main and sub-header rows)
    'HDG', 'DTK', 'ALT', 'TAS', 'MH', 'GS', 'WCA', 'VAR',
    'WAYPOINT', 'ROUTE', 'DIST', 'ETE', 'FUEL', 'WIND',
    'LEG', 'REM', 'CUM', 'ACT', 'ETA', 'ISA',
    # Wind / performance sub-headers
    'ALOFT', 'DIR', 'SPD', 'OAT', 'KTAS', 'KIAS', 'IAS', 'OAD', 'CMP',
    # Summary section words that may appear in the same Y range
    'DATE', 'IDENT', 'ACFT', 'PERF', 'TOTAL', 'FROM', 'INFO', 'CREW',
}


def fingerprint(pdf_path: str, ocr_text: str) -> bool:
    return _FINGERPRINT in ocr_text.upper()


def _render_page(pdf_path: str, page_num: int = 0, scale: float = 3.0) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _extract_table_waypoints(img: Image.Image) -> list[tuple[str, int | None]]:
    """
    Extract (ident, altitude_ft) pairs from the Garmin Pilot waypoint table
    using positional OCR. Returns rows in table order (departure and destination
    rows included — caller strips them).
    """
    data = pytesseract.image_to_data(
        img, config='--psm 6 --oem 3', output_type=pytesseract.Output.DICT
    )

    words = []
    for i in range(len(data['text'])):
        txt = data['text'][i].strip()
        if txt and int(data['conf'][i]) > 15:
            words.append({'text': txt, 'left': data['left'][i], 'top': data['top'][i]})

    if not words:
        return []

    # Find the Y bracket of the waypoint table.
    # Table starts after the "ROUTE" label and ends before the wind/RINDSTAT footer.
    route_y: int | None = None
    end_y: int | None = None
    for w in sorted(words, key=lambda x: x['top']):
        if w['text'].upper() == 'ROUTE' and route_y is None:
            route_y = w['top']
        if route_y is not None and w['top'] > route_y + 50:
            if w['text'].upper() in ('RINDSTAT', 'STARTUP', 'TAKEOFF'):
                end_y = w['top']
                break

    if route_y is None:
        return []
    if end_y is None:
        end_y = max(w['top'] for w in words)

    # Skip the terse route string row itself (sits ~30-80px below the ROUTE label)
    table_words = [w for w in words if route_y + 80 < w['top'] < end_y]

    # Ident column: leftmost 18% of page width
    page_width = max((w['left'] for w in words), default=1000)
    ident_col_max = int(page_width * 0.18)

    # Group into rows by Y proximity (±12px tolerance)
    rows: list[list[dict]] = []
    for w in sorted(table_words, key=lambda x: x['top']):
        for row in rows:
            if abs(row[0]['top'] - w['top']) <= 12:
                row.append(w)
                break
        else:
            rows.append([w])

    for row in rows:
        row.sort(key=lambda x: x['left'])

    result: list[tuple[str, int | None]] = []
    for row in rows:
        if not row:
            continue
        # First token in the ident column must look like an ICAO waypoint ident
        ident: str | None = None
        for w in row:
            if w['left'] <= ident_col_max:
                txt = w['text']
                if _IDENT_PAT.match(txt) and txt.upper() not in _TABLE_HDR_WORDS:
                    ident = txt
                    break
        if not ident:
            continue

        # Skip rows with no numeric content at all — pure header/label rows
        if not any(re.search(r'\d', w['text']) for w in row):
            continue

        # Altitude: first 3-5 digit value in 500–60 000 ft range
        alt: int | None = None
        for w in row:
            if re.match(r'^\d{3,5}$', w['text']):
                v = int(w['text'])
                if 500 <= v <= 60000:
                    alt = v
                    break

        result.append((ident, alt))

    return result


def _parse_route_line(ocr_text: str) -> str | None:
    """Extract the terse ROUTE string (diagnostic only)."""
    # Allow dots for airway tokens like V341.OSH
    m = re.search(r'ROUTE\s*\n([A-Z][A-Z0-9 .]+[A-Z0-9])[.)]?\s*\n', ocr_text)
    if not m:
        m = re.search(r'ROUTE\s*\n?([A-Z]{2,5}(?:\s+[A-Z0-9.]{2,}){1,})', ocr_text)
    return m.group(1).strip() if m else None


def _parse_plan_altitude(ocr_text: str) -> int | None:
    """Extract cruise altitude from the summary header line."""
    m = re.search(r'\d+\.?\d*NM\s+(\d{1,2},?\d{3}|\d{4,5})FT', ocr_text)
    if not m:
        m = re.search(r'(\d{1,2},\d{3}|\d{4,5})FT', ocr_text)
    if m:
        return int(m.group(1).replace(',', ''))
    return None


def _terse_intermediates(tokens: list[str]) -> list[str]:
    """Non-airway intermediate idents from the terse route tokens (fallback only)."""
    result: list[str] = []
    for tok in tokens[1:-1]:
        base = tok.split('.')[0]
        if _AIRWAY_PAT.match(base):
            # Airway token: capture the exit fix if embedded (V341.OSH → OSH)
            if '.' in tok:
                exit_fix = tok.split('.')[1]
                if exit_fix and exit_fix not in result:
                    result.append(exit_fix)
        elif tok not in result:
            result.append(tok)
    return result


def _build_via_map(tokens: list[str], table_idents: list[str]) -> dict[str, str]:
    """
    Build ident → airway_name mapping for audit/logging.

    Walks the terse ROUTE tokens to find airway spans, then maps the
    corresponding table idents to the airway name. Fixes reached directly
    are left out (callers default to "DIRECT").
    """
    via_map: dict[str, str] = {}

    for i, tok in enumerate(tokens):
        base = tok.split('.')[0]
        if not _AIRWAY_PAT.match(base):
            continue

        airway_name = base
        # Exit fix: either embedded (V341.OSH) or the next token
        if '.' in tok:
            exit_fix: str | None = tok.split('.')[1]
        elif i + 1 < len(tokens):
            exit_fix = tokens[i + 1]
        else:
            exit_fix = None

        # Span in the table: from after the preceding direct fix to the exit fix
        prev_fix = next(
            (tokens[j] for j in range(i - 1, -1, -1)
             if not _AIRWAY_PAT.match(tokens[j].split('.')[0])),
            None,
        )
        start_idx = 0
        if prev_fix and prev_fix in table_idents:
            start_idx = table_idents.index(prev_fix) + 1

        end_idx = len(table_idents)
        if exit_fix and exit_fix in table_idents:
            end_idx = table_idents.index(exit_fix) + 1

        for ident in table_idents[start_idx:end_idx]:
            via_map[ident] = airway_name

    return via_map


def parse(pdf_path: str, ocr_text: str) -> CommonRoute:
    """Parse a Garmin Pilot navlog PDF (image-based, iOS export).

    The waypoint table is the authoritative source for ident sequence and
    altitudes (it contains airway-expanded intermediate fixes). The terse
    ROUTE line is diagnostic-only: it populates raw_route_string and
    provides via/airway annotation for RoutePoint.via.
    """
    # --- Terse ROUTE line (diagnostic) ---
    route_string = _parse_route_line(ocr_text)
    if not route_string:
        raise ValueError(
            "Could not find ROUTE line in Garmin Pilot navlog. "
            f"Text snippet: {ocr_text[:400]!r}"
        )

    tokens = route_string.split()
    if len(tokens) < 2:
        raise ValueError(f"Route has fewer than 2 idents: {tokens!r}")

    departure = tokens[0]
    destination = tokens[-1]
    plan_altitude = _parse_plan_altitude(ocr_text)
    has_airways = any(_AIRWAY_PAT.match(t.split('.')[0]) for t in tokens[1:-1])

    # --- Waypoint table (authoritative) ---
    img = _render_page(pdf_path, scale=3.0)
    table_rows = _extract_table_waypoints(img)

    # Strip departure and destination airport rows
    while table_rows and table_rows[0][0] == departure:
        table_rows = table_rows[1:]
    while table_rows and table_rows[-1][0] == destination:
        table_rows = table_rows[:-1]

    # --- Fallback: table OCR failed, use terse route idents ---
    if not table_rows:
        if has_airways:
            print(
                "  Warning: airways in terse ROUTE line but waypoint table OCR failed. "
                "Route will use compressed form — airway-expanded intermediate fixes missing."
            )
        fallback_idents = _terse_intermediates(tokens)
        table_rows = [(ident, plan_altitude) for ident in fallback_idents]

    # --- Via annotation ---
    table_ident_list = [ident for ident, _ in table_rows]
    via_map = _build_via_map(tokens, table_ident_list)

    points = [
        RoutePoint(
            ident=ident,
            point_type_hint=None,
            altitude_ft=alt if alt is not None else plan_altitude,
            via=via_map.get(ident, "DIRECT"),
            sequence=i + 1,
        )
        for i, (ident, alt) in enumerate(table_rows)
    ]

    return CommonRoute(
        departure=departure,
        destination=destination,
        points=points,
        source_format=FORMAT_KEY,
        raw_route_string=route_string,
    )


register(FORMAT_KEY, fingerprint, parse)
