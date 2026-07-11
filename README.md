# NavLog2FMS

Converts a flight plan navlog PDF into an X-Plane 12 `.fms` file, ready to load
in the G1000 CO ROUTE list — no manual re-entry required.

## Supported navlog formats

| Source | Format | Notes |
|--------|--------|-------|
| Garmin Pilot (iOS) | PDF (image-based) | Uses OCR |
| SkyVector | PDF (text-based) | Direct text extraction |

## Prerequisites

- Python 3.12+
- [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html) — required for Garmin Pilot PDFs

  Install on macOS with Homebrew:
  ```bash
  brew install tesseract
  ```

## Installation

```bash
git clone <repo-url>
cd NavLog2FMS
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## First-time setup

Pass your X-Plane install path once — it is saved automatically for all future runs:

```bash
python -m navlog2fms /path/to/navlog.pdf \
  --xplane-path "/path/to/X-Plane 12"
```

The path is stored in `~/.navlog2fms`. After that, just run:

```bash
python -m navlog2fms /path/to/navlog.pdf
```

### X-Plane path by install type

| Install method | Default path |
|----------------|--------------|
| Steam (macOS) | `~/Library/Application Support/Steam/steamapps/common/X-Plane 12` |
| Direct download (macOS) | `/Applications/X-Plane 12` or `~/X-Plane 12` |

## Usage

```
python -m navlog2fms <pdf> [--xplane-path PATH] [--name NAME] [--dry-run]
```

| Argument | Description |
|----------|-------------|
| `pdf` | Path to the navlog PDF. Use an absolute path if the filename contains spaces. |
| `--xplane-path` | Path to your X-Plane 12 folder. Only needed on first run — saved automatically. |
| `--name` | Custom output filename stem, e.g. `--name KAWO-PAE` produces `KAWO-PAE.fms`. Defaults to `DEPARTURE-DESTINATION`. |
| `--dry-run` | Print the resolved route and FMS file content without writing anything. Useful for checking before it touches your sim folder. |

### Examples

**Dry run to check the route first:**
```bash
python -m navlog2fms "/Users/you/Downloads/KAWO KAWO navlog.pdf" --dry-run
```

**Write the FMS file directly into X-Plane:**
```bash
python -m navlog2fms "/Users/you/Downloads/KAWO KAWO navlog.pdf"
```

**Custom filename:**
```bash
python -m navlog2fms navlog.pdf --name "KAWO-LEION-PAE-KAWO"
```

The `.fms` file is written to `<X-Plane>/Output/FMS plans/` and is available
immediately in the G1000 CO ROUTE list — no simulator restart needed.

## How it works

```
navlog.pdf
  → format detector         identifies Garmin Pilot vs SkyVector
  → source parser           extracts departure, destination, waypoints, altitude
  → nav database resolver   looks up each ident in X-Plane's own nav database
                            (earth_fix.dat, earth_nav.dat, apt.dat)
  → .fms writer             produces a v3 format file X-Plane can load
```

**Ident collisions** (same ident used in multiple regions) are resolved
automatically by picking the candidate closest to the previous waypoint.
The chosen fix is logged so you can audit it.

**Unresolved waypoints** (idents not found in the nav database) cause a clear
error listing which idents failed — the tool never writes a partial or broken
file to your sim folder.

## Running the tests

```bash
pip install -e ".[dev]"
pytest tests/
```

The test suite covers the writer (against a confirmed-working X-Plane fixture),
the nav database resolver (against your local X-Plane install), and both parsers
(against the sample PDF files).

## Project structure

```
navlog2fms/
  models.py          — RoutePoint, CommonRoute, ResolvedPoint, ResolvedRoute
  detector.py        — format detection (pdfplumber → OCR fallback)
  config.py          — reads/writes ~/.navlog2fms for saved settings
  parsers/
    garmin_pilot.py  — Garmin Pilot iOS export parser (OCR-based)
    skyvector.py     — SkyVector navlog parser (text-based)
  resolver.py        — X-Plane nav database loader and ident resolver
  writer.py          — v3 FMS format writer
  cli.py             — command-line entry point
tests/
  fixtures/
    KAWO-KAWO.fms    — confirmed-working FMS file (ground truth for writer tests)
```

## Adding a new navlog format

1. Create `navlog2fms/parsers/<format_name>.py` implementing `fingerprint()` and `parse()`
2. Call `register()` at the bottom of the file
3. Add the import to `navlog2fms/parsers/__init__.py`

No changes to any other file are required.
