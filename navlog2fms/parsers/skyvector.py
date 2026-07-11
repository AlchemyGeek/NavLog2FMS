import re

from navlog2fms.models import CommonRoute, RoutePoint
from navlog2fms.parsers import register

FORMAT_KEY = "skyvector"

# SkyVector PDFs have no "GARMIN" branding but always have these labels
_FINGERPRINT_TOKENS = ("Planned Route", "Squawk Code")


def fingerprint(pdf_path: str, ocr_text: str) -> bool:
    return all(tok in ocr_text for tok in _FINGERPRINT_TOKENS)


def parse(pdf_path: str, ocr_text: str) -> CommonRoute:
    # --- Departure / destination from the "KAWO — KAWO" header ---
    # em-dash, en-dash, or ASCII hyphen; spaces optional
    dep_dest_match = re.search(
        r'\b([A-Z]{3,5})\s*[—–―-]+\s*([A-Z]{3,5})\b', ocr_text  # ― = U+2015
    )
    if not dep_dest_match:
        raise ValueError(
            "Could not find departure — destination header in SkyVector navlog. "
            f"Text snippet: {ocr_text[:400]!r}"
        )
    departure = dep_dest_match.group(1)
    destination = dep_dest_match.group(2)

    # --- Intermediate waypoints from "Planned Route" line ---
    route_match = re.search(
        r'Planned Route[^\n]*\n\(?([A-Z][A-Z0-9 ]+[A-Z0-9])[\).]?\s*\n',
        ocr_text
    )
    if not route_match:
        # Looser: just grab the line after "Planned Route"
        route_match = re.search(
            r'Planned Route[^\n]*\n([A-Z][A-Z0-9 ]+)',
            ocr_text
        )
    if not route_match:
        raise ValueError(
            "Could not find Planned Route line in SkyVector navlog. "
            f"Text snippet: {ocr_text[:400]!r}"
        )

    route_string = route_match.group(1).strip().rstrip(')').strip()
    intermediate = route_string.split()

    # --- Single cruise altitude ---
    # Each waypoint row shows altitude followed by a temperature: "8000 5°C"
    # Grab the first such occurrence.
    altitude: int | None = None
    alt_match = re.search(r'\b(\d{3,5})\s+[-+]?\d+\s*°\s*[Cc]', ocr_text)
    if not alt_match:
        # Fallback: look for a standalone 4-digit altitude in the table region
        alt_match = re.search(r'\b([3-9]\d{3}|[1-2]\d{4})\b', ocr_text)
    if alt_match:
        candidate = int(alt_match.group(1))
        if 500 <= candidate <= 60000:
            altitude = candidate

    points = [
        RoutePoint(
            ident=ident,
            point_type_hint=None,
            altitude_ft=altitude,
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
