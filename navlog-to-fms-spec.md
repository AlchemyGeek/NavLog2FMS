# Navlog → X-Plane FMS Import Tool — Build Spec

## Goal
A Python CLI utility that takes a navlog PDF (Garmin Pilot first, others later),
extracts the flight plan waypoints, resolves them against X-Plane's own nav
database, and writes a `.fms` file into X-Plane's `Output/FMS plans/` folder —
ready to load in the G1000 CO ROUTE list.

## Confirmed facts (tested against a real X-Plane 12 install)
- `.fms` files can be dropped into `Output/FMS plans/` **while the sim is running** —
  no restart needed. Confirmed both v3 and v1100 format files loaded successfully.
- X-Plane accepts a mismatched `CYCLE` value with just a warning dialog, not a
  failure — so the tool does not need to know the user's exact installed AIRAC
  cycle to produce a loadable file.
- Two format options, both work:
  - **v3 (legacy, simpler)** — 5 columns per line, no via/special/airway column:
    ```
    I
    3 version
    1
    <NUMENR>
    <type> <ident> <alt_ft> <lat> <lon>
    ...
    ```
  - **v1100 (current)** — adds header block (CYCLE/ADEP/ADES/NUMENR) and a
    via/special column per waypoint line:
    ```
    I
    1100 Version
    CYCLE <ccyy>
    ADEP <icao>
    ADES <icao>
    NUMENR <n>
    <type> <ident> <via> <alt_ft> <lat> <lon>
    ...
    ```
  - **Decision: target v3 for the writer.** Simpler, fully sufficient for
    direct waypoint-to-waypoint routes (no airways/procedures in scope for v1),
    and confirmed working. Revisit v1100 only if we later add airway/procedure
    support.
- Type codes: `1`=airport, `2`=NDB, `3`=VOR, `11`=named fix/intersection,
  `28`=unnamed lat/lon waypoint (bypasses nav-database lookup entirely — useful
  fallback/debug path).
- Waypoint idents must resolve to the **user's actual installed nav database**
  (`earth_fix.dat`, `earth_nav.dat`, `apt.dat` inside the X-Plane install) with
  correct type code + coordinates, or the route may fail to load or draw wrong.
  Ident collisions across regions are possible (same ident, different navaid)
  — the resolver needs a disambiguation strategy (see below).

## Out of scope for v1
- SID/STAR/airway expansion. If a source navlog contains a named procedure
  instead of individual fixes, the parser should flag it as unresolved rather
  than guess.
- Any in-cockpit automation (auto-selecting/activating the loaded route in the
  G1000 UI). The user does that final step manually.

## Architecture

```
navlog.pdf
  → [format detector]
  → [source-specific parser]  →  CommonRoute
  → [nav database resolver]  →  ResolvedRoute
  → [.fms writer]             →  Output/FMS plans/<name>.fms
```

### 1. Common intermediate schema
Every source parser outputs this — nothing downstream should know or care
which vendor's PDF it came from.

```python
@dataclass
class RoutePoint:
    ident: str                  # "MERIT", "KBFI", "PAE"
    point_type_hint: str | None # "fix" | "vor" | "ndb" | "airport" | None (often absent from PDF)
    altitude_ft: int | None
    sequence: int

@dataclass
class CommonRoute:
    departure: str               # ICAO ident
    destination: str              # ICAO ident
    points: list[RoutePoint]      # excludes departure/destination unless the
                                   # source lists them inline; writer handles
                                   # ADEP/ADES separately
    source_format: str            # "garmin_pilot", "skyview", etc. — for logs/debugging
    raw_route_string: str | None  # the filed route string if the PDF has one, for diagnostics
```

