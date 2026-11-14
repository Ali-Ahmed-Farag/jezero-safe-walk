"""Independent validator + report owner for the Task 06 CTX basemap.

Verifies ``web/data/ctx_basemap.jpg`` against the CONTRACT - re-derived here
from ``web/data/grid_meta.json``, the Task 03 DEM geometry, the pinned source
identity and the approved Task 06 decisions - without importing anything from
``pipeline/export_ctx_basemap.py`` (house cross-validation pattern: a
shared-wrong-derivation blind spot is avoided by deriving the expected image
from the contract text, not from the exporter's code).

Approved decisions encoded here (Task 06 rulings + preflight audit,
2026-11-13/14):

- Source: S2 ``JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif`` only.
- Target geometry: EXACTLY the existing DEM grid (1016 x 1075 @ 20 m,
  equirectangular lat_ts=18.4663, R=3396190); never recreated.
- Proper geospatial warp (source lat_ts=0 vs target lat_ts=18.4663), never a
  plain resize; outward source-window pixel snapping with a coverage proof.
- Resampling: Average.
- NoData: the source declares DN=0; the approved census state is ZERO DN=0
  pixels (measured 2026-11-13 over the whole mosaic); a warp gap count > 0
  is a hard failure (no fabrication, no interpolation).
- Contrast: conservative percentile linear stretch from the measured
  histogram (p0.5 / p99.5), half-even rounding.
- JPEG: RGB (grayscale replicated), quality 85, size <= 5 MB.

Checks performed (full-element, never size-only):

1. Metadata contract, DEM identity/provenance chain.
2. Source identity (SHA pin + provenance sidecar consistency + product fields).
3. Source header vs the pinned preflight contract.
4. Output file: exists, <= 5 MB, decodes via rasterio (1016 x 1075, 3x uint8)
   AND via Pillow (independent JPEG decoder), three bands identical.
5. FULL-image comparison against an independently derived expected image
   (independent window derivation, warp and stretch): max/mean/p99 abs
   difference, PSNR, 3x3-blur structural agreement and Pearson correlation
   against tolerances justified by an independent-encoder q85 measurement.
6. Coverage: the independent warp produces zero gap pixels; pure-black /
   pure-white counts measured on the output.
7. Determinism: the exporter runs TWICE into a temporary directory and the
   SHA-256 of both runs must equal each other and the final artifact.
8. Documentation: the ``docs/sources.md`` Task 06 row exists with DOI, Mars
   Trek WMTS equivalent, attribution and the source SHA-256.

Report: on a full pass this script writes the deterministic
``data/processed/ctx_basemap_report.md`` (no timestamps, relative posix
paths, ASCII, LF-only). On any failure the report is NOT written and the
script exits non-zero.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\verify_ctx_basemap.py
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
from rasterio.crs import CRS
from rasterio.warp import Resampling, reproject, transform as rtransform

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a pinned requirement
    Image = None

DEFAULT_SOURCE = Path("data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif")
DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/ctx_basemap.jpg")
DEFAULT_REPORT = Path("data/processed/ctx_basemap_report.md")
DEFAULT_SOURCES_DOC = Path("docs/sources.md")

# Pinned identities (house pattern: duplicated in export_ctx_basemap.py and
# in the provenance sidecar - update all together).
EXPECTED_SOURCE_SHA256 = "842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615"
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"
EXPECTED_SOURCE_SIZE = 36_269_402

# Pinned source contract (preflight audit + ISIS label).
EXPECTED_SRC_WIDTH, EXPECTED_SRC_HEIGHT = 5322, 5040
EXPECTED_SRC_TRANSFORM = (6.0, 0.0, 4573663.250853, 0.0, -6.0, 1109693.140188)
EXPECTED_SRC_NODATA = 0.0
EXPECTED_SRC_CRS_TOKENS = ("+proj=eqc", "+lat_ts=0", "+lon_0=0", "+R=3396190", "+units=m")
TRANSFORM_TOL = 1e-6

JPEG_QUALITY = 85
MAX_BYTES = 5 * 1024 * 1024
STRETCH_LO_PCT = 0.5
STRETCH_HI_PCT = 99.5
AXIS_TOL = 1e-9
GAP_SENTINEL = -9999.0

# JPEG q85 is LOSSY and content-determined. Independent-encoder reference
# (Pillow q85 encoding of the same expected image, measured 2026-11-14):
# mean|diff| 3.05, p99 11, max 25, PSNR 36.11 dB, blur3x3-mean 0.56 DN for
# THIS content (~1.9 bits/px of high-frequency Mars terrain at 1016x1075).
# Tolerances below are ~1.6x those measured baselines (structural blur bound
# ~2.7x); every measured value is reported alongside its bound.
TOL_MAX_DIFF = 40
TOL_MEAN_DIFF = 5.0
TOL_P99_DIFF = 18.0
TOL_PSNR = 34.0
TOL_BLUR_MEAN_DIFF = 1.5
TOL_CORRELATION = 0.99

REQUIRED_META_KEYS = ("width", "height", "crs", "provenance")
REQUIRED_SIDECAR_KEYS = ("url", "file_size", "sha256", "doi", "attribution", "mars_trek_wmts_equivalent")

SOURCE_DOC_FRAGMENTS = (
    "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif",
    "10.5066/P9GV1ND3",
    "trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0",
    "842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615",
    "NASA/JPL-Caltech/MSSS",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def derive_window(target_ds, s2crs: CRS, src_transform):
    """Independently re-derived outward-snapped window (same contract math)."""
    t = src_transform
    px, py = t.a, -t.e
    db = target_ds.bounds
    gx, gy = rtransform(
        target_ds.crs, s2crs,
        [db.left, db.right, db.right, db.left],
        [db.bottom, db.bottom, db.top, db.top],
    )
    col_lo = math.floor((min(gx) - t.c) / px)
    col_hi = math.ceil((max(gx) - t.c) / px)
    row_lo = math.floor((t.f - max(gy)) / py)
    row_hi = math.ceil((t.f - min(gy)) / py)
    wx = [t.c + col_lo * px, t.c + col_hi * px]
    wy = [t.f - row_lo * py, t.f - row_hi * py]
    bx, by = rtransform(s2crs, target_ds.crs, [wx[0], wx[1], wx[1], wx[0]], [wy[1], wy[1], wy[0], wy[0]])
    covers = (
        min(bx) <= db.left + 1e-6 and max(bx) >= db.right - 1e-6
        and min(by) <= db.bottom + 1e-6 and max(by) >= db.top - 1e-6
    )
    return col_lo, row_lo, col_hi, row_hi, covers


def derive_expected_image(target_ds, source_path: Path):
    """Independently derive the expected uint8 RGB image from the contract."""
    with rasterio.open(source_path) as src:
        s2crs = CRS.from_proj4(src.crs.to_proj4())
        t = src.transform
        px, py = t.a, -t.e
        col_lo, row_lo, col_hi, row_hi, covers = derive_window(target_ds, s2crs, t)
        if not covers:
            raise RuntimeError("independent window derivation failed the coverage proof")
        win = rasterio.windows.Window(col_lo, row_lo, col_hi - col_lo, row_hi - row_lo)
        window = src.read(1, window=win)
    zeros = int((window == 0).sum())
    hist = np.bincount(window.ravel(), minlength=256)
    cdf = np.cumsum(hist) / window.size * 100.0
    lo = int(np.searchsorted(cdf, STRETCH_LO_PCT, side="left"))
    hi = int(np.searchsorted(cdf, STRETCH_HI_PCT, side="left"))
    src_transform = rasterio.transform.from_origin(
        t.c + col_lo * px, t.f - row_lo * py, px, py
    )
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
    scale = 255.0 / float(hi - lo)
    gray = np.clip(np.rint((dst.astype(np.float64) - float(lo)) * scale), 0, 255).astype(np.uint8)
    expected = np.stack([gray, gray, gray], axis=-1)
    return {
        "window": (col_lo, row_lo, col_hi, row_hi),
        "window_shape": window.shape,
        "zeros": zeros,
        "lo": lo, "hi": hi,
        "gaps": gaps,
        "expected": expected,
        "hist": hist,
        "cdf": cdf,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--sources-doc", type=Path, default=DEFAULT_SOURCES_DOC)
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.source, args.raster, args.meta, args.dest, args.report)}
    if len(resolves) < 5:
        print("[error] --source, --raster, --meta, --dest and --report must be distinct paths", file=sys.stderr)
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
        "target DEM SHA-256 chain (pin + metadata + provenance path)",
        pin_ok and prov_ok and dem_file_ok,
        f"{raster_sha} (pin match={pin_ok}, provenance match={prov_ok}, path match={dem_file_ok})",
    )

    # ------------------------------------------------ 2: source identity + sidecar
    src_sha = sha256_of(args.source)
    src_sha_ok = src_sha == EXPECTED_SOURCE_SHA256
    sidecar_path = args.source.with_name(args.source.name + ".provenance.json")
    sidecar_ok = sidecar_path.is_file()
    sidecar: dict = {}
    if sidecar_ok:
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sidecar_ok = False
    sidecar_keys_ok = sidecar_ok and all(
        str(sidecar.get(k, "")).strip() for k in REQUIRED_SIDECAR_KEYS
    )
    sidecar_sha_ok = sidecar_ok and str(sidecar.get("sha256", "")).strip().lower() == src_sha
    sidecar_size_ok = sidecar_ok and int(sidecar.get("file_size", -1)) == EXPECTED_SOURCE_SIZE
    failed |= not add(
        "source SHA-256 pin",
        src_sha_ok,
        f"{src_sha} (pin match={src_sha_ok})",
    )
    failed |= not add(
        "source provenance sidecar complete and consistent",
        sidecar_keys_ok and sidecar_sha_ok and sidecar_size_ok,
        f"sidecar={sidecar_path.as_posix()}, keys complete={sidecar_keys_ok}, "
        f"sha match={sidecar_sha_ok}, size match={sidecar_size_ok}",
    )

    # ------------------------------------------------ 3: source header vs pin
    try:
        with rasterio.open(args.source) as s:
            hdr_ok = (
                (s.width, s.height) == (EXPECTED_SRC_WIDTH, EXPECTED_SRC_HEIGHT)
                and s.count == 1 and (s.dtypes or [""])[0] == "uint8"
                and float(s.nodata) == EXPECTED_SRC_NODATA
            )
            t = s.transform
            t_ok = all(abs(a - e) <= TRANSFORM_TOL for a, e in zip(
                (t.a, t.b, t.c, t.d, t.e, t.f), EXPECTED_SRC_TRANSFORM))
            toks = (s.crs.to_proj4() or "").split()
            crs_ok = all(tok in toks for tok in EXPECTED_SRC_CRS_TOKENS)
        failed |= not add(
            "source header matches pinned preflight contract",
            hdr_ok and t_ok and crs_ok,
            f"dims {EXPECTED_SRC_WIDTH}x{EXPECTED_SRC_HEIGHT} 1x uint8 nodata={EXPECTED_SRC_NODATA!r}, "
            f"transform match={t_ok}, crs tokens match={crs_ok}",
        )
    except Exception as exc:  # noqa: BLE001
        add("source header matches pinned preflight contract", False, f"unreadable: {exc}")
        print("[error] cannot continue without the source", file=sys.stderr)
        return 1

    # ------------------------------------------------ 4: output file identity
    if not args.dest.is_file():
        add("output exists", False, f"not found: {args.dest}")
        print("[error] run pipeline/export_ctx_basemap.py first", file=sys.stderr)
        return 1
    dest_size = args.dest.stat().st_size
    size_ok = dest_size <= MAX_BYTES
    dest_sha = sha256_of(args.dest)
    failed |= not add(
        f"output size <= {MAX_BYTES} bytes (5 MB)",
        size_ok,
        f"{dest_size} bytes ({dest_size / 1024:.1f} KiB), sha256={dest_sha}",
    )
    try:
        with rasterio.open(args.dest) as out:
            rio_ok = (out.width, out.height, out.count) == (
                int(meta["width"]), int(meta["height"]), 3
            ) and (out.dtypes or [""])[0] == "uint8"
        failed |= not add(
            "output rasterio identity (dims == grid contract, 3x uint8)",
            rio_ok,
            f"{meta['width']}x{meta['height']} expected; count=3, dtype=uint8 required",
        )
    except Exception as exc:  # noqa: BLE001
        add("output rasterio identity", False, f"decode failed: {exc}")
        failed = True

    # ------------------------------------------------ 5: independent PIL decode
    if Image is None:
        add("Pillow available (independent decoder)", False, "PIL not importable")
        failed = True
        print("[error] Pillow missing; cannot perform the independent decode", file=sys.stderr)
        return 1
    try:
        img = Image.open(args.dest)
        img.load()
        pil_mode_ok = img.mode == "RGB"
        pil_size_ok = img.size == (int(meta["width"]), int(meta["height"]))
        decoded = np.asarray(img)  # (H, W, 3) uint8
        pil_ok = pil_mode_ok and pil_size_ok
        failed |= not add(
            "Pillow independent decode (mode RGB, exact dims)",
            pil_ok,
            f"mode={img.mode!r} (RGB required), size={img.size!r} "
            f"({meta['width']}x{meta['height']} required)",
        )
    except Exception as exc:  # noqa: BLE001
        add("Pillow independent decode", False, f"decode failed: {exc}")
        print("[error] cannot continue without a decodable output", file=sys.stderr)
        return 1

    inter_band_max = int(np.abs(decoded[:, :, 0].astype(np.int16) - decoded[:, :, 1].astype(np.int16)).max())
    inter_band_max = max(inter_band_max, int(np.abs(decoded[:, :, 0].astype(np.int16) - decoded[:, :, 2].astype(np.int16)).max()))
    failed |= not add(
        "grayscale replication preserved (three JPEG bands identical)",
        inter_band_max == 0,
        f"max inter-band difference = {inter_band_max}",
    )

    # ------------------------------------------------ 6: independent expected image + comparison
    try:
        with rasterio.open(args.raster) as target_ds:
            if target_ds.width != int(meta["width"]) or target_ds.height != int(meta["height"]):
                raise RuntimeError("target DEM dims disagree with grid_meta.json")
            derived = derive_expected_image(target_ds, args.source)
    except Exception as exc:  # noqa: BLE001
        add("independent expected-image derivation", False, f"failed: {exc}")
        print("[error] cannot continue without the derived expectation", file=sys.stderr)
        return 1

    lo, hi = derived["lo"], derived["hi"]
    zeros = derived["zeros"]
    gaps = derived["gaps"]
    failed |= not add(
        "DN=0 census state holds (zero DN=0 pixels in the window)",
        zeros == 0,
        f"{zeros} zero pixels in the {derived['window_shape'][0]}x{derived['window_shape'][1]} window "
        "(approved state: none; the declared-NoData ambiguity cannot arise)",
    )
    failed |= not add(
        "independent warp has zero coverage gaps (Average resampling)",
        gaps == 0,
        f"{gaps} gap pixels of {int(meta['width']) * int(meta['height'])} "
        "(policy: any gap is a hard failure - nothing fabricated or interpolated)",
    )
    failed |= not add(
        "independent stretch bounds derived from the measured histogram",
        1 <= lo < hi <= 255,
        f"p{STRETCH_LO_PCT:g}={lo}, p{STRETCH_HI_PCT:g}={hi} "
        f"(window min/max from histogram: {int(np.nonzero(derived['hist'])[0].min())}/"
        f"{int(np.nonzero(derived['hist'])[0].max())})",
    )

    expected = derived["expected"]
    diff = np.abs(decoded.astype(np.int16) - expected.astype(np.int16))
    max_diff = int(diff.max())
    mean_diff = float(diff.mean())
    p99_diff = float(np.percentile(diff, 99))
    mse = float(((decoded.astype(np.float64) - expected.astype(np.float64)) ** 2).mean())
    psnr = 10.0 * math.log10(255.0**2 / mse) if mse > 0 else float("inf")

    def blur3(a: np.ndarray) -> np.ndarray:
        p = np.pad(a.astype(np.float64), 1, mode="edge")
        return (
            p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:]
            + p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:]
            + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]
        ) / 9.0

    band_out = decoded[:, :, 0]
    band_exp = expected[:, :, 0]
    blur_diff = float(np.abs(blur3(band_out) - blur3(band_exp)).mean())
    a = decoded.astype(np.float64).ravel()
    b = expected.astype(np.float64).ravel()
    corr = float(np.corrcoef(a, b)[0, 1])
    comparison_ok = (
        max_diff <= TOL_MAX_DIFF and mean_diff <= TOL_MEAN_DIFF
        and p99_diff <= TOL_P99_DIFF and psnr >= TOL_PSNR
    )
    failed |= not add(
        "FULL-image comparison vs independently derived expected image",
        comparison_ok,
        f"max|diff|={max_diff} (tol {TOL_MAX_DIFF}), mean|diff|={mean_diff!r} (tol {TOL_MEAN_DIFF}), "
        f"p99|diff|={p99_diff!r} (tol {TOL_P99_DIFF}), PSNR={psnr!r} dB (tol {TOL_PSNR}) "
        f"over {decoded.size} values "
        "(this is the target-geometry proof: the JPEG pixels match the exact DEM-grid warp; "
        "bounds justified by the independent-encoder q85 measurement of this content)",
    )
    failed |= not add(
        "structural agreement after 3x3 box blur (JPEG noise suppressed)",
        blur_diff <= TOL_BLUR_MEAN_DIFF,
        f"blur3x3 mean|diff|={blur_diff!r} DN (tol {TOL_BLUR_MEAN_DIFF}) - "
        "the decoded structure matches the independent expectation once "
        "lossy-quantization noise is smoothed out",
    )
    failed |= not add(
        "correlation vs independent expectation",
        corr >= TOL_CORRELATION,
        f"pearson r={corr!r} (tol {TOL_CORRELATION})",
    )

    pure_black = int((decoded[:, :, 0] == 0).all(axis=-1).sum())
    pure_white = int((decoded[:, :, 0] == 255).all(axis=-1).sum())
    exp_black = int((expected[:, :, 0] == 0).all(axis=-1).sum())
    exp_white = int((expected[:, :, 0] == 255).all(axis=-1).sum())
    add(
        "pure-black/pure-white counts measured (informational)",
        True,
        f"output black={pure_black} white={pure_white}; expected black={exp_black} white={exp_white} "
        "(tail-clip pixels from the documented p0.5/p99.5 stretch)",
    )

    # ------------------------------------------------ 7: determinism (double export)
    exporter = Path(__file__).resolve().parent / "export_ctx_basemap.py"
    tmp = Path(tempfile.mkdtemp(prefix="ctxbm-det-"))
    run_shas: list[str] = []
    run_codes: list[int] = []
    try:
        for i in (1, 2):
            dest_i = tmp / f"ctx_basemap_run{i}.jpg"
            proc = subprocess.run(
                [
                    sys.executable, str(exporter),
                    "--source", str(args.source.resolve()),
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
        det_ok = run_shas[0] == run_shas[1] == dest_sha
        failed |= not add(
            "determinism: two temp exports equal the final artifact (SHA-256 x3)",
            det_ok,
            f"run1={run_shas[0][:16]}..., run2={run_shas[1][:16]}..., "
            f"final={dest_sha[:16]}..., exit codes {run_codes}; temp dir removed",
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
        "docs/sources.md Task 06 row complete (URL, DOI, WMTS, SHA, attribution)",
        not missing_frags,
        "all required fragments present" if not missing_frags
        else f"missing fragments: {missing_frags}",
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
    hist = derived["hist"]
    n_px = int(hist.sum())
    pct_rows = []
    for p in (0.1, 0.5, 1, 2, 5, 50, 95, 98, 99, 99.5, 99.9):
        dn = int(np.searchsorted(derived["cdf"], p, side="left"))
        pct_rows.append(f"| p{p:g} | {dn} |")
    pct_table = "\n".join(pct_rows)
    nonzero_min = int(np.nonzero(hist)[0].min())
    nonzero_max = int(np.nonzero(hist)[0].max())
    window_cols, window_rows, window_col_hi, window_row_hi = (
        derived["window"][0], derived["window"][1], derived["window"][2], derived["window"][3]
    )

    report = f"""# CTX Basemap Report - `web/data/ctx_basemap.jpg` (Task 06)

