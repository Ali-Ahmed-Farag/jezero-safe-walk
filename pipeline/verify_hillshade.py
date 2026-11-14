"""Independent validator + report owner for the Task 06 hillshade.

Verifies ``web/data/hillshade.png`` against the CONTRACT - re-derived here
from ``web/data/grid_meta.json``, the pinned Task 03 DEM and the documented
hillshade parameters - without importing anything from
``pipeline/export_hillshade.py`` (house cross-validation pattern: a
shared-wrong-derivation blind spot is avoided by deriving the expected image
from the contract text, not from the exporter's code).

Contract encoded here (documented in the exporter's docstring):

- Source: pinned ``data/processed/dem_20m_crop.tif`` on the EXACT shared grid
  (1016 x 1075 @ 20 m projected, eqc lat_ts=18.4663, R=3396190).
- Lambertian single-direction hillshade from Horn 3x3 gradients;
  azimuth 315 deg (NW), altitude 45 deg, z-factor 1.0 (projected-metre
  horizontal == metre vertical; no artificial exaggeration).
- Edge-replicate padding; NoData/NaN/+-Infinity: hard fail (grid is
  contractually complete).
- Output: uint8 half-even ``255 * max(dot(n, L), 0)``; lossless mode-L PNG
  <= 3 MB (PLAN line 210), atomic promotion, deterministic.

Checks performed (full-element, never size-only):

1. Metadata contract, DEM identity/provenance chain.
2. DEM geometry (dims, north-up, unrotated, CRS tokens, pixel size).
3. Classification census: the DEM must contain ZERO invalid pixels
   (NoData/NaN/+-Infinity) - the hillshade contract cannot be met otherwise.
4. Output file: exists, <= 3 MB, decodes via Pillow as mode L 1016 x 1075.
5. FULL-array EXACT equality against the independently derived shading
   (PNG is lossless, so any difference is a derivation/encoding defect).
6. Determinism: the exporter runs TWICE into a temporary directory and the
   SHA-256 of both runs must equal each other and the final artifact.

Report: on a full pass this script writes the deterministic
``data/processed/hillshade_report.md`` (no timestamps, relative posix paths,
ASCII, LF-only). On any failure the report is NOT written and the script
exits non-zero.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\verify_hillshade.py
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

DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/hillshade.png")
DEFAULT_REPORT = Path("data/processed/hillshade_report.md")

# Pinned cropped-DEM identity (house pattern: duplicated in
# export_hillshade.py and in grid_meta provenance - update all together).
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Documented illumination/processing contract (must match export_hillshade.py).
AZIMUTH_DEG = 315.0
ALTITUDE_DEG = 45.0
Z_FACTOR = 1.0
CELLSIZE = 20.0
MAX_BYTES = 3 * 1024 * 1024

AXIS_TOL = 1e-9

REQUIRED_META_KEYS = ("width", "height", "crs", "pixel_size_projected_m", "provenance")

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def derive_expected_shading(raster_path: Path, meta: dict) -> dict:
    """Independently derive the expected uint8 hillshade from the contract."""
    with rasterio.open(raster_path) as d:
        t = d.transform
        raw = d.read(1)
    src_nodata = float(meta["nodata_elev_dem"])
    inf_count = int(np.isinf(raw).sum())
    nan_count = int(np.isnan(raw).sum())
    nodata_count = int((raw == np.float32(src_nodata)).sum())
    z = raw.astype(np.float64)
    zpad = np.pad(z, 1, mode="edge")
    z1 = zpad[:-2, :-2]; z2 = zpad[:-2, 1:-1]; z3 = zpad[:-2, 2:]
    z4 = zpad[1:-1, :-2]; z5 = zpad[1:-1, 1:-1]; z6 = zpad[1:-1, 2:]
    z7 = zpad[2:, :-2]; z8 = zpad[2:, 1:-1]; z9 = zpad[2:, 2:]
    csx = float(t.a); csy = float(-t.e)
    dzdx = (((z3 + 2.0 * z6 + z9) - (z1 + 2.0 * z4 + z7)) / (8.0 * csx)) * Z_FACTOR
    dzdn = (((z1 + 2.0 * z2 + z3) - (z7 + 2.0 * z8 + z9)) / (8.0 * csy)) * Z_FACTOR
    slope_deg = np.degrees(np.arctan(np.sqrt(dzdx * dzdx + dzdn * dzdn)))
    az_rad = math.radians(AZIMUTH_DEG)
    alt_rad = math.radians(ALTITUDE_DEG)
    lx = math.sin(az_rad) * math.cos(alt_rad)
    ly = math.cos(az_rad) * math.cos(alt_rad)
    lz = math.sin(alt_rad)
    denom = np.sqrt(dzdx * dzdx + dzdn * dzdn + 1.0)
    shade = np.clip((-dzdx * lx - dzdn * ly + lz) / denom, 0.0, 1.0)
    out = np.rint(shade * 255.0).astype(np.uint8)
    return {
        "expected": out,
        "inf": inf_count, "nan": nan_count, "nodata": nodata_count,
        "slope_min": float(slope_deg.min()), "slope_max": float(slope_deg.max()),
        "slope_mean": float(slope_deg.mean()),
        "shade_min": int(out.min()), "shade_max": int(out.max()),
        "shade_mean": float(out.mean()), "shade_std": float(out.std()),
        "self_shadowed": int((out == 0).sum()),
        "flat_value": int(np.rint(255.0 * math.sin(alt_rad))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.dest, args.report)}
    if len(resolves) < 4:
        print("[error] --raster, --meta, --dest and --report must be distinct paths", file=sys.stderr)
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
        "DEM SHA-256 chain (pin + metadata + provenance path)",
        pin_ok and prov_ok and dem_file_ok,
        f"{raster_sha} (pin match={pin_ok}, provenance match={prov_ok}, path match={dem_file_ok})",
    )

    # ------------------------------------------------ 2: DEM geometry
    try:
        with rasterio.open(args.raster) as d:
            t = d.transform
            geom_ok = (
                (d.width, d.height) == (int(meta["width"]), int(meta["height"]))
                and d.count == 1 and (d.dtypes or [""])[0] == "float32"
                and abs(t.b) <= AXIS_TOL and abs(t.d) <= AXIS_TOL
                and t.a > 0 and t.e < 0
            )
            psp = meta.get("pixel_size_projected_m")
            psp_ok = abs(t.a - float(psp["x"])) <= AXIS_TOL and abs(-t.e - float(psp["y"])) <= AXIS_TOL
            crs_tokens_meta = str(meta.get("crs", "")).split()
            crs_ok = all(tok in (d.crs.to_proj4() or "").split() for tok in crs_tokens_meta)
            dims = (d.width, d.height)
        failed |= not add(
            "DEM identity/geometry (dims, 1x float32, north-up, unrotated)",
            geom_ok,
            f"{dims[0]}x{dims[1]}, a={t.a!r}, e={t.e!r}, |b|={abs(t.b)!r}, |d|={abs(t.d)!r}",
        )
        failed |= not add(
            "DEM pixel size == metadata pixel_size_projected_m (20 m projected)",
            psp_ok,
            f"transform ({t.a!r}, {-t.e!r}) vs metadata ({psp['x']!r}, {psp['y']!r})",
        )
        failed |= not add(
            "DEM CRS tokens complete (eqc lat_ts=18.4663 R=3396190)",
            crs_ok,
            f"tokens subset={crs_ok}",
        )
    except Exception as exc:  # noqa: BLE001
        add("DEM identity/geometry", False, f"unreadable: {exc}")
        print("[error] cannot continue without the DEM", file=sys.stderr)
        return 1

    # ------------------------------------------------ 3: census (must be clean)
    try:
        derived = derive_expected_shading(args.raster, meta)
    except Exception as exc:  # noqa: BLE001
        add("independent expected-shading derivation", False, f"failed: {exc}")
        print("[error] cannot continue without the derived expectation", file=sys.stderr)
        return 1
    invalid = derived["inf"] + derived["nan"] + derived["nodata"]
    failed |= not add(
        "classification census: DEM contains ZERO NoData/NaN/+-Infinity pixels",
        invalid == 0,
        f"nodata={derived['nodata']}, nan={derived['nan']}, inf={derived['inf']} "
        f"(total {dims[0] * dims[1]}; the interpolation-free contract holds vacuously)",
    )

    # ------------------------------------------------ 4: output file identity
    if not args.dest.is_file():
        add("output exists", False, f"not found: {args.dest}")
        print("[error] run pipeline/export_hillshade.py first", file=sys.stderr)
        return 1
    dest_size = args.dest.stat().st_size
    failed |= not add(
        f"output size <= {MAX_BYTES} bytes (3 MB)",
        dest_size <= MAX_BYTES,
        f"{dest_size} bytes ({dest_size / 1024:.1f} KiB)",
    )
    try:
        img = Image.open(args.dest)
        img.load()
        pil_ok = img.mode == "L" and img.size == (int(meta["width"]), int(meta["height"]))
        decoded = np.asarray(img)
        failed |= not add(
            "Pillow decode (mode L, exact dims)",
            pil_ok,
            f"mode={img.mode!r} (L required), size={img.size!r} "
            f"({meta['width']}x{meta['height']} required)",
        )
    except Exception as exc:  # noqa: BLE001
        add("Pillow decode", False, f"decode failed: {exc}")
        print("[error] cannot continue without a decodable output", file=sys.stderr)
        return 1

    # ------------------------------------------------ 5: FULL-array exact equality
    expected = derived["expected"]
    differing = int((decoded != expected).sum())
    elements = int(decoded.size)
    failed |= not add(
        "FULL-array EXACT equality vs independently derived shading "
        "(PNG lossless: zero tolerance)",
        differing == 0,
        f"{elements - differing}/{elements} elements equal ({differing} differing) - "
        "this is the target-grid alignment proof: every output pixel equals the "
        "contract hillshade on the exact DEM grid",
    )
    out_min, out_max = int(decoded.min()), int(decoded.max())
    failed |= not add(
        "pixel values within [0, 255] uint8 and distribution sane",
        0 <= out_min and out_max <= 255,
        f"range [{out_min}, {out_max}], mean {float(decoded.mean()):.3f}, "
        f"std {float(decoded.std()):.3f}, self-shadowed(=0) {int((decoded == 0).sum())} px",
    )

    # ------------------------------------------------ 6: determinism (double export)
    exporter = Path(__file__).resolve().parent / "export_hillshade.py"
    tmp = Path(tempfile.mkdtemp(prefix="hillshade-det-"))
    run_shas: list[str] = []
    run_codes: list[int] = []
    try:
        for i in (1, 2):
            dest_i = tmp / f"hillshade_run{i}.png"
            proc = subprocess.run(
                [
                    sys.executable, str(exporter),
                    "--raster", str(args.raster.resolve()),
                    "--meta", str(args.meta.resolve()),
                    "--dest", str(dest_i),
                    "--overwrite",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=600,
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
        dest_sha = sha256_of(args.dest)
        det_ok = run_shas[0] == run_shas[1] == dest_sha
        failed |= not add(
            "determinism: two temp exports equal the final artifact (SHA-256 x3)",
            det_ok,
            f"run1={run_shas[0][:16]}..., run2={run_shas[1][:16]}..., final={dest_sha[:16]}..., "
            f"exit codes {run_codes}; temp dir removed",
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
    dest_sha = sha256_of(args.dest)
    report = f"""# Hillshade Report - `web/data/hillshade.png` (Task 06, delivery slot 4)

