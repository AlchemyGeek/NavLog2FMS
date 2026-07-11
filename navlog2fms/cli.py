import argparse
import os
import sys

from navlog2fms import config as cfg
from navlog2fms.detector import load_and_detect
from navlog2fms.resolver import resolve
from navlog2fms.writer import build_fms_v3, default_output_path, write_fms


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a navlog PDF to an X-Plane .fms flight plan."
    )
    parser.add_argument("pdf", help="Path to the navlog PDF (use absolute path or quote if it contains spaces)")
    parser.add_argument(
        "--xplane-path",
        default=None,
        help="Path to X-Plane 12 install folder (saved automatically for future runs)",
    )
    parser.add_argument("--name", default=None, help="Output filename stem (without .fms)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print resolved route and FMS content without writing")
    args = parser.parse_args()

    pdf_path = os.path.abspath(args.pdf)
    if not os.path.isfile(pdf_path):
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        print(f"  Working directory: {os.getcwd()}", file=sys.stderr)
        print("  Tip: use an absolute path, e.g. /Users/you/Downloads/navlog.pdf", file=sys.stderr)
        sys.exit(1)

    # Resolve X-Plane path: CLI arg takes priority, then saved config
    xplane_path = args.xplane_path or cfg.get_xplane_path()
    if not xplane_path:
        print("Error: X-Plane path not set.", file=sys.stderr)
        print("  Pass it once with --xplane-path and it will be saved for future runs.", file=sys.stderr)
        sys.exit(1)
    if args.xplane_path:
        cfg.set_xplane_path(args.xplane_path)

    print(f"Parsing: {pdf_path}")
    common = load_and_detect(pdf_path)
    print(f"Format:  {common.source_format}")
    print(f"Route:   {common.departure} → {' → '.join(p.ident for p in common.points)} → {common.destination}")

    resolved = resolve(common, xplane_path)

    print("\nResolved waypoints:")
    all_pts = [resolved.departure] + resolved.points + [resolved.destination]
    for pt in all_pts:
        status = "OK" if pt.resolved else "UNRESOLVED"
        alt = f"{pt.altitude_ft}ft" if pt.altitude_ft is not None else "—"
        print(f"  [{status}] type={pt.type_code} {pt.ident:6s}  {alt:8s}  "
              f"{pt.lat:.6f} {pt.lon:.6f}")

    fms_content = build_fms_v3(resolved)

    if args.dry_run:
        print("\n--- FMS file (dry run, not written) ---")
        print(fms_content)
        return

    out_path = default_output_path(resolved, xplane_path, args.name)
    write_fms(resolved, out_path)
    print(f"\nDone. Load '{out_path}' in X-Plane via the CO ROUTE list.")


if __name__ == "__main__":
    sys.exit(main())