Task 06 deliverable evidence - written by `pipeline/verify_ctx_basemap.py`
after the exporter (`pipeline/export_ctx_basemap.py`) and every independent
validation check (including the double-export determinism proof) passed.
Deterministic content: no timestamps; all values are measured from the files
listed below.

## 1. Approved decisions (implemented and validated)

- Source: **S2 only** - the USGS Mars 2020 TRN CTX orthomosaic 6 m
  (`JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0`), the exact product
  NASA JPL Mars Trek streams as "MRO CTX, Jezero Mosaic, Controlled"
  (layer ID == file name; verified against the Trek service catalog and
  GetCapabilities).
- Target geometry: **exactly the existing DEM grid** (`grid_meta.json` +
  `data/processed/dem_20m_crop.tif`): {meta['width']} x {meta['height']} px @ 20 m,
  equirectangular lat_ts=18.4663, R=3396190.
- **Proper geospatial warp** (source lat_ts=0 vs target lat_ts=18.4663;
  empirically a pure x-rescale, no y-warp), never a plain resize.
- **Outward source-window pixel snapping** with a proven coverage proof.
- Resampling: **Average** (6 m -> 20 m area-average; approved).
- NoData: the source GeoTIFF declares **DN=0 = NoData**; the approved census
  state is **ZERO DN=0 pixels** (measured over the whole
  {EXPECTED_SRC_WIDTH * EXPECTED_SRC_HEIGHT:,}-pixel mosaic), so the
  "valid dark pixel vs missing pixel" ambiguity cannot arise; any warp gap
  is a hard failure (nothing fabricated, nothing interpolated).
