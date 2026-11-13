# Elevation Binary Report - `web/data/elev_dm_i16.bin` (Task 05)

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
| Source raster | `data/processed/dem_20m_crop.tif` (Task 03 crop) |
| Raster file size | 4377084 bytes |
| Raster SHA-256 | `b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae` |
| Pinned SHA match | YES |
| == metadata `provenance.dem_sha256` | YES |
| Provenance chain | crop tag `SOURCE_SHA256` == `provenance.source_dem_sha256` (raw DEM `data/raw/M20_JezeroCrater_CTXDEM_20m.tif`) |
| Metadata file | `web/data/grid_meta.json` |

## 3. Output identity

| Item | Value |
|---|---|
| Output binary | `web/data/elev_dm_i16.bin` |
| File size | 2184400 bytes (exactly 1092200 elements x 2; headerless; PLAN 5.2 "~2 MB" satisfied) |
| SHA-256 | `30b016ce37fc962e6eadfe6f892fb8dbf76f3f197a9e2e34945037357bda82dc` |
| Dimensions | 1016 x 1075 px (W x H, from `grid_meta.json`) |
| Element count | 1092200 |
| Dtype / byte order | signed Int16, explicit `<i2` (little-endian) |
| Layout | row-major, row 0 = north, col 0 = west; `index = row*width + col` |

## 4. Pixel classification (honest counts)

| Class | Count |
|---|---|
| Valid | 1092200 |
| Source NoData (sentinel `-3.4028234663852886e+38`) | 0 |
| NaN | 0 |
| +/-Infinity | 0 |
| Total | 1092200 |

**The source contains ZERO NoData/NaN/Infinity pixels.** The sentinel/NaN
mapping and the Infinity hard-fail paths were therefore NOT exercised by data;
they are verified by code review and the validator's structural checks only
(the team declined a synthetic-pixel test). The sentinel agreement check is
the (honest) comparison 0 == 0.

## 5. Elevation ranges

| Item | Value |
|---|---|
| Actual source elevation range | [-2683.66162109375, -1650.4349365234375] m (float32-exact; == `grid_meta.elev_range_m`) |
| x10 conversion bracket (mode-agnostic) | [-26837, -16504] dm |
| Stored Int16 range (valid samples) | [-26837, -16504] dm |
| Int16 headroom | 5931 (low) / 49271 (high); sentinel -32768 outside the stored range |

## 6. Quantization and decode error measurements (measured)

| Item | Value |
|---|---|
| Max absolute quantization error (half-even) | 0.5 dm = **0.05 m** - attained exactly at the 476 tie samples (`frac(v*10) == 0.5`) |
| Rounding-mode fingerprint `mean(stored - true)` | -0.0002811470862994415 dm (nearest ~= 0; floor ~-0.5; truncation ~+0.5) |
| Max absolute decode error `int16/10 - raster` | 0.0500000000001819 m (bound: 0.05 m + 1e-9 m = 0.050000001) |
| Decode half-ulp (theoretical, float64 at ~2683 m) | <= 2.2737e-13 m |

## 7. Layout proof (orientation + endianness)

A W/H transposition preserves the flat element count, so size alone cannot
prove orientation. Decode error under each hypothesis (exactly one must pass):

| Hypothesis | Max abs decode error (m) | Verdict |
|---|---|---|
| as-written (C-order, little-endian) | 0.0500000000001819 | PASS |
| row-flipped (south-first) | 503.8470214843751 | fail |
| col-flipped (east-first) | 983.940625 | fail |
| rotated 180 degrees | 911.2125488281249 | fail |
| transposed (W/H swap) | 979.1393066406249 | fail |
| big-endian reinterpretation | 5941.649609375 | fail |

Full-array equality against the independently derived expected bytes:
1092200/1092200 elements equal (0 differing).

## 8. Validator results

