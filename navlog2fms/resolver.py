import math
import os
from dataclasses import dataclass

from navlog2fms.models import CommonRoute, ResolvedPoint, ResolvedRoute

# Nav database file locations relative to X-Plane install root
_FIX_DAT_REL = "Resources/default data/earth_fix.dat"
_NAV_DAT_REL = "Resources/default data/earth_nav.dat"
_APT_DAT_REL = "Global Scenery/Global Airports/Earth nav data/apt.dat"

# X-Plane earth_nav.dat type codes we care about for FMS routing
_NAV_TYPES = {
    2: 2,   # NDB → FMS type 2
    3: 3,   # VOR/VORTAC/VOR-DME → FMS type 3
}


@dataclass
class _NavEntry:
    ident: str
    type_code: int
    lat: float
    lon: float


class NavDatabase:
    """Loads and caches X-Plane nav databases from a given install path."""

    def __init__(self, xplane_path: str) -> None:
        self._xplane_path = xplane_path
        self._fixes: dict[str, list[_NavEntry]] = {}    # earth_fix.dat
        self._navaids: dict[str, list[_NavEntry]] = {}  # earth_nav.dat (VOR/NDB only)
        self._airports: dict[str, list[_NavEntry]] = {} # apt.dat
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        fix_path = os.path.join(self._xplane_path, _FIX_DAT_REL)
        nav_path = os.path.join(self._xplane_path, _NAV_DAT_REL)
        apt_path = os.path.join(self._xplane_path, _APT_DAT_REL)

        for path, label in [(fix_path, "earth_fix.dat"), (nav_path, "earth_nav.dat"), (apt_path, "apt.dat")]:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"X-Plane nav database not found: {path}")

        self._fixes = _load_fixes(fix_path)
        self._navaids = _load_navaids(nav_path)
        self._airports = _load_airports(apt_path)
        self._loaded = True

    def lookup(self, ident: str) -> list[_NavEntry]:
        """Return all candidates for an ident across airports, navaids, and fixes."""
        candidates: list[_NavEntry] = []
        candidates.extend(self._airports.get(ident, []))
        candidates.extend(self._navaids.get(ident, []))
        candidates.extend(self._fixes.get(ident, []))
        return candidates


def _add(d: dict[str, list[_NavEntry]], entry: _NavEntry) -> None:
    d.setdefault(entry.ident, []).append(entry)


