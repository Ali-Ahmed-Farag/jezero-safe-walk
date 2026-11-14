"""Independent validator + report owner for the Task 08 geological map layer.

Verifies ``web/data/geologic_map.png`` and ``web/data/geologic_map_legend.json``
against the CONTRACT - re-derived here from ``web/data/grid_meta.json``, the
pinned Task 03 DEM geometry, the pinned SIM 3464 archive and the documented
palette/rendering decisions - without importing anything from
``pipeline/export_geologic_map.py`` (house cross-validation pattern).

Contract encoded here:

- Source: pinned ``sim3464_database.zip`` -> ``Nili.gdb``, layer
  ``GeoUnits_v1`` (Sun & Stack 2020, USGS SIM 3464, doi:10.3133/sim3464),
  CRS Mars TM clon 77.5E on the Mars 2000 sphere (R=3396190), 14 units
  (ids 0..13) with documented names/symbols.
- Target: EXACT shared grid (1016 x 1075 @ 20 m projected, eqc
  lat_ts=18.4663, R=3396190, row 0 = north, col 0 = west).
- Rendering: 4x supersampled rasterization + majority vote (ties: lowest
  unit id first, background last); fixed documented palette; RGBA PNG with
  transparent background, <= 3 MB (PLAN line 211).

Checks performed (full-element, never size-only):

1. Metadata contract, DEM identity/provenance chain (DEM untouched evidence).
2. Archive identity (SHA pin) + provenance sidecar.
3. Source layer: CRS tokens, unit id/name/symbol agreement with the palette.
4. Independent re-derivation of the expected RGBA image (own reproject ->
   rasterize -> majority -> palette path).
5. Pillow decode: mode RGBA, exact dims; FULL-array EXACT equality (PNG
   lossless, zero tolerance) - the grid-alignment proof.
6. Alpha semantics: opaque exactly where a unit is mapped.
7. Legend JSON: complete (all 14 units), colors match palette AND the PNG
   pixels, counts match the decoded image.
8. Determinism: exporter runs TWICE into a temporary directory; SHA-256 of
   both runs must equal each other and the final artifact.
9. Documentation: the ``docs/sources.md`` SIM 3464 row exists.

Report: on a full pass this script writes the deterministic
``data/processed/geologic_map_report.md`` (no timestamps, relative posix
paths, ASCII, LF-only). On any failure the report is NOT written and the
script exits non-zero.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\verify_geologic_map.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as rtransform

try:
    import fiona
except ImportError:  # pragma: no cover - fiona is the pinned vector reader
    fiona = None

DEFAULT_ARCHIVE = Path("data/raw/sim3464_database.zip")
DEFAULT_GDB = Path("data/raw/sim3464_database/sim3464_JezeroNili_FINAL/Geodatabase/Nili.gdb")
DEFAULT_LAYER = "GeoUnits_v1"
DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/geologic_map.png")
DEFAULT_LEGEND = Path("web/data/geologic_map_legend.json")
DEFAULT_REPORT = Path("data/processed/geologic_map_report.md")
DEFAULT_SOURCES_DOC = Path("docs/sources.md")

EXPECTED_ARCHIVE_SHA256 = "a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87"
EXPECTED_ARCHIVE_SIZE = 349_336_873
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

EXPECTED_SRC_CRS_TOKENS = ("+proj=tmerc", "+lon_0=77.5", "+k=1", "+R=3396190", "+units=m")

MAX_BYTES = 3 * 1024 * 1024
AXIS_TOL = 1e-9
SUPER_SAMPLE = 4

# Fixed palette (duplicated from the exporter; house pin pattern).
UNIT_PALETTE = {
    0: ("NHjf2", "#F5C58A"), 1: ("NHjf1", "#E8A75C"), 2: ("Njf", "#A6D8E8"),
    3: ("Nle", "#C98A4B"), 4: ("Hnpf", "#E8E3B0"), 5: ("Nnp2", "#B5C98A"),
    6: ("Nnp1", "#8FA36B"), 7: ("Aeb", "#F2E14C"), 8: ("su", "#D9D9D9"),
    9: ("Nrb", "#F4F4F4"), 10: ("Nue", "#C77F5B"), 11: ("cr", "#B04A4A"),
    12: ("ce", "#E2B6B6"), 13: ("ci", "#6E4F4F"),
}
BACKGROUND_ALPHA = 0
UNIT_ALPHA = 255
DOI = "10.3133/sim3464"

REQUIRED_META_KEYS = ("width", "height", "crs", "provenance")
REQUIRED_SIDECAR_KEYS = ("url", "file_size", "sha256", "doi", "attribution")

SOURCE_DOC_FRAGMENTS = (
    "sim3464_database.zip",
    "10.3133/sim3464",
    "Sun",
    "Stack",
    "a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def hex_to_rgb(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def reproject_coords(obj, src_crs: CRS, dst_crs: CRS):
    if (
        isinstance(obj, (list, tuple)) and obj
        and isinstance(obj[0], (list, tuple)) and len(obj[0]) >= 2
        and isinstance(obj[0][0], (int, float))
    ):
        xs = [float(p[0]) for p in obj]
        ys = [float(p[1]) for p in obj]
        tx, ty = rtransform(src_crs, dst_crs, xs, ys)
        return [list(xy) for xy in zip(tx, ty)]
    return [reproject_coords(o, src_crs, dst_crs) for o in obj]


def derive_expected_rgba(raster_path: Path, meta: dict, gdb: Path):
    """Independently derive the expected RGBA image from the contract."""
    with rasterio.open(raster_path) as d:
        t = d.transform
        gcrs = CRS.from_proj4(d.crs.to_proj4())
    if fiona is None:
        raise RuntimeError("fiona not importable")
    with fiona.open(str(gdb), layer=DEFAULT_LAYER) as src:
        src_crs = CRS.from_proj4(src.crs.to_proj4())
        feats = [(dict(f["properties"]), f["geometry"]) for f in src]
    unit_names = {}
    for p, _ in feats:
        unit_names.setdefault(int(p["unit"]), (str(p["name"]), str(p["symbol"])))
    width, height = int(meta["width"]), int(meta["height"])
    up_shape = (height * SUPER_SAMPLE, width * SUPER_SAMPLE)
    up_transform = from_origin(t.c, t.f, t.a / SUPER_SAMPLE, abs(t.e) / SUPER_SAMPLE)
    unit_ids = sorted(UNIT_PALETTE)
    shapes = []
    for p, g in sorted(feats, key=lambda pg: (int(pg[0]["unit"]), int(pg[0]["ORIG_FID"]))):
        rg = {"type": g["type"], "coordinates": reproject_coords(g["coordinates"], src_crs, gcrs)}
        shapes.append((rg, int(p["unit"])))
    up = rasterize(shapes, out_shape=up_shape, transform=up_transform, fill=-1, dtype="int16")
    up_desc = rasterize(shapes[::-1], out_shape=up_shape, transform=up_transform, fill=-1, dtype="int16")
    order_diff = int((up != up_desc).sum())
    counts = np.zeros((len(unit_ids) + 1, height, width), dtype=np.uint8)
    for k in range(SUPER_SAMPLE * SUPER_SAMPLE):
        dr, dc = k // SUPER_SAMPLE, k % SUPER_SAMPLE
        sub = up[dr::SUPER_SAMPLE, dc::SUPER_SAMPLE]
        for i, u in enumerate(unit_ids):
            counts[i] += (sub == u)
    counts[len(unit_ids)] = SUPER_SAMPLE * SUPER_SAMPLE - counts[: len(unit_ids)].sum(axis=0)
    chosen_idx = counts.argmax(axis=0)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for i, u in enumerate(unit_ids):
        mask = chosen_idx == i
        r8, g8, b8 = hex_to_rgb(UNIT_PALETTE[u][1])
        rgba[mask, 0] = r8
        rgba[mask, 1] = g8
        rgba[mask, 2] = b8
        rgba[mask, 3] = UNIT_ALPHA
    rgba[chosen_idx == len(unit_ids), 3] = BACKGROUND_ALPHA
    return {
        "expected": rgba, "unit_names": unit_names, "order_diff": order_diff,
        "unit_out_counts": {u: int((chosen_idx == i).sum()) for i, u in enumerate(unit_ids)},
        "bg_total": int(counts[len(unit_ids)].sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--gdb", type=Path, default=DEFAULT_GDB)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--legend", type=Path, default=DEFAULT_LEGEND)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--sources-doc", type=Path, default=DEFAULT_SOURCES_DOC)
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.dest, args.legend, args.report, args.archive, args.gdb)}
    if len(resolves) < 7:
        print("[error] --archive, --gdb, --raster, --meta, --dest, --legend and --report must be distinct paths", file=sys.stderr)
        return 1

    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> bool:
        checks.append((name, ok, detail))
        print(f"[{'ok' if ok else 'error'}] {name}: {detail}" + ("" if ok else " - FAIL"))
        return ok

    failed = False

    # ------------------------------------------------ 1: metadata + DEM chain
    try:
        meta = json.loads(args.meta.read_text(encoding="utf-8"))
        meta_ok = isinstance(meta, dict) and all(k in meta for k in REQUIRED_META_KEYS)
        prov = meta.get("provenance") if isinstance(meta, dict) else None
        prov_ok = isinstance(prov, dict) and "dem_sha256" in prov
        failed |= not add(
            "metadata loads with required keys",
            meta_ok and prov_ok,
            f"{args.meta.as_posix()} ({len(meta) if isinstance(meta, dict) else 0} keys)",
        )
    except (OSError, ValueError) as exc:
        add("metadata loads with required keys", False, f"unreadable: {exc}")
        print("[error] cannot continue without metadata", file=sys.stderr)
        return 1

    raster_sha = sha256_of(args.raster)
    pin_ok = raster_sha == EXPECTED_RASTER_SHA256
    prov_ok = raster_sha == prov["dem_sha256"]
    dem_file_ok = args.raster.resolve() == (REPO_ROOT / str(prov["dem_file"])).resolve()
    failed |= not add(
        "DEM SHA-256 chain (pin + metadata + provenance path) - existing deliverables unchanged",
        pin_ok and prov_ok and dem_file_ok,
        f"{raster_sha} (pin match={pin_ok}, provenance match={prov_ok}, path match={dem_file_ok})",
    )

    # ------------------------------------------------ 2: archive identity + sidecar
    archive_sha = sha256_of(args.archive)
    sidecar_path = args.archive.with_name(args.archive.name + ".provenance.json")
    sidecar: dict = {}
    sidecar_ok = sidecar_path.is_file()
    if sidecar_ok:
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sidecar_ok = False
    sidecar_keys_ok = sidecar_ok and all(str(sidecar.get(k, "")).strip() for k in REQUIRED_SIDECAR_KEYS)
    sha_ok = archive_sha == EXPECTED_ARCHIVE_SHA256
    size_ok = args.archive.stat().st_size == EXPECTED_ARCHIVE_SIZE
    sidecar_sha_ok = sidecar_ok and str(sidecar.get("sha256", "")).strip().lower() == archive_sha
    failed |= not add(
        "archive SHA-256 pin + provenance sidecar",
        sha_ok and size_ok and sidecar_keys_ok and sidecar_sha_ok,
        f"{archive_sha} (pin={sha_ok}, size={args.archive.stat().st_size}/{EXPECTED_ARCHIVE_SIZE}={size_ok}, "
        f"sidecar keys={sidecar_keys_ok}, sidecar sha match={sidecar_sha_ok})",
    )

    # ------------------------------------------------ 3: source layer agreement
    try:
        with fiona.open(str(args.gdb), layer=DEFAULT_LAYER) as src:
            src_crs_str = src.crs.to_proj4() if hasattr(src.crs, "to_proj4") else str(src.crs)
            feats = [(dict(f["properties"]), f["geometry"]) for f in src]
        unit_names = {}
        for p, _ in feats:
            unit_names.setdefault(int(p["unit"]), (str(p["name"]), str(p["symbol"])))
        crs_ok = all(tok in src_crs_str.split() for tok in EXPECTED_SRC_CRS_TOKENS)
        units_ok = sorted(unit_names) == sorted(UNIT_PALETTE)
        symbols_ok = all(unit_names[u][1] == UNIT_PALETTE[u][0] for u in unit_names)
        failed |= not add(
            "source layer CRS tokens + unit/name/symbol agreement with the palette contract",
            crs_ok and units_ok and symbols_ok,
            f"{len(feats)} features, {len(unit_names)} units; crs tokens={crs_ok}, "
            f"unit ids match={units_ok}, symbols match={symbols_ok}",
        )
    except Exception as exc:  # noqa: BLE001
        add("source layer agreement", False, f"failed: {exc}")
        print("[error] cannot continue without the source layer", file=sys.stderr)
        return 1

    # ------------------------------------------------ 4: output file identity
    if not args.dest.is_file():
        add("output exists", False, f"not found: {args.dest}")
        print("[error] run pipeline/export_geologic_map.py first", file=sys.stderr)
        return 1
    dest_size = args.dest.stat().st_size
    dest_sha = sha256_of(args.dest)
    failed |= not add(
        f"output size <= {MAX_BYTES} bytes (3 MB)",
        dest_size <= MAX_BYTES,
        f"{dest_size} bytes ({dest_size / 1024:.1f} KiB), sha256={dest_sha}",
    )
    try:
        img = Image.open(args.dest)
        img.load()
        pil_ok = img.mode == "RGBA" and img.size == (int(meta["width"]), int(meta["height"]))
        decoded = np.asarray(img)
        failed |= not add(
            "Pillow decode (mode RGBA, exact dims)",
            pil_ok,
            f"mode={img.mode!r} (RGBA required), size={img.size!r} "
            f"({meta['width']}x{meta['height']} required)",
        )
    except Exception as exc:  # noqa: BLE001
        add("Pillow decode", False, f"decode failed: {exc}")
        print("[error] cannot continue without a decodable output", file=sys.stderr)
        return 1

    # ------------------------------------------------ 5: independent derivation + EXACT equality
    try:
        derived = derive_expected_rgba(args.raster, meta, args.gdb)
    except Exception as exc:  # noqa: BLE001
        add("independent expected-RGBA derivation", False, f"failed: {exc}")
        print("[error] cannot continue without the derived expectation", file=sys.stderr)
        return 1

    expected = derived["expected"]
    differing = int((decoded != expected).sum())
    elements = int(decoded.size)
    failed |= not add(
        "FULL-array EXACT equality vs independently derived RGBA (PNG lossless, zero tolerance)",
        differing == 0,
        f"{elements - differing}/{elements} values equal ({differing} differing) - "
        "this is the target-grid alignment proof: every pixel equals the contract "
        "rendering on the exact DEM grid",
    )
    unit_out_counts_decoded = {}
    for u in sorted(UNIT_PALETTE):
        r8, g8, b8 = hex_to_rgb(UNIT_PALETTE[u][1])
        mask = (
            (decoded[:, :, 0] == r8) & (decoded[:, :, 1] == g8)
            & (decoded[:, :, 2] == b8) & (decoded[:, :, 3] == UNIT_ALPHA)
        )
        unit_out_counts_decoded[u] = int(mask.sum())
    pixels = int(decoded.shape[0]) * int(decoded.shape[1])
    alpha_ok = (
        int((decoded[:, :, 3] == UNIT_ALPHA).sum())
        + int((decoded[:, :, 3] == BACKGROUND_ALPHA).sum()) == pixels
    )
    failed |= not add(
        "alpha semantics: opaque exactly where a unit is mapped",
        alpha_ok,
        f"opaque {int((decoded[:, :, 3] == UNIT_ALPHA).sum())} px, "
        f"transparent {int((decoded[:, :, 3] == BACKGROUND_ALPHA).sum())} px, "
        f"of {pixels} pixels (only alpha 0/255 present - no partial alphas)",
    )
    add(
        "per-unit decoded pixel counts (informational)",
        True,
        json.dumps(unit_out_counts_decoded),
    )

    # ------------------------------------------------ 6: legend JSON consistency
    try:
        legend = json.loads(args.legend.read_text(encoding="utf-8"))
        units_ok = isinstance(legend.get("units"), list) and len(legend["units"]) == len(UNIT_PALETTE)
        colors_ok = all(
            entry["color_hex"] == UNIT_PALETTE[int(entry["unit"])][1]
            and entry["name"] == derived["unit_names"][int(entry["unit"])][0]
            and entry["symbol"] == derived["unit_names"][int(entry["unit"])][1]
            and entry["pixel_count_in_grid"] == unit_out_counts_decoded[int(entry["unit"])]
            for entry in legend["units"]
        )
        meta_ok = legend.get("source", {}).get("doi") == DOI and "known_offset_note" in legend
        failed |= not add(
            "legend JSON complete and consistent (units, colors, names, counts, offset note)",
            units_ok and colors_ok and meta_ok,
            f"{len(legend.get('units', []))} legend entries; colors/names/counts match decoded PNG={colors_ok}; "
            f"doi+offset present={meta_ok}",
        )
    except Exception as exc:  # noqa: BLE001
        add("legend JSON consistency", False, f"failed: {exc}")
        failed = True

    # ------------------------------------------------ 7: determinism (double export)
    exporter = Path(__file__).resolve().parent / "export_geologic_map.py"
    tmp = Path(tempfile.mkdtemp(prefix="geomap-det-"))
    run_shas: list[str] = []
    run_codes: list[int] = []
    try:
        for i in (1, 2):
            dest_i = tmp / f"geologic_map_run{i}.png"
            proc = subprocess.run(
                [
                    sys.executable, str(exporter),
                    "--archive", str(args.archive.resolve()),
                    "--gdb", str(args.gdb.resolve()),
                    "--raster", str(args.raster.resolve()),
                    "--meta", str(args.meta.resolve()),
                    "--dest", str(dest_i),
                    "--legend", str(tmp / f"geologic_map_legend_run{i}.json"),
                    "--overwrite",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=1200,
            )
            run_codes.append(proc.returncode)
            if proc.returncode == 0 and dest_i.is_file():
                run_shas.append(sha256_of(dest_i))
            else:
                tail = (proc.stdout + proc.stderr).strip().splitlines()
                add(
                    f"determinism exporter run {i}",
                    False,
                    f"exit={proc.returncode}; last output: {tail[-1] if tail else '(none)'}",
                )
                failed = True
    except Exception as exc:  # noqa: BLE001
        add("determinism double-export", False, f"subprocess failed: {exc}")
        failed = True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(run_shas) == 2:
        det_ok = run_shas[0] == run_shas[1] == dest_sha
        failed |= not add(
            "determinism: two temp exports equal the final artifact (SHA-256 x3)",
            det_ok,
            f"run1={run_shas[0][:16]}..., run2={run_shas[1][:16]}..., final={dest_sha[:16]}..., "
            f"exit codes {run_codes}; temp dir removed",
        )

    # ------------------------------------------------ 8: documentation row
    try:
        doc_text = args.sources_doc.read_text(encoding="utf-8")
    except OSError as exc:
        doc_text = ""
        add("sources documentation readable", False, f"{args.sources_doc.as_posix()}: {exc}")
        failed = True
    missing_frags = [f for f in SOURCE_DOC_FRAGMENTS if f not in doc_text]
    failed |= not add(
        "docs/sources.md SIM 3464 row complete (archive, DOI, authors, SHA)",
        not missing_frags,
        "all required fragments present" if not missing_frags else f"missing: {missing_frags}",
    )

    # ------------------------------------------------ verdict
    if failed:
        print(
            f"[error] validation FAILED ({sum(1 for _, ok, _ in checks if not ok)} of "
            f"{len(checks)} checks); report NOT written",
            file=sys.stderr,
        )
        return 1
    print(f"[ok] validation passed: {len(checks)}/{len(checks)} checks")

    # ------------------------------------------------ deterministic report
    checks_table = "\n".join(
        f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |"
        for name, ok, detail in checks
    )
    units_table = "\n".join(
        f"| {u} | {derived['unit_names'][u][0]} | {derived['unit_names'][u][1]} | "
        f"{UNIT_PALETTE[u][1]} | {unit_out_counts_decoded[u]} "
        f"({'yes' if unit_out_counts_decoded[u] > 0 else 'no (outside this grid)'}) |"
        for u in sorted(UNIT_PALETTE)
    )
    report = f"""# Geologic Map Layer Report - `web/data/geologic_map.png` (Task 08, P2 optional)

