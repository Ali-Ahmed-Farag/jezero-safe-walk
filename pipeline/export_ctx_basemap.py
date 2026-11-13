"""Export the Jezero Safe Walk CTX basemap JPEG (Task 06).

Reads the approved S2 source (``data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_
Eqc_latTs0_lon0.tif`` - the USGS Mars 2020 TRN CTX orthomosaic, 6 m/px, the
exact product NASA JPL Mars Trek streams as "MRO CTX, Jezero Mosaic,
Controlled") and the Task 04 shared-grid contract (``web/data/grid_meta.json``
+ the Task 03 DEM geometry), and writes ``web/data/ctx_basemap.jpg``:
1016 x 1075 RGB JPEG, quality 85, <= 5 MB (docs/PLAN.md line 209).

Approved decisions implemented exactly (Task 06 rulings + preflight audit
2026-11-13/14):

- Source: S2 only (no substitution without explicit team approval).
- Target geometry: EXACTLY the existing DEM grid (transform, CRS, dims from
  ``data/processed/dem_20m_crop.tif``); never recreated or approximated.
- Reprojection: proper geospatial warp onto the target grid (source lat_ts=0
  vs target lat_ts=18.4663; empirically a pure x-rescale), never a plain
  resize. Resampling: **Average** (approved; area-averaging is the correct
  anti-aliased 6 m -> 20 m minification for a visual basemap).
- Source window: outward pixel snapping; the snapped window is PROVEN to
  fully cover the target grid before any use.
- NoData: the source GeoTIFF declares DN=0 as NoData. The DN=0 census
  (2026-11-13) measured ZERO DN=0 pixels in the whole 26,822,880-px mosaic,
  so the ambiguity "valid dark pixel vs missing pixel" cannot arise. The
  exporter enforces this: any DN=0 pixel appearing in the window on a re-run
  ABORTS for re-review (no silent classification, no interpolation, no
  fabrication). Gaps after the warp also abort.
- Contrast: conservative percentile linear stretch over valid pixels, bounds
  computed FROM the measured histogram. Measured distribution (window,
  12,802,048 px): min 31, max 255, mean 152.12, std 27.61; p0.5=74,
  p99.5=229; saturated-255 mass 0.055%. Selected bounds: **p0.5 / p99.5**
  (clips 1.0% of pixels total; ~1.65x gain). p2/p98 was REJECTED as it
  clips 4% and over-flattens a background basemap.
- JPEG: quality 85 (encoded with Pillow, the pinned DE1 imaging dependency
  per PLAN A6; explicit ``subsampling=0``/4:4:4 for version-stable output),
  grayscale replicated to 3-band RGB, atomic ``.part`` -> ``os.replace``
  promotion, size asserted <= 5 MB. Encoder choice justified by measurement:
  at q85 on this content, Pillow achieves PSNR 36.11 dB (max err 25 DN) vs
  GDAL's 33.78 dB (max err 34 DN) - see pipeline/verify_ctx_basemap.py.

Report ownership: ``data/processed/ctx_basemap_report.md`` is written by the
INDEPENDENT validator ``pipeline/verify_ctx_basemap.py`` after every check
(including the double-export determinism proof) passes. This exporter prints
its full evidence to stdout.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\export_ctx_basemap.py
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
from rasterio.crs import CRS
from rasterio.warp import Resampling, reproject, transform as rtransform

DEFAULT_SOURCE = Path("data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif")
DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/ctx_basemap.jpg")

# Pinned identities (house pattern: duplicated in verify_ctx_basemap.py and
# in the provenance sidecar - update all together).
EXPECTED_SOURCE_SHA256 = "842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615"
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Pinned source contract (preflight audit + ISIS label; hard-fail on drift).
EXPECTED_SRC_WIDTH, EXPECTED_SRC_HEIGHT = 5322, 5040
EXPECTED_SRC_TRANSFORM = (6.0, 0.0, 4573663.250853, 0.0, -6.0, 1109693.140188)
EXPECTED_SRC_NODATA = 0.0
EXPECTED_SRC_CRS_TOKENS = ("+proj=eqc", "+lat_ts=0", "+lon_0=0", "+R=3396190", "+units=m")
TRANSFORM_TOL = 1e-6

# Export contract (docs/PLAN.md line 209).
JPEG_QUALITY = 85
MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Contrast-stretch policy (measured-histogram-justified; see docstring).
STRETCH_LO_PCT = 0.5
STRETCH_HI_PCT = 99.5

AXIS_TOL = 1e-9
GAP_SENTINEL = -9999.0

REQUIRED_META_KEYS = ("width", "height", "crs", "provenance")

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
    if dest.suffix.lower() != ".jpg":
        die(f"--dest must end with '.jpg' (got {dest.name!r}); refusing unsafe destination")
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
    prov = meta.get("provenance")
    if not isinstance(prov, dict) or "dem_sha256" not in prov:
        die("metadata 'provenance.dem_sha256' missing")
    print(f"[ok] metadata loaded: {path.as_posix()}")
    return meta


def open_and_validate_target(raster: Path, meta: dict):
    if not raster.is_file():
        die(f"target DEM raster not found: {raster}")
    ds = rasterio.open(raster)
    if ds.count != 1:
        die(f"target DEM has {ds.count} bands; expected 1")
    if ds.width != meta["width"] or ds.height != meta["height"]:
        die(f"target DEM dims {ds.width}x{ds.height} != metadata {meta['width']}x{meta['height']}")
    t = ds.transform
    if abs(t.b) > AXIS_TOL or abs(t.d) > AXIS_TOL:
        die("target DEM grid is rotated/sheared")
    if t.a <= 0 or t.e >= 0:
        die("target DEM is not north-up")
    crs_tokens_meta = str(meta.get("crs", "")).split()
    crs_tokens_ras = (ds.crs.to_proj4() or "").split()
    absent = [tok for tok in crs_tokens_meta if tok not in crs_tokens_ras]
    if absent:
        die(f"target DEM CRS is missing metadata CRS tokens: {', '.join(absent)}")
    print(
        f"[ok] target geometry: {ds.width}x{ds.height} px @ {t.a!r}/{abs(t.e)!r} m, "
        f"north-up, unrotated, CRS tokens complete"
    )
    return ds


def open_and_validate_source(source: Path) -> None:
    if not source.is_file():
        die(f"source raster not found: {source} (run pipeline/acquire_ctx_basemap.py first)")
    src_sha = sha256_of(source)
    if src_sha != EXPECTED_SOURCE_SHA256:
        die(f"source SHA-256 mismatch: got {src_sha}, expected pinned {EXPECTED_SOURCE_SHA256}")
    ds = rasterio.open(source)
    if (ds.width, ds.height) != (EXPECTED_SRC_WIDTH, EXPECTED_SRC_HEIGHT):
        die(f"source dims {ds.width}x{ds.height} != pinned {EXPECTED_SRC_WIDTH}x{EXPECTED_SRC_HEIGHT}")
    if ds.count != 1 or (ds.dtypes or [""])[0] != "uint8":
        die(f"source band/dtype mismatch: count={ds.count}, dtype={(ds.dtypes or [''])[0]!r}")
    if float(ds.nodata if ds.nodata is not None else float("nan")) != EXPECTED_SRC_NODATA:
        die(f"source NoData tag is {ds.nodata!r}; pinned contract requires {EXPECTED_SRC_NODATA!r}")
    t = ds.transform
    got = (t.a, t.b, t.c, t.d, t.e, t.f)
    bad = [
        f"{name}: got {g!r}, expected {e!r}"
        for name, g, e in zip(("a", "b", "c", "d", "e", "f"), got, EXPECTED_SRC_TRANSFORM)
        if abs(g - e) > TRANSFORM_TOL
    ]
    if bad:
        die("source transform drift: " + "; ".join(bad))
    toks = (ds.crs.to_proj4() or "").split()
    absent = [tok for tok in EXPECTED_SRC_CRS_TOKENS if tok not in toks]
    if absent:
        die(f"source CRS is missing pinned tokens: {', '.join(absent)}")
    print(
        f"[ok] source validated: sha256={src_sha}, {ds.width}x{ds.height} 1x uint8, "
        f"nodata={ds.nodata!r}, 6 m/px eqc lat_ts=0 R=3396190, transform == preflight pin"
    )


def compute_window(target_ds, s2crs: CRS, src_transform) -> tuple[int, int, int, int]:
    """Outward-snapped source pixel window covering the exact target grid."""
    t = src_transform
    px, py = t.a, -t.e
    db = target_ds.bounds
    gx, gy = rtransform(
        target_ds.crs, s2crs,
        [db.left, db.right, db.right, db.left],
        [db.bottom, db.bottom, db.top, db.top],
    )
    gxmin, gxmax, gymin, gymax = min(gx), max(gx), min(gy), max(gy)
    col_lo = math.floor((gxmin - t.c) / px)
    col_hi = math.ceil((gxmax - t.c) / px)
    row_lo = math.floor((t.f - gymax) / py)
    row_hi = math.ceil((t.f - gymin) / py)
    if not (0 <= col_lo < col_hi <= target_ds.width * 100 and row_lo >= 0):
        die(f"unsnapped window out of range: cols [{col_lo}, {col_hi}), rows [{row_lo}, {row_hi})")
    print(
        f"[ok] grid bounds in source CRS: x [{gxmin:.3f}, {gxmax:.3f}], y [{gymin:.3f}, {gymax:.3f}]; "
        f"outward-snapped window cols [{col_lo}, {col_hi}), rows [{row_lo}, {row_hi}) "
        f"({col_hi - col_lo}x{row_hi - row_lo} px)"
    )
    # Prove the snapped window fully covers the target grid.
    wx = [t.c + col_lo * px, t.c + col_hi * px]
    wy = [t.f - row_lo * py, t.f - row_hi * py]
    bx, by = rtransform(s2crs, target_ds.crs, [wx[0], wx[1], wx[1], wx[0]], [wy[1], wy[1], wy[0], wy[0]])
    wminx, wmaxx, wminy, wmaxy = min(bx), max(bx), min(by), max(by)
    covers = (
        wminx <= db.left + 1e-6 and wmaxx >= db.right - 1e-6
        and wminy <= db.bottom + 1e-6 and wmaxy >= db.top - 1e-6
    )
    if not covers:
        die(
            "snapped window does not fully cover the target grid: "
            f"window x[{wminx:.3f},{wmaxx:.3f}] y[{wminy:.3f},{wmaxy:.3f}] vs "
            f"grid x[{db.left:.3f},{db.right:.3f}] y[{db.bottom:.3f},{db.top:.3f}]"
        )
    print(
        f"[ok] coverage proof: snapped window covers the grid with margins "
        f"left {db.left - wminx:.3f} m, right {wmaxx - db.right:.3f} m, "
        f"bottom {db.bottom - wminy:.3f} m, top {wmaxy - db.top:.3f} m"
    )
    return col_lo, row_lo, col_hi, row_hi


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="deliberately replace an existing destination file",
    )
    parser.add_argument("--stretch-lo-pct", type=float, default=STRETCH_LO_PCT)
    parser.add_argument("--stretch-hi-pct", type=float, default=STRETCH_HI_PCT)
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.source, args.raster, args.meta, args.dest)}
    if len(resolves) < 4:
        die("--source, --raster, --meta and --dest must be distinct paths")
    if not (0.0 <= args.stretch_lo_pct < args.stretch_hi_pct <= 100.0):
        die(f"stretch percentiles invalid: {args.stretch_lo_pct!r} / {args.stretch_hi_pct!r}")

    # --------------------------------------------- 1: destination safety
    validate_dest(args.dest, args.overwrite)

    # --------------------------------------------- 2: contracts
    meta = load_meta(args.meta)
    target_ds = open_and_validate_target(args.raster, meta)
    if sha256_of(args.raster) != EXPECTED_RASTER_SHA256:
        die("target DEM SHA-256 does not match the pinned Task 03 crop")
    if sha256_of(args.raster) != meta["provenance"]["dem_sha256"]:
        die("target DEM SHA-256 disagrees with metadata provenance.dem_sha256")
    print("[ok] target provenance chain: DEM SHA matches pin + metadata")
    open_and_validate_source(args.source)

    # --------------------------------------------- 3: source window (outward snap)
    with rasterio.open(args.source) as src:
        s2crs = CRS.from_proj4(src.crs.to_proj4())
        col_lo, row_lo, col_hi, row_hi = compute_window(target_ds, s2crs, src.transform)
        t = src.transform
        px, py = t.a, -t.e
        win = rasterio.windows.Window(col_lo, row_lo, col_hi - col_lo, row_hi - row_lo)
        src_transform = rasterio.transform.from_origin(
            t.c + col_lo * px, t.f - row_lo * py, px, py
        )

        # ----------------------------------------- 4: DN=0 census guard (approved state)
        window = src.read(1, window=win)
        if window.shape != (row_hi - row_lo, col_hi - col_lo):
            die(f"window read shape {window.shape} != requested")
        zeros = int((window == 0).sum())
        print(
            f"[ok] DN=0 census (window): {zeros} zero pixels of {window.size} "
            f"({100.0 * zeros / window.size:.6f}%)"
        )
        if zeros:
            die(
                "the approved census state (ZERO DN=0 pixels in the window) no longer holds; "
                "per the approved NoData gate a re-run must STOP for review instead of "
                "silently classifying zeros as NoData or data. No output written."
            )

        # ----------------------------------------- 5: histogram + stretch bounds
        hist = np.bincount(window.ravel(), minlength=256)
        cdf = np.cumsum(hist) / window.size * 100.0
        lo = int(np.searchsorted(cdf, args.stretch_lo_pct, side="left"))
        hi = int(np.searchsorted(cdf, args.stretch_hi_pct, side="left"))
        if not (1 <= lo < hi <= 255):
            die(f"derived stretch bounds invalid: lo={lo}, hi={hi}")
        clip_lo = float(hist[:lo].sum() / window.size * 100.0)
        clip_hi = float(hist[hi + 1:].sum() / window.size * 100.0)
        print(
            f"[ok] measured histogram: min={int(window.min())}, max={int(window.max())}, "
            f"mean={float(window.mean()):.3f}, std={float(window.std()):.3f}"
        )
        print(
            f"[ok] stretch bounds from the measured histogram: p{args.stretch_lo_pct:g}={lo}, "
            f"p{args.stretch_hi_pct:g}={hi}; clipped below={clip_lo:.4f}%, "
            f"above={clip_hi:.4f}% (total {clip_lo + clip_hi:.4f}%)"
        )

        # ----------------------------------------- 6: warp to the EXACT target grid
        dst = np.full((target_ds.height, target_ds.width), GAP_SENTINEL, dtype=np.float32)
        reproject(
            source=window,
            destination=dst,
            src_transform=src_transform,
            src_crs=s2crs,
            src_nodata=EXPECTED_SRC_NODATA,
            dst_transform=target_ds.transform,
            dst_crs=target_ds.crs,
            dst_nodata=GAP_SENTINEL,
            resampling=Resampling.average,
        )
        gaps = int((dst == GAP_SENTINEL).sum())
        print(
            f"[ok] warp (Average, lat_ts=0 -> lat_ts=18.4663): output gaps = {gaps} "
            f"of {dst.size} (policy: hard fail on any gap)"
        )
        if gaps:
            die("warp produced genuine coverage gaps; refusing to fabricate or interpolate")

    target_ds.close()

    # --------------------------------------------- 7: conservative linear stretch
    v64 = dst.astype(np.float64)  # exact widening before the stretch arithmetic
    scale = 255.0 / float(hi - lo)
    stretched = np.clip(np.rint((v64 - float(lo)) * scale), 0, 255).astype(np.uint8)
    if not stretched.flags["C_CONTIGUOUS"]:
        die("stretched array is not C-contiguous")
    after_mean = float(stretched.mean())
    after_std = float(stretched.std())
    pure_black = int((stretched == 0).sum())
    pure_white = int((stretched == 255).sum())
    print(
        f"[ok] stretch applied: [{lo},{hi}] -> [0,255] (half-even rounding); "
        f"after: mean={after_mean:.3f}, std={after_std:.3f}, "
        f"pure-black={pure_black} px ({100.0 * pure_black / stretched.size:.4f}%), "
        f"pure-white={pure_white} px ({100.0 * pure_white / stretched.size:.4f}%)"
    )

    # --------------------------------------------- 8: grayscale -> RGB + atomic write
    rgb = np.stack([stretched, stretched, stretched], axis=0)  # rasterio order: (bands, rows, cols)
    rgb_hwc = np.transpose(rgb, (1, 2, 0))  # PIL order: (rows, cols, bands)
    partial = args.dest.with_name(args.dest.name + ".part")
    try:
        Image.fromarray(rgb_hwc, mode="RGB").save(
            partial, format="JPEG", quality=JPEG_QUALITY, subsampling=0
        )
    except Exception as exc:  # noqa: BLE001 - any encode failure is a failed export
        die(f"JPEG encode failed: {exc}")
    size = partial.stat().st_size
    if size > MAX_BYTES:
        print(
            f"[error] partial JPEG is {size} bytes > {MAX_BYTES} limit; "
            f"kept for inspection at {partial}",
            file=sys.stderr,
        )
        return 1
    try:
        os.replace(partial, args.dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial JPEG failed: {exc}", file=sys.stderr)
        return 1

    # --------------------------------------------- 9: post-write verification
    with rasterio.open(args.dest) as out:
        out_ok = (out.width, out.height, out.count) == (
            meta["width"], meta["height"], 3
        ) and (out.dtypes or [""])[0] == "uint8"
    if not out_ok:
        die("promoted JPEG failed re-open verification (dims/bands/dtype)")
    dest_sha = sha256_of(args.dest)
    print(f"[ok] promoted: {args.dest.as_posix()} ({size} bytes = {size / 1024:.1f} KiB)")
    print(
        f"[summary] source={args.source.as_posix()} sha256={EXPECTED_SOURCE_SHA256}, "
        f"window_cols=[{col_lo},{col_hi}) rows=[{row_lo},{row_hi}), "
        f"window={col_hi - col_lo}x{row_hi - row_lo} px, zeros={zeros}, "
        f"stretch=[{lo},{hi}] (p{args.stretch_lo_pct:g}/p{args.stretch_hi_pct:g}), "
        f"clip_total={clip_lo + clip_hi:.4f}%, gaps=0, dest={args.dest.as_posix()} "
        f"({meta['width']}x{meta['height']} RGB q{JPEG_QUALITY}, {size} bytes), "
        f"dest_sha256={dest_sha}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
