import pytest
from navlog2fms import config as cfg
from navlog2fms.resolver import NavDatabase, resolve
from navlog2fms.models import CommonRoute, RoutePoint

XPLANE_PATH = cfg.get_xplane_path()
pytestmark = pytest.mark.skipif(
    not XPLANE_PATH,
    reason="X-Plane path not configured — run navlog2fms once with --xplane-path to enable these tests",
)


@pytest.fixture(scope="module")
def db():
    database = NavDatabase(XPLANE_PATH)
    database.load()
    return database


def test_airport_lookup(db):
    candidates = db.lookup("KAWO")
    airports = [c for c in candidates if c.type_code == 1]
    assert len(airports) >= 1
    # Arlington Muni (Washington state) should be among the candidates
    arlington = [a for a in airports if abs(a.lat - 48.16) < 0.1 and abs(a.lon - (-122.16)) < 0.1]
    assert len(arlington) >= 1, f"Arlington Muni KAWO not found; candidates: {airports}"


def test_vor_lookup(db):
    candidates = db.lookup("PAE")
    vors = [c for c in candidates if c.type_code == 3]
    assert len(vors) >= 1


def test_fix_lookup(db):
    candidates = db.lookup("LEION")
    fixes = [c for c in candidates if c.type_code == 11]
    assert len(fixes) >= 1
    f = fixes[0]
    assert abs(f.lat - 48.08) < 0.1


def test_fix_savoy(db):
    candidates = db.lookup("SAVOY")
    fixes = [c for c in candidates if c.type_code == 11]
    assert len(fixes) >= 1


def test_unknown_ident(db):
    assert db.lookup("ZZZZZ") == []


def test_full_resolve():
    common = CommonRoute(
        departure="KAWO",
        destination="KAWO",
        points=[
            RoutePoint(ident="LEION", point_type_hint=None, altitude_ft=3500, sequence=1),
            RoutePoint(ident="PAE",   point_type_hint=None, altitude_ft=3500, sequence=2),
            RoutePoint(ident="SAVOY", point_type_hint=None, altitude_ft=3500, sequence=3),
        ],
        source_format="garmin_pilot",
        raw_route_string="KAWO LEION PAE SAVOY KAWO",
    )
    resolved = resolve(common, XPLANE_PATH)

    assert resolved.departure.ident == "KAWO"
    assert resolved.departure.type_code == 1
    assert resolved.destination.ident == "KAWO"
    assert resolved.departure.resolved

    assert len(resolved.points) == 3

    leion = resolved.points[0]
    assert leion.ident == "LEION"
    assert leion.type_code == 11
    assert leion.altitude_ft == 3500

    pae = resolved.points[1]
    assert pae.ident == "PAE"
    assert pae.type_code == 3
    # Should pick the US PAE, not the Thai one
    assert abs(pae.lat - 47.92) < 0.1

    savoy = resolved.points[2]
    assert savoy.ident == "SAVOY"
    assert savoy.type_code == 11


def test_unresolved_raises():
    common = CommonRoute(
        departure="KAWO",
        destination="KAWO",
        points=[RoutePoint(ident="ZZZZZ", point_type_hint=None, altitude_ft=3500, sequence=1)],
        source_format="garmin_pilot",
        raw_route_string="KAWO ZZZZZ KAWO",
    )
    with pytest.raises(ValueError, match="ZZZZZ"):
        resolve(common, XPLANE_PATH)
