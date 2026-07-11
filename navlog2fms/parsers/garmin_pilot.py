import re

from navlog2fms.models import CommonRoute, RoutePoint
from navlog2fms.parsers import register

FORMAT_KEY = "garmin_pilot"
_FINGERPRINT = "GARMIN"


def fingerprint(pdf_path: str, ocr_text: str) -> bool:
    return _FINGERPRINT in ocr_text.upper()


def parse(pdf_path: str, ocr_text: str) -> CommonRoute:
    """Parse a Garmin Pilot navlog PDF (image-based, iOS export).

    Relies on pre-OCR'd text passed in by the detector so OCR runs only once.
    """
    # --- Extract ROUTE line ---
    # Format: "ROUTE\nKAWO LEION PAE SAVOY KAWO."
    route_match = re.search(
        r'ROUTE\s*\n([A-Z][A-Z0-9 ]+[A-Z0-9])\.?\s*\n', ocr_text
    )
    if not route_match:
        # Looser fallback: ROUTE on same line or right after with optional dot/newline
        route_match = re.search(
            r'ROUTE\s*\n?([A-Z]{2,5}(?:\s+[A-Z0-9]{2,5}){1,})',
            ocr_text
        )
    if not route_match:
        raise ValueError(
            "Could not find ROUTE line in Garmin Pilot navlog. "
            f"Text snippet: {ocr_text[:400]!r}"
        )

    route_string = route_match.group(1).strip()
    idents = route_string.split()

    if len(idents) < 2:
        raise ValueError(f"Route has fewer than 2 idents: {idents}")

    departure = idents[0]
    destination = idents[-1]
    intermediate = idents[1:-1]

    # --- Extract plan altitude from summary line ---
    # Format: "55.4NM 3,500FT" — altitude follows the distance value
    plan_altitude: int | None = None
    alt_match = re.search(r'\d+\.?\d*NM\s+(\d{1,2},?\d{3}|\d{4,5})FT', ocr_text)
    if not alt_match:
        # Looser fallback
        alt_match = re.search(r'(\d{1,2},\d{3}|\d{4,5})FT', ocr_text)
    if alt_match:
        plan_altitude = int(alt_match.group(1).replace(',', ''))

    # --- Try per-waypoint altitude from table ---
    # Each table row may start with the ident followed by HDG DTK ALT ...
    # e.g. "SAVOY 42 42 3500 ..." or "241 242 3500 ..." (ident OCR'd or not)
    altitude_map: dict[str, int] = {}
    for ident in intermediate:
        m = re.search(
            rf'\b{re.escape(ident)}\b[^\n]*?(\d{{3,5}})\s+(\d{{3,5}})\s+(\d{{3,5}})',
            ocr_text
        )
        if m:
            # columns after ident: HDG DTK ALT → third number is altitude
            candidate = int(m.group(3))
            if 500 <= candidate <= 60000:
                altitude_map[ident] = candidate

    points = [
        RoutePoint(
            ident=ident,
            point_type_hint=None,
            altitude_ft=altitude_map.get(ident, plan_altitude),
            sequence=i + 1,
        )
        for i, ident in enumerate(intermediate)
    ]

    return CommonRoute(
        departure=departure,
        destination=destination,
        points=points,
        source_format=FORMAT_KEY,
        raw_route_string=route_string,
    )


register(FORMAT_KEY, fingerprint, parse)
