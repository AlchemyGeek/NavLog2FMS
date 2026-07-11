import os
import pytest
from navlog2fms.detector import load_and_detect

PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "navlog.pdf")


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="SkyVector sample PDF not present")
def test_parse_skyvector():
    route = load_and_detect(PDF_PATH)

    assert route.source_format == "skyvector"
    assert route.departure == "KAWO"
    assert route.destination == "KAWO"

    idents = [p.ident for p in route.points]
    assert idents == ["LEION", "PAE", "SAVOY"]


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="SkyVector sample PDF not present")
def test_parse_altitude():
    route = load_and_detect(PDF_PATH)
    for pt in route.points:
        assert pt.altitude_ft == 8000


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="SkyVector sample PDF not present")
def test_route_string():
    route = load_and_detect(PDF_PATH)
    assert route.raw_route_string is not None
    assert "LEION" in route.raw_route_string