| Check | Result | Measured detail |
|---|---|---|
| metadata loads with required keys | PASS | web/data/grid_meta.json (21 keys) |
| metadata contract values | PASS | elev_scale=10, nodata_elev=-32768, row0='north', col0='west', layout='row_major' |
| raster SHA-256 chain (pin + metadata + provenance path) | PASS | b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae (pin match=True, provenance match=True, dem_file match=True) |
| raster identity/geometry (1x float32, dims, north-up, unrotated) | PASS | count1=True, float32=True, dims_match=True, unrotated=True, north_up=True; transform a=20.0 e=-20.0 |b|=0.0 |d|=0.0 |
| raster CRS tokens + projected pixel size match metadata | PASS | crs tokens subset=True, pixel size match=True |
| raster provenance tags (Task 03 chain) | PASS | 6/6 present, SOURCE_SHA256 vs provenance source_dem_sha256 consistent=True |
| raster NoData record agrees with metadata nodata_elev_dem | PASS | raster nodata=-3.4028234663852886e+38, metadata=-3.4028234663852886e+38 |
| source contains no +/-Infinity | PASS | 0 infinite samples (the exporter's hard-fail path is therefore NOT exercised by data) |
| pixel classification partitions the grid | PASS | valid=1092200, nodata=0, nan=0, inf=0, total=1092200 |
| contract fit: valid conversions inside Int16, none collides with sentinel | PASS | valid conversion range [-26837.0, -16504.0], collision-free=True |
| exact byte size (elements x 2, headerless) | PASS | 2184400 bytes vs expected 2184400 (1092200 elements) |
| FULL-array equality vs independently derived expected bytes | PASS | 0 differing elements of 1092200 (catches rounding, scale, sentinel, order, transposition and endianness at once) |
| layout/endianness hypothesis matrix (exactly one PASS: as-written LE) | PASS | as-written (C-order, little-endian): max_err=0.0500000000001819 m (PASS); row-flipped (south-first): max_err=503.8470214843751 m (fail); col-flipped (east-first): max_err=983.940625 m (fail); rotated 180 degrees: max_err=911.2125488281249 m (fail); transposed (W/H swap): max_err=979.1393066406249 m (fail); big-endian reinterpretation: max_err=5941.649609375 m (fail) |
| decoded elevation bound abs(int16/10 - raster) <= 0.05 m + 1e-9 m | PASS | max abs decode error 0.0500000000001819 m over 1092200 valid elements (tolerance 0.050000001) |
| rounding-mode fingerprint (nearest family ~= 0 dm) | PASS | mean(stored - true) = -0.0002811470862994415 dm (floor would be ~-0.5, truncation ~+0.5 on all-negative data) |
| half-even tie invariant (stored == even neighbor at every exact 0.5 dm tie) | PASS | 476 exact tie sample(s); every stored value equals the even neighbor -> half-even proven from the artifact itself |
| sentinel agreement with metadata (positions and value) | PASS | bin sentinel count 0 == source invalid count 0 (value -32768 == metadata nodata_elev); NOTE: mapping path NOT exercised - 0 NoData/NaN pixels in this source |
| stored Int16 range within contract bracket | PASS | stored [-26837, -16504] dm within [-26837, -16504] (headroom 5931 low / 49271 high) |
| metadata elev_range_m equals the live raster range | PASS | metadata [-2683.66162109375, -1650.4349365234375] vs raster [-2683.66162109375, -1650.4349365234375] |
| determinism: two temp exports equal the final artifact (SHA-256 x3) | PASS | run1=30b016ce37fc962e..., run2=30b016ce37fc962e..., final=30b016ce37fc962e..., exit codes [0, 0]; temp dir removed |

## 9. Determinism result

The exporter ran twice into a temporary directory; exit codes 0 and 0;
SHA-256 of run 1 == run 2 == final artifact
(`30b016ce37fc962e6eadfe6f892fb8dbf76f3f197a9e2e34945037357bda82dc`). The temporary directory was removed;
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
- Determinism proven for consecutive runs on this machine (numpy 2.4.6,
  rasterio 1.4.4); re-exports assume the pinned environment.

## 12. Environment

- Python 3.11.0, rasterio 1.4.4, GDAL 3.10.3, numpy 2.4.6
- Scripts: `pipeline/export_elev_bin.py` (exporter), `pipeline/verify_elev_bin.py`
  (this validator + report owner; rerunnable, deterministic report content)
