"""Export the Jezero Safe Walk DEM hillshade (Task 06, delivery slot 4).

Reads the Task 03 cropped DEM (``data/processed/dem_20m_crop.tif``, pinned)
and writes ``web/data/hillshade.png``: a 1016 x 1075 single-band (mode L)
lossless PNG hillshade on the EXACT shared grid (row 0 = north, col 0 = west),
<= 3 MB (docs/PLAN.md lines 210 and 325).

Chosen processing parameters (docs/PLAN.md specifies NO azimuth/altitude/
z-factor, so these are technically justified and documented here; PLAN L806:
hillshade is shading derived from the DEM):

- Algorithm: **Lambertian single-direction hillshade** from Horn 3x3 surface
  gradients (Horn 1981) - the same Horn method the Data Science track uses
  for slope (analysis/compute_slope.py), so the two slope-derived products
  are methodologically consistent.
- Illumination: **azimuth 315 deg (northwest), altitude 45 deg** - the
  standard cartographic convention (also the GDAL gdaldem default). NW
  lighting is the accepted convention because it avoids the perceptual
  inversion ("hollow relief") that low-se lighting causes; 45 deg balances
  relief visibility across Jezero's gentle inter-crater terrain.
- **z-factor (vertical exaggeration) = 1.0.** Mars-specific reasoning: the
  DEM's horizontal spacing is 20 m in PROJECTED METRES
  (``grid_meta.pixel_size_projected_m = 20/20``, verified from the transform)
  and its vertical units are METRES (elevations as stored in the USGS
  product). Because both axes are the same physical unit on the same sphere
  (R = 3396190), no unit conversion or z-factor is needed; any z != 1 would
  introduce an artificial vertical exaggeration (an artificial terrain
  feature). No Earth-style degree-based slope correction is applicable.
- Edge handling: **edge-replicate padding** of the DEM for the 3x3 windows.
  Border slopes are then computed from real adjacent terrain instead of a
  black frame or reflected (mirrored) terrain - no artificial border
  features, no artificial ridges at the grid edge.
- NoData handling: the shared grid is contractually COMPLETE (Task 05
  measured ZERO NoData/NaN pixels; the exporter re-measures on every run).
  Any NoData/NaN/+-Infinity in the DEM is a HARD FAIL with a census - the
  hillshade is never interpolated across missing cells and never fabricated.
- Output: uint8 = half-even rounded ``255 * max(dot(n, L), 0)`` (surface
  normal n from the gradients; self-shadowed slopes clamp to 0, flat ground
  maps to 180 at 45 deg altitude), encoded as a **lossless grayscale PNG**
  (mode L), atomic ``.part`` -> ``os.replace`` promotion, size asserted
  <= 3 MB.

Report ownership: ``data/processed/hillshade_report.md`` is written by the
INDEPENDENT validator ``pipeline/verify_hillshade.py`` after every check
(including the double-export determinism proof) passes. This exporter prints
its full evidence to stdout.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\export_hillshade.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/hillshade.png")

# Pinned cropped-DEM identity (house pattern: duplicated in
# verify_hillshade.py and in grid_meta provenance - update all together).
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Illumination contract (documented above).
AZIMUTH_DEG = 315.0   # clockwise from north; light source bearing
ALTITUDE_DEG = 45.0   # sun elevation above horizon
Z_FACTOR = 1.0        # horizontal (projected m) and vertical (m) agree

MAX_BYTES = 3 * 1024 * 1024  # PLAN line 210: <= 3 MB

AXIS_TOL = 1e-9
CELLSIZE = 20.0      # expected projected cell size (m), verified from transform

REQUIRED_META_KEYS = ("width", "height", "crs", "pixel_size_projected_m", "provenance")

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def die(msg: str) -> None:
    raise SystemExit(f"[error] {msg}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dest(dest: Path, overwrite: bool) -> None:
    if dest.suffix.lower() != ".png":
        die(f"--dest must end with '.png' (got {dest.name!r}); refusing unsafe destination")
    if not dest.parent.is_dir():
        die(f"--dest parent directory does not exist: {dest.parent}")
    parts_lower = {p.lower() for p in dest.parts}
    for guarded in ("pipeline", "docs", "analysis"):
        if guarded in parts_lower:
            die(f"--dest must not live under {guarded}/: {dest}")
    try:
        rel = dest.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = None
    if rel is not None and len(rel.parts) >= 2 and rel.parts[0] == "data" and rel.parts[1] == "raw":
        die(f"--dest must not live under data/raw/: {dest}")
    if dest.exists() and not overwrite:
        die(
            f"destination already exists: {dest}\n"
            "       re-run with --overwrite to replace it deliberately"
        )


def load_meta(path: Path) -> dict:
    if not path.is_file():
        die(f"metadata file not found: {path}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        die(f"metadata file is not readable JSON: {exc}")
    missing = [k for k in REQUIRED_META_KEYS if k not in meta]
    if missing:
        die(f"metadata is missing required keys: {', '.join(missing)}")
    print(f"[ok] metadata loaded: {path.as_posix()}")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="deliberately replace an existing destination file",
    )
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.dest)}
    if len(resolves) < 3:
        die("--raster, --meta and --dest must be distinct paths")

    # --------------------------------------------- 1: destination safety
    validate_dest(args.dest, args.overwrite)

    # --------------------------------------------- 2: metadata + DEM identity
    meta = load_meta(args.meta)
    if not args.raster.is_file():
        die(f"raster not found: {args.raster}")
    raster_sha = sha256_of(args.raster)
    if raster_sha != EXPECTED_RASTER_SHA256:
        die(f"raster SHA-256 mismatch: got {raster_sha}, expected pinned {EXPECTED_RASTER_SHA256}")
    prov = meta.get("provenance")
    if not isinstance(prov, dict) or raster_sha != prov.get("dem_sha256"):
        die("raster SHA-256 disagrees with metadata provenance.dem_sha256")
    print(f"[ok] DEM identity: sha256={raster_sha} matches pin + metadata provenance")

    ds = rasterio.open(args.raster)
    if (ds.width, ds.height) != (int(meta["width"]), int(meta["height"])):
        die(f"DEM dims {ds.width}x{ds.height} != metadata {meta['width']}x{meta['height']}")
    if ds.count != 1 or (ds.dtypes or [""])[0] != "float32":
        die(f"DEM band/dtype mismatch: count={ds.count}, dtype={(ds.dtypes or [''])[0]!r}")
    t = ds.transform
    if abs(t.b) > AXIS_TOL or abs(t.d) > AXIS_TOL:
        die("DEM grid is rotated/sheared")
    if t.a <= 0 or t.e >= 0:
        die("DEM is not north-up")
    psp = meta.get("pixel_size_projected_m")
    if not (abs(t.a - float(psp["x"])) <= AXIS_TOL and abs(-t.e - float(psp["y"])) <= AXIS_TOL):
        die("DEM pixel size disagrees with metadata pixel_size_projected_m")
    if abs(t.a - CELLSIZE) > AXIS_TOL or abs(-t.e - CELLSIZE) > AXIS_TOL:
        die(f"cell size is ({t.a!r}, {-t.e!r}); the hillshade contract expects {CELLSIZE} m")
    crs_tokens_meta = str(meta.get("crs", "")).split()
    crs_tokens_ras = (ds.crs.to_proj4() or "").split()
    absent = [tok for tok in crs_tokens_meta if tok not in crs_tokens_ras]
    if absent:
        die(f"DEM CRS is missing metadata CRS tokens: {', '.join(absent)}")
    print(
        f"[ok] DEM geometry: {ds.width}x{ds.height} @ {t.a!r}/{abs(t.e)!r} m projected, "
        f"north-up, unrotated, CRS tokens complete (eqc lat_ts=18.4663 R=3396190)"
    )

    # --------------------------------------------- 3: read + classification census
    raw = ds.read(1)
    ds.close()
    if raw.shape != (ds.height, ds.width) or not raw.flags["C_CONTIGUOUS"]:
        die("read shape/contiguity mismatch")

    src_nodata = float(meta["nodata_elev_dem"])
    inf_mask = np.isinf(raw)
    inf_count = int(inf_mask.sum())
    nan_mask = np.isnan(raw)
    nan_count = int(nan_mask.sum())
    nodata_mask = raw == np.float32(src_nodata)
    nodata_count = int(nodata_mask.sum())
    invalid_count = inf_count + nan_count + nodata_count
    print(
        f"[ok] classification census: valid={raw.size - invalid_count}, "
        f"nodata={nodata_count}, nan={nan_count}, inf={inf_count} (total {raw.size})"
    )
    if invalid_count:
        die(
            "DEM contains NoData/NaN/+-Infinity pixels; the shared grid is contractually "
            "complete, so this must not happen. Per the approved policy the hillshade is "
            "never interpolated across missing cells - STOP for review. No output written."
        )

    # --------------------------------------------- 4: Horn gradients (edge-replicate)
    z = raw.astype(np.float64)  # exact widening before the arithmetic
    zpad = np.pad(z, 1, mode="edge")
    z1 = zpad[:-2, :-2]; z2 = zpad[:-2, 1:-1]; z3 = zpad[:-2, 2:]
    z4 = zpad[1:-1, :-2]; z5 = zpad[1:-1, 1:-1]; z6 = zpad[1:-1, 2:]
    z7 = zpad[2:, :-2]; z8 = zpad[2:, 1:-1]; z9 = zpad[2:, 2:]
    # East- and north-positive gradients (metres per metre), Horn 3x3.
    dzdx = ((z3 + 2.0 * z6 + z9) - (z1 + 2.0 * z4 + z7)) / (8.0 * CELLSIZE)
    dzdn = ((z1 + 2.0 * z2 + z3) - (z7 + 2.0 * z8 + z9)) / (8.0 * CELLSIZE)
    dzdx *= Z_FACTOR
    dzdn *= Z_FACTOR
    slope_rad = np.arctan(np.sqrt(dzdx * dzdx + dzdn * dzdn))
    slope_deg = np.degrees(slope_rad)
    print(
        f"[ok] Horn gradients (edge-replicate, cell {CELLSIZE} m, z-factor {Z_FACTOR}): "
        f"slope range [{float(slope_deg.min()):.3f}, {float(slope_deg.max()):.3f}] deg, "
        f"mean {float(slope_deg.mean()):.3f} deg"
    )

    # --------------------------------------------- 5: Lambertian shading
    az_rad = math.radians(AZIMUTH_DEG)
    alt_rad = math.radians(ALTITUDE_DEG)
    lx = math.sin(az_rad) * math.cos(alt_rad)   # east component of the light vector
    ly = math.cos(az_rad) * math.cos(alt_rad)   # north component
    lz = math.sin(alt_rad)                      # up component
    denom = np.sqrt(dzdx * dzdx + dzdn * dzdn + 1.0)
    shade = (-dzdx * lx - dzdn * ly + lz) / denom
    shade = np.clip(shade, 0.0, 1.0)
    out = np.rint(shade * 255.0).astype(np.uint8)
    if not out.flags["C_CONTIGUOUS"]:
        die("shading array is not C-contiguous")
    flat_expect = 255.0 * math.sin(alt_rad)
    flat_count = int((out == int(np.rint(flat_expect))).sum())
    print(
        f"[ok] shading: azimuth={AZIMUTH_DEG} alt={ALTITUDE_DEG} z={Z_FACTOR}; "
        f"flat-terrain expectation {flat_expect!r} -> {int(np.rint(flat_expect))}; "
        f"output range [{int(out.min())}, {int(out.max())}], "
        f"mean {float(out.mean()):.3f}, std {float(out.std()):.3f}, "
        f"self-shadowed (=0): {int((out == 0).sum())} px "
        f"({100.0 * (out == 0).sum() / out.size:.4f}%)"
    )

    # --------------------------------------------- 6: atomic write (lossless PNG)
    partial = args.dest.with_name(args.dest.name + ".part")
    try:
        Image.fromarray(out, mode="L").save(partial, format="PNG")
    except Exception as exc:  # noqa: BLE001 - any encode failure is a failed export
        die(f"PNG encode failed: {exc}")
    size = partial.stat().st_size
    if size > MAX_BYTES:
        print(
            f"[error] partial PNG is {size} bytes > {MAX_BYTES} limit; "
            f"kept for inspection at {partial}",
            file=sys.stderr,
        )
        return 1
    try:
        os.replace(partial, args.dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial PNG failed: {exc}", file=sys.stderr)
        return 1

    # --------------------------------------------- 7: post-write verification
    with Image.open(args.dest) as img:
        img.load()
        out_ok = img.mode == "L" and img.size == (int(meta["width"]), int(meta["height"]))
        pil_size = img.size
    if not out_ok:
        die("promoted PNG failed re-open verification (mode/dims)")
    dest_sha = sha256_of(args.dest)
    print(f"[ok] promoted: {args.dest.as_posix()} ({size} bytes = {size / 1024:.1f} KiB)")
    print(
        f"[summary] raster={args.raster.as_posix()} sha256={raster_sha}, "
        f"dims={ds.width}x{ds.height}, az={AZIMUTH_DEG} alt={ALTITUDE_DEG} z={Z_FACTOR}, "
        f"invalid=0, slope=[{float(slope_deg.min()):.3f},{float(slope_deg.max()):.3f}] deg, "
        f"dest={args.dest.as_posix()} (mode L, {pil_size[0]}x{pil_size[1]}, {size} bytes), "
        f"dest_sha256={dest_sha}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
