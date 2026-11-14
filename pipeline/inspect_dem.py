"""Read-only inspection of the raw USGS Jezero CTX DEM (Task 02).

Opens the original GeoTIFF without cropping, resampling, reprojecting, or
modifying it, measures all required metadata and elevation statistics, assesses
geographic coverage against the project frame, cross-checks measurements against
the official PDS4 label (documentation evidence, cited inline), and writes a
deterministic markdown report. The source file is never written to; its
SHA-256 is re-verified at the end of the run to prove it.

Run inside the project venv:

    .venv\\Scripts\\python.exe pipeline\\inspect_dem.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

CHUNK = 1 << 20

# Project frame from the shared data contract (docs/PLAN.md §5.1). Used for the
# coverage assessment only - no cropping or grid decisions happen in this task.
PROJECT_BOUNDS = {
    "lon_min": 77.2229, "lon_max": 77.5840,
    "lat_min": 18.3068, "lat_max": 18.6693,
}
# docs/sources.md ("Area of interest") registers the same frame at higher
# precision than PLAN §5.1's four-decimal values. Both sets are reported for the
# Task 03 snap ruling; which one governs is an OPEN DECISION, not made here.
PRECISE_BOUNDS = {
    "lon_min": 77.2229331, "lon_max": 77.583964,
    "lat_min": 18.3067994, "lat_max": 18.669315,
}
PROJECT_LAT_REF = 18.5  # PLAN §5.1: meter conversions are referenced at this latitude
COVERAGE_TOL_DEG = 1e-9

DEFAULT_SOURCE = Path("data/raw/M20_JezeroCrater_CTXDEM_20m.tif")
DEFAULT_REPORT = Path("data/processed/dem_inspection_report.md")

# Reference values transcribed from the official PDS4 label
# https://astrogeology.usgs.gov/ckan/dataset/f8ef46b8-d512-4c46-b825-fe9633c38e1c/
# resource/5691ea08-1db4-4018-a341-e415e716add7/download/m20_jezerocrater_ctxdem_20m.xml
# (fetched 2026-11-13). Used ONLY as documentation cross-checks; the GeoTIFF's
# own measurements remain the primary evidence.
PDS4_REFERENCE = {
    "title": "Mars 2020 Science Investigation CTX DEM Mosaic",
    "lid": "urn:nasa:pds:mars2020_ctx_basemap_2021:data:m20_ctxdem_mosaic",
    "version": "1.0",
    "file_name": "M20_JezeroCrater_CTXDEM_20m.tif",
    "width": 4456,
    "height": 5067,
    "bands": 1,
    "data_type": "IEEE754LSBSingle",
    "missing_constant": -3.4028234663852886e+38,
    "projection": "Equirectangular",
    "lat_0": 0.0,
    "lat_ts": 18.4663,
    "lon_0": 0.0,
    "a_axis_radius_m": 3396190.0,
    "b_axis_radius_m": 3396190.0,
    "c_axis_radius_m": 3396190.0,
    "latitude_type": "Planetocentric",
    "longitude_direction": "Positive East",
    "upperleft_x_m": 4328999.99999999814,
    "upperleft_y_m": 1143420.00000000279,
    "pixel_resolution_m": 20.0,
    "pixel_scale_px_per_deg": 2963.73487616531111,
    "west_deg": 76.9974370614600048,
    "east_deg": 78.5825633240881842,
    "north_deg": 19.2901870068661516,
    "south_deg": 17.5805199105447514,
}

SPHEROID_RE = re.compile(r'SPHEROID\["([^"]+)",\s*([0-9.eE+-]+),\s*([0-9.eE+-]+)')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_source(path: Path) -> int:
    """Pre-inspection validation: exists, non-empty, opens, tiny read works."""
    if not path.is_file():
        raise SystemExit(f"[error] source not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise SystemExit(f"[error] source is empty: {path}")
    try:
        with rasterio.open(path) as ds:
            probe = ds.read(
                1, window=Window(0, 0, min(8, ds.width), min(8, ds.height))
            )
            if probe.size == 0:
                raise ValueError("empty probe read")
    except Exception as exc:
        raise SystemExit(f"[error] source is not a readable raster: {exc}")
    print(f"[ok] source validation passed ({size} bytes)")
    return size


def body_radii(crs: "rasterio.crs.CRS") -> tuple[float, float, str]:
    """Semi-major/minor radii of the CRS body, parsed from proj4 or WKT."""
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
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    validate_source(args.source)
    sha_start = sha256_of(args.source)

    prov_path = args.source.with_name(args.source.name + ".provenance.json")
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.is_file() else {}

    with rasterio.open(args.source) as ds:
        # ---------------------------------------------------------------- meta
        profile = dict(ds.profile)
        tags = ds.tags()
        band_tags = ds.tags(1)
        width, height, count = ds.width, ds.height, ds.count
        dtypes = list(ds.dtypes)
        driver = ds.driver
        nodata = ds.nodata
        transform = ds.transform
        res = ds.res
        bounds = ds.bounds
        block_shapes = ds.block_shapes
        band_units = ds.units
        band_scales = ds.scales
        band_offsets = ds.offsets
        crs = ds.crs
        if crs is None:
            raise SystemExit("[error] source has no CRS; cannot inspect spatially")
        wkt1 = crs.to_wkt()
        try:
            wkt2 = crs.to_wkt(version="WKT2_2019")
        except TypeError:
            wkt2 = wkt1
        try:
            authority = crs.to_authority()
        except Exception as exc:
            authority = f"unresolvable ({type(exc).__name__})"
        is_geo = crs.is_geographic
        linear_units = crs.linear_units
        angular_units = ("degree (implied by geographic CRS)"
                         if is_geo else "n/a (projected CRS; linear units above)")
        a_r, b_r, radii_src = body_radii(crs)
        sphere = abs(a_r - b_r) < 1e-6

        # ------------------------------------------------------- statistics
        raw = ds.read(1)
        total_px = int(raw.size)
        if nodata is not None:
            nodata_mask = raw == np.float32(nodata)
        else:
            nodata_mask = np.zeros(raw.shape, dtype=bool)
        nan_mask = np.isnan(raw) if raw.dtype.kind == "f" else np.zeros(raw.shape, dtype=bool)
        invalid_mask = nodata_mask | nan_mask
        valid_arr = raw[~invalid_mask]
        valid_count = int(valid_arr.size)
        nodata_count = int(nodata_mask.sum())
        nan_count = int(nan_mask.sum())
        if valid_count == 0:
            raise SystemExit("[error] no valid pixels found; cannot compute statistics")
        f64 = valid_arr.astype(np.float64)
        v_min, v_max = float(f64.min()), float(f64.max())
        v_mean, v_std = float(f64.mean()), float(f64.std())  # population std (ddof=0)
        # representative values: 10 evenly spaced valid pixels
        idx = np.linspace(0, valid_arr.size - 1, num=min(10, valid_arr.size), dtype=int)
        samples = [float(x) for x in valid_arr[idx]]
        # Independent PDS4 sentinel cross-check: count pixels equal to the PDS4
        # label's missing_constant (independent of the GeoTIFF's nodata tag) and
        # require that count to match the tag-derived count.
        pds4_sentinel_count = int(
            np.count_nonzero(raw == np.float32(PDS4_REFERENCE["missing_constant"]))
        )
        pds4_sentinel_agrees = pds4_sentinel_count == nodata_count
        # cross-check against GDAL's own masked read
        gdal_valid = int(np.ma.count(ds.read(1, masked=True)))
        gdal_agrees = gdal_valid == valid_count
        # corner/center pixel values with their pixel-center coordinates
        pts = [(0, 0), (0, width - 1), (height - 1, 0), (height - 1, width - 1),
               (height // 2, width // 2)]
        corners = []
        for r, c in pts:
            x, y = transform * (c + 0.5, r + 0.5)
            corners.append({"row": r, "col": c, "value": float(raw[r, c]),
                            "x": float(x), "y": float(y)})

        # -------------------------------------------------------- coverage
        if is_geo:
            geo = bounds
            conv_method = "none - CRS is already geographic lon/lat"
        else:
            geo_crs = geographic_body_crs(crs)
            lons, lats = warp_transform(
                crs, geo_crs,
                [bounds.left, bounds.right, bounds.left, bounds.right],
                [bounds.top, bounds.top, bounds.bottom, bounds.bottom],
            )
            from rasterio.coords import BoundingBox
            geo = BoundingBox(min(lons), min(lats), max(lons), max(lats))
            conv_method = (
                "GDAL/PROJ coordinate transformation from the file's CRS to a "
                f"geographic lon/lat CRS on the SAME body (a={a_r} m, b={b_r} m, "
                "source: " + radii_src + "); no Earth CRS involved"
            )
        margins_deg = {
            "west": PROJECT_BOUNDS["lon_min"] - geo.left,
            "east": geo.right - PROJECT_BOUNDS["lon_max"],
            "south": PROJECT_BOUNDS["lat_min"] - geo.bottom,
            "north": geo.top - PROJECT_BOUNDS["lat_max"],
        }
        covers = all(m >= -COVERAGE_TOL_DEG for m in margins_deg.values())
        m_per_deg_lat = math.pi * a_r / 180.0  # sphere radius from CRS body
        m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(PROJECT_LAT_REF))
        margins_m = {
            k: v * (m_per_deg_lon if k in ("west", "east") else m_per_deg_lat)
            for k, v in margins_deg.items()
        }

        # ground pixel meters at PROJECT_LAT_REF (sphere approximation)
        if is_geo:
            ground_px = {
                "x_m": res[0] * m_per_deg_lon,
                "y_m": abs(res[1]) * m_per_deg_lat,
            }
        else:
            m_lat_ts = re.search(r"\+lat_ts=([0-9.eE+-]+)", crs.to_proj4() or "")
            lat_ts = float(m_lat_ts[1]) if m_lat_ts else None
            ground_px = {
                "x_m": res[0] * (math.cos(math.radians(PROJECT_LAT_REF))
                                 / math.cos(math.radians(lat_ts))) if lat_ts is not None else None,
                "y_m": abs(res[1]),
                "note": "projected CRS: y is exact ground meters; x scaled by cos(lat)/cos(lat_ts)"
                        if lat_ts is not None else "projected CRS: lat_ts not found in proj4",
            }
        # Sub-pixel alignment observations for Task 03 (documented, NOT decided):
        # where each contract bound sits inside the DEM grid, in fractional
        # pixels, for both the PLAN §5.1 bounds and the docs/sources.md bounds.
        def px_offset(target_deg):
            # x direction: 0-based fractional column of a longitude in the DEM
            col_f = (target_deg - geo.left) / (geo.right - geo.left) * width
            return {"fractional_pixel": col_f, "whole_pixel_distance": abs(col_f - round(col_f))}

        def row_offset(target_lat):
            # y direction: 0-based fractional row (row 0 = north)
            row_f = (geo.top - target_lat) / (geo.top - geo.bottom) * height
            return {"fractional_pixel": row_f, "whole_pixel_distance": abs(row_f - round(row_f))}

        def frame_offsets(bnds):
            return {
                "lon_min": px_offset(bnds["lon_min"]),
                "lon_max": px_offset(bnds["lon_max"]),
                "lat_min": row_offset(bnds["lat_min"]),
                "lat_max": row_offset(bnds["lat_max"]),
            }

        align_obs = {
            "plan_5_1_bounds": frame_offsets(PROJECT_BOUNDS),
            "sources_md_precise_bounds": frame_offsets(PRECISE_BOUNDS),
        }

        # ------------------------------------------------- PDS4 cross-check
        checks = []
        def record(name, actual, ref, tol=None):
            if tol is None:
                ok = actual == ref
            else:
                ok = abs(actual - ref) <= tol
            checks.append((name, actual, ref, ok))
        record("width", width, PDS4_REFERENCE["width"])
        record("height", height, PDS4_REFERENCE["height"])
        record("bands", count, PDS4_REFERENCE["bands"])
        record("dtype (IEEE754LSBSingle == float32 LE)", dtypes[0], "float32")
        record("nodata == PDS4 missing_constant",
               float(np.float32(nodata)) if nodata is not None else float("nan"),
               PDS4_REFERENCE["missing_constant"])
        record("body semi-major axis", a_r, PDS4_REFERENCE["a_axis_radius_m"], tol=1e-6)
        record("pixel size x (m)", res[0], PDS4_REFERENCE["pixel_resolution_m"], tol=1e-6)
        record("pixel size y (m)", abs(res[1]), PDS4_REFERENCE["pixel_resolution_m"], tol=1e-6)
        lat_ts_p = re.search(r"\+lat_ts=([0-9.eE+-]+)", crs.to_proj4() or "")
        if lat_ts_p:
            record("equirectangular standard parallel", float(lat_ts_p[1]),
                   PDS4_REFERENCE["lat_ts"], tol=1e-6)
        if not is_geo:
            record("upper-left x", transform.c, PDS4_REFERENCE["upperleft_x_m"], tol=1e-3)
            record("upper-left y", transform.f, PDS4_REFERENCE["upperleft_y_m"], tol=1e-3)
            record("west bound (deg)", geo.left, PDS4_REFERENCE["west_deg"], tol=1e-5)
            record("east bound (deg)", geo.right, PDS4_REFERENCE["east_deg"], tol=1e-5)
            record("north bound (deg)", geo.top, PDS4_REFERENCE["north_deg"], tol=1e-5)
            record("south bound (deg)", geo.bottom, PDS4_REFERENCE["south_deg"], tol=1e-5)

    sha_end = sha256_of(args.source)
    source_unchanged = sha_start == sha_end

    # ------------------------------------------------------------ report
    def yck(v):
        return "MATCH" if v else "**MISMATCH**"

    report = f"""# DEM Inspection Report — M20_JezeroCrater_CTXDEM_20m.tif

