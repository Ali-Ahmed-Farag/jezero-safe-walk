"""Grid metadata contract for the Jezero Safe Walk processed DEM (Task 04).

Generates ``web/data/grid_meta.json`` - the shared spatial contract consumed
by the Data Scientist (slope PLAN §5.3, validation §5.7) and Full Stack
(site transform §5.1, astar.js §5.5, Leaflet overlay §5.8) - plus a
deterministic report ``data/processed/grid_meta_report.md``.

Rulings applied (user, 2026-11-13):
- ``pixel_size_m`` = GROUND meters at latitude 18.5 (Option A): x =
  res_x*cos(18.5 deg)/cos(lat_ts), y = res_y. The projected sizes are recorded
  additively as ``pixel_size_projected_m`` with ``ground_ref_lat: 18.5``.
- ``bounds`` = the ACTUAL geographic bounds of the crop raster at full
  precision (Option A). The requested PLAN §5.1 four-decimal frame is recorded
  separately as ``requested_frame``; the subset invariant (requested_frame
  lies fully inside bounds) is validated at runtime.
- Everything is derived LIVE from the raster; hardcoding grid constants is
  forbidden, and PLAN §5.2's example numbers (W=1000, H=1050, ...) are
  examples that must never appear.

Guarantees:
- The DEM is opened read-only and never written; its SHA-256 is re-verified
  after the run to prove it stayed byte-identical.
- Pre-flight validation (validate_dem) rejects rotated/sheared grids,
  non-west-to-east/non-north-up orientation, non-finite geometry (affine
  coefficients, bounds, resolution, dimensions), and +/-infinity pixel
  values outside NoData - before any metadata is generated.
- ``elev_dm_i16.bin`` is NOT created in this task (separate later task).
- Idempotent: reruns produce byte-identical JSON and report (no timestamps,
  no absolute paths, posix relative paths, fixed key order, ASCII only).
- The JSON is written to ``<dest>.part`` first and renamed into place only
  after every check passes (atomic promotion, same pattern as crop_dem.py;
  a failed run keeps the .part for diagnosis).

Run inside the project venv:

    .venv\\Scripts\\python.exe pipeline\\make_grid_meta.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

# --------------------------------------------------------------------- constants

CHUNK = 1 << 20  # 1 MiB streaming hash blocks, same pattern as acquire_dem.py

DEFAULT_DEM = Path("data/processed/dem_20m_crop.tif")
DEFAULT_DEST = Path("web/data/grid_meta.json")
DEFAULT_REPORT = Path("data/processed/grid_meta_report.md")

# PLAN §5.1 clause + user ruling 2026-11-13: meter conversions (slope dx/dy,
# ground distances) are referenced at this latitude.
GROUND_REF_LAT = 18.5

# PLAN §5.2: elevation stored in decimeters (meters x 10) in the future
# elev_dm_i16.bin; slope_u8.bin stores degrees x 4 rounded (PLAN §5.3).
ELEV_SCALE = 10
SLOPE_SCALE = 4

# PLAN §5.2: Int16 little-endian sentinel for the future elev_dm_i16.bin.
# Recorded in the contract NOW so every consumer agrees before the bin exists.
NODATA_ELEV = -32768
# PLAN §5.3: byte 255 marks edges/unknown -> semantically "forbidden"
# (63.75 deg), NOT NoData; kept distinct from nodata_elev on purpose.
SLOPE_EDGE_VALUE = 255

# Int16 representable range for the stored_elev fit check.
INT16_MIN = -32768
INT16_MAX = 32767

# Coverage tolerance in degrees for the requested-frame subset invariant
# (same style and scale as crop_dem.py: a real one-pixel coverage miss is
# ~3.6e-4 deg here and fails ~350,000x above this epsilon).
COVERAGE_TOL_DEG = 1e-9
# Pixel-space epsilon for the margin >= 0 assertion (same 1e-9 scale as
# crop_dem.py's EPS_PX; intentionally different unit from COVERAGE_TOL_DEG).
PX_TOL = 1e-9
# Tolerance for the independent ground pixel-size cross-check (meters).
GROUND_XCHECK_TOL_M = 1e-6
# Axis-alignment tolerance for the affine shear terms b/d (meters). b and d
# are exactly 0.0 in this north-up grid; producer float noise is ~1e-14 m, so
# anything beyond 1 nm is a real rotation/shear (a 0.001 deg rotation over a
# 20 m pixel already yields |b| ~ 3.5e-4 m - rejected ~350,000x above it).
AXIS_TOL_M = 1e-9

# Rover-track Site 1 landing site (lat, lon) per PLAN; used ONLY as a labeled
# decode round-trip sample point, never as a grid anchor.
LANDING_SITE = (18.4446, 77.4509)
# Decode round-trip sample count and fixed seed -> deterministic sample set,
# therefore a deterministic max-error statistic in the report.
ROUNDTRIP_SAMPLES = 999
RANDOM_SEED = 20261113
# Per-axis decode error bound: half a pixel plus a float-noise epsilon for
# points that sit exactly on a pixel boundary.
ROUNDTRIP_TOL_PX = 0.5 + 1e-9

# Provenance tags written into the crop by pipeline/crop_dem.py (Task 03).
REQUIRED_TAGS = (
    "AOI_REQUESTED",
    "AOI_SNAP_RULE",
    "SOURCE_COL0",
    "SOURCE_ROW0",
    "SOURCE_SHA256",
    "SOURCE_FILE",
)

# The exact shared-contract text embedded in grid_meta.json under "notes".
# Consumers parse this recipe; any edit is a BREAKING contract change and
# needs an explicit ruling. ASCII by design (ensure_ascii JSON).
GRID_NOTES = (
    "Jezero Safe Walk shared grid contract (DE1). All processed grids "
    "(dem_20m_crop.tif, elev_dm_i16.bin, slope_u8.bin, ctx_basemap.jpg, "
    "hillshade.png) share width, height and bounds exactly. Indexing: "
    "row 0 = north, col 0 = west, row-major; index = row*width + col. "
    "bounds are outer-corner coordinates of the edge pixels. "
    "(lat,lon) -> (row,col), exactly linear: "
    "col = floor((lon - bounds.lon_min) / deg_per_px_x); "
    "row = floor((bounds.lat_max - lat) / deg_per_px_y); "
    "deg_per_px_x = (bounds.lon_max - bounds.lon_min)/width; "
    "deg_per_px_y = (bounds.lat_max - bounds.lat_min)/height. "
    "Pixel-center decode: lon = bounds.lon_min + (col+0.5)*deg_per_px_x; "
    "lat = bounds.lat_max - (row+0.5)*deg_per_px_y. "
    "Decode domain is half-open: [lon_min, lon_max) x (lat_min, lat_max]; "
    "points exactly on the east/south outer edge yield col == width / "
    "row == height and are outside the grid - always range-check "
    "0 <= col < width and 0 <= row < height. "
    "elev_dm_i16.bin decode: elev_m = int16_le/elev_scale (10 = decimeters); "
    "nodata_elev = -32768. "
    "slope_u8.bin decode: slope_deg = byte/slope_scale (4); byte 255 marks "
    "edges/unknown -> forbidden (63.75 deg), not NoData. "
    "pixel_size_m = GROUND meters at ground_ref_lat 18.5 (slope dx/dy per "
    "PLAN 5.3, distances per 5.6); pixel_size_projected_m = CRS grid units "
    "(20 m). "
    "pixel_m (single scalar for astar.js, PLAN 5.5) = sqrt(pixel_size_m.x * "
    "pixel_size_m.y); diagonal step = pixel_m * sqrt(2) (= sqrt(x^2+y^2) to "
    "<1e-6 m). "
    "requested_frame (PLAN 5.1 four-decimal AOI) lies fully inside bounds "
    "(outward pixel snap). "
    "Vertical reference: elevations as stored in the source DEM product "
    "(docs/sources.md); reconciliation with the rover-track Site frame is "
    "Data Scientist scope (PLAN 5.7)."
)

# WKT1 SPHEROID fallback for body radii, exactly as in crop_dem.py.
SPHEROID_RE = re.compile(r'SPHEROID\["([^"]+)",\s*([0-9.eE+-]+),\s*([0-9.eE+-]+)')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dem(path: Path) -> int:
    """Pre-flight validation: exists, non-empty, opens as GTiff, 1x float32,
    square positive res, CRS + nodata present, provenance tags present."""
    if not path.is_file():
        raise SystemExit(f"[error] DEM not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise SystemExit(f"[error] DEM is empty: {path}")
    try:
        with rasterio.open(path) as ds:
            driver, crs, nodata = ds.driver, ds.crs, ds.nodata
            count, dtype, res = ds.count, (ds.dtypes or [""])[0], ds.res
            tags = ds.tags()
            width, height = ds.width, ds.height
            transform, bounds = ds.transform, ds.bounds
            ds.read(1, window=Window(0, 0, min(8, ds.width), min(8, ds.height)))
            # Full-band scan for +/-infinity pixels OUTSIDE NoData (Task 04
            # hardening): infinite elevations cannot back the decimeter Int16
            # export or elev_range_m. NaN is deliberately NOT rejected here -
            # the existing NaN handling in main() counts it separately and
            # masks it out of the valid set. Pixels equal to NoData are
            # legitimate and are never counted as invalid (a hypothetical
            # inf-valued NoData sentinel is excluded by the != test).
            raw = ds.read(1)
            sentinel = np.float32(nodata)
            inf_count = int(np.count_nonzero(np.isinf(raw) & (raw != sentinel)))
    except Exception as exc:
        raise SystemExit(f"[error] DEM is not a readable raster: {exc}")
    if driver != "GTiff":
        raise SystemExit(f"[error] DEM driver is {driver!r}; expected 'GTiff' (the Task 03 crop)")
    if crs is None:
        raise SystemExit("[error] DEM has no CRS; the grid contract needs the embedded CRS")
    if nodata is None:
        raise SystemExit("[error] DEM has no nodata; the contract must record nodata_elev_dem")
    if count != 1:
        raise SystemExit(f"[error] DEM has {count} bands; expected exactly 1")
    if dtype != "float32":
        raise SystemExit(f"[error] DEM dtype is {dtype!r}; expected 'float32'")
    # Geometry hardening (Task 04): the decode recipe and the bounds/pixel-size
    # contract assume an axis-aligned, north-up, west-to-east, finite grid.
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise SystemExit(
            f"[error] DEM dimensions must be positive integers (width={width!r}, height={height!r})"
        )
    nonfinite_coeffs = [
        name for name, value in (("a", transform.a), ("b", transform.b), ("c", transform.c),
                                 ("d", transform.d), ("e", transform.e), ("f", transform.f))
        if not math.isfinite(value)
    ]
    if nonfinite_coeffs:
        raise SystemExit(
            "[error] DEM affine transform has non-finite coefficients: "
            + ", ".join(f"{name}={getattr(transform, name)!r}" for name in nonfinite_coeffs)
        )
    if abs(transform.b) > AXIS_TOL_M or abs(transform.d) > AXIS_TOL_M:
        raise SystemExit(
            f"[error] DEM grid is rotated or sheared (transform.b={transform.b!r}, "
            f"transform.d={transform.d!r}; an axis-aligned grid requires |b| and |d| "
            f"<= {AXIS_TOL_M!r} m)"
        )
    if transform.a <= 0:
        raise SystemExit(
            f"[error] DEM is not west-to-east: transform.a={transform.a!r} must be > 0 "
            "(the contract's col 0 = west requires a positive x step)"
        )
    if transform.e >= 0:
        raise SystemExit(
            f"[error] DEM is not north-up: transform.e={transform.e!r} must be < 0 "
            "(the contract's row 0 = north requires a negative y step)"
        )
    if not all(math.isfinite(v) for v in (bounds.left, bounds.bottom, bounds.right, bounds.top)):
        raise SystemExit(
            f"[error] DEM bounds are not finite: left={bounds.left!r}, bottom={bounds.bottom!r}, "
            f"right={bounds.right!r}, top={bounds.top!r}"
        )
    if not (math.isfinite(res[0]) and math.isfinite(res[1]) and res[0] > 0 and res[1] > 0):
        raise SystemExit(f"[error] DEM pixel size is not finite and positive: {res!r}")
    if not math.isclose(res[0], abs(res[1]), rel_tol=1e-9, abs_tol=1e-9):
        raise SystemExit(
            f"[error] DEM pixels are not square (res={res!r}); the decode recipe "
            "in grid_meta.json assumes a regular grid"
        )
    missing = [t for t in REQUIRED_TAGS if not tags.get(t)]
    if missing:
        raise SystemExit(
            "[error] DEM is missing provenance tags written by pipeline/crop_dem.py: "
            + ", ".join(missing)
        )
    if inf_count:
        raise SystemExit(
            f"[error] DEM has {inf_count} pixel value(s) at +/-infinity outside NoData; "
            "infinite elevations cannot back the decimeter Int16 contract or elev_range_m"
        )
    print(f"[ok] DEM validation passed ({size} bytes, GTiff {count}x {dtype}, res {res!r}, tags OK)")
    return size


def parse_requested_frame(tag: str) -> dict[str, float]:
    """Parse the AOI_REQUESTED tag into the four-decimal requested frame."""
    pairs = tag.split(";")
    if len(pairs) != 4:
        raise SystemExit(
            f"[error] AOI_REQUESTED tag must have 4 'key=value' pairs, got {len(pairs)}: {tag!r}"
        )
    frame: dict[str, float] = {}
    try:
        for pair in pairs:
            key, value = pair.split("=", 1)
            frame[key.strip()] = float(value)
    except ValueError as exc:
        raise SystemExit(f"[error] AOI_REQUESTED tag is malformed ({tag!r}): {exc}")
    expected = {"lon_min", "lon_max", "lat_min", "lat_max"}
    if set(frame) != expected:
        raise SystemExit(
            f"[error] AOI_REQUESTED tag must contain exactly {sorted(expected)}; got {sorted(frame)}"
        )
    return frame


def parse_origin_index(tag_value: str, tag_name: str) -> int:
    """Parse SOURCE_COL0/SOURCE_ROW0 into a non-negative 0-based int."""
    try:
        value = int(tag_value)
    except ValueError as exc:
        raise SystemExit(f"[error] {tag_name} tag is not an integer ({tag_value!r}): {exc}")
    if value < 0:
        raise SystemExit(f"[error] {tag_name} tag is negative ({value}); the crop grid is 0-based")
    return value


def parse_source_sha256(tag_value: str) -> str:
    """Parse SOURCE_SHA256 into a 64-char lowercase hex digest."""
    if not re.fullmatch(r"[0-9a-f]{64}", tag_value):
        raise SystemExit(
            f"[error] SOURCE_SHA256 tag is not a 64-char lowercase hex digest ({tag_value!r})"
        )
    return tag_value


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


def haversine_m(
    lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float, radius_m: float
) -> float:
    """Great-circle arc distance on a sphere: 2R*asin(sqrt(haversine))."""
    phi1, phi2 = math.radians(lat1_deg), math.radians(lat2_deg)
    dphi = phi2 - phi1
    dlam = math.radians(lon2_deg - lon1_deg)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(h))


def strip_no_defs_flag(proj4: str) -> str:
    """Drop ONE trailing ``+no_defs`` / ``+no_defs=True`` token from a proj4 string.

    The flag carries no information; the ``=True`` form is a rasterio/GDAL
    serialization quirk (this CRS's to_proj4() emits it) that some JSON
    consumers' parsers reject. The authoritative CRS remains the GeoTIFF's
    embedded WKT; the recorded string is a convenience projection only.
    """
    return re.sub(r"\s\+no_defs(=True)?$", "", proj4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    # CLI distinct-paths guard (same as crop_dem.py): a --dest or --report
    # resolving onto --dem would let the os.replace promotion replace the
    # measured raster itself; pairwise-distinct resolved paths keep "DEM never
    # written" true even under misuse.
    resolves = {p.resolve() for p in (args.dem, args.dest, args.report)}
    if len(resolves) < 3:
        raise SystemExit("[error] --dem, --dest and --report must be distinct paths")

    print("[info] elev_dm_i16.bin is NOT created in this task (separate later task)")
    dem_size = validate_dem(args.dem)
    sha_before = sha256_of(args.dem)

    # ------------------------------------------------ measurements (live)
    with rasterio.open(args.dem) as src:
        width, height = src.width, src.height
        res_x, res_y = src.res[0], abs(src.res[1])
        transform = src.transform
        proj_bounds = src.bounds
        nodata_dem = src.nodata
        src_crs = src.crs
        driver = src.driver
        proj4_raw = (src_crs.to_proj4() or "").strip()
        tags = src.tags()

        # ------------------------------------------------- 2: parse tags
        requested = parse_requested_frame(tags["AOI_REQUESTED"])
        source_col0 = parse_origin_index(tags["SOURCE_COL0"], "SOURCE_COL0")
        source_row0 = parse_origin_index(tags["SOURCE_ROW0"], "SOURCE_ROW0")
        source_sha = parse_source_sha256(tags["SOURCE_SHA256"])
        print(
            f"[ok] provenance tags parsed: frame lon {requested['lon_min']}.."
            f"{requested['lon_max']} lat {requested['lat_min']}..{requested['lat_max']}, "
            f"origin col0={source_col0} row0={source_row0}, snap={tags['AOI_SNAP_RULE']!r}"
        )

        # ------------------------------ 3: geographic bounds (live warp)
        # Geographic lon/lat CRS on the SAME body (Mars): radii via the
        # two-stage body_radii (for THIS CRS to_proj4() emits the sphere form
        # +R=..., so the WKT SPHEROID branch is the exercised one). Never an
        # Earth CRS, so AOI degrees and file meters share one reference.
        a_r, b_r, radii_src = body_radii(src_crs)
        geo_crs = geographic_body_crs(src_crs)
        corners = [
            transform * (0, 0), transform * (width, 0),
            transform * (0, height), transform * (width, height),
        ]
        xs, ys = warp_transform(
            src_crs, geo_crs,
            [c[0] for c in corners], [c[1] for c in corners],
        )
        # Equirectangular is axis-aligned, so min/max over the corners is exact.
        lon_min, lon_max = min(xs), max(xs)
        lat_min, lat_max = min(ys), max(ys)
        print(
            f"[ok] geographic bounds (outer corners): lon [{lon_min!r}, {lon_max!r}], "
            f"lat [{lat_min!r}, {lat_max!r}]"
        )

        # ------------------------------------- 9 (crs key): recorded string
        crs_str = strip_no_defs_flag(proj4_raw)
        crs_ok = (
            "+proj=eqc" in crs_str
            and "+lat_ts=" in crs_str
            and ("+R=" in crs_str or "+a=" in crs_str)
        )
        if not crs_ok:
            print(
                f"[error] recorded CRS string failed sanity check: {crs_str!r} "
                "(expected an Equirectangular Mars proj4 with lat_ts and a body radius)",
                file=sys.stderr,
            )
            return 1
        print(f"[ok] CRS recorded as: {crs_str}")

        # ------------------------------------------- 4: ground pixel sizes
        m_lat_ts = re.search(r"\+lat_ts=([0-9.eE+-]+)", proj4_raw)
        if not m_lat_ts:
            # This DEM's CRS always emits +lat_ts (standard parallel); a CRS
            # without it would need an explicit ruling before proceeding.
            print(
                "[error] +lat_ts not found in the DEM proj4 string; the "
                "ground-scale conversion needs the standard parallel",
                file=sys.stderr,
            )
            return 1
        lat_ts = float(m_lat_ts[1])
        # x: one projected pixel spans res_x CRS meters, but east-west GROUND
        # meters shrink by cos(lat); the projection stretches them back by
        # 1/cos(lat_ts), so the ground size at GROUND_REF_LAT is
        # res_x * cos(lat_ref) / cos(lat_ts).
        # y: equirectangular y = R*phi (lat_ts does not enter), so projected
        # y-meters are true ground meters at EVERY latitude on the sphere -
        # y_ground is exactly res_y.
        x_ground = res_x * math.cos(math.radians(GROUND_REF_LAT)) / math.cos(math.radians(lat_ts))
        y_ground = res_y
        pixel_m = math.sqrt(x_ground * y_ground)

        # ------------------------------------ 5: independent cross-check
        # Recompute one pixel's ground size by warping two probes to the
        # geographic CRS and measuring great-circle arcs - independent of the
        # formula above because it exercises GDAL/PROJ itself.
        lon_mid = (lon_min + lon_max) / 2
        bx, by = warp_transform(geo_crs, src_crs, [lon_mid], [GROUND_REF_LAT])
        x0, y0 = bx[0], by[0]
        back_lon, back_lat = warp_transform(
            src_crs, geo_crs,
            [x0, x0 + res_x, x0],
            [y0, y0, y0 - res_y],
        )
        # Great-circle arcs on the sphere from the CRS body radius (this body
        # is spherical: the SPHEROID flattening is 0, so a == b).
        d_x = haversine_m(back_lat[0], back_lon[0], back_lat[1], back_lon[1], a_r)
        d_y = haversine_m(back_lat[0], back_lon[0], back_lat[2], back_lon[2], a_r)
        delta_x = abs(d_x - x_ground)
        delta_y = abs(d_y - y_ground)
        xcheck_ok = delta_x <= GROUND_XCHECK_TOL_M and delta_y <= GROUND_XCHECK_TOL_M
        if not xcheck_ok:
            print(
                f"[error] ground pixel-size cross-check failed: "
                f"|d_x - x_ground|={delta_x!r} m, |d_y - y_ground|={delta_y!r} m "
                f"(tolerance {GROUND_XCHECK_TOL_M} m)",
                file=sys.stderr,
            )
            return 1
        print(
            f"[ok] ground pixel-size cross-check: d_x={d_x!r} m, d_y={d_y!r} m "
            f"(deltas {delta_x!r}, {delta_y!r} m)"
        )

        # ------------------------------------------------- 6: elevations
        raw = src.read(1)
        sentinel_count = int(np.count_nonzero(raw == np.float32(nodata_dem)))
        nan_count = int(np.count_nonzero(np.isnan(raw)))
        valid = raw[~((raw == np.float32(nodata_dem)) | np.isnan(raw))]
        if valid.size == 0:
            print("[error] DEM has no valid pixels; elev_range_m would be empty", file=sys.stderr)
            return 1
        elev_min = float(valid.min())
        elev_max = float(valid.max())
        print(
            f"[ok] elevations: {valid.size} valid px of {raw.size}, "
            f"range [{elev_min!r}, {elev_max!r}] m, sentinel={sentinel_count}, NaN={nan_count}"
        )

        # ------------------------------------ 8: coverage of requested frame
        # Projected frame of the requested frame (four corners; min/max is
        # exact for the axis-aligned Equirectangular), then per-side margins
        # in crop-grid pixels (same formulas as crop_dem.py check i).
        req_lons = [requested["lon_min"], requested["lon_max"],
                    requested["lon_min"], requested["lon_max"]]
        req_lats = [requested["lat_min"], requested["lat_min"],
                    requested["lat_max"], requested["lat_max"]]
        rx, ry = warp_transform(geo_crs, src_crs, req_lons, req_lats)
        x_west, x_east = min(rx), max(rx)
        y_south, y_north = min(ry), max(ry)
        margin_px = {
            "west": (x_west - proj_bounds.left) / res_x,
            "east": (proj_bounds.right - x_east) / res_x,
            "north": (proj_bounds.top - y_north) / res_y,
            "south": (y_south - proj_bounds.bottom) / res_y,
        }
        # Meter margins via degrees: m/deg lat = pi*a/180 (body radius a);
        # m/deg lon at GROUND_REF_LAT = that * cos(lat_ref); the projected
        # m/deg lon = m/deg lat * cos(lat_ts) converts pixel meters to degrees.
        m_per_deg_lat = math.pi * a_r / 180.0
        m_per_deg_lon_ground = m_per_deg_lat * math.cos(math.radians(GROUND_REF_LAT))
        m_per_deg_lon_proj = m_per_deg_lat * math.cos(math.radians(lat_ts))
        margin_m = {
            "west": margin_px["west"] * res_x / m_per_deg_lon_proj * m_per_deg_lon_ground,
            "east": margin_px["east"] * res_x / m_per_deg_lon_proj * m_per_deg_lon_ground,
            "north": margin_px["north"] * res_y,
            "south": margin_px["south"] * res_y,
        }
        # Two-space tolerance assertion (crop_dem.py style): margins must be
        # non-negative in pixel space, and the requested frame must lie within
        # the geographic bounds +/- COVERAGE_TOL_DEG in degree space.
        margins_nonneg = all(m >= -PX_TOL for m in margin_px.values())
        deg_cover = (
            requested["lon_min"] >= lon_min - COVERAGE_TOL_DEG
            and requested["lon_max"] <= lon_max + COVERAGE_TOL_DEG
            and requested["lat_min"] >= lat_min - COVERAGE_TOL_DEG
            and requested["lat_max"] <= lat_max + COVERAGE_TOL_DEG
        )
        cover_ok = margins_nonneg and deg_cover
        if not cover_ok:
            print(
                "[error] requested frame is not fully covered by the DEM raster:\n"
                f"  margins (px): {margin_px!r}\n"
                f"  geographic bounds: lon [{lon_min!r}, {lon_max!r}], "
                f"lat [{lat_min!r}, {lat_max!r}]",
                file=sys.stderr,
            )
            return 1
        print(f"[ok] requested frame fully covered; margins (px): {margin_px!r}")

    # ------------------------------------------------ checks ledger
    # Rows are rendered sorted by name in the report (§8), so append order is
    # free; the promotion gate below is the single point that must see all
    # pre-promotion rows PASS.
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    # Check (a) has no boolean: validate_dem/parse_* abort via SystemExit, so
    # reaching this point PROVES the tags were present and parseable.
    record("a. provenance tags present and parseable", True,
           f"AOI_REQUESTED -> 4 keys; SOURCE_COL0={source_col0}, SOURCE_ROW0={source_row0}; "
           f"SOURCE_SHA256={source_sha[:12]}... (64 hex); "
           f"AOI_SNAP_RULE={tags['AOI_SNAP_RULE']!r}; SOURCE_FILE={tags['SOURCE_FILE']!r}")
    record("b. recorded CRS string sanity", crs_ok,
           f"crs={crs_str!r}; stripped one trailing +no_defs flag; contains "
           "+proj=eqc, +lat_ts=, and a body radius token")
    record("d. requested frame fully covered", cover_ok,
           f"margins (px): west={margin_px['west']!r}, east={margin_px['east']!r}, "
           f"north={margin_px['north']!r}, south={margin_px['south']!r}; meter margins "
           f"{margin_m!r}; px-space >= -{PX_TOL} and deg-space within +/-{COVERAGE_TOL_DEG}")
    record("e. ground pixel-size cross-check", xcheck_ok,
           f"x_ground={x_ground!r} m vs warp d_x={d_x!r} m (delta {delta_x!r} m); "
           f"y_ground={y_ground!r} m vs warp d_y={d_y!r} m (delta {delta_y!r} m); "
           f"tolerance {GROUND_XCHECK_TOL_M} m")

    # ------------------------------------------------ 7: Int16 fit check
    # Rounding-mode-AGNOSTIC by construction: floor() of the minimum and
    # ceil() of the maximum bracket EVERY per-pixel rounding of
    # elev_m * ELEV_SCALE (truncation, round-half-up, round-half-even all land
    # inside [stored_lo, stored_hi]), so the fit does not depend on which
    # rounding the future elev_dm_i16.bin task chooses. The sentinel must
    # additionally stay OUTSIDE that bracket: if a representable valid value
    # could equal NODATA_ELEV, decoders could not tell data from NoData.
    stored_lo = math.floor(elev_min * ELEV_SCALE)
    stored_hi = math.ceil(elev_max * ELEV_SCALE)
    int16_ok = (
        stored_lo >= INT16_MIN
        and stored_hi <= INT16_MAX
        and not (stored_lo <= NODATA_ELEV <= stored_hi)
    )
    if not int16_ok:
        print(
            f"[error] elevation range does not fit the Int16 contract: stored "
            f"range [{stored_lo}, {stored_hi}] vs Int16 [{INT16_MIN}, {INT16_MAX}], "
            f"and sentinel {NODATA_ELEV} must stay outside the stored range",
            file=sys.stderr,
        )
        return 1
    record("c. elevations fit Int16, sentinel distinct", int16_ok,
           f"valid range [{elev_min!r}, {elev_max!r}] m; x{ELEV_SCALE} -> stored "
           f"[{stored_lo}, {stored_hi}] within [{INT16_MIN}, {INT16_MAX}]; sentinel "
           f"{NODATA_ELEV} outside stored range (headroom {stored_lo - INT16_MIN} lo / "
           f"{INT16_MAX - stored_hi} hi); sentinel px={sentinel_count}, NaN px={nan_count}")
    print(f"[ok] Int16 fit: stored range [{stored_lo}, {stored_hi}], sentinel distinct")

    # ------------------------------------------------ 9: build the JSON dict
    # Key order IS part of the contract: insertion order preserved by
    # json.dumps (sort_keys is deliberately NOT used).
    data = {
        "width": width,
        "height": height,
        "bounds": {
            "lon_min": lon_min, "lon_max": lon_max,
            "lat_min": lat_min, "lat_max": lat_max,
        },
        "requested_frame": {
            "lon_min": requested["lon_min"], "lon_max": requested["lon_max"],
            "lat_min": requested["lat_min"], "lat_max": requested["lat_max"],
        },
        "bounds_are": "outer_corners",
        "pixel_size_m": {"x": x_ground, "y": y_ground},
        "pixel_size_projected_m": {"x": res_x, "y": res_y},
        "ground_ref_lat": GROUND_REF_LAT,
        "pixel_m": pixel_m,
        "elev_scale": ELEV_SCALE,
        "slope_scale": SLOPE_SCALE,
        "nodata_elev": NODATA_ELEV,
        "nodata_elev_dem": nodata_dem,
        "slope_edge_value": SLOPE_EDGE_VALUE,
        "row0": "north",
        "col0": "west",
        "layout": "row_major",
        "crs": crs_str,
        "elev_range_m": [elev_min, elev_max],
        "provenance": {
            "dem_file": args.dem.as_posix(),
            "dem_sha256": sha_before,
            "source_dem": tags["SOURCE_FILE"],
            "source_dem_sha256": source_sha,
            "source_col0": source_col0,
            "source_row0": source_row0,
            "snap_rule": tags["AOI_SNAP_RULE"],
        },
        "notes": GRID_NOTES,
    }

    # --------------------------------------------- 10: decode round-trip
    # The notes recipe must invert: encode (lat,lon) -> (row,col) via floor(),
    # decode the pixel center, and land back within half a pixel per axis.
    # The +1e-9 epsilon admits the exact-boundary case (error exactly 0.5 px)
    # for points that sit ON a pixel edge.
    deg_px_x = (lon_max - lon_min) / width
    deg_px_y = (lat_max - lat_min) / height
    samples = [
        (requested["lon_min"], requested["lat_min"]),
        (requested["lon_max"], requested["lat_min"]),
        (requested["lon_min"], requested["lat_max"]),
        (requested["lon_max"], requested["lat_max"]),
        (LANDING_SITE[1], LANDING_SITE[0]),  # constant is (lat, lon) -> (lon, lat)
    ]
    rng = random.Random(RANDOM_SEED)  # fixed seed -> deterministic sample set
    for _ in range(ROUNDTRIP_SAMPLES):
        samples.append((
            rng.uniform(requested["lon_min"], requested["lon_max"]),
            rng.uniform(requested["lat_min"], requested["lat_max"]),
        ))
    rt_out_of_range = 0
    rt_max_err = 0.0
    for lon, lat in samples:
        col = math.floor((lon - lon_min) / deg_px_x)
        row = math.floor((lat_max - lat) / deg_px_y)
        if not (0 <= col < width and 0 <= row < height):
            rt_out_of_range += 1
            continue
        lon_c = lon_min + (col + 0.5) * deg_px_x
        lat_c = lat_max - (row + 0.5) * deg_px_y
        rt_max_err = max(
            rt_max_err,
            abs(lon - lon_c) / deg_px_x,
            abs(lat - lat_c) / deg_px_y,
        )
    rt_ok = rt_out_of_range == 0 and rt_max_err < ROUNDTRIP_TOL_PX
    if not rt_ok:
        print(
            f"[error] decode round-trip failed: points={len(samples)}, "
            f"out_of_range={rt_out_of_range}, max per-axis error={rt_max_err!r} px "
            f"(tolerance {ROUNDTRIP_TOL_PX} px)",
            file=sys.stderr,
        )
        return 1
    record("f. decode round-trip", rt_ok,
           f"{len(samples)} points (4 requested-frame corners + landing site + "
           f"{ROUNDTRIP_SAMPLES} seeded uniform, seed {RANDOM_SEED}); "
           f"out-of-range={rt_out_of_range}; max per-axis pixel error "
           f"{rt_max_err!r} < {ROUNDTRIP_TOL_PX} px")
    print(f"[ok] decode round-trip: {len(samples)} points, max error {rt_max_err!r} px")

    # ---------------------------------------------- 11: write JSON (.part)
    dest = args.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")  # -> grid_meta.json.part
    try:
        partial.write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",  # pin LF so the recorded size/sha hold on any OS checkout
        )
        with partial.open("r", encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[error] writing or parsing the partial JSON failed: {exc}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    # Exact dict equality: json.dumps serializes floats via their shortest
    # round-tripping repr, so parsed == data proves every float survived.
    json_ok = parsed == data
    if not json_ok:
        print(
            "[error] JSON round-trip mismatch: the reopened .part differs from "
            "the built dict",
            file=sys.stderr,
        )
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    record("g. JSON .part round-trip", json_ok,
           "json.dumps(indent=2, ensure_ascii=True) + newline; reopened with "
           "json.load; parsed == built dict exactly (float round-trip via repr)")
    print(f"[ok] partial JSON written and round-tripped: {partial}")

    # (i) DEM unchanged: hash again only after every read handle is closed
    sha_after = sha256_of(args.dem)
    dem_unchanged = sha_after == sha_before
    if not dem_unchanged:
        print(
            f"[error] DEM INTEGRITY FAILURE: SHA-256 changed during the run "
            f"(before {sha_before}, after {sha_after}); nothing promoted",
            file=sys.stderr,
        )
        return 1
    record("i. DEM unchanged (SHA-256)", dem_unchanged,
           f"after={sha_after} == before={sha_before} == provenance dem_sha256")
    print(f"[ok] DEM unchanged during the run: {sha_after}")

    # NOTE: every recorded boolean is True-by-construction on the success path
    # (each False condition returns 1 earlier), so this gate is a fail-safe
    # invariant and audit point for FUTURE ledger rows - do not rely on it
    # alone, and do not delete it as "dead code".
    if not all(ok for _, ok, _ in checks):
        failed = [f"  {name}: {detail}" for name, ok, detail in checks if not ok]
        print(
            f"[error] validation FAILED ({len(failed)} of {len(checks)} checks); "
            "grid_meta.json NOT promoted",
            file=sys.stderr,
        )
        for line in failed:
            print(f"[error] {line}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    print(f"[ok] validation passed: {len(checks)}/{len(checks)} checks")

    # ------------------------------------------------ atomic promotion
    try:
        os.replace(partial, dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial JSON failed: {exc}", file=sys.stderr)
        print(f"[info] partial kept for diagnosis: {partial}", file=sys.stderr)
        return 1
    try:
        with dest.open("r", encoding="utf-8") as fh:
            promoted = json.load(fh)
        promoted_ok = promoted == data
    except (OSError, ValueError) as exc:
        print(f"[error] promoted JSON is not readable: {exc}", file=sys.stderr)
        return 1
    if not promoted_ok:
        print("[error] promoted JSON differs from the validated dict", file=sys.stderr)
        return 1
    dest_size = dest.stat().st_size
    dest_sha = sha256_of(dest)
    record("h. promotion and promoted file readable", True,
           f"os.replace({partial.name} -> {dest.name}); reopened with json.load OK; "
           f"size={dest_size} bytes, sha256={dest_sha}")
    print(f"[ok] promoted: {dest} ({dest_size} bytes)")

    # ---------------------------------------- 12: deterministic report
    # ASCII content throughout (spec), no timestamps, no absolute paths.
    margin_table = "\n".join(
        f"| {side} | {req_deg:.4f} | {act_deg!r} | {margin_px[side]!r} | {margin_m[side]!r} |"
        for side, req_deg, act_deg in (
            ("west", requested["lon_min"], lon_min),
            ("east", requested["lon_max"], lon_max),
            ("north", requested["lat_max"], lat_max),
            ("south", requested["lat_min"], lat_min),
        )
    )
    checks_table = "\n".join(
        f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |"
        for name, ok, detail in sorted(checks, key=lambda row: row[0])
    )

    report = f"""# Grid Metadata Report - shared spatial contract (grid_meta.json)

Task 04 deliverable - generated by `pipeline/make_grid_meta.py` from measured
values only. The DEM is opened read-only and never written (SHA-256 re-verified
at the end of the run). elev_dm_i16.bin is NOT created in this task.

## 0. Rulings applied (user, 2026-11-13)

- pixel_size_m = GROUND meters at latitude 18.5 (Option A): x =
  res_x * cos(18.5 deg) / cos(lat_ts), y = res_y. The projected sizes are
  recorded additively as pixel_size_projected_m with ground_ref_lat 18.5.
- bounds = the ACTUAL geographic bounds of the crop raster at full precision
  (Option A). The requested PLAN 5.1 four-decimal frame is recorded separately
  as requested_frame; the subset invariant (requested_frame contained in
  bounds) is validated at runtime (check d in section 8).
- All values are derived LIVE from the raster; PLAN 5.2's example numbers
  (W=1000, H=1050, ...) are examples and never appear in the artifacts.

## 1. Source identity (DEM)

| Item | Value |
|---|---|
| DEM file | `{args.dem.as_posix()}` |
| File size | {dem_size} bytes |
| SHA-256 (live, before) | `{sha_before}` |
| SHA-256 (after) | `{sha_after}` |
| Unchanged by this run | {'YES' if sha_after == sha_before else 'NO - INTEGRITY FAILURE'} |
| Driver / bands / dtype | {driver} / 1 / float32 |
| NoData | {nodata_dem!r} |

## 2. Grid (measured from the DEM)

| Item | Value |
|---|---|
| Dimensions | {width} x {height} px |
| Pixel resolution (projected m) | x={res_x!r}, y={res_y!r} |
| Affine transform | a={transform.a!r}, b={transform.b!r}, c={transform.c!r}, d={transform.d!r}, e={transform.e!r}, f={transform.f!r} |
| CRS as recorded in JSON | `{crs_str}` |
| CRS note | one trailing `+no_defs` flag stripped from to_proj4(); the authoritative CRS is the GeoTIFF's embedded WKT (Equirectangular Mars sphere, radii a={a_r!r} m, b={b_r!r} m via {radii_src}) |

## 3. Actual geographic bounds vs requested frame

Bounds are outer-corner coordinates (warp of the four raster corners to the
same-body geographic CRS; exact for the axis-aligned Equirectangular).

| Item | Value |
|---|---|
| Actual bounds (deg, full precision) | lon {lon_min!r} .. {lon_max!r}, lat {lat_min!r} .. {lat_max!r} |
| Requested frame (deg, four-decimal form as approved) | lon {requested['lon_min']:.4f} .. {requested['lon_max']:.4f}, lat {requested['lat_min']:.4f} .. {requested['lat_max']:.4f} |

| Side | Requested (deg) | Actual DEM bound (deg) | Margin (px) | Margin (m) |
|---|---|---|---|---|
{margin_table}

Margins are measured in projected space (px) and converted to meters via
m/deg lat = pi*a/180 (a={a_r!r}) and m/deg lon at {GROUND_REF_LAT} deg = that *
cos({GROUND_REF_LAT} deg).

**Verdict: {'REQUESTED FRAME FULLY COVERED' if cover_ok else 'REQUESTED FRAME NOT COVERED'}**
(px margins >= -{PX_TOL}; degree space within +/-{COVERAGE_TOL_DEG})

## 4. Pixel sizes (ground vs projected)

| Item | Value |
|---|---|
| Formula inputs | res_x={res_x!r} m, lat_ts={lat_ts!r} deg, ground_ref_lat={GROUND_REF_LAT} deg |
| x_ground = res_x*cos(18.5)/cos(lat_ts) | {x_ground!r} m |
| y_ground = res_y (equirectangular y = R*phi, true ground meters) | {y_ground!r} m |
| pixel_m = sqrt(x_ground*y_ground) | {pixel_m!r} m |
| pixel_size_projected_m | x={res_x!r}, y={res_y!r} (CRS grid units) |

Independent cross-check (warp a probe pixel to geographic, measure
great-circle arcs on the body sphere, radius a={a_r!r} m):

| Item | Value |
|---|---|
| d_x (x direction) | {d_x!r} m, delta vs x_ground {delta_x!r} m |
| d_y (y direction) | {d_y!r} m, delta vs y_ground {delta_y!r} m |
| Tolerance | {GROUND_XCHECK_TOL_M} m each |

## 5. Elevations

| Item | Value |
|---|---|
| Total pixels | {width * height} |
| Sentinel pixels (== nodata) | {sentinel_count} |
| NaN pixels | {nan_count} |
| Valid pixels | {valid.size} |
| elev_min (m) | {elev_min!r} |
| elev_max (m) | {elev_max!r} |
| Stored Int16 fit | floor(elev_min*{ELEV_SCALE})={stored_lo}, ceil(elev_max*{ELEV_SCALE})={stored_hi}, within [{INT16_MIN}, {INT16_MAX}]: {'YES' if stored_lo >= INT16_MIN and stored_hi <= INT16_MAX else 'NO'} |
| Sentinel distinctness | nodata_elev {NODATA_ELEV} outside stored range: {'YES' if not (stored_lo <= NODATA_ELEV <= stored_hi) else 'NO'} (rounding-mode-agnostic bracket) |

## 6. Decode round-trip (notes recipe vs actual bounds)

| Item | Value |
|---|---|
| Sample points | {len(samples)} (4 requested-frame corners + landing site (lat {LANDING_SITE[0]}, lon {LANDING_SITE[1]}) + {ROUNDTRIP_SAMPLES} seeded uniform, seed {RANDOM_SEED}) |
| deg_per_px_x / deg_per_px_y | {deg_px_x!r} / {deg_px_y!r} deg |
| Decode domain | half-open: [lon_min, lon_max) x (lat_min, lat_max]; the east/south outer edge maps to col == width / row == height (outside the grid) - always range-check |
| Out-of-range indices | {rt_out_of_range} |
| Max per-axis pixel error | {rt_max_err!r} px |
| Threshold | < {ROUNDTRIP_TOL_PX} px (half pixel + float-noise epsilon) |
| Verdict | {'PASS' if rt_ok else 'FAIL'} |

## 7. JSON artifact

| Item | Value |
|---|---|
| File | `{dest.as_posix()}` |
| File size | {dest_size} bytes |
| SHA-256 | `{dest_sha}` |
| Top-level keys | {len(data)} (fixed insertion order, sort_keys not used) |
| Serialization | json.dumps(indent=2, ensure_ascii=True) + trailing newline |
| Round-trip | .part reopened with json.load and compared equal before promotion; promoted file re-read and compared equal after |

## 8. Checks

All checks were enforced before or at promotion; a failure aborts with exit
code 1 and keeps the .part for diagnosis.

| Check | Result | Measured detail |
|---|---|---|
{checks_table}

## 9. Environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}
- Script: `pipeline/make_grid_meta.py` (rerunnable; deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.report.write_text(report, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[error] writing the grid metadata report failed: {exc}", file=sys.stderr)
        return 1
    print(f"[ok] report written: {args.report}")
    print(
        f"[summary] grid {width}x{height}, pixel_size_m=({x_ground!r}, {y_ground!r}) m "
        f"ground at {GROUND_REF_LAT} deg, bounds lon [{lon_min!r}, {lon_max!r}] "
        f"lat [{lat_min!r}, {lat_max!r}], dest={dest.as_posix()}, sha256={dest_sha}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
