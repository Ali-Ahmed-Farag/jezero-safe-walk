"""Crop the raw USGS Jezero CTX DEM to the project AOI (Task 03).

Produces ``data/processed/dem_20m_crop.tif`` without resampling, reprojecting,
or altering any pixel value:

- The PLAN §5.1 contract frame (AOI) is transformed from geographic lon/lat on
  the SAME body (Mars radii parsed from the source CRS - never an Earth CRS)
  into the file's own projected CRS, then snapped OUTWARD to whole source
  pixels, so the output fully covers the AOI while every output pixel is a
  verbatim copy of a source pixel (CRS, resolution, dtype, and NoData are
  preserved exactly).
- The crop is written to ``<dest>.part`` first and renamed into place only
  after every validation check passes (atomic promotion, same pattern as
  acquire_dem.py; a failed validation keeps the .part for diagnosis).
- A deterministic markdown report (no timestamps, no absolute paths) is
  written to ``data/processed/dem_crop_report.md``.
- The source file is never written to; its SHA-256 is re-verified after the
  crop to prove it stayed byte-identical.

The source is pinned by SHA-256 (measured at acquisition 2026-11-13); the
script refuses to crop anything else.

Run inside the project venv:

    .venv\\Scripts\\python.exe pipeline\\crop_dem.py
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.coords import BoundingBox
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

# --------------------------------------------------------------------- constants

CHUNK = 1 << 20  # 1 MiB streaming hash blocks, same pattern as acquire_dem.py

DEFAULT_SOURCE = Path("data/raw/M20_JezeroCrater_CTXDEM_20m.tif")
DEFAULT_DEST = Path("data/processed/dem_20m_crop.tif")
DEFAULT_REPORT = Path("data/processed/dem_crop_report.md")

# SHA-256 of the pristine DEM, measured at acquisition on 2026-11-13 (Task 02).
# Cropping any other file is refused: the crop's provenance chain starts here.
# NOTE: this pin is duplicated in pipeline/acquire_dem.py and in
# data/raw/M20_JezeroCrater_CTXDEM_20m.tif.provenance.json - update all three
# together if the source is ever legitimately re-acquired (a shared
# pipeline/common.py module is a possible future refactor).
EXPECTED_SOURCE_SHA256 = "ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2"

# PLAN §5.1 contract frame, approved by the user as the governing AOI for
# Task 03 (decision recorded 2026-11-13). docs/sources.md registers the same
# frame at higher precision, but the user explicitly ruled that PLAN §5.1
# governs; the precise values are intentionally NOT used here.
AOI_BOUNDS = {
    "lon_min": 77.2229, "lon_max": 77.5840,
    "lat_min": 18.3068, "lat_max": 18.6693,
}

# Outward pixel snapping: expand the AOI rectangle to whole source pixels so
# every requested edge is fully covered (never clipped) by the crop.
SNAP_RULE = "outward_pixel_snapping"
# Fractional-pixel epsilon: an AOI edge within EPS_PX of a pixel boundary is
# treated as lying exactly ON that boundary (guards float noise in the
# projected -> pixel arithmetic) instead of triggering a one-pixel outward
# expansion from pure rounding.
EPS_PX = 1e-9

# PLAN §5.1: meter conversions are referenced at this latitude.
PROJECT_LAT_REF = 18.5
# Coverage tolerance for the "AOI fully covered" verdict (degrees).
# NOTE: EPS_PX (1e-9 px ≈ 2e-8 m) and COVERAGE_TOL_DEG (1e-9° ≈ 5.6e-5 m here)
# are intentionally different units and scales: the degree tolerance absorbs
# the worst-case epsilon clip with ~3 orders of magnitude of headroom, while a
# real one-pixel coverage miss (~3.6e-4°) still fails ~350,000× above it.
# Do not "harmonize" the two constants.
COVERAGE_TOL_DEG = 1e-9

# WKT1 SPHEROID fallback for body radii, exactly as in inspect_dem.py.
SPHEROID_RE = re.compile(r'SPHEROID\["([^"]+)",\s*([0-9.eE+-]+),\s*([0-9.eE+-]+)')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_source(path: Path) -> int:
    """Pre-flight validation: exists, non-empty, readable, CRS, 1 band float32, square positive res."""
    if not path.is_file():
        raise SystemExit(f"[error] source not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise SystemExit(f"[error] source is empty: {path}")
    try:
        with rasterio.open(path) as ds:
            crs, count = ds.crs, ds.count
            dtype = (ds.dtypes or [""])[0]
            res = ds.res
            ds.read(1, window=Window(0, 0, min(8, ds.width), min(8, ds.height)))
    except Exception as exc:
        raise SystemExit(f"[error] source is not a readable raster: {exc}")
    if crs is None:
        raise SystemExit("[error] source has no CRS; a crop without a CRS is unusable")
    if count != 1:
        raise SystemExit(f"[error] source has {count} bands; expected exactly 1")
    if dtype != "float32":
        raise SystemExit(f"[error] source dtype is {dtype!r}; expected 'float32'")
    if res[0] <= 0 or abs(res[1]) <= 0:
        raise SystemExit(f"[error] source pixel size is not positive: {res!r}")
    if not math.isclose(res[0], abs(res[1]), rel_tol=1e-9, abs_tol=1e-9):
        raise SystemExit(
            f"[error] source pixels are not square (res={res!r}); the crop "
            "preserves the source grid, so non-square pixels need an explicit "
            "ruling before proceeding"
        )
    print(f"[ok] source validation passed ({size} bytes, {count}x {dtype}, res {res!r})")
    return size


def body_radii(crs: "rasterio.crs.CRS") -> tuple[float, float, str]:
    """Semi-major/minor radii of the CRS body, parsed from proj4 or WKT.

    For THIS DEM's CRS, ``to_proj4()`` emits the sphere form (``+R=3396190``)
    with no ``+a``/``+b``, so the WKT SPHEROID fallback is the exercised path
    (``SPHEROID["Mars_2000_Sphere",3396190,0]`` - rf=0 means b=a). The proj4
    branch stays for CRSs that do publish ``+a``/``+b``.
    """
    proj4 = crs.to_proj4() or ""
    a_m = re.search(r"\+a=([0-9.eE+-]+)", proj4)
    b_m = re.search(r"\+b=([0-9.eE+-]+)", proj4)
    if a_m and b_m:
        return float(a_m[1]), float(b_m[1]), "proj4"
    m = SPHEROID_RE.search(crs.to_wkt())
    if not m:
        raise SystemExit("[error] cannot derive body radii from CRS (no SPHEROID/proj4 +a/+b)")
    a, rf = float(m[2]), float(m[3])
    b = a * (1 - 1 / rf) if rf > 0 else a
    return a, b, "wkt-SPHEROID"


def geographic_body_crs(crs: "rasterio.crs.CRS") -> "rasterio.crs.CRS":
    """Geographic lon/lat CRS on the SAME body - never an Earth CRS."""
    a, b, _ = body_radii(crs)
    return rasterio.crs.CRS.from_string(f"+proj=longlat +a={a!r} +b={b!r} +no_defs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    # Guard the CLI surface: a --dest or --report resolving onto --source is
    # the only path by which the pinned source could be replaced or shadowed
    # (os.replace promotion happens after validation, so check (j) cannot see
    # it). Distinct resolved paths keep "source modification impossible" true
    # even under misuse.
    resolves = {p.resolve() for p in (args.source, args.dest, args.report)}
    if len(resolves) < 3:
        raise SystemExit("[error] --source, --dest and --report must be distinct paths")

    # ------------------------------------------------ 1-2: source identity
    validate_source(args.source)
    sha_before = sha256_of(args.source)
    if sha_before != EXPECTED_SOURCE_SHA256:
        print(
            f"[error] source SHA-256 mismatch: got {sha_before}, expected "
            f"{EXPECTED_SOURCE_SHA256}; refusing to crop a file that is not the "
            "pinned acquisition",
            file=sys.stderr,
        )
        return 1
    print(f"[ok] source SHA-256 matches the pinned acquisition: {sha_before}")

    # Tag reproduces the PLAN §5.1 values in the exact four-decimal form
    # approved for Task 03 (e.g. 77.5840, not 77.584).
    aoi_requested = ";".join(f"{k}={v:.4f}" for k, v in AOI_BOUNDS.items())

    # --------------------------------------- 3-6: projection, snap, window
    with rasterio.open(args.source) as src:
        src_crs = src.crs
        src_res = src.res
        src_bounds = src.bounds
        src_nodata = src.nodata
        src_width, src_height = src.width, src.height

        # Geographic lon/lat CRS on the SAME body (Mars) - the radii come from
        # the file's own CRS (proj4 +a/+b, WKT1 SPHEROID fallback), never from
        # an Earth datum, so AOI degrees and file meters share one reference.
        a_r, b_r, radii_src = body_radii(src_crs)
        geo_crs = geographic_body_crs(src_crs)

        # Transform the four AOI corners (lon_min, lon_max) x (lat_min, lat_max)
        # from that geographic CRS into the file's projected CRS. The
        # Equirectangular projection is axis-aligned, so min/max over the
        # corners is exact for this CRS.
        lons = [AOI_BOUNDS["lon_min"], AOI_BOUNDS["lon_max"],
                AOI_BOUNDS["lon_min"], AOI_BOUNDS["lon_max"]]
        lats = [AOI_BOUNDS["lat_min"], AOI_BOUNDS["lat_min"],
                AOI_BOUNDS["lat_max"], AOI_BOUNDS["lat_max"]]
        xs, ys = warp_transform(geo_crs, src_crs, lons, lats)
        x_west, x_east = min(xs), max(xs)
        y_south, y_north = min(ys), max(ys)
        if not (x_west >= src_bounds.left and x_east <= src_bounds.right
                and y_north <= src_bounds.top and y_south >= src_bounds.bottom):
            print(
                "[error] requested AOI is not fully inside the source raster:\n"
                f"  AOI projected    : x [{x_west!r}, {x_east!r}], "
                f"y [{y_south!r}, {y_north!r}]\n"
                f"  source bounds    : x [{src_bounds.left!r}, {src_bounds.right!r}], "
                f"y [{src_bounds.bottom!r}, {src_bounds.top!r}]",
                file=sys.stderr,
            )
            return 1
        print(f"[ok] AOI projected: x [{x_west!r}, {x_east!r}], y [{y_south!r}, {y_north!r}]")

        # Fractional pixel positions of the AOI edges in the source grid
        # (rows count from north, matching the raster's row order).
        res_x, res_y = src_res[0], abs(src_res[1])
        col_f_west = (x_west - src_bounds.left) / res_x
        col_f_east = (x_east - src_bounds.left) / res_x
        row_f_north = (src_bounds.top - y_north) / res_y
        row_f_south = (src_bounds.top - y_south) / res_y

        # OUTWARD snap: +EPS on start edges / -EPS on end edges treats a
        # fractional position within EPS_PX of an integer as lying exactly ON
        # that pixel boundary (float-noise guard); every other value is pushed
        # outward by floor()/ceil() so the window fully covers the AOI.
        # col1/row1 are EXCLUSIVE ends (Python/rasterio window convention).
        col0 = math.floor(col_f_west + EPS_PX)
        col1 = math.ceil(col_f_east - EPS_PX)
        row0 = math.floor(row_f_north + EPS_PX)
        row1 = math.ceil(row_f_south - EPS_PX)
        win_w, win_h = col1 - col0, row1 - row0
        if win_w < 1 or win_h < 1:
            print(
                f"[error] snapped window collapsed: cols [{col0}, {col1}), "
                f"rows [{row0}, {row1}) - AOI smaller than one pixel?",
                file=sys.stderr,
            )
            return 1
        if not (0 <= col0 and col1 <= src_width and 0 <= row0 and row1 <= src_height):
            print(
                f"[error] snapped window [{col0}, {row0}, {win_w}x{win_h}] lies "
                f"outside the raster ({src_width}x{src_height})",
                file=sys.stderr,
            )
            return 1
        window = Window(col0, row0, win_w, win_h)
        out_transform = src.window_transform(window)
        src_window = src.read(1, window=window)
    print(
        f"[ok] outward snap: cols [{col0}, {col1}), rows [{row0}, {row1}) "
        f"= {win_w}x{win_h} px"
    )

    # --------------------------------------------- 8: write partial crop
    dest = args.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    # Explicit deterministic profile instead of src.profile wholesale: the
    # source is untiled/uncompressed, but copying a profile can carry tiling,
    # blocksize, or compression quirks; these explicit keys keep the bytes
    # deterministic on every rerun.
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "crs": src_crs,
        "transform": out_transform,
        "nodata": src_nodata,
        "width": win_w,
        "height": win_h,
    }
    try:
        with rasterio.open(partial, "w", **profile) as dst:
            dst.write(src_window, 1)  # explicit band index (README gotcha #1)
            dst.update_tags(
                SOURCE_FILE=args.source.as_posix(),
                SOURCE_SHA256=sha_before,
                AOI_REQUESTED=aoi_requested,
                AOI_SNAP_RULE=SNAP_RULE,
                SOURCE_COL0=str(col0),
                SOURCE_ROW0=str(row0),
            )
    except Exception as exc:
        print(f"[error] writing partial crop failed: {exc}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    print(f"[ok] partial crop written: {partial} ({win_w}x{win_h} px)")

    # -------------------------------------------- 9: validate the .part
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    try:
        with rasterio.open(partial) as dst, rasterio.open(args.source) as src2:
            # (a) dimensions match the snap window
            dims_ok = dst.width == win_w and dst.height == win_h
            record("a. dimensions == snap window", dims_ok,
                   f"dst {dst.width}x{dst.height} vs window {win_w}x{win_h}")

            # (b) resolution preserved (compared against the live source res)
            dst_res = (dst.res[0], abs(dst.res[1]))
            src_res_cmp = (src_res[0], abs(src_res[1]))
            record("b. resolution preserved", dst_res == src_res_cmp,
                   f"dst.res={dst_res!r} vs source res={src_res_cmp!r}")

            # (c) band count and dtype preserved
            cd_ok = dst.count == 1 and dst.dtypes[0] == "float32"
            record("c. 1 band float32 preserved", cd_ok,
                   f"count={dst.count}, dtype={dst.dtypes[0]!r}")

            # (d) NoData bitwise-equal to the source's (it lives in the file
            # as float32, so bit patterns - not float64 reprs - are the truth)
            if dst.nodata is None and src_nodata is None:
                nodata_ok, nodata_detail = True, "both None"
            elif dst.nodata is None or src_nodata is None:
                nodata_ok = False
                nodata_detail = f"dst.nodata={dst.nodata!r} vs source nodata={src_nodata!r}"
            else:
                d_bits = int(np.array([dst.nodata], dtype=np.float32).view(np.int32)[0])
                s_bits = int(np.array([src_nodata], dtype=np.float32).view(np.int32)[0])
                nodata_ok = d_bits == s_bits
                nodata_detail = (
                    f"dst.nodata={dst.nodata!r}, source nodata={src_nodata!r}; "
                    f"float32 bits {'identical' if nodata_ok else 'DIFFER'} "
                    f"(0x{d_bits & 0xFFFFFFFF:08X} vs 0x{s_bits & 0xFFFFFFFF:08X})"
                )
            record("d. NoData bitwise-equal", nodata_ok, nodata_detail)

            # (e) CRS preserved: object equality AND identical WKT1 text
            crs_obj_eq = dst.crs == src_crs
            wkt_eq = (dst.crs is not None and src_crs is not None
                      and dst.crs.to_wkt() == src_crs.to_wkt())
            record("e. CRS preserved (object + WKT1)", crs_obj_eq and wkt_eq,
                   f"CRS equal: {crs_obj_eq}; WKT1 equal: {wkt_eq}")

            # (f) all six affine coefficients identical to what was written
            coeffs = ("a", "b", "c", "d", "e", "f")
            got = tuple(getattr(dst.transform, k) for k in coeffs)
            want = tuple(getattr(out_transform, k) for k in coeffs)
            record("f. transform coeffs exact", got == want,
                   f"dst={got!r} vs written={want!r}")

            # (g) pixel equivalence: the crop must be a verbatim copy of the
            # source window. equal_nan=True makes NaN pixels compare position
            # by position; NaN/sentinel accounting is checked separately in (h).
            fresh = src2.read(1, window=window)
            crop = dst.read(1)
            if fresh.shape != crop.shape:
                record("g. pixel equivalence", False,
                       f"shape mismatch: dst {crop.shape} vs source window {fresh.shape}")
            else:
                both_nan = np.isnan(fresh) & np.isnan(crop)
                differing = int(np.count_nonzero((fresh != crop) & ~both_nan))
                px_equal = np.array_equal(fresh, crop, equal_nan=True)
                record("g. pixel equivalence", px_equal and differing == 0,
                       f"np.array_equal(..., equal_nan=True)={px_equal}; "
                       f"differing pixels={differing} of {fresh.size}")

                # (h) NoData accounting: sentinel and NaN counts must match
                # between the crop and the fresh source window (measured, not
                # assumed - the numbers are small/zero here but must be proven).
                def invalid_counts(arr: np.ndarray) -> tuple[int, int]:
                    sentinel = (
                        int(np.count_nonzero(arr == np.float32(src_nodata)))
                        if src_nodata is not None else 0
                    )
                    return sentinel, int(np.count_nonzero(np.isnan(arr)))

                s_sent, s_nan = invalid_counts(fresh)
                d_sent, d_nan = invalid_counts(crop)
                record("h. NoData accounting", (s_sent, s_nan) == (d_sent, d_nan),
                       f"crop: sentinel={d_sent}, NaN={d_nan}; "
                       f"source window: sentinel={s_sent}, NaN={s_nan}")

            # (i) coverage: the output must fully cover the requested AOI.
            # Margins are measured in PROJECTED space (px), then converted to
            # meters through degrees (m/deg lat = pi*a/180 from the body radius
            # a; m/deg lon at PROJECT_LAT_REF = that * cos(lat_ref); the
            # projected m/deg lon = m/deg lat * cos(lat_ts) comes from the
            # CRS's standard parallel).
            dst_bounds = dst.bounds
            m_per_deg_lat = math.pi * a_r / 180.0
            m_per_deg_lon_ground = m_per_deg_lat * math.cos(math.radians(PROJECT_LAT_REF))
            m_lat_ts = re.search(r"\+lat_ts=([0-9.eE+-]+)", src_crs.to_proj4() or "")
            lat_ts = float(m_lat_ts[1]) if m_lat_ts else None
            m_per_deg_lon_proj = (
                m_per_deg_lat * math.cos(math.radians(lat_ts)) if lat_ts is not None else None
            )
            margin_px = {
                "west": (x_west - dst_bounds.left) / res_x,
                "east": (dst_bounds.right - x_east) / res_x,
                "north": (dst_bounds.top - y_north) / res_y,
                "south": (y_south - dst_bounds.bottom) / res_y,
            }

            def margin_meters(side: str) -> float | None:
                px = margin_px[side]
                if side in ("west", "east"):
                    if m_per_deg_lon_proj is None:
                        return None
                    deg = px * res_x / m_per_deg_lon_proj
                    return deg * m_per_deg_lon_ground
                deg = px * res_y / m_per_deg_lat
                return deg * m_per_deg_lat

            lons_out, lats_out = warp_transform(
                src_crs, geo_crs,
                [dst_bounds.left, dst_bounds.right, dst_bounds.left, dst_bounds.right],
                [dst_bounds.top, dst_bounds.top, dst_bounds.bottom, dst_bounds.bottom],
            )
            dst_geo = BoundingBox(min(lons_out), min(lats_out), max(lons_out), max(lats_out))
            cover_ok = (
                AOI_BOUNDS["lon_min"] >= dst_geo.left - COVERAGE_TOL_DEG
                and AOI_BOUNDS["lon_max"] <= dst_geo.right + COVERAGE_TOL_DEG
                and AOI_BOUNDS["lat_min"] >= dst_geo.bottom - COVERAGE_TOL_DEG
                and AOI_BOUNDS["lat_max"] <= dst_geo.top + COVERAGE_TOL_DEG
            )
            margins_rows = []
            for side, req_deg, req_m, act_m, act_deg, margin in (
                ("west", AOI_BOUNDS["lon_min"], x_west, dst_bounds.left, dst_geo.left, margin_px["west"]),
                ("east", AOI_BOUNDS["lon_max"], x_east, dst_bounds.right, dst_geo.right, margin_px["east"]),
                ("north", AOI_BOUNDS["lat_max"], y_north, dst_bounds.top, dst_geo.top, margin_px["north"]),
                ("south", AOI_BOUNDS["lat_min"], y_south, dst_bounds.bottom, dst_geo.bottom, margin_px["south"]),
            ):
                m_val = margin_meters(side)
                margins_rows.append((side, req_deg, req_m, act_m, act_deg, margin, m_val))
            margins_str = "; ".join(
                f"{side}={margin!r} px" if m_val is None
                else f"{side}={margin!r} px = {m_val!r} m"
                for side, *_rest, margin, m_val in margins_rows
            )
            record("i. AOI fully covered", cover_ok,
                   f"output geo bounds lon [{dst_geo.left!r}, {dst_geo.right!r}], "
                   f"lat [{dst_geo.bottom!r}, {dst_geo.top!r}]; margins: {margins_str}; "
                   f"tol={COVERAGE_TOL_DEG} deg")
    except Exception as exc:
        print(f"[error] validating the partial crop failed: {exc}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1

    # (j) source unchanged: hash it again only after every read handle is closed
    sha_after = sha256_of(args.source)
    record("j. source unchanged (SHA-256)", sha_after == sha_before == EXPECTED_SOURCE_SHA256,
           f"after={sha_after}; before={sha_before}; pinned={EXPECTED_SOURCE_SHA256}")

    if not all(ok for _, ok, _ in checks):
        failed = [f"  {name}: {detail}" for name, ok, detail in checks if not ok]
        print(
            f"[error] validation FAILED ({len(failed)} of {len(checks)} checks); "
            "crop NOT promoted",
            file=sys.stderr,
        )
        for line in failed:
            print(f"[error] {line}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    print(f"[ok] validation passed: {len(checks)}/{len(checks)} checks")

    # ------------------------------------------- 10: atomic promotion
    try:
        os.replace(partial, dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial crop failed: {exc}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    try:
        with rasterio.open(dest) as final:
            final_ok = (
                (final.width, final.height) == (win_w, win_h)
                and (final.res[0], abs(final.res[1])) == src_res_cmp
            )
            final_tags = final.tags()
    except Exception as exc:
        print(f"[error] promoted crop is not readable: {exc}", file=sys.stderr)
        return 1
    if not final_ok:
        print("[error] promoted crop failed the quick readability check", file=sys.stderr)
        return 1
    dest_size = dest.stat().st_size
    dest_sha = sha256_of(dest)
    print(f"[ok] promoted: {dest} ({dest_size} bytes)")

    # ---------------------------------------------- 11: deterministic report
    # Distances of the fractional AOI edges from the nearest integer pixel
    # (how far each edge is from an exact grid line).
    frac = {
        "col_f_west": col_f_west, "col_f_east": col_f_east,
        "row_f_north": row_f_north, "row_f_south": row_f_south,
    }
    frac_rows = "\n".join(
        f"| `{name}` | {val!r} | {abs(val - round(val))!r} |"
        for name, val in frac.items()
    )
    coeffs_str = ", ".join(f"{k}={v!r}" for k, v in zip(coeffs, want))
    margin_table = "\n".join(
        f"| {side} | {req_deg:.4f} | {req_m!r} | {act_m!r} | {act_deg!r} | {margin!r} | "
        + (f"{m_val!r}" if m_val is not None else "n/a (lat_ts not in proj4)")
        + " |"
        for side, req_deg, req_m, act_m, act_deg, margin, m_val in margins_rows
    )
    validation_table = "\n".join(
        f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |"
        for name, ok, detail in checks
    )
    extent_x_m, extent_y_m = win_w * res_x, win_h * res_y
    # Ground-scale x meters per pixel at PROJECT_LAT_REF (inspect_dem.py §5
    # formula): projected px * cos(lat_ref)/cos(lat_ts). Deferred DECISION for
    # grid_meta.json; reported here only as context.
    ground_x_px = (
        res_x * m_per_deg_lon_ground / m_per_deg_lon_proj
        if m_per_deg_lon_proj is not None else None
    )

    report = f"""# DEM Crop Report — outward pixel snap to the PLAN §5.1 AOI