Task 02 deliverable (DE1) — generated by `pipeline/inspect_dem.py` from measured values only.
The source file was opened read-only; no crop, resample, or reprojection was performed.

## 1. Source and acquisition

| Item | Value |
|---|---|
| Source URL | {prov.get('url', 'not recorded')} |
| Final URL (after redirect) | {prov.get('final_url', 'not recorded')} |
| HTTP status | {prov.get('http_status', 'not recorded')} |
| Content-Length (server) | {prov.get('content_length', 'not recorded')} bytes |
| Acquired on | {prov.get('acquired_on', 'not recorded')} |
| Acquisition tool | {prov.get('tool', 'not recorded')} |
| Server Last-Modified | {prov.get('server_last_modified', 'not recorded')} |
| Server ETag | {prov.get('server_etag', 'not recorded')} |
| Local file | `{args.source.as_posix()}` |
| File size (measured) | {args.source.stat().st_size} bytes |
| SHA-256 (measured) | `{sha_start}` |
| Provenance sidecar | `{prov_path.name}` |
| Readability | opens with rasterio/GDAL; validation read OK |
| Source unchanged by inspection | {'YES — SHA-256 identical before/after' if source_unchanged else 'NO — INTEGRITY FAILURE'} |

## 2. Raster metadata (measured)

