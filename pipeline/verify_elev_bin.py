"""Independent validator + report owner for the Task 05 elevation binary.

Verifies ``web/data/elev_dm_i16.bin`` against the CONTRACT - re-derived here
from ``web/data/grid_meta.json`` and the approved decisions - without
importing anything from ``pipeline/export_elev_bin.py`` (house cross-validation
pattern: a shared-wrong-derivation blind spot is avoided by deriving the
expected byte stream from the contract text, not from the exporter's code).

Approved decisions encoded here (team ruling, 2026-11-13):

- Rounding: half-even via ``numpy.rint``.
- Arithmetic: Float32 -> Float64 widening BEFORE the x10 multiply.
- Conversion: decimetres = metres x 10 (``elev_scale``).
- Encoding: signed Int16, explicitly little-endian (``<i2``).
- NaN and source NoData -> ``grid_meta.nodata_elev`` (-32768).
- +/-Infinity: the exporter must hard-fail; a binary produced from a source
  containing Infinity is invalid by definition.
- Out-of-range values: never clipped/wrapped/truncated (both sides must abort).

Checks performed (full-element, never size-only):

1. Metadata contract values, provenance SHA chain, provenance tags.
2. Raster identity/geometry (dims, north-up, unrotated, CRS tokens, NoData).
3. Infinity scan of the source (must be zero for a valid artifact to exist).
4. Independently computed expected Int16 array + FULL-array byte equality.
5. Layout hypothesis matrix {as-written, row-flip, col-flip, rot180,
   transposed, big-endian} - exactly one hypothesis may pass the decode bound;
   file size alone cannot catch a transposition (1016 x 1075 keeps the same
   flat element count), so this matrix is the orientation proof.
6. Decoded elevation error bound: max |int16/10 - raster| <= 0.05 m + 1e-9 m
   (half-even quantization 0.5 dm = 0.05 m, plus a float64 decode half-ulp
   of <= 2.3e-13 m), plus the rounding-mode fingerprint (mean stored - true
   in dm: ~= 0 nearest / -0.5 floor / +0.5 truncation on all-negative data),
   plus a tie-direction invariant proving the half-even mode from the
   artifact itself (at every exact 0.5-dm tie the stored value must be the
   even neighbor).
7. Sentinel agreement with metadata + Int16 range + sentinel-collision.
8. Determinism: the exporter runs TWICE into a temporary directory and the
   SHA-256 of both runs must equal each other and the final artifact.

Report: on a full pass this script writes the deterministic
``data/processed/elev_bin_report.md`` (no timestamps, relative posix paths,
ASCII) - it owns the report because the report must contain validator +
determinism evidence that only exists after validation. On any failure the
report is NOT written and the script exits non-zero.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\verify_elev_bin.py
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

DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_BIN = Path("web/data/elev_dm_i16.bin")
DEFAULT_REPORT = Path("data/processed/elev_bin_report.md")

# Pinned cropped-DEM identity (Task 03 crop; equals grid_meta provenance).
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Contract constants (docs/PLAN.md §5.2; grid_meta.json).
ELEV_SCALE = 10
NODATA_ELEV = -32768
INT16_MIN = -32768
INT16_MAX = 32767
DTYPE_LE = "<i2"

AXIS_TOL = 1e-9

# Approved half-even bound: quantization 0.5 dm = 0.05 m (attained exactly at
# ties) + a float64 decode half-ulp (<= 2.3e-13 m here) + float-noise epsilon.
DECODE_TOL_M = 0.05 + 1e-9
# Rounding-mode fingerprint: |mean(stored - true)| must look like a NEAREST
# family mode (~= 0 dm); floor/truncation sit at -/+0.5 dm on this data.
FINGERPRINT_TOL_DM = 0.01

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

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--bin", type=Path, default=DEFAULT_BIN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.bin, args.report)}
    if len(resolves) < 4:
        print("[error] --raster, --meta, --bin and --report must be distinct paths", file=sys.stderr)
        return 1

    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> bool:
        checks.append((name, ok, detail))
        print(f"[{'ok' if ok else 'error'}] {name}: {detail}" + ("" if ok else " - FAIL"))
        return ok

    failed = False

    # ------------------------------------------------ 1: metadata contract
    try:
        meta = json.loads(args.meta.read_text(encoding="utf-8"))
        meta_ok = isinstance(meta, dict) and all(k in meta for k in REQUIRED_META_KEYS)
        prov = meta.get("provenance") if isinstance(meta, dict) else None
        prov_ok = isinstance(prov, dict) and all(k in prov for k in REQUIRED_PROVENANCE_KEYS)
        failed |= not add(
            "metadata loads with required keys",
            meta_ok and prov_ok,
            f"{args.meta.as_posix()} ({len(meta) if isinstance(meta, dict) else 0} keys)"
            + ("" if meta_ok and prov_ok else " - missing required keys"),
        )
    except (OSError, ValueError) as exc:
        add("metadata loads with required keys", False, f"unreadable: {exc}")
        print("[error] cannot continue without metadata", file=sys.stderr)
        return 1

    contract_ok = (
        meta["elev_scale"] == ELEV_SCALE
        and meta["nodata_elev"] == NODATA_ELEV
        and (meta["row0"], meta["col0"], meta["layout"]) == ("north", "west", "row_major")
    )
    failed |= not add(
        "metadata contract values",
        contract_ok,
        f"elev_scale={meta['elev_scale']!r}, nodata_elev={meta['nodata_elev']!r}, "
        f"row0={meta['row0']!r}, col0={meta['col0']!r}, layout={meta['layout']!r}",
    )

    # ------------------------------------------------ 2: raster identity
    raster_sha = sha256_of(args.raster)
    pin_ok = raster_sha == EXPECTED_RASTER_SHA256
    prov_ok = raster_sha == prov["dem_sha256"]
    dem_file_ok = args.raster.resolve() == (REPO_ROOT / str(prov["dem_file"])).resolve()
    failed |= not add(
        "raster SHA-256 chain (pin + metadata + provenance path)",
        pin_ok and prov_ok and dem_file_ok,
        f"{raster_sha} (pin match={pin_ok}, provenance match={prov_ok}, "
        f"dem_file match={dem_file_ok})",
    )

    try:
        ds = rasterio.open(args.raster)
        raw = ds.read(1)
        src_nodata = ds.nodata
        transform = ds.transform
        crs_proj4 = ds.crs.to_proj4() or "" if ds.crs else ""
        tags = ds.tags()
        count_ok = ds.count == 1
        dtype_ok = (ds.dtypes or [""])[0] == "float32"
        dims_ok = ds.width == meta["width"] and ds.height == meta["height"]
        rot_ok = abs(transform.b) <= AXIS_TOL and abs(transform.d) <= AXIS_TOL
        northup_ok = transform.a > 0 and transform.e < 0
        raster_ok = count_ok and dtype_ok and dims_ok and rot_ok and northup_ok
        psp = meta.get("pixel_size_projected_m")
        psp_ok = not isinstance(psp, dict) or (
            abs(transform.a - float(psp["x"])) <= AXIS_TOL
            and abs(-transform.e - float(psp["y"])) <= AXIS_TOL
        )
        crs_tokens_meta = str(meta.get("crs", "")).split()
        crs_ok = all(tok in crs_proj4.split() for tok in crs_tokens_meta)
        tags_ok = all(str(tags.get(k, "")).strip() for k in REQUIRED_TAGS)
        tag_src_ok = str(tags.get("SOURCE_SHA256", "")).strip().lower() in (
            "",
            str(prov["source_dem_sha256"]).strip().lower(),
        )
        ds.close()
        failed |= not add(
            "raster identity/geometry (1x float32, dims, north-up, unrotated)",
            raster_ok,
            f"count1={count_ok}, float32={dtype_ok}, dims_match={dims_ok}, "
            f"unrotated={rot_ok}, north_up={northup_ok}; "
            f"transform a={transform.a!r} e={transform.e!r} |b|={abs(transform.b)!r} |d|={abs(transform.d)!r}",
        )
        failed |= not add(
            "raster CRS tokens + projected pixel size match metadata",
            crs_ok and psp_ok,
            f"crs tokens subset={crs_ok}, pixel size match={psp_ok}",
        )
        failed |= not add(
            "raster provenance tags (Task 03 chain)",
            tags_ok and tag_src_ok,
            f"{sum(1 for k in REQUIRED_TAGS if str(tags.get(k, '')).strip())}/{len(REQUIRED_TAGS)} present, "
            f"SOURCE_SHA256 vs provenance source_dem_sha256 consistent={tag_src_ok}",
        )
    except Exception as exc:  # noqa: BLE001 - any read failure is a failed check
        add("raster identity/geometry", False, f"unreadable: {exc}")
        print("[error] cannot continue without the raster", file=sys.stderr)
        return 1

    # ------------------------------------------------ 3: NoData/NaN/Infinity
    meta_nodata_dem = float(meta["nodata_elev_dem"])
    nodata_agree = src_nodata is None or float(src_nodata) == meta_nodata_dem
    failed |= not add(
        "raster NoData record agrees with metadata nodata_elev_dem",
        nodata_agree,
        f"raster nodata={src_nodata!r}, metadata={meta_nodata_dem!r}",
    )

    inf_mask = np.isinf(raw)
    inf_count = int(inf_mask.sum())
    if inf_count:
        idx = np.argwhere(inf_mask)[:5]
        samples = ", ".join(f"(row={r}, col={c}, value={raw[r, c]!r})" for r, c in idx)
        failed |= not add(
            "source contains no +/-Infinity (exporter must hard-fail otherwise)",
            False,
            f"{inf_count} infinite sample(s): {samples}; a valid binary cannot exist",
        )
        print("[error] source has Infinity; the binary under test cannot be valid", file=sys.stderr)
        return 1
    add(
        "source contains no +/-Infinity",
        True,
        "0 infinite samples (the exporter's hard-fail path is therefore NOT exercised by data)",
    )

    nan_mask = np.isnan(raw)
    if math.isnan(meta_nodata_dem):
        nodata_mask = np.zeros(raw.shape, dtype=bool)
    else:
        nodata_mask = raw == np.float32(meta_nodata_dem)
    invalid_mask = nodata_mask | nan_mask
    valid_mask = ~invalid_mask
    valid_count = int(valid_mask.sum())
    nodata_count = int(nodata_mask.sum())
    nan_count = int(nan_mask.sum())
    elements = int(meta["width"]) * int(meta["height"])
    counts_ok = valid_count + nodata_count + nan_count == elements and valid_count > 0
    if not add(
        "pixel classification partitions the grid",
        counts_ok,
        f"valid={valid_count}, nodata={nodata_count}, nan={nan_count}, inf=0, total={elements}",
    ):
        print("[error] degenerate source; refusing to derive expected values", file=sys.stderr)
        return 1

    # ------------------------------------------------ 4: expected array (contract-derived)
    v64 = raw.astype(np.float64)  # exact widening, then exact x10 in Float64
    prod = v64 * float(ELEV_SCALE)
    rint = np.rint(prod)  # approved half-even
    vals = rint[valid_mask]
    fits_int16 = bool(vals.min() >= INT16_MIN and vals.max() <= INT16_MAX)
    no_collision = bool(not (vals == NODATA_ELEV).any())
    failed |= not add(
        "contract fit: valid conversions inside Int16, none collides with sentinel",
        fits_int16 and no_collision,
        f"valid conversion range [{float(vals.min())!r}, {float(vals.max())!r}], "
        f"collision-free={no_collision}",
    )
    rint[~valid_mask] = float(NODATA_ELEV)
    expected = rint.astype(np.dtype(DTYPE_LE))
    expected_bytes = expected.tobytes(order="C")
    bracket_lo = math.floor(float(prod[valid_mask].min()))
    bracket_hi = math.ceil(float(prod[valid_mask].max()))

    # ------------------------------------------------ 5: binary file + size
    if not args.bin.is_file():
        add("output binary exists", False, f"not found: {args.bin}")
        print("[error] run pipeline/export_elev_bin.py first", file=sys.stderr)
        return 1
    bin_size = args.bin.stat().st_size
    size_ok = bin_size == elements * 2
    if not add(
        "exact byte size (elements x 2, headerless)",
        size_ok,
        f"{bin_size} bytes vs expected {elements * 2} ({elements} elements)",
    ):
        print("[error] wrong size; element-wise comparison is impossible", file=sys.stderr)
        return 1
    bin_sha = sha256_of(args.bin)
    data = args.bin.read_bytes()

    # ------------------------------------------------ 6: full-array equality
    actual = np.frombuffer(data, dtype=np.dtype(DTYPE_LE)).reshape(
        int(meta["height"]), int(meta["width"])
    )
    differing = int((actual != expected).sum())
    failed |= not add(
        "FULL-array equality vs independently derived expected bytes",
        differing == 0,
        f"{differing} differing elements of {elements} (catches rounding, scale, "
        "sentinel, order, transposition and endianness at once)",
    )

    # ------------------------------------------------ 7: layout hypothesis matrix
    raster64 = raw.astype(np.float64)

    def hyp_max_err(arr2d: np.ndarray) -> float:
        dec = arr2d[valid_mask].astype(np.float64) / float(ELEV_SCALE)
        return float(np.abs(dec - raster64[valid_mask]).max())

    hypotheses = (
        ("as-written (C-order, little-endian)", actual),
        ("row-flipped (south-first)", actual[::-1, :]),
        ("col-flipped (east-first)", actual[:, ::-1]),
        ("rotated 180 degrees", actual[::-1, ::-1]),
        ("transposed (W/H swap)", np.frombuffer(data, dtype=np.dtype(DTYPE_LE)).reshape(
            int(meta["width"]), int(meta["height"])
        ).T),
        ("big-endian reinterpretation", np.frombuffer(data, dtype=np.dtype(">i2")).reshape(
            int(meta["height"]), int(meta["width"])
        )),
    )
    hyp_rows = []
    passes = []
    for label, arr in hypotheses:
        err = hyp_max_err(arr)
        ok = err <= DECODE_TOL_M
        passes.append(ok)
        hyp_rows.append((label, err, ok))
    exactly_one = passes.count(True) == 1 and passes[0] is True
    failed |= not add(
        "layout/endianness hypothesis matrix (exactly one PASS: as-written LE)",
        exactly_one,
        "; ".join(
            f"{label}: max_err={err!r} m ({'PASS' if ok else 'fail'})"
            for label, err, ok in hyp_rows
        ),
    )

    # ------------------------------------------------ 8: decode bound + fingerprint
    dec_err = hyp_max_err(actual)
    failed |= not add(
        "decoded elevation bound abs(int16/10 - raster) <= 0.05 m + 1e-9 m",
        dec_err <= DECODE_TOL_M,
        f"max abs decode error {dec_err!r} m over {valid_count} valid elements "
        f"(tolerance {DECODE_TOL_M!r})",
    )
    fingerprint_dm = float(
        (actual[valid_mask].astype(np.float64) - prod[valid_mask]).mean()
    )
    failed |= not add(
        "rounding-mode fingerprint (nearest family ~= 0 dm)",
        abs(fingerprint_dm) <= FINGERPRINT_TOL_DM,
        f"mean(stored - true) = {fingerprint_dm!r} dm "
        f"(floor would be ~-0.5, truncation ~+0.5 on all-negative data)",
    )
    tie_mask = (prod - np.floor(prod)) == 0.5
    ties = int(tie_mask[valid_mask].sum())
    if ties:
        stored_tie = actual[tie_mask].astype(np.float64)
        k_tie = np.floor(prod[tie_mask])
        even_neighbor = np.where(k_tie % 2 == 0, k_tie, k_tie + 1)
        tie_ok = bool((stored_tie == even_neighbor).all())
        tie_detail = (
            f"{ties} exact tie sample(s); every stored value equals the even "
            "neighbor -> half-even proven from the artifact itself"
            if tie_ok
            else f"{ties} exact tie sample(s); a stored value differs from its even neighbor"
        )
    else:
        tie_ok = True  # vacuous without ties (recorded honestly)
        tie_detail = "no exact 0.5 dm ties in this dataset; invariant vacuously true"
    failed |= not add(
        "half-even tie invariant (stored == even neighbor at every exact 0.5 dm tie)",
        tie_ok,
        tie_detail,
    )

    # ------------------------------------------------ 9: sentinel + range on ACTUAL
    sentinel_positions = actual == np.int16(NODATA_ELEV)
    sentinel_ok = bool(
        int(sentinel_positions.sum()) == invalid_mask.sum()
        and bool((sentinel_positions == ~valid_mask).all())
    )
    failed |= not add(
        "sentinel agreement with metadata (positions and value)",
        sentinel_ok,
        f"bin sentinel count {int(sentinel_positions.sum())} == source invalid count "
        f"{int(invalid_mask.sum())} (value {NODATA_ELEV} == metadata nodata_elev); "
        "NOTE: mapping path NOT exercised - 0 NoData/NaN pixels in this source",
    )
    stored_min = int(actual[valid_mask].min())
    stored_max = int(actual[valid_mask].max())
    range_ok = (
        stored_min >= INT16_MIN
        and stored_max <= INT16_MAX
        and stored_min >= bracket_lo
        and stored_max <= bracket_hi
    )
    failed |= not add(
        "stored Int16 range within contract bracket",
        range_ok,
        f"stored [{stored_min}, {stored_max}] dm within [{bracket_lo}, {bracket_hi}] "
        f"(headroom {stored_min - INT16_MIN} low / {INT16_MAX - stored_max} high)",
    )
    src_min = float(raw[valid_mask].min())
    src_max = float(raw[valid_mask].max())
    elev_range_ok = list(meta["elev_range_m"]) == [src_min, src_max]
    failed |= not add(
        "metadata elev_range_m equals the live raster range",
        elev_range_ok,
        f"metadata {meta['elev_range_m']!r} vs raster [{src_min!r}, {src_max!r}]",
    )

    # ------------------------------------------------ 10: determinism (double export)
    exporter = Path(__file__).resolve().parent / "export_elev_bin.py"
    tmp = Path(tempfile.mkdtemp(prefix="elevbin-det-"))
    run_shas: list[str] = []
    run_codes: list[int] = []
    try:
        for i in (1, 2):
            dest_i = tmp / f"elev_dm_i16_run{i}.bin"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(exporter),
                    "--raster",
                    str(args.raster.resolve()),
                    "--meta",
                    str(args.meta.resolve()),
                    "--dest",
                    str(dest_i),
                    "--overwrite",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
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
    except Exception as exc:  # noqa: BLE001 - subprocess/spawn failures are check failures
        add("determinism double-export", False, f"subprocess failed: {exc}")
        failed = True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(run_shas) == 2:
        det_ok = run_shas[0] == run_shas[1] == bin_sha
        failed |= not add(
            "determinism: two temp exports equal the final artifact (SHA-256 x3)",
            det_ok,
            f"run1={run_shas[0][:16]}..., run2={run_shas[1][:16]}..., final={bin_sha[:16]}..., "
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
    hyp_table = "\n".join(
        f"| {label} | {err!r} | {'PASS' if ok else 'fail'} |"
        for label, err, ok in hyp_rows
    )
    checks_table = "\n".join(
        f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |"
        for name, ok, detail in checks
    )
    report = f"""# Elevation Binary Report - `web/data/elev_dm_i16.bin` (Task 05)