Task 03 deliverable — generated by `pipeline/crop_dem.py` from measured values only.
No resampling, reprojection, or pixel-value change was performed; every output
pixel is a verbatim copy of a source pixel.

## 1. Source identity

| Item | Value |
|---|---|
| Source file | `{args.source.as_posix()}` |
| File size | {args.source.stat().st_size} bytes |
| SHA-256 (before) | `{sha_before}` |
| SHA-256 (after) | `{sha_after}` |
| Pinned-match | {'YES — equals the acquisition hash of 2026-11-13' if sha_before == EXPECTED_SOURCE_SHA256 else '**NO — MISMATCH**'} |

## 2. Requested AOI — PLAN §5.1 (approved decision)

Requested frame: lon {AOI_BOUNDS['lon_min']:.4f}–{AOI_BOUNDS['lon_max']:.4f},
lat {AOI_BOUNDS['lat_min']:.4f}–{AOI_BOUNDS['lat_max']:.4f} (four-decimal form
as approved; e.g. 77.5840, not the float repr 77.584).

These four-degree values were approved by the user as the governing AOI for
Task 03 (2026-11-13). docs/sources.md registers a higher-precision AOI, but the
user explicitly ruled that PLAN §5.1 governs; the precise values are
deliberately not used. This section records what was REQUESTED; the ACTUAL
output bounds (after outward pixel snapping) are in §7.