- Contrast: **conservative percentile linear stretch from the measured
  histogram** (p{STRETCH_LO_PCT:g} / p{STRETCH_HI_PCT:g}), half-even rounding.
  p2/p98 was rejected (would clip 4% and over-flatten a basemap).
- JPEG: **quality {JPEG_QUALITY}, <= 5 MB**, grayscale replicated to RGB,
  atomic `.part` -> `os.replace` promotion.

Contract: `docs/PLAN.md` line 209 (`ctx_basemap.jpg`, JPEG quality 85,
<= 5 MB, DE1) and line 325 (deliverable slot).

## 2. Source identity

| Item | Value |
|---|---|
| Product | Mars 2020 Terrain Relative Navigation Context Camera Orthorectified Image Mosaic (USGS Astrogeology) |
| Primary URL | `{str(sidecar.get('url', ''))}` |
| Mars Trek WMTS equivalent | `{str(sidecar.get('mars_trek_wmts_equivalent', ''))}` |
| DOI | `{str(sidecar.get('doi', ''))}` |
| File size | {args.source.stat().st_size} bytes (pinned {EXPECTED_SOURCE_SIZE}) |
| SHA-256 | `{src_sha}` |
| Acquisition date (UTC) | {str(sidecar.get('acquired_on', ''))} |
| Acquisition tool | `{str(sidecar.get('tool', ''))}` |
| Dimensions / dtype / NoData | {EXPECTED_SRC_WIDTH} x {EXPECTED_SRC_HEIGHT}, 1 x uint8, nodata=0.0 |
| CRS / pixel size | equirectangular lat_ts=0, R=3396190; 6.0 m/px |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `{args.dest.as_posix()}` |
| File size | {dest_size} bytes ({dest_size / 1024:.1f} KiB; limit {MAX_BYTES} = 5 MB) |
| SHA-256 | `{dest_sha}` |
| Dimensions | {meta['width']} x {meta['height']} px, 3 bands uint8 (grayscale replicated) |
| JPEG quality | {JPEG_QUALITY} |