def _load_fixes(path: str) -> dict[str, list[_NavEntry]]:
    """Parse earth_fix.dat (format 1200): lat lon ident ..."""
    result: dict[str, list[_NavEntry]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("I") or line.startswith("A") or line == "99":
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                ident = parts[2]
            except (ValueError, IndexError):
                continue
            _add(result, _NavEntry(ident=ident, type_code=11, lat=lat, lon=lon))
    return result


def _load_navaids(path: str) -> dict[str, list[_NavEntry]]:
    """Parse earth_nav.dat (format 1200): type lat lon elev freq range magvar ident ..."""
    result: dict[str, list[_NavEntry]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("I") or line == "99":
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                nav_type = int(parts[0])
                lat = float(parts[1])
                lon = float(parts[2])
                ident = parts[7]
            except (ValueError, IndexError):
                continue
            fms_type = _NAV_TYPES.get(nav_type)
            if fms_type is None:
                continue
            _add(result, _NavEntry(ident=ident, type_code=fms_type, lat=lat, lon=lon))
    return result


_APT_RECORD_PREFIXES = ("1 ", "16 ", "17 ")  # land airport, seaplane base, heliport


def _load_airports(path: str) -> dict[str, list[_NavEntry]]:
    """Parse apt.dat streaming, extracting land-airport ICAO and datum lat/lon.

    Type-16 (seaplane base) and type-17 (heliport) records must also reset
    state, or their 1302 datum_* lines corrupt the preceding land airport.
    """
    result: dict[str, list[_NavEntry]] = {}
    current_icao: str | None = None
    current_lat: float | None = None
    current_lon: float | None = None

    def _maybe_save() -> None:
        if current_icao and current_lat is not None and current_lon is not None:
            _add(result, _NavEntry(ident=current_icao, type_code=1,
                                   lat=current_lat, lon=current_lon))

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if any(line.startswith(p) for p in _APT_RECORD_PREFIXES):
                _maybe_save()
                if line.startswith("1 "):
                    parts = line.split(None, 5)
                    current_icao = parts[4] if len(parts) >= 5 else None
                else:
                    current_icao = None  # seaplane/heliport: don't track
                current_lat = None
                current_lon = None
            elif line.startswith("1302 datum_lat ") and current_icao:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        current_lat = float(parts[2])
                    except ValueError:
                        pass
            elif line.startswith("1302 datum_lon ") and current_icao:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        current_lon = float(parts[2])
                    except ValueError:
                        pass

    _maybe_save()
    return result


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065  # Earth radius in nautical miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _pick_closest(candidates: list[_NavEntry], ref_lat: float, ref_lon: float) -> tuple[_NavEntry, float]:
    best = min(candidates, key=lambda e: _haversine_nm(ref_lat, ref_lon, e.lat, e.lon))
    dist = _haversine_nm(ref_lat, ref_lon, best.lat, best.lon)
    return best, dist


def resolve(common: CommonRoute, xplane_path: str) -> ResolvedRoute:
    db = NavDatabase(xplane_path)
    print("Loading nav databases (apt.dat is large, ~5-10s)…")
    db.load()

    unresolved: list[str] = []

    def _resolve_ident(ident: str, ref_lat: float, ref_lon: float, seq: int,
                       altitude_ft: int | None) -> ResolvedPoint:
        candidates = db.lookup(ident)
        if not candidates:
            unresolved.append(ident)
            return ResolvedPoint(ident=ident, type_code=28, altitude_ft=altitude_ft,
                                 lat=0.0, lon=0.0, resolved=False, sequence=seq)
        if len(candidates) == 1:
            e = candidates[0]
            return ResolvedPoint(ident=ident, type_code=e.type_code, altitude_ft=altitude_ft,
                                 lat=e.lat, lon=e.lon, resolved=True, sequence=seq)
        # Multiple matches — pick closest to previous waypoint
        best, dist = _pick_closest(candidates, ref_lat, ref_lon)
        print(f"  Collision: {ident} has {len(candidates)} candidates — "
              f"picked ({best.lat:.4f}, {best.lon:.4f}) type={best.type_code}, "
              f"{dist:.1f} NM from previous fix")
        return ResolvedPoint(ident=ident, type_code=best.type_code, altitude_ft=altitude_ft,
                             lat=best.lat, lon=best.lon, resolved=True, sequence=seq)

    # Resolve departure (airport)
    dep = _resolve_ident(common.departure, 0.0, 0.0, 0, altitude_ft=0)
    ref_lat, ref_lon = dep.lat, dep.lon

    # Resolve intermediate points
    resolved_points: list[ResolvedPoint] = []
    for pt in common.points:
        rp = _resolve_ident(pt.ident, ref_lat, ref_lon, pt.sequence, pt.altitude_ft)
        if rp.resolved:
            ref_lat, ref_lon = rp.lat, rp.lon
        resolved_points.append(rp)

    # Resolve destination (airport), proximity from last resolved point
    dest = _resolve_ident(common.destination, ref_lat, ref_lon, len(common.points) + 1, altitude_ft=0)

    if unresolved:
        raise ValueError(
            f"Could not resolve {len(unresolved)} waypoint(s): {', '.join(unresolved)}. "
            "Check idents against your X-Plane nav database."
        )

    return ResolvedRoute(
        departure=dep,
        destination=dest,
        points=resolved_points,
        source_format=common.source_format,
    )