| Item | Value |
|---|---|
| Driver | {driver} |
| Width × Height | {width} × {height} pixels |
| Bands | {count} |
| Data type (per band) | {', '.join(dtypes)} |
| Affine transform | a={transform.a!r}, b={transform.b!r}, c={transform.c!r}, d={transform.d!r}, e={transform.e!r}, f={transform.f!r} |
| Pixel resolution (CRS units) | x={res[0]!r}, y={abs(res[1])!r} |
| Ground pixel size at {PROJECT_LAT_REF}° (see notes) | x={ground_px['x_m'] if ground_px['x_m'] is None else round(ground_px['x_m'], 6)} m, y={round(ground_px['y_m'], 6)} m |
| Raster bounds (CRS units) | left={bounds.left!r}, bottom={bounds.bottom!r}, right={bounds.right!r}, top={bounds.top!r} |
| NoData | {nodata!r} |
| Compression | {profile.get('compress', 'none (not stated in profile)')} |
| Tiled | {profile.get('tiled', 'not stated')} |
| Block shapes | {block_shapes} |
| Interleave | {profile.get('interleave', 'not stated')} |
| Band scales / offsets / units | {band_scales} / {band_offsets} / {band_units} |
| Dataset tags | {tags if tags else 'none'} |
| Band 1 tags | {band_tags if band_tags else 'none'} |