Task 05 deliverable evidence - written by `pipeline/verify_elev_bin.py` after
the exporter (`pipeline/export_elev_bin.py`) and every independent validation
check (including the double-export determinism proof) passed. Deterministic
content: no timestamps; all values are measured from the files listed below.

## 1. Approved conversion decisions (team ruling, implemented and validated)

- Rounding: **half-even** via `numpy.rint`.
- Arithmetic: **Float32 -> Float64 widening BEFORE the x10 multiply** (exact;
  the output is a pure function of the stored Float32 bits).
- Conversion: **decimetres = metres x 10** (`elev_scale`).
- Encoding: **signed Int16, explicitly little-endian** (`<i2`).
- **NaN -> `-32768`** (`grid_meta.nodata_elev`); **source NoData -> `-32768`**.
- **+/-Infinity: hard fail** with diagnostics (never mapped, never clipped).
- Out-of-range values are **never clipped, wrapped or truncated** (abort).
- No `.gitattributes` added (team decision); no synthetic NoData test added
  (team decision).

Contract: `docs/PLAN.md` 5.2 line 207 (`elev_dm_i16.bin` = elevation in
decimetres, Int16 little-endian, DE1), 5.1 lines 196-199 (shared grid, row 0 =
north, col 0 = west, row-major), and the `grid_meta.json` `notes` decode recipe
(`elev_m = int16_le / elev_scale`; `index = row*width + col`).