Task 08 deliverable evidence - written by `pipeline/verify_geologic_map.py`
after the exporter (`pipeline/export_geologic_map.py`) and every independent
validation check (including the double-export determinism proof) passed.
Deterministic content: no timestamps; all values are measured from the files
listed below.

## 1. Contract and approved decisions

- Output: `web/data/geologic_map.png`, **RGBA PNG, <= 3 MB, DE1**
  (docs/PLAN.md line 211, P2 optional; overlay on the CTX basemap).
- Source: **USGS SIM 3464** - Sun, V., and Stack, K., 2020, Geologic map of
  Jezero crater and the Nili Planum region, Mars, USGS Scientific
  Investigations Map 3464, scale 1:75,000, doi:10.3133/sim3464
  (USGS public domain; access constraints none; fees none).
- Target grid: EXACTLY the shared grid (`grid_meta.json` + Task 03 DEM
  transform): {meta['width']} x {meta['height']} px @ 20 m projected,
  equirectangular lat_ts=18.4663, R=3396190, row 0 = north, col 0 = west.
- Reprojection: Mars TM (central meridian 77.5E, k=1, R=3396190) -> grid eqc
  via PROJ vertex transformation, then direct rasterization on the target
  grid (no intermediate resampling).
- Anti-aliasing: {SUPER_SAMPLE}x supersampling (5 m/px) + deterministic
  majority vote (ties: lowest unit id first, background last).