## 3. Spatial reference (measured from the file's embedded CRS)

- **Geographic or projected:** {'geographic (lon/lat)' if is_geo else 'projected'}; linear units: {linear_units}; angular units: {angular_units}
- **Authority/code:** {authority if authority else 'NOT resolvable to an authority code — embedded WKT below is the primary evidence'}
- **Body (Mars) radii:** a={a_r!r} m, b={b_r!r} m (parsed from {radii_src}); sphere: {sphere}
- **Vertical datum/elevation reference in file:** {'stated in dataset/band tags — see §2' if (set(tags) - {'AREA_OR_POINT'} or band_tags) else 'NOT stated inside the GeoTIFF (only GDAL metadata tag AREA_OR_POINT present); see §9 and the PDS4 documentation cross-check (§7)'}

### CRS WKT (WKT1, as reported by GDAL from the file's GeoTIFF keys)

```
{wkt1}
```

### CRS WKT (WKT2_2019)

```
{wkt2}
```

## 4. Elevation statistics (measured, valid pixels only)

| Statistic | Value |
|---|---|
| Valid pixels | {valid_count} |
| NoData pixels (sentinel ==) | {nodata_count} |
| NaN pixels | {nan_count} |
| Total pixels | {total_px} |
| NoData+NaN percentage | {100.0 * (nodata_count + nan_count) / total_px:.4f} % |
| Minimum | {v_min!r} |
| Maximum | {v_max!r} |
| Mean | {v_mean!r} |
| Std deviation (population, ddof=0) | {v_std!r} |