## 4. Source window (outward snap + coverage proof)

| Item | Value |
|---|---|
| Snapped window (source px) | cols [{window_cols}, {window_col_hi}), rows [{window_rows}, {window_row_hi}) = {window_col_hi - window_cols} x {window_row_hi - window_rows} px |
| Window size | {derived['window_shape'][0]} x {derived['window_shape'][1]} px = {int(derived['window_shape'][0]) * int(derived['window_shape'][1]):,} px |
| Coverage proof | snapped window fully covers the target grid (independent derivation, tolerance 1e-6 m) |
| DN=0 census (window) | {zeros} zero pixels (0.000000%) |

## 5. Measured histogram (window, valid pixels = all {n_px:,})

| Percentile | DN |
|---|---|
{pct_table}

Distribution summary: DN range [{nonzero_min}, {nonzero_max}]; no DN=0 pixels exist.

## 6. Contrast stretch (conservative, from the measured histogram)

| Item | Value |
|---|---|
| Bounds | p{STRETCH_LO_PCT:g} = {lo}, p{STRETCH_HI_PCT:g} = {hi} |
| Mapping | linear [{lo}, {hi}] -> [0, 255], half-even rounding, clamped |
| Clipped mass | {100.0 * hist[:lo].sum() / n_px:.4f}% below, {100.0 * hist[hi + 1:].sum() / n_px:.4f}% above (total {100.0 * (hist[:lo].sum() + hist[hi + 1:].sum()) / n_px:.4f}%) |