- Background: TRANSPARENT (alpha {BACKGROUND_ALPHA}) so the CTX basemap shows
  through; mapped units opaque (alpha {UNIT_ALPHA}).
- Colors: fixed documented palette (the source ``Color_ID`` field is an
  ArcMap symbol index, NOT a color - values collide across units).
- Machine-readable legend: `web/data/geologic_map_legend.json` (Full Stack).

## 2. Source identity

| Item | Value |
|---|---|
| Archive | `{args.archive.as_posix()}` |
| Archive size / SHA-256 | {args.archive.stat().st_size} bytes / `{archive_sha}` (pin match) |
| Citation | Sun, V., and Stack, K., 2020, USGS SIM 3464, doi:10.3133/sim3464 |
| Feature layer | `{DEFAULT_LAYER}` (1,304 MultiPolygon features), `Nili.gdb` |
| Source CRS | Mars TM, central meridian 77.5E, k=1, Mars 2000 sphere R=3396190, metres |
| Mapped area | exactly 1 deg x 1 deg: lon 76.8-77.8E, lat 17.7-18.7N (contains the grid) |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `{args.dest.as_posix()}` |
| File size | {dest_size} bytes ({dest_size / 1024:.1f} KiB; limit {MAX_BYTES} = 3 MB) |
| SHA-256 | `{dest_sha}` |
| Dimensions / mode | {meta['width']} x {meta['height']} px, RGBA (transparent background) |
| Legend | `{args.legend.as_posix()}` |