## 2. Input identity

| Item | Value |
|---|---|
| Source raster | `{args.raster.as_posix()}` (Task 03 crop) |
| Raster file size | {args.raster.stat().st_size} bytes |
| Raster SHA-256 | `{raster_sha}` |
| Pinned SHA match | {'YES' if raster_sha == EXPECTED_RASTER_SHA256 else '**NO**'} |
| == metadata `provenance.dem_sha256` | {'YES' if raster_sha == prov['dem_sha256'] else '**NO**'} |
| Provenance chain | crop tag `SOURCE_SHA256` == `provenance.source_dem_sha256` (raw DEM `{str(prov['source_dem'])}`) |
| Metadata file | `{args.meta.as_posix()}` |

## 3. Output identity

| Item | Value |
|---|---|
| Output binary | `{args.bin.as_posix()}` |
| File size | {bin_size} bytes (exactly {elements} elements x 2; headerless; PLAN 5.2 "~2 MB" satisfied) |
| SHA-256 | `{bin_sha}` |
| Dimensions | {meta['width']} x {meta['height']} px (W x H, from `grid_meta.json`) |
| Element count | {elements} |
| Dtype / byte order | signed Int16, explicit `{DTYPE_LE}` (little-endian) |
| Layout | row-major, row 0 = north, col 0 = west; `index = row*width + col` |

