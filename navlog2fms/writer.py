import os
from navlog2fms.models import ResolvedPoint, ResolvedRoute


def build_fms_v3(route: ResolvedRoute) -> str:
    """Return the v3 FMS file content as a string."""
    all_points: list[ResolvedPoint] = [route.departure] + route.points + [route.destination]

    unresolved = [p.ident for p in all_points if not p.resolved]
    if unresolved:
        raise ValueError(
            f"Cannot write FMS file: unresolved waypoints: {', '.join(unresolved)}"
        )

    numenr = len(all_points)
    lines = ["I", "3 version", "1", str(numenr)]
    for pt in all_points:
        alt = pt.altitude_ft if pt.altitude_ft is not None else 0
        lines.append(f"{pt.type_code} {pt.ident} {alt} {pt.lat:.6f} {pt.lon:.6f}")

    return "\n".join(lines) + "\n"


def write_fms(route: ResolvedRoute, output_path: str) -> None:
    content = build_fms_v3(route)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Written: {output_path}")


def default_output_path(route: ResolvedRoute, xplane_path: str, name: str | None = None) -> str:
    if name:
        filename = f"{name}.fms"
    else:
        dep = route.departure.ident
        dest = route.destination.ident
        filename = f"{dep}-{dest}.fms"
    return os.path.join(xplane_path, "Output", "FMS plans", filename)