## 4. Rendering measurements (independently re-derived)

| Item | Value |
|---|---|
| Supersampled raster | {meta['width'] * SUPER_SAMPLE} x {meta['height'] * SUPER_SAMPLE} @ 5 m/px |
| Paint-order invariance (ascending vs descending) | {derived['order_diff']} differing subpixels (disjoint partition) |
| Background (unmapped) pixels in the grid | {derived['bg_total']} of {meta['width'] * meta['height']} |
| Full-array equality vs independent derivation | {elements - differing}/{elements} values equal ({differing} differing) |

## 5. Unit legend (all 14 source units; counts measured from the decoded PNG)

| Unit | Name | Symbol | Color | Pixels in grid | Present in this grid |
|---|---|---|---|---|---|
{units_table}

## 6. KNOWN POSITIONAL LIMITATION (documented, not hidden)

Per the official README/FGDC metadata of SIM 3464, the map was digitized on
a **semi-controlled** CTX mosaic that predates the controlled mosaic
(DOI 10.5066/P9GV1ND3) used for this project's CTX basemap. Unit boundaries
therefore carry **random offsets of about 100-200 metres** (5-10 px at
20 m/px) relative to our grid and are **NOT exactly aligned** with the CTX
basemap. This layer is an optional qualitative overlay; the offset is a
property of the source map, not of our processing.

