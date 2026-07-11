import os
import pytest
from navlog2fms.detector import load_and_detect

PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "KAWO KAWO N117ZS 07102026 NAVLOG.pdf")


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="Sample PDF not present")
def test_parse_garmin_pilot():
    route = load_and_detect(PDF_PATH)

    assert route.source_format == "garmin_pilot"
    assert route.departure == "KAWO"
    assert route.destination == "KAWO"

    idents = [p.ident for p in route.points]
    assert idents == ["LEION", "PAE", "SAVOY"]


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="Sample PDF not present")
def test_parse_altitudes():
    route = load_and_detect(PDF_PATH)
    for pt in route.points:
        assert pt.altitude_ft is not None
        assert 1000 <= pt.altitude_ft <= 20000


@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="Sample PDF not present")
def test_route_string():
    route = load_and_detect(PDF_PATH)
    assert route.raw_route_string is not None
    assert "KAWO" in route.raw_route_string