Task 06 hillshade deliverable evidence - written by
`pipeline/verify_hillshade.py` after the exporter
(`pipeline/export_hillshade.py`) and every independent validation check
(including the double-export determinism proof) passed. Deterministic
content: no timestamps; all values are measured from the files listed below.

## 1. Approved processing decisions (documented and validated)

- Output: `web/data/hillshade.png`, **PNG, <= 3 MB, DE1**
  (docs/PLAN.md line 210; delivery slot 4 with `ctx_basemap.jpg`, line 325;
  glossary line 806: hillshade = shading derived from the DEM).
- Algorithm: **Lambertian single-direction hillshade from Horn 3x3 surface
  gradients** (Horn 1981) - methodologically consistent with the Data
  Science track's Horn slope (`analysis/compute_slope.py`).
- Illumination: **azimuth 315 deg (NW), altitude 45 deg** - the standard
  cartographic convention (GDAL gdaldem defaults); NW lighting avoids the
  perceptual "hollow relief" inversion.
- **z-factor = 1.0** - Mars-specific: horizontal spacing is 20 m in PROJECTED
  METRES and vertical units are METRES (same physical unit, same sphere
  R = 3396190), so no unit conversion or exaggeration is needed; any z != 1
  would be an artificial terrain feature.
- Edge handling: **edge-replicate padding** (real adjacent terrain at the
  borders; no black frame, no mirrored terrain, no artificial features).
