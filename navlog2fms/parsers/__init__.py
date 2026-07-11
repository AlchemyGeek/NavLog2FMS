from collections.abc import Callable
from navlog2fms.models import CommonRoute

# Registry: format_key -> (fingerprint_fn, parse_fn)
# fingerprint_fn(pdf_path, ocr_text) -> bool
# parse_fn(pdf_path) -> CommonRoute
_REGISTRY: dict[str, tuple[Callable, Callable]] = {}


def register(format_key: str, fingerprint_fn: Callable, parse_fn: Callable) -> None:
    _REGISTRY[format_key] = (fingerprint_fn, parse_fn)


def detect_and_parse(pdf_path: str, ocr_text: str) -> CommonRoute:
    for format_key, (fingerprint_fn, parse_fn) in _REGISTRY.items():
        if fingerprint_fn(pdf_path, ocr_text):
            return parse_fn(pdf_path, ocr_text)
    raise ValueError(
        f"Unrecognized navlog format. Detected text snippet: {ocr_text[:200]!r}"
    )


def registered_formats() -> list[str]:
    return list(_REGISTRY.keys())


# Import parsers to trigger registration
from navlog2fms.parsers import garmin_pilot  # noqa: E402, F401
from navlog2fms.parsers import skyvector     # noqa: E402, F401