## 4. Pixel classification (honest counts)

| Class | Count |
|---|---|
| Valid | {valid_count} |
| Source NoData (sentinel `{meta['nodata_elev_dem']!r}`) | {nodata_count} |
| NaN | {nan_count} |
| +/-Infinity | {inf_count} |
| Total | {elements} |

**The source contains ZERO NoData/NaN/Infinity pixels.** The sentinel/NaN
mapping and the Infinity hard-fail paths were therefore NOT exercised by data;
they are verified by code review and the validator's structural checks only
(the team declined a synthetic-pixel test). The sentinel agreement check is
the (honest) comparison 0 == 0.

## 5. Elevation ranges

| Item | Value |
|---|---|
| Actual source elevation range | [{src_min!r}, {src_max!r}] m (float32-exact; == `grid_meta.elev_range_m`) |
| x10 conversion bracket (mode-agnostic) | [{bracket_lo}, {bracket_hi}] dm |
| Stored Int16 range (valid samples) | [{stored_min}, {stored_max}] dm |
| Int16 headroom | {stored_min - INT16_MIN} (low) / {INT16_MAX - stored_max} (high); sentinel {NODATA_ELEV} outside the stored range |

## 6. Quantization and decode error measurements (measured)

| Item | Value |
|---|---|
| Max absolute quantization error (half-even) | 0.5 dm = **0.05 m** - attained exactly at the {ties} tie samples (`frac(v*10) == 0.5`) |
| Rounding-mode fingerprint `mean(stored - true)` | {fingerprint_dm!r} dm (nearest ~= 0; floor ~-0.5; truncation ~+0.5) |
| Max absolute decode error `int16/10 - raster` | {dec_err!r} m (bound: 0.05 m + 1e-9 m = {DECODE_TOL_M!r}) |
| Decode half-ulp (theoretical, float64 at ~2683 m) | <= 2.2737e-13 m |