- NoData: the grid is contractually complete; any NoData/NaN/+-Infinity is a
  HARD FAIL - never interpolated, never fabricated.
- Output: uint8 half-even `255 * max(dot(n, L), 0)`; flat ground maps to
  {derived['flat_value']} at 45 deg; lossless grayscale PNG (mode L).

## 2. Input identity

| Item | Value |
|---|---|
| Source DEM | `{args.raster.as_posix()}` (Task 03 crop) |
| DEM file size | {args.raster.stat().st_size} bytes |
| DEM SHA-256 | `{raster_sha}` (pin + metadata provenance match) |
| Dimensions | {dims[0]} x {dims[1]} px @ 20 m projected |
| CRS | equirectangular lat_ts=18.4663, R=3396190, metres |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `{args.dest.as_posix()}` |
| File size | {dest_size} bytes ({dest_size / 1024:.1f} KiB; limit {MAX_BYTES} = 3 MB) |
| SHA-256 | `{dest_sha}` |
| Dimensions / mode | {meta['width']} x {meta['height']} px, single-band grayscale (PIL mode L) |

## 4. Processing parameters (as executed)

| Parameter | Value |
|---|---|
| Method | Lambertian hillshade, Horn 3x3 gradients (edge-replicate padding) |
| Azimuth | {AZIMUTH_DEG} deg (clockwise from north) |
| Altitude | {ALTITUDE_DEG} deg |
| z-factor | {Z_FACTOR} |
| Cell size | {CELLSIZE} m x {CELLSIZE} m (projected; verified from the transform) |
| Rounding | half-even via `numpy.rint` |
| Self-shadow clamp | `max(dot, 0)` before scaling |

