from dataclasses import dataclass, field


@dataclass
class RoutePoint:
    ident: str
    point_type_hint: str | None  # "fix" | "vor" | "ndb" | "airport" | None
    altitude_ft: int | None
    sequence: int


@dataclass
class CommonRoute:
    departure: str               # ICAO ident
    destination: str             # ICAO ident
    points: list[RoutePoint]     # intermediate waypoints only
    source_format: str           # "garmin_pilot", "skyvector", etc.
    raw_route_string: str | None


@dataclass
class ResolvedPoint:
    ident: str
    type_code: int   # 1=airport, 2=NDB, 3=VOR, 11=named fix, 28=lat/lon
    altitude_ft: int | None
    lat: float
    lon: float
    resolved: bool
    sequence: int


@dataclass
class ResolvedRoute:
    departure: ResolvedPoint
    destination: ResolvedPoint
    points: list[ResolvedPoint]  # intermediate waypoints only
    source_format: str