## 3. AOI in the DEM's projected CRS

| Edge | Value (m) |
|---|---|
| x_west | {x_west!r} |
| x_east | {x_east!r} |
| y_north | {y_north!r} |
| y_south | {y_south!r} |

Method: GDAL/PROJ coordinate transformation from a geographic lon/lat CRS on
the SAME body — Mars radii a={a_r!r} m, b={b_r!r} m (source: {radii_src}) — to the
file's own projected CRS. No Earth CRS (e.g. EPSG:4326) is involved at any
point.

## 4. Fractional pixel positions in the source grid

0-based; rows count from north (row 0 = raster top).

| Edge | Fractional position | Distance from nearest integer |
|---|---|---|
{frac_rows}

## 5. Outward snap

| Item | Value |
|---|---|
| Snap rule | `{SNAP_RULE}` (expand to whole pixels; the AOI is fully covered, never clipped) |
| Epsilon | {EPS_PX!r} fractional px (edges within EPS of a pixel boundary are treated as exactly on it) |
| Window in source grid | cols [{col0}, {col1}), rows [{row0}, {row1}) — col1/row1 exclusive |
| Window origin (0-based) | col0={col0}, row0={row0} |
| Window size | {win_w} x {win_h} px (width x height) |
"""

    report += f"""
## 6. Output raster