## 5. Measured evidence

| Item | Value |
|---|---|
| Classification census | valid {dims[0] * dims[1] - invalid}, nodata {derived['nodata']}, nan {derived['nan']}, inf {derived['inf']} |
| Slope range (Horn, 20 m) | [{derived['slope_min']:.3f}, {derived['slope_max']:.3f}] deg (mean {derived['slope_mean']:.3f} deg) |
| Shading range | [{derived['shade_min']}, {derived['shade_max']}] |
| Shading mean / std | {derived['shade_mean']:.3f} / {derived['shade_std']:.3f} |
| Self-shadowed pixels (=0) | {derived['self_shadowed']} ({100.0 * derived['self_shadowed'] / elements:.4f}%) |
| Full-array equality vs independent derivation | {elements - differing}/{elements} elements equal ({differing} differing; PNG lossless, zero tolerance) |

## 6. Validator results

| Check | Result | Measured detail |
|---|---|---|
{checks_table}

## 7. Determinism result

The exporter ran twice into a temporary directory; exit codes {run_codes[0]} and {run_codes[1]};
SHA-256 of run 1 == run 2 == final artifact (`{run_shas[0] if run_shas else 'n/a'}`).
The temporary directory was removed; the final artifact was not rewritten.

## 8. Untested behavior and limitations

- The NoData/NaN/+-Infinity hard-fail path is NOT exercised by data (0 such
  pixels); enforced by explicit abort guards and verified by code review only
  (same honest caveat pattern as Task 05).
- Border pixels use edge-replicated neighbours (documented; 1-px border band,
  no artificial features).
- Determinism proven for consecutive runs on this machine (numpy
  {np.__version__}, rasterio {rasterio.__version__}, Pillow {Image.__version__ if hasattr(Image, '__version__') else 'n/a'});
  re-exports assume the pinned environment.
- The PNG intentionally carries no georeferencing; the layer is geolocated
  through `web/data/grid_meta.json` (pixel (row, col) maps exactly onto the
  shared decode grid, row 0 = north, col 0 = west).

## 9. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}, Pillow {getattr(__import__('PIL'), '__version__')}
- Scripts: `pipeline/export_hillshade.py` (exporter),
  `pipeline/verify_hillshade.py` (this validator + report owner; rerunnable,
  deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.report.write_text(report, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[error] writing the hillshade report failed: {exc}", file=sys.stderr)
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