## 7. Warp and coverage

| Item | Value |
|---|---|
| Resampling | Average (GDAL/rasterio) |
| Output gap pixels | {gaps} of {int(meta['width']) * int(meta['height'])} (0.000000%) |
| Pure-black pixels (output, measured) | {pure_black} ({100.0 * pure_black / decoded.shape[0] / decoded.shape[1]:.4f}%; documented tail-clip of the stretch) |
| Pure-white pixels (output, measured) | {pure_white} ({100.0 * pure_white / decoded.shape[0] / decoded.shape[1]:.4f}%) |

## 8. Independent comparison (target-geometry proof)

The expected image was derived independently (window, warp and stretch
re-implemented in this validator; the JPEG is decoded with Pillow as a second,
independent decoder):

| Item | Value |
|---|---|
| Max abs difference | {max_diff} DN (tolerance {TOL_MAX_DIFF}) |
| Mean abs difference | {mean_diff!r} DN (tolerance {TOL_MEAN_DIFF}) |
| 99th percentile abs difference | {p99_diff!r} DN (tolerance {TOL_P99_DIFF}) |
| PSNR (vs expected) | {psnr!r} dB (tolerance {TOL_PSNR}) |
| Blur 3x3 mean abs difference | {blur_diff!r} DN (tolerance {TOL_BLUR_MEAN_DIFF}) |
| Pearson correlation | {corr!r} (tolerance {TOL_CORRELATION}) |
| Inter-band difference | {inter_band_max} (bands must be identical) |
| Compared values | {decoded.size} (full image x 3 bands) |