| Item | Value |
|---|---|
| File | `{dest.as_posix()}` |
| Dimensions | {win_w} x {win_h} px (width x height) |
| Affine transform | {coeffs_str} |
| Pixel resolution | x={src_res_cmp[0]!r}, y={src_res_cmp[1]!r} (projected m, preserved from source) |
| Data type | float32, 1 band |
| NoData | {src_nodata!r} (bitwise identical to source) |
| CRS | identical to source CRS (object equality and WKT1 text both verified; embedded Equirectangular Mars CRS used as-is, no authority substitution) |
| Tags written | {final_tags} |
| File size | {dest_size} bytes |
| SHA-256 | `{dest_sha}` |

## 7. Requested vs actual bounds

| Side | Requested (deg) | Requested (m) | Actual output (m) | Actual output (deg) | Margin (px) | Margin (m) |
|---|---|---|---|---|---|---|
{margin_table}

Actual output geographic bounds via warp of the output corners to the same-body
geographic CRS: lon {dst_geo.left!r}–{dst_geo.right!r},
lat {dst_geo.bottom!r}–{dst_geo.top!r}. Margins are measured in projected space
(px) and converted to meters via m/deg lat = π·a/180 (a={a_r!r}) and m/deg lon at
{PROJECT_LAT_REF}° = that × cos({PROJECT_LAT_REF}°).

