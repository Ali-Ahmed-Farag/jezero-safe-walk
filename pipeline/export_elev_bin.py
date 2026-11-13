"""Export the Jezero Safe Walk elevation binary (Task 05).

Reads the Task 03 cropped DEM (``data/processed/dem_20m_crop.tif``) and the
Task 04 shared-grid metadata (``web/data/grid_meta.json``), converts elevation
metres to decimetres, and writes ``web/data/elev_dm_i16.bin``: a flat,
headerless, row-major Int16 little-endian array (row 0 = north, col 0 = west).

Approved decisions (team ruling, recorded in the Task 05 analysis),
implemented exactly:

- Rounding: half-even via ``numpy.rint``.
- Arithmetic: widen Float32 -> Float64 BEFORE the x10 multiply. Widening is
  exact (every Float32 is a Float64) and the product then needs <= 28 mantissa
  bits (24 + 4), so the result is a pure function of the stored Float32 bits.
  (A Float32 multiply would be lossy and flip ~1.1k near-tie pixels.)
- Conversion: decimetres = metres x 10 (``elev_scale``).
- Encoding: signed Int16, EXPLICITLY little-endian (``<i2``), never native.
- NoData: source NoData pixels and NaN both map to ``grid_meta.nodata_elev``
  (-32768).
- +/-Infinity: HARD FAIL with diagnostics (never mapped, never clipped).
- Out-of-range values are never clipped, wrapped or truncated: the run aborts
  before writing anything.
- No ``.gitattributes`` is added (team decision); no synthetic NoData test
  (team decision).

Contract references: docs/PLAN.md §5.2 line 207 (``elev_dm_i16.bin`` =
decimetres, Int16 little-endian), §5.1 lines 196-199 (shared grid, row 0 =
north, col 0 = west, row-major) and the ``grid_meta.json`` "notes" decode
recipe (``elev_m = int16_le / elev_scale``).

Report ownership: ``data/processed/elev_bin_report.md`` is written by the
INDEPENDENT validator ``pipeline/verify_elev_bin.py`` after every check
(including the double-export determinism proof) passes, because the report
must contain validator + determinism evidence that only exists after
validation. This exporter prints its full evidence to stdout.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\export_elev_bin.py
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

DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/elev_dm_i16.bin")

# Pinned cropped-DEM identity (Task 03 crop; equals grid_meta provenance).
# NOTE: this pin is duplicated in pipeline/verify_elev_bin.py and in
# web/data/grid_meta.json provenance.dem_sha256 - update all three together
# (house pattern: crop_dem.py documents the same pin-duplication rule for
# acquire_dem.py + crop_dem.py + the provenance sidecar).
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Contract constants (docs/PLAN.md §5.2; grid_meta.json).
ELEV_SCALE = 10
NODATA_ELEV = -32768
INT16_MIN = -32768
INT16_MAX = 32767
DTYPE_LE = "<i2"

# Geometry guards (Task 04 hardening style): reject rotated/sheared grids.
AXIS_TOL = 1e-9

# Provenance tags embedded in the crop by pipeline/crop_dem.py (Task 03),
# as required by pipeline/make_grid_meta.py.
REQUIRED_TAGS = (
    "AOI_REQUESTED",
    "AOI_SNAP_RULE",
    "SOURCE_COL0",
    "SOURCE_ROW0",
    "SOURCE_SHA256",
    "SOURCE_FILE",
)

REQUIRED_META_KEYS = (
    "width",
    "height",
    "elev_scale",
    "nodata_elev",
    "nodata_elev_dem",
    "row0",
    "col0",
    "layout",
    "elev_range_m",
    "provenance",
)
REQUIRED_PROVENANCE_KEYS = ("dem_file", "dem_sha256", "source_dem", "source_dem_sha256")

CHUNK = 1 << 20

REPO_ROOT = Path(__file__).resolve().parents[1]


def die(msg: str) -> None:
    raise SystemExit(f"[error] {msg}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dest(dest: Path, overwrite: bool) -> None:
    """Refuse unsafe destinations and accidental overwrites."""
    if dest.suffix.lower() != ".bin":
        die(f"--dest must end with '.bin' (got {dest.name!r}); refusing unsafe destination")
    if not dest.parent.is_dir():
        die(f"--dest parent directory does not exist: {dest.parent}")
    parts_lower = {p.lower() for p in dest.parts}
    for guarded in ("pipeline", "docs", "analysis"):
        if guarded in parts_lower:  # case-insensitive: Windows paths are case-insensitive
            die(f"--dest must not live under {guarded}/: {dest}")
    try:
        rel = dest.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = None  # outside the repository (e.g. a temp dir) - allowed
    if rel is not None and len(rel.parts) >= 2 and rel.parts[0] == "data" and rel.parts[1] == "raw":
        die(f"--dest must not live under data/raw/: {dest}")
    if dest.exists():
        if not overwrite:
            die(
                f"destination already exists: {dest}\n"
                "       re-run with --overwrite to replace it deliberately"
            )
        print("[ok] existing destination present; --overwrite given, it will be replaced")


def load_meta(path: Path) -> dict:
    if not path.is_file():
        die(f"metadata file not found: {path}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        die(f"metadata file is not readable JSON: {exc}")
    if not isinstance(meta, dict):
        die("metadata JSON root is not an object")
    missing = [k for k in REQUIRED_META_KEYS if k not in meta]
    if missing:
        die(f"metadata is missing required keys: {', '.join(missing)}")
    prov = meta.get("provenance")
    if not isinstance(prov, dict):
        die("metadata 'provenance' is not an object")
    missing = [k for k in REQUIRED_PROVENANCE_KEYS if k not in prov]
    if missing:
        die(f"metadata provenance is missing required keys: {', '.join(missing)}")
    print(f"[ok] metadata loaded: {path.as_posix()} ({len(meta)} top-level keys)")
    return meta


def check_meta_contract(meta: dict) -> None:
    """The exporter enforces the shared-grid contract values it depends on."""
    if meta["elev_scale"] != ELEV_SCALE:
        die(f"metadata elev_scale is {meta['elev_scale']!r}; contract requires {ELEV_SCALE}")
    if meta["nodata_elev"] != NODATA_ELEV:
        die(f"metadata nodata_elev is {meta['nodata_elev']!r}; contract requires {NODATA_ELEV}")
    if (meta["row0"], meta["col0"], meta["layout"]) != ("north", "west", "row_major"):
        die(
            "metadata grid order is "
            f"row0={meta['row0']!r}, col0={meta['col0']!r}, layout={meta['layout']!r}; "
            "contract requires row0='north', col0='west', layout='row_major'"
        )
    print(
        "[ok] metadata contract: elev_scale=10, nodata_elev=-32768, "
        "row0=north, col0=west, layout=row_major"
    )


def open_and_validate_raster(raster: Path, meta: dict):
    """Open the raster and enforce every identity/geometry invariant."""
    if not raster.is_file():
        die(f"raster not found: {raster}")
    if raster.stat().st_size == 0:
        die(f"raster is empty: {raster}")
    try:
        ds = rasterio.open(raster)
    except Exception as exc:
        die(f"raster is not a readable raster: {exc}")
    if ds.count != 1:
        die(f"raster has {ds.count} bands; expected exactly 1")
    dtype = (ds.dtypes or [""])[0]
    if dtype != "float32":
        die(f"raster dtype is {dtype!r}; expected 'float32'")
    if ds.width != meta["width"] or ds.height != meta["height"]:
        die(
            f"raster dims {ds.width}x{ds.height} do not match metadata "
            f"{meta['width']}x{meta['height']}"
        )
    if ds.crs is None:
        die("raster has no CRS")
    t = ds.transform
    if abs(t.b) > AXIS_TOL or abs(t.d) > AXIS_TOL:
        die(f"raster grid is rotated/sheared (|b|={abs(t.b)!r}, |d|={abs(t.d)!r} > {AXIS_TOL})")
    if t.a <= 0 or t.e >= 0:
        die(f"raster is not north-up (a={t.a!r}, e={t.e!r}; need a>0, e<0)")
    psp = meta.get("pixel_size_projected_m")
    if isinstance(psp, dict):
        if abs(t.a - float(psp["x"])) > AXIS_TOL or abs(-t.e - float(psp["y"])) > AXIS_TOL:
            die(
                f"raster pixel size ({t.a!r}, {-t.e!r}) disagrees with metadata "
                f"pixel_size_projected_m ({psp['x']!r}, {psp['y']!r})"
            )
    crs_tokens_meta = str(meta.get("crs", "")).split()
    crs_tokens_ras = (ds.crs.to_proj4() or "").split()
    absent = [tok for tok in crs_tokens_meta if tok not in crs_tokens_ras]
    if absent:
        die(f"raster CRS is missing metadata CRS tokens: {', '.join(absent)}")
    tags = ds.tags()
    missing_tags = [k for k in REQUIRED_TAGS if not str(tags.get(k, "")).strip()]
    if missing_tags:
        die(f"raster provenance tags missing: {', '.join(missing_tags)}")
    return ds, tags, t


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="deliberately replace an existing destination file",
    )
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.dest)}
    if len(resolves) < 3:
        die("--raster, --meta and --dest must be distinct paths")

    # --------------------------------------------- 1: destination safety
    validate_dest(args.dest, args.overwrite)

    # --------------------------------------------- 2: metadata contract
    meta = load_meta(args.meta)
    check_meta_contract(meta)

    # --------------------------------------------- 3: raster identity + geometry
    ds, tags, transform = open_and_validate_raster(args.raster, meta)
    width, height = ds.width, ds.height
    elements = width * height
    print(
        f"[ok] raster validated: {width}x{height} px, 1x float32, "
        f"north-up (a={transform.a!r}, e={transform.e!r}), crs present, "
        f"tags complete ({len(REQUIRED_TAGS)}/{len(REQUIRED_TAGS)})"
    )

    # --------------------------------------------- 4: provenance chain
    raster_sha = sha256_of(args.raster)
    if raster_sha != EXPECTED_RASTER_SHA256:
        die(f"raster SHA-256 mismatch: got {raster_sha}, expected pinned {EXPECTED_RASTER_SHA256}")
    prov = meta["provenance"]
    if raster_sha != prov["dem_sha256"]:
        die(f"raster SHA-256 {raster_sha} != metadata provenance dem_sha256 {prov['dem_sha256']}")
    meta_dem_path = (REPO_ROOT / str(prov["dem_file"])).resolve()
    if args.raster.resolve() != meta_dem_path:
        die(
            f"--raster {args.raster.as_posix()} is not the metadata provenance file "
            f"{str(prov['dem_file'])}"
        )
    tag_src_sha = str(tags.get("SOURCE_SHA256", "")).strip().lower()
    if tag_src_sha and tag_src_sha != str(prov["source_dem_sha256"]).strip().lower():
        die(
            "crop tag SOURCE_SHA256 disagrees with metadata provenance "
            f"source_dem_sha256 ({tag_src_sha} vs {prov['source_dem_sha256']})"
        )
    print(f"[ok] provenance chain: crop SHA matches pin + metadata; SOURCE_SHA256 tag consistent")

    # --------------------------------------------- 5: read + classify pixels
    src_nodata = ds.nodata  # the raster's OWN NoData record
    raw = ds.read(1)
    ds.close()
    if raw.shape != (height, width):
        die(f"read shape {raw.shape} != ({height}, {width})")
    if not raw.flags["C_CONTIGUOUS"]:
        die("rasterio read did not return a C-contiguous array; refusing to guess layout")

    meta_nodata_dem = float(meta["nodata_elev_dem"])
    if src_nodata is None:
        effective_nodata = meta_nodata_dem
        print("[ok] raster records no NoData; using metadata nodata_elev_dem")
    else:
        src_f = float(src_nodata)
        agrees = src_f == meta_nodata_dem or (
            math.isnan(src_f) and math.isnan(meta_nodata_dem)
        )
        if not agrees:
            die(
                f"raster NoData {src_f!r} != metadata nodata_elev_dem "
                f"{meta_nodata_dem!r}"
            )
        effective_nodata = src_f
        print(f"[ok] source NoData (raster record): {src_nodata!r} == metadata nodata_elev_dem")

    inf_mask = np.isinf(raw)
    inf_count = int(inf_mask.sum())
    if inf_count:
        idx = np.argwhere(inf_mask)[:5]
        samples = ", ".join(f"(row={r}, col={c}, value={raw[r, c]!r})" for r, c in idx)
        die(
            f"source contains {inf_count} +/-Infinity sample(s); approved policy is HARD FAIL. "
            f"First samples: {samples}. No output was written."
        )

    nan_mask = np.isnan(raw)
    if math.isnan(effective_nodata):
        nodata_mask = np.zeros(raw.shape, dtype=bool)
    else:
        nodata_mask = raw == np.float32(effective_nodata)
    invalid_mask = nodata_mask | nan_mask
    valid_mask = ~invalid_mask
    valid_count = int(valid_mask.sum())
    nodata_count = int(nodata_mask.sum())
    nan_count = int(nan_mask.sum())
    print(
        f"[ok] pixel classification: valid={valid_count}, nodata={nodata_count}, "
        f"nan={nan_count}, inf={inf_count} (total {elements})"
    )
    if valid_count == 0:
        die("source has no valid pixels; refusing to emit an all-sentinel elevation binary")

    # --------------------------------------------- 6: convert (approved pipeline)
    # Widen FIRST (exact), then multiply in Float64 (exact: 24+4 <= 53 bits),
    # then half-even rounding via numpy.rint.
    v64 = raw.astype(np.float64)
    prod = v64 * float(ELEV_SCALE)
    rint = np.rint(prod)

    vals = rint[valid_mask]
    vmin, vmax = float(vals.min()), float(vals.max())
    if vmin < INT16_MIN or vmax > INT16_MAX:
        die(
            "converted values exceed the Int16 range; refusing to clip, wrap or "
            f"truncate (valid range would be [{vmin!r}, {vmax!r}])"
        )
    print(f"[ok] Int16 range check (valid samples): [{vmin!r}, {vmax!r}] fits [{INT16_MIN}, {INT16_MAX}]")
    if int((vals == NODATA_ELEV).sum()):
        die("a valid sample converts to -32768, colliding with the NoData sentinel; aborting")
    print(f"[ok] sentinel collision check: no valid sample equals {NODATA_ELEV}")

    # --------------------------------------------- 7: assemble the Int16 grid
    rint[~valid_mask] = float(NODATA_ELEV)  # NaN/NoData -> sentinel BEFORE the cast
    stored = rint.astype(np.dtype(DTYPE_LE))
    if stored.dtype.str != DTYPE_LE or stored.dtype.itemsize != 2:
        die(f"cast produced dtype {stored.dtype.str!r}; expected {DTYPE_LE!r}")
    if not stored.flags["C_CONTIGUOUS"]:
        die("stored array is not C-contiguous; refusing to serialize an ambiguous layout")
    if int(stored[~valid_mask].min(initial=NODATA_ELEV)) != NODATA_ELEV or int(
        stored[~valid_mask].max(initial=NODATA_ELEV)
    ) != NODATA_ELEV:
        die("sentinel fill failed for invalid positions")
    stored_min, stored_max = int(stored[valid_mask].min()), int(stored[valid_mask].max())

    payload = stored.tobytes(order="C")
    expected_bytes = elements * 2
    if len(payload) != expected_bytes:
        die(f"payload is {len(payload)} bytes; expected {expected_bytes}")
    print(
        f"[ok] payload assembled: {elements} x Int16 LE, row-major (row 0 = north), "
        f"{len(payload)} bytes (expected {expected_bytes})"
    )

    # --------------------------------------------- 8: decode evidence (stdout)
    dec = stored[valid_mask].astype(np.float64) / float(ELEV_SCALE)
    decode_err = np.abs(dec - v64[valid_mask])
    max_decode_err = float(decode_err.max())
    quant_err_dm = np.abs(stored[valid_mask].astype(np.float64) - prod[valid_mask])
    max_quant_dm = float(quant_err_dm.max())
    ties = int(((prod[valid_mask] - np.floor(prod[valid_mask])) == 0.5).sum())
    fingerprint_dm = float((stored[valid_mask].astype(np.float64) - prod[valid_mask]).mean())
    src_min = float(raw[valid_mask].min())
    src_max = float(raw[valid_mask].max())
    print(
        "[ok] decode evidence: max quantization error "
        f"{max_quant_dm!r} dm = {max_quant_dm / 10.0!r} m (ties at 0.5 dm: {ties}); "
        f"max decode error {max_decode_err!r} m (bound 0.05 + 1e-9); "
        f"half-even fingerprint {fingerprint_dm!r} dm (nearest ~= 0)"
    )

    # --------------------------------------------- 9: atomic promotion
    partial = args.dest.with_name(args.dest.name + ".part")
    try:
        with partial.open("wb") as fh:
            fh.write(payload)
    except OSError as exc:
        print(f"[error] writing the partial binary failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] partial written: {partial} ({len(payload)} bytes)")
    try:
        os.replace(partial, args.dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial binary failed: {exc}", file=sys.stderr)
        return 1
    try:
        with args.dest.open("rb") as fh:
            back = fh.read()
    except OSError as exc:
        print(f"[error] re-reading the promoted binary failed: {exc}", file=sys.stderr)
        return 1
    if back != payload:
        die("promoted file content differs from the serialized payload (paranoia check)")
    dest_sha = sha256_of(args.dest)
    print(f"[ok] promoted: {args.dest.as_posix()} ({len(payload)} bytes), sha256={dest_sha}")

    # --------------------------------------------- 10: summary
    print(
        f"[summary] raster={args.raster.as_posix()} sha256={raster_sha}, "
        f"dims={width}x{height}, elements={elements}, bytes={len(payload)}, "
        f"valid={valid_count} nodata={nodata_count} nan={nan_count} inf={inf_count}, "
        f"src_range=[{src_min!r}, {src_max!r}] m, stored_range=[{stored_min}, {stored_max}] dm, "
        f"max_decode_err={max_decode_err!r} m, dest={args.dest.as_posix()}, "
        f"dest_sha256={dest_sha}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