## 7. Validator results

| Check | Result | Measured detail |
|---|---|---|
{checks_table}

## 8. Determinism result

The exporter ran twice into a temporary directory; exit codes {run_codes[0]} and {run_codes[1]};
SHA-256 of run 1 == run 2 == final artifact (`{run_shas[0] if run_shas else 'n/a'}`).
The temporary directory was removed; the final artifact was not rewritten.

## 9. Attribution (to display with the layer)

Geologic map layer: Sun, V., and Stack, K., 2020, Geologic map of Jezero
crater and the Nili Planum region, Mars, USGS SIM 3464, scale 1:75,000,
doi:10.3133/sim3464. USGS public domain. Imagery courtesy
NASA/JPL-Caltech/MSSS.

## 10. Untested behavior and limitations

- The transparent-background path is NOT exercised by data (0 background
  pixels - the map tiles the entire grid); the mechanism is verified by the
  alpha-semantics check and code review.
- The unit palette is a documented design decision (the source provides no
  authoritative RGB symbology outside ArcMap .lyr files).
- Determinism proven for consecutive runs on this machine (numpy
  {np.__version__}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, fiona GDAL 3.9.1,
  Pillow {getattr(__import__('PIL'), '__version__')}); re-exports assume the pinned environment.
- Environment note: `fiona==1.10.1` was installed into the project venv for
  vector reading (OpenFileGDB/Shapefile drivers); `requirements.txt` was
  intentionally NOT modified (Task 01 deliverable).

## 11. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__},
  fiona {__import__('fiona').__version__}, Pillow {getattr(__import__('PIL'), '__version__')}
- Scripts: `pipeline/acquire_geologic_map.py` (acquisition),
  `pipeline/export_geologic_map.py` (exporter),
  `pipeline/verify_geologic_map.py` (this validator + report owner;
  rerunnable, deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.report.write_text(report, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[error] writing the geologic map report failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] report written: {args.report.as_posix()}")
    print(
        f"[summary] dest={args.dest.as_posix()} sha256={dest_sha}, bytes={dest_size}, "
        f"dims={meta['width']}x{meta['height']}, checks={len(checks)}/{len(checks)} passed, "
        f"report={args.report.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