### 2. Format detection
- Extract text from page 1 with `pdfplumber`.
- Fingerprint via distinctive header/footer text per vendor (e.g. "Garmin
  Pilot" branding string). Simple substring match — no ML/fuzzy matching needed.
- Unrecognized format → clear error naming what was/wasn't detected, do not
  guess.

### 3. Source-specific parsers
- One module per vendor: `parsers/garmin_pilot.py`, `parsers/skyview.py`, etc.
- Each implements a single function: `parse(pdf_path) -> CommonRoute`.
- **Garmin Pilot parser is the only one built in this phase.** Confirmed
  against a real sample (KAWO-LEION-PAE-SAVOY-KAWO round-robin):
  - Page 1 has a `ROUTE` line directly under the summary header, formatted as
    a plain space-delimited ident string, e.g. `KAWO LEION PAE SAVOY KAWO`.
    **Prefer this as the primary source of waypoint sequence/idents** — it's
    far more robust to parse than the detailed table below it.
  - The detailed `WAYPOINT` table repeats the same idents with per-leg data
    (HDG, DTK, ALT, wind, fuel, time). Only the `ALT` column is needed from
    this table, matched back to each ident from the route string, to get
    cruise/leg altitude per point.
  - First and last rows of the table are the departure/destination airport
    and show **field elevation** in the `ALT` column, not a cruise altitude
    — these must be treated as ADEP/ADES, not as `RoutePoint`s with that
    elevation value.
  - No point-type column anywhere in the PDF (fix vs. VOR vs. airport isn't
    stated) — confirms type resolution is entirely the nav database
    resolver's job, not something to extract from the PDF.
  - Page 2 has a `NAVAID FREQUENCIES` table listing VOR/NDB idents and
    frequencies for navaids along the route — not needed for the FMS file,
    but useful as an independent ground-truth check when testing the
    resolver's type-code assignment (e.g. confirms PAE is a VOR/DME).
  - Format fingerprint for detection: "Garmin Pilot"-style header block with
    `DATE / IDENT / ACFT TYPE / PERF` fields and the `ROUTE` label.
- Registry pattern so adding a new vendor later = new file + one registration
  line, no changes to existing parsers or the pipeline.

### 4. Nav database resolver
- Locate the user's X-Plane install (prompt for path or accept as CLI arg;
  don't guess a default that might be wrong on a given machine).
- Parse `earth_fix.dat` (named fixes), `earth_nav.dat` (VOR/NDB/ILS etc.),
  `apt.dat` (airports) once per run, cache as in-memory dict keyed by ident.
- For each `RoutePoint`:
  - Look up ident across all three sources.
  - **Zero matches** → mark point as unresolved, surface clearly at the end
    (don't fail the whole route silently).
  - **One match** → resolve type code + lat/lon from the nav database (not
    from the PDF's own coordinates, if it has any — the sim's database is
    ground truth for what the sim can actually draw).
  - **Multiple matches (ident collision)** → disambiguate by proximity to the
    previous resolved waypoint (or departure airport for the first point).
    Log which one was picked and why, so it's auditable.
- Output: `ResolvedRoute` — same shape as `CommonRoute` but each point now has
  `type_code: int`, `lat: float`, `lon: float`, and `resolved: bool`.

### 5. `.fms` writer
- Takes `ResolvedRoute`, writes v3 format as specified above.
- Skips/errors clearly on any unresolved points rather than writing a broken
  file — better to fail loudly than hand X-Plane a route with a garbage line.
- Writes to `<xplane_install>/Output/FMS plans/<name>.fms`, filename
  derived from departure+destination+timestamp or user-supplied.

### 6. CLI
```
navlog2fms path/to/navlog.pdf --xplane-path "/path/to/X-Plane 12" [--name custom_name] [--dry-run]
```
- `--dry-run` prints the resolved route and would-be file contents without
  writing, for sanity-checking before it touches the sim's folder.

## Testing approach
- Two known-good `.fms` files already confirmed to load in X-Plane 12 (from
  this conversation) — use as fixtures for writer unit tests, so we're
  testing against ground truth we've personally verified, not just spec text.
- Nav resolver tests need to run against a real (or trimmed sample of) the
  user's `earth_fix.dat`/`earth_nav.dat`/`apt.dat` — ask Claude Code to check
  for these files locally rather than assuming a path.
- Garmin Pilot parser tests need the real sample PDF once supplied.

## Open items before/while building
1. Confirm X-Plane install path convention on the user's machine (macOS,
   given the screenshot) — likely `~/X-Plane 12/` or under `/Applications/`.
2. Decide disambiguation logic precisely once we hit a real collision case in
   testing (proximity-based is the default plan above).
3. SkyVector parser build itself — see notes below, deferred to phase 2.

## SkyVector navlog — confirmed format notes (phase 2 parser)
Sample seen: same KAWO-LEION-PAE-SAVOY-KAWO round-robin, exported from
SkyVector (not "SkyView" — different product, a Dynon EFIS; get the vendor
name right in the parser registry).

Key differences from Garmin Pilot that change the build approach:
- **Coordinates are given directly per waypoint**, in DM format, e.g.
  `N 48°09.64' W 122°09.54'`. Garmin Pilot's navlog has no lat/lon at all.
  Useful as a cross-check against the nav-database resolver, or as a
  `type 28` (lat/lon-only) fallback if an ident fails to resolve — but DMS→
  decimal conversion needs care (minutes are decimal-minutes here, not
  minutes+seconds).
- **Plain text extraction comes out jumbled** — column headers
  (`Waypoint Route TAS MH GS Dist Altitude wDir wSpd Temp...`) extract as one
  block, separated from the actual per-waypoint data values, rather than
  row-aligned like Garmin Pilot's table. This is a known `pdfplumber` issue
  with visually complex tables (PDF internal draw order != reading order).
  **Will need `pdfplumber.extract_tables()` with explicit table-detection
  settings, or positional (x/y) reconstruction** — the "just grab a text
  line" trick that works for Garmin Pilot's `ROUTE` line won't work here.
- **Altitude is a single constant for the whole route** (8000 ft in the
  sample), not per-leg like Garmin Pilot. Schema already supports this
  (`altitude_ft` per point) — just don't assume variation is present.
- **Bonus pages bundled in** (airport diagrams) — parser must identify which
  page(s) hold the actual navlog data rather than assuming page 1 always has
  it exclusively.
- **Format fingerprint**: no Garmin branding; presence of `Planned Route`,
  `Squawk Code`, `Clearance` labels plus the DMS coordinate pattern are
  reasonable detection signals.

**Sequencing decision:** build and prove the Garmin Pilot parser + resolver +
writer + CLI first (clean data, low risk). Add the SkyVector parser as phase
2, once the pipeline itself is solid and this becomes "new parser module"
work rather than "debug everything at once."
