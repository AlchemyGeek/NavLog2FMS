import os
from navlog2fms.models import ResolvedPoint, ResolvedRoute
from navlog2fms.writer import build_fms_v3

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "KAWO-KAWO.fms")


def _make_route() -> ResolvedRoute:
    return ResolvedRoute(
        departure=ResolvedPoint(ident="KAWO", type_code=1, altitude_ft=0,
                                lat=48.160750, lon=-122.159028, resolved=True, sequence=0),
        destination=ResolvedPoint(ident="KAWO", type_code=1, altitude_ft=0,
                                  lat=48.160750, lon=-122.159028, resolved=True, sequence=4),
        points=[
            ResolvedPoint(ident="LEION", type_code=11, altitude_ft=3500,
                          lat=48.083489, lon=-122.661319, resolved=True, sequence=1),
            ResolvedPoint(ident="PAE",   type_code=3,  altitude_ft=3500,
                          lat=47.919833, lon=-122.277800, resolved=True, sequence=2),
            ResolvedPoint(ident="SAVOY", type_code=11, altitude_ft=3500,
                          lat=47.975533, lon=-122.151992, resolved=True, sequence=3),
        ],
        source_format="garmin_pilot",
    )


def test_header():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[0] == "I"
    assert lines[1] == "3 version"
    assert lines[2] == "1"


def test_numenr():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[3] == "5"   # 1 dep + 3 intermediate + 1 dest


def test_departure_line():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[4] == "1 KAWO 0 48.160750 -122.159028"


def test_intermediate_fix():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[5] == "11 LEION 3500 48.083489 -122.661319"


def test_intermediate_vor():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[6] == "3 PAE 3500 47.919833 -122.277800"


def test_destination_line():
    content = build_fms_v3(_make_route())
    lines = content.splitlines()
    assert lines[8] == "1 KAWO 0 48.160750 -122.159028"


def test_matches_confirmed_xplane_fixture():
    """Output must be byte-for-byte identical to the file confirmed working in X-Plane."""
    with open(FIXTURE) as f:
        expected = f.read()
    assert build_fms_v3(_make_route()) == expected


def test_unresolved_raises():
    route = _make_route()
    route.points[0] = ResolvedPoint(ident="BOGUS", type_code=28, altitude_ft=None,
                                    lat=0.0, lon=0.0, resolved=False, sequence=1)
    try:
        build_fms_v3(route)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "BOGUS" in str(e)