## 7. Layout proof (orientation + endianness)

A W/H transposition preserves the flat element count, so size alone cannot
prove orientation. Decode error under each hypothesis (exactly one must pass):

| Hypothesis | Max abs decode error (m) | Verdict |
|---|---|---|
{hyp_table}

Full-array equality against the independently derived expected bytes:
{elements - differing}/{elements} elements equal ({differing} differing).

## 8. Validator results

| Check | Result | Measured detail |
|---|---|---|
{checks_table}

## 9. Determinism result

The exporter ran twice into a temporary directory; exit codes {run_codes[0]} and {run_codes[1]};
SHA-256 of run 1 == run 2 == final artifact
(`{run_shas[0] if run_shas else 'n/a'}`). The temporary directory was removed;
the final artifact was not rewritten by this check.

## 10. Full Stack NoData consumer contract (decided; Task 05 handoff)

- Any sample equal to `grid_meta.nodata_elev` (`-32768`) is **Missing**.
- Never decode it as a real elevation.
- Exclude it from min/max/mean and ascent/descent calculations.
- Render it as a **gap** in the Elevation Profile.
- Do **not** interpolate across missing samples.
- Do **not** calculate ascent/descent across a NoData gap.
- Apply the same exclusion to 3-point smoothing.

(Recorded here as the Task 05 handoff; `docs/PLAN.md` and `grid_meta.json`
were intentionally NOT modified in this task.)