**Verdict: {'AOI FULLY COVERED' if cover_ok else 'AOI NOT COVERED (run would have aborted before promotion)'}** (tolerance {COVERAGE_TOL_DEG}°)

## 8. Validation results

All checks were run against the partial file before promotion, on a fresh
window read of the source.

| Check | Result | Measured detail |
|---|---|---|
{validation_table}

## 9. Notes for Task 04 (grid contract)

- Source-grid origin: the crop starts at source pixel col0={col0}, row0={row0}
  (0-based indices in the ORIGINAL {src_width}x{src_height} grid).
- Row 0 = north preserved: crop row 0 is source row {row0}; rows still run
  north → south and pixels stay row-major (no flip, no transposition).
- Actual extent: {win_w}·20 m = {extent_x_m!r} m (x) × {win_h}·20 m = {extent_y_m!r} m (y),
  vs PLAN §5.1's "≈20×21 km" phrasing (the outward snap slightly exceeds the
  requested frame on every side).
- Pixel sizes: {src_res_cmp[0]!r} m (x) × {src_res_cmp[1]!r} m (y) in PROJECTED meters.
  The ground-scale x meters at lat {PROJECT_LAT_REF}° (≈ {ground_x_px if ground_x_px is not None else 'n/a (lat_ts not in proj4)'} m/px) is a
  grid_meta.json decision still open from Task 02 §9 item 2 — not ruled here.
- NoData sentinel and NaN counts are recorded in §8 check (h); the crop
  preserves them exactly.

## 10. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}
- Script: `pipeline/crop_dem.py` (rerunnable; deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.report.write_text(report, encoding="utf-8")
    except OSError as exc:
        print(f"[error] writing the crop report failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] report written: {args.report}")
    print(
        f"[summary] window=cols [{col0}, {col1}) rows [{row0}, {row1}) "
        f"({win_w}x{win_h} px), dims={win_w}x{win_h}, dest={dest.as_posix()}, "
        f"sha256={dest_sha}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