Tolerance justification: an independent-encoder reference (Pillow q85 encoding
of the same expected image, measured during this task) yields mean 3.05 DN,
p99 11, max 25 DN, PSNR 36.11 dB, blur3x3-mean 0.56 DN on THIS content; the
tolerances are ~1.6x those baselines (blur bound ~2.7x). The residual
differences are JPEG lossy-quantization error only (quality {JPEG_QUALITY});
the comparison against the independently warped expectation IS the proof that
the JPEG corresponds to the exact target DEM geometry (plain JPEG carries no
georeferencing tags by design).

## 9. Validator results

| Check | Result | Measured detail |
|---|---|---|
{checks_table}

## 10. Determinism result

The exporter ran twice into a temporary directory; exit codes {run_codes[0]} and {run_codes[1]};
SHA-256 of run 1 == run 2 == final artifact
(`{run_shas[0] if run_shas else 'n/a'}`). The temporary directory was removed;
the final artifact was not rewritten by this check. Re-exports on the pinned
environment are byte-identical.

## 11. Attribution (to display with the layer)

{str(sidecar.get('attribution', ''))}

## 12. Untested behavior and limitations

- The DN=0 NoData mapping and warp-gap hard-fail paths are NOT exercised by
  data (0 zero pixels; 0 gaps); they are enforced by explicit abort guards in
  both scripts and verified by code review only (conservative stop-policy for
  re-runs that encounter zeros or gaps).
- JPEG determinism is proven for consecutive runs on this machine
  (rasterio/GDAL {rasterio.__gdal_version__} libjpeg encoder); a different
  JPEG encoder version could produce byte-different (but visually equivalent)
  output; the pinned environment governs.
- The pure-black/pure-white pixels are the documented stretch tail-clip
  (~1% total), not missing data.
- Plain JPEG intentionally carries no georeferencing; the web layer is
  geolocated through `web/data/grid_meta.json` (pixel (row, col) maps exactly
  onto the shared decode grid).

## 13. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}, Pillow {Image.__version__ if Image else 'n/a'}
- Scripts: `pipeline/acquire_ctx_basemap.py` (acquisition),
  `pipeline/export_ctx_basemap.py` (exporter),
  `pipeline/verify_ctx_basemap.py` (this validator + report owner;
  rerunnable, deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.report.write_text(report, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[error] writing the CTX basemap report failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] report written: {args.report.as_posix()}")
    print(
        f"[summary] dest={args.dest.as_posix()} sha256={dest_sha}, bytes={dest_size}, "
        f"dims={meta['width']}x{meta['height']}, checks={len(checks)}/{len(checks)} passed, "
        f"max_diff={max_diff}, mean_diff={mean_diff!r}, report={args.report.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
