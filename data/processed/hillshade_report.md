# Hillshade Report - `web/data/hillshade.png` (Task 06, delivery slot 4)

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
  180 at 45 deg; lossless grayscale PNG (mode L).

## 2. Input identity

| Item | Value |
|---|---|
| Source DEM | `data/processed/dem_20m_crop.tif` (Task 03 crop) |
| DEM file size | 4377084 bytes |
| DEM SHA-256 | `b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae` (pin + metadata provenance match) |
| Dimensions | 1016 x 1075 px @ 20 m projected |
| CRS | equirectangular lat_ts=18.4663, R=3396190, metres |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `web/data/hillshade.png` |
| File size | 407341 bytes (397.8 KiB; limit 3145728 = 3 MB) |
| SHA-256 | `90b04c96443da2f4bed67a31349ad26eedd759c2eb699e2d397dcdff2f6936fe` |
| Dimensions / mode | 1016 x 1075 px, single-band grayscale (PIL mode L) |

## 4. Processing parameters (as executed)

| Parameter | Value |
|---|---|
| Method | Lambertian hillshade, Horn 3x3 gradients (edge-replicate padding) |
| Azimuth | 315.0 deg (clockwise from north) |
| Altitude | 45.0 deg |
| z-factor | 1.0 |
| Cell size | 20.0 m x 20.0 m (projected; verified from the transform) |
| Rounding | half-even via `numpy.rint` |
| Self-shadow clamp | `max(dot, 0)` before scaling |

## 5. Measured evidence

| Item | Value |
|---|---|
| Classification census | valid 1092200, nodata 0, nan 0, inf 0 |
| Slope range (Horn, 20 m) | [0.001, 39.716] deg (mean 5.515 deg) |
| Shading range | [50, 251] |
| Shading mean / std | 174.839 / 17.579 |
| Self-shadowed pixels (=0) | 0 (0.0000%) |
| Full-array equality vs independent derivation | 1092200/1092200 elements equal (0 differing; PNG lossless, zero tolerance) |

## 6. Validator results

| Check | Result | Measured detail |
|---|---|---|
| metadata loads with required keys | PASS | web/data/grid_meta.json (21 keys) |
| DEM SHA-256 chain (pin + metadata + provenance path) | PASS | b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae (pin match=True, provenance match=True, path match=True) |
| DEM identity/geometry (dims, 1x float32, north-up, unrotated) | PASS | 1016x1075, a=20.0, e=-20.0, |b|=0.0, |d|=0.0 |
| DEM pixel size == metadata pixel_size_projected_m (20 m projected) | PASS | transform (20.0, 20.0) vs metadata (20.0, 20.0) |
| DEM CRS tokens complete (eqc lat_ts=18.4663 R=3396190) | PASS | tokens subset=True |
| classification census: DEM contains ZERO NoData/NaN/+-Infinity pixels | PASS | nodata=0, nan=0, inf=0 (total 1092200; the interpolation-free contract holds vacuously) |
| output size <= 3145728 bytes (3 MB) | PASS | 407341 bytes (397.8 KiB) |
| Pillow decode (mode L, exact dims) | PASS | mode='L' (L required), size=(1016, 1075) (1016x1075 required) |
| FULL-array EXACT equality vs independently derived shading (PNG lossless: zero tolerance) | PASS | 1092200/1092200 elements equal (0 differing) - this is the target-grid alignment proof: every output pixel equals the contract hillshade on the exact DEM grid |
| pixel values within [0, 255] uint8 and distribution sane | PASS | range [50, 251], mean 174.839, std 17.579, self-shadowed(=0) 0 px |
| determinism: two temp exports equal the final artifact (SHA-256 x3) | PASS | run1=90b04c96443da2f4..., run2=90b04c96443da2f4..., final=90b04c96443da2f4..., exit codes [0, 0]; temp dir removed |

## 7. Determinism result

The exporter ran twice into a temporary directory; exit codes 0 and 0;
SHA-256 of run 1 == run 2 == final artifact (`90b04c96443da2f4bed67a31349ad26eedd759c2eb699e2d397dcdff2f6936fe`).
The temporary directory was removed; the final artifact was not rewritten.

## 8. Untested behavior and limitations

- The NoData/NaN/+-Infinity hard-fail path is NOT exercised by data (0 such
  pixels); enforced by explicit abort guards and verified by code review only
  (same honest caveat pattern as Task 05).
- Border pixels use edge-replicated neighbours (documented; 1-px border band,
  no artificial features).
- Determinism proven for consecutive runs on this machine (numpy
  2.4.6, rasterio 1.4.4, Pillow 13.0.0);
  re-exports assume the pinned environment.
- The PNG intentionally carries no georeferencing; the layer is geolocated
  through `web/data/grid_meta.json` (pixel (row, col) maps exactly onto the
  shared decode grid, row 0 = north, col 0 = west).

## 9. Environment

- Python 3.11.0, rasterio 1.4.4, GDAL 3.10.3, numpy 2.4.6, Pillow 13.0.0
- Scripts: `pipeline/export_hillshade.py` (exporter),
  `pipeline/verify_hillshade.py` (this validator + report owner; rerunnable,
  deterministic report content)