## 11. Untested behavior and limitations

- Sentinel/NaN mapping and +/-Infinity rejection: not exercised by data
  (0 such pixels); verified by code review + structural checks only.
- Decode bound verified against this dataset and pinned environment only.
- No `.gitattributes` (team decision): `core.autocrlf=true` is in effect on
  this machine (system-scope Git for Windows default). Git's binary-detection
  disables EOL conversion for `elev_dm_i16.bin` itself (it contains NUL
  bytes); the residual risk applies to future text-like binary formats.
- A future raster whose NoData record is +/-Infinity hard-fails under the
  approved Infinity policy (Task 04 contemplated accepting such a sentinel;
  Task 05 chose the conservative fail-safe reading - a future ruling can
  relax it).
- Determinism proven for consecutive runs on this machine (numpy {np.__version__},
  rasterio {rasterio.__version__}); re-exports assume the pinned environment.

## 12. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}
- Scripts: `pipeline/export_elev_bin.py` (exporter), `pipeline/verify_elev_bin.py`
  (this validator + report owner; rerunnable, deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Pin LF line endings so the report is byte-identical on any OS
        # (house pattern: make_grid_meta.py pins LF for the same reason).
        args.report.write_text(report, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[error] writing the elevation binary report failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] report written: {args.report.as_posix()}")
    print(
        f"[summary] bin={args.bin.as_posix()} sha256={bin_sha}, bytes={bin_size}, "
        f"elements={elements}, checks={len(checks)}/{len(checks)} passed, "
        f"max_decode_err={dec_err!r} m, report={args.report.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