Statistics were computed with float64 accumulation over all pixels except the
NoData sentinel and NaNs. Independent sentinel cross-check: {pds4_sentinel_count}
pixel(s) equal the PDS4 label's `missing_constant`
({PDS4_REFERENCE['missing_constant']!r}) — {'AGREES' if pds4_sentinel_agrees else 'DISAGREES'} with the NoData-tag count ({nodata_count}).

Representative valid pixel values (10 evenly spaced):

```
{samples}
```

Representative corner/center pixels (value @ CRS coordinates of pixel center):

```
{corners}
```

## 5. Geographic coverage vs project frame

- Conversion method: {conv_method}
- DEM geographic bounds (lon/lat, Mars): west={geo.left!r}, east={geo.right!r}, south={geo.bottom!r}, north={geo.top!r}
- Project frame (PLAN §5.1 contract): lon {PROJECT_BOUNDS['lon_min']}–{PROJECT_BOUNDS['lon_max']}, lat {PROJECT_BOUNDS['lat_min']}–{PROJECT_BOUNDS['lat_max']}

| Side | Margin (deg) | Margin (approx. m at {PROJECT_LAT_REF}°) |
|---|---|---|
| West (DEM extends beyond lon_min) | {margins_deg['west']!r} | {margins_m['west']:.1f} |
| East (DEM extends beyond lon_max) | {margins_deg['east']!r} | {margins_m['east']:.1f} |
| South (DEM extends beyond lat_min) | {margins_deg['south']!r} | {margins_m['south']:.1f} |
| North (DEM extends beyond lat_max) | {margins_deg['north']!r} | {margins_m['north']:.1f} |

**Coverage verdict: {'FULL — the source DEM completely covers the project frame' if covers else 'INSUFFICIENT — STOP FOR REVIEW'}**
(margins measured with tolerance {COVERAGE_TOL_DEG}°; meter margins use the sphere radius from the CRS body, m/deg lat = π·a/180, m/deg lon = π·a·cos({PROJECT_LAT_REF}°)/180)

## 6. NoData analysis

- NoData value: {nodata!r} (float32; equals the PDS4 `Special_Constants/missing_constant` per §7)
- NoData pixels: {nodata_count} of {total_px} ({100.0 * nodata_count / total_px:.4f} %); NaN pixels: {nan_count}
- GDAL masked-read valid count: {gdal_valid} — {'AGREES' if gdal_agrees else 'DISAGREES'} with explicit sentinel count ({valid_count})
- PDS4-label sentinel cross-check: {pds4_sentinel_count} pixels equal `missing_constant` — {'AGREES' if pds4_sentinel_agrees else 'DISAGREES'} with the tag-based count ({nodata_count})

## 7. Cross-check vs official PDS4 label (documentation evidence)

Source: {PDS4_REFERENCE['lid']} v{PDS4_REFERENCE['version']} — fetched 2026-11-13 from
astrogeology.usgs.gov (label file `m20_jezerocrater_ctxdem_20m.xml`).

| Check | Measured | PDS4 reference | Result |
|---|---|---|---|
""" + "\n".join(
        f"| {n} | {a!r} | {r!r} | {yck(ok)} |" for n, a, r, ok in checks
    ) + f"""

Note: the PDS4 label declares the data type as `IEEE754LSBSingle` (little-endian
IEEE 754 single precision), which corresponds to the measured GDAL dtype
`float32` on this little-endian platform.

## 8. Confirmed facts vs inferred information

**Confirmed (measured from the file):** driver, dimensions, band count, dtype,
transform, resolution, bounds, NoData value, all §4 statistics, CRS WKT and its
parameters, coverage margins, SHA-256, file size.

**Source-documentation evidence (cited, not measured from the binary):** product
identity/version, MOLA vertical control and "meters" vertical units, public-domain
use constraint, publication date 2021-10-14 (USGS product page + PDS4 label, see §7).

**Inferred (reasoning, clearly labeled):** that elevation values are meters
consistent with the PDS4 "Vertical Coordinate System Units: Meters" statement and
consistent in magnitude with Jezero elevations (≈ −2586…−1786 m for the rover
track per PLAN §4) — treated as strong corroboration, not proof from the binary.

## 9. Unresolved questions and technical risks for Task 03

1. **Sub-pixel alignment:** the contract frame edges fall at these fractional
   pixel positions inside the DEM grid (0-based; rows count from north):

   PLAN §5.1 bounds (4 decimals):
   ```
   {align_obs['plan_5_1_bounds']}
   ```

   docs/sources.md "Area of interest" precise bounds:
   ```
   {align_obs['sources_md_precise_bounds']}
   ```

   The two bound sets differ at the 4th–7th decimal, shifting frame-edge
   positions by up to ~0.1 px (≤ ~2 m). Task 03 must decide how to snap the crop
   to the pixel grid AND which bound set governs. NOT decided here.
2. **East-west ground pixel size:** the file is Equirectangular with standard
   parallel {PDS4_REFERENCE['lat_ts']}°; ground x-meters at {PROJECT_LAT_REF}° are
   {ground_px['x_m'] if ground_px['x_m'] is None else round(ground_px['x_m'], 6)} m
   vs 20.000 m in projected space ({'negligible' if ground_px['x_m'] and abs(ground_px['x_m'] - 20) < 0.01 else 'material'} difference).
   `grid_meta.json` (Task 04) needs a ruling on which value the contract wants.
3. **Vertical reference:** elevations are MOLA-controlled per USGS documentation;
   the precise vertical datum (MOLA areoid vs ellipsoid) is not stated inside the
   GeoTIFF. Must be reconciled with the rover-track datum by the Data Scientist
   before validation comparisons (PLAN §5.7).
4. **Authority resolution:** {authority if authority else 'the embedded CRS does not resolve to an authority code (consistent with the Task 01 IAU_2000/IAU_2015 database finding)'} — WKT preserved above; no substitution made.
5. **Latitude convention:** planetocentric per documentation; on a spherical body
   (a == b measured: {sphere}) planetocentric == planetographic, so no
   ocentric/ographic ambiguity affects the frame comparison.

## 10. Acquisition environment

- Python {sys.version.split()[0]}, rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}, numpy {np.__version__}
- Script: `pipeline/inspect_dem.py` (rerunnable; deterministic report content)
"""

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print(f"[ok] report written: {args.report}")
    print(f"[ok] source unchanged during inspection: {source_unchanged}")
    if not source_unchanged:
        print(
            "[error] SOURCE INTEGRITY FAILURE: SHA-256 changed during inspection "
            "(see report §1); exiting with code 1",
            file=sys.stderr,
        )
        return 1
    print(f"[ok] PDS4 cross-check: {sum(1 for *_, ok in checks if ok)}/{len(checks)} MATCH")
    print(f"[ok] coverage verdict: {'FULL' if covers else 'INSUFFICIENT'}")
    print(
        f"[summary] {width}x{height} {dtypes[0]}, res=({res[0]!r}, {abs(res[1])!r}), "
        f"nodata={nodata!r}, valid={valid_count}, elev range [{v_min!r}, {v_max!r}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
