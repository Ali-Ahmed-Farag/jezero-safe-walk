# CTX Basemap Report - `web/data/ctx_basemap.jpg` (Task 06)

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
  `data/processed/dem_20m_crop.tif`): 1016 x 1075 px @ 20 m,
  equirectangular lat_ts=18.4663, R=3396190.
- **Proper geospatial warp** (source lat_ts=0 vs target lat_ts=18.4663;
  empirically a pure x-rescale, no y-warp), never a plain resize.
- **Outward source-window pixel snapping** with a proven coverage proof.
- Resampling: **Average** (6 m -> 20 m area-average; approved).
- NoData: the source GeoTIFF declares **DN=0 = NoData**; the approved census
  state is **ZERO DN=0 pixels** (measured over the whole
  26,822,880-pixel mosaic), so the
  "valid dark pixel vs missing pixel" ambiguity cannot arise; any warp gap
  is a hard failure (nothing fabricated, nothing interpolated).
- Contrast: **conservative percentile linear stretch from the measured
  histogram** (p0.5 / p99.5), half-even rounding.
  p2/p98 was rejected (would clip 4% and over-flatten a basemap).
- JPEG: **quality 85, <= 5 MB**, grayscale replicated to RGB,
  atomic `.part` -> `os.replace` promotion.

Contract: `docs/PLAN.md` line 209 (`ctx_basemap.jpg`, JPEG quality 85,
<= 5 MB, DE1) and line 325 (deliverable slot).

## 2. Source identity

| Item | Value |
|---|---|
| Product | Mars 2020 Terrain Relative Navigation Context Camera Orthorectified Image Mosaic (USGS Astrogeology) |
| Primary URL | `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif` |
| Mars Trek WMTS equivalent | `https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml` |
| DOI | `10.5066/P9GV1ND3` |
| File size | 36269402 bytes (pinned 36269402) |
| SHA-256 | `842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615` |
| Acquisition date (UTC) | 2026-11-13 |
| Acquisition tool | `pipeline/acquire_ctx_basemap.py` |
| Dimensions / dtype / NoData | 5322 x 5040, 1 x uint8, nodata=0.0 |
| CRS / pixel size | equirectangular lat_ts=0, R=3396190; 6.0 m/px |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `web/data/ctx_basemap.jpg` |
| File size | 337494 bytes (329.6 KiB; limit 5242880 = 5 MB) |
| SHA-256 | `d40feeb267230016a35b151378e19f5480412873a16134055611e1967b786282` |
| Dimensions | 1016 x 1075 px, 3 bands uint8 (grayscale replicated) |
| JPEG quality | 85 |

## 4. Source window (outward snap + coverage proof)

| Item | Value |
|---|---|
| Snapped window (source px) | cols [613, 4185), rows [512, 4096) = 3572 x 3584 px |
| Window size | 3584 x 3572 px = 12,802,048 px |
| Coverage proof | snapped window fully covers the target grid (independent derivation, tolerance 1e-6 m) |
| DN=0 census (window) | 0 zero pixels (0.000000%) |

## 5. Measured histogram (window, valid pixels = all 12,802,048)

| Percentile | DN |
|---|---|
| p0.1 | 57 |
| p0.5 | 74 |
| p1 | 83 |
| p2 | 93 |
| p5 | 107 |
| p50 | 152 |
| p95 | 196 |
| p98 | 208 |
| p99 | 219 |
| p99.5 | 229 |
| p99.9 | 250 |

Distribution summary: DN range [31, 255]; no DN=0 pixels exist.

## 6. Contrast stretch (conservative, from the measured histogram)

| Item | Value |
|---|---|
| Bounds | p0.5 = 74, p99.5 = 229 |
| Mapping | linear [74, 229] -> [0, 255], half-even rounding, clamped |
| Clipped mass | 0.4624% below, 0.4829% above (total 0.9453%) |

## 7. Warp and coverage

| Item | Value |
|---|---|
| Resampling | Average (GDAL/rasterio) |
| Output gap pixels | 0 of 1092200 (0.000000%) |
| Pure-black pixels (output, measured) | 0 (0.0000%; documented tail-clip of the stretch) |
| Pure-white pixels (output, measured) | 0 (0.0000%) |

## 8. Independent comparison (target-geometry proof)

The expected image was derived independently (window, warp and stretch
re-implemented in this validator; the JPEG is decoded with Pillow as a second,
independent decoder):

| Item | Value |
|---|---|
| Max abs difference | 25 DN (tolerance 40) |
| Mean abs difference | 3.050808459989013 DN (tolerance 5.0) |
| 99th percentile abs difference | 11.0 DN (tolerance 18.0) |
| PSNR (vs expected) | 36.10503870090101 dB (tolerance 34.0) |
| Blur 3x3 mean abs difference | 0.5600196341736353 DN (tolerance 1.5) |
| Pearson correlation | 0.9958662000164897 (tolerance 0.99) |
| Inter-band difference | 0 (bands must be identical) |
| Compared values | 3276600 (full image x 3 bands) |

Tolerance justification: an independent-encoder reference (Pillow q85 encoding
of the same expected image, measured during this task) yields mean 3.05 DN,
p99 11, max 25 DN, PSNR 36.11 dB, blur3x3-mean 0.56 DN on THIS content; the
tolerances are ~1.6x those baselines (blur bound ~2.7x). The residual
differences are JPEG lossy-quantization error only (quality 85);
the comparison against the independently warped expectation IS the proof that
the JPEG corresponds to the exact target DEM geometry (plain JPEG carries no
georeferencing tags by design).

## 9. Validator results

| Check | Result | Measured detail |
|---|---|---|
| metadata loads with required keys | PASS | web/data/grid_meta.json (21 keys) |
| target DEM SHA-256 chain (pin + metadata + provenance path) | PASS | b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae (pin match=True, provenance match=True, path match=True) |
| source SHA-256 pin | PASS | 842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615 (pin match=True) |
| source provenance sidecar complete and consistent | PASS | sidecar=data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif.provenance.json, keys complete=True, sha match=True, size match=True |
| source header matches pinned preflight contract | PASS | dims 5322x5040 1x uint8 nodata=0.0, transform match=True, crs tokens match=True |
| output size <= 5242880 bytes (5 MB) | PASS | 337494 bytes (329.6 KiB), sha256=d40feeb267230016a35b151378e19f5480412873a16134055611e1967b786282 |
| output rasterio identity (dims == grid contract, 3x uint8) | PASS | 1016x1075 expected; count=3, dtype=uint8 required |
| Pillow independent decode (mode RGB, exact dims) | PASS | mode='RGB' (RGB required), size=(1016, 1075) (1016x1075 required) |
| grayscale replication preserved (three JPEG bands identical) | PASS | max inter-band difference = 0 |
| DN=0 census state holds (zero DN=0 pixels in the window) | PASS | 0 zero pixels in the 3584x3572 window (approved state: none; the declared-NoData ambiguity cannot arise) |
| independent warp has zero coverage gaps (Average resampling) | PASS | 0 gap pixels of 1092200 (policy: any gap is a hard failure - nothing fabricated or interpolated) |
| independent stretch bounds derived from the measured histogram | PASS | p0.5=74, p99.5=229 (window min/max from histogram: 31/255) |
| FULL-image comparison vs independently derived expected image | PASS | max|diff|=25 (tol 40), mean|diff|=3.050808459989013 (tol 5.0), p99|diff|=11.0 (tol 18.0), PSNR=36.10503870090101 dB (tol 34.0) over 3276600 values (this is the target-geometry proof: the JPEG pixels match the exact DEM-grid warp; bounds justified by the independent-encoder q85 measurement of this content) |
| structural agreement after 3x3 box blur (JPEG noise suppressed) | PASS | blur3x3 mean|diff|=0.5600196341736353 DN (tol 1.5) - the decoded structure matches the independent expectation once lossy-quantization noise is smoothed out |
| correlation vs independent expectation | PASS | pearson r=0.9958662000164897 (tol 0.99) |
| pure-black/pure-white counts measured (informational) | PASS | output black=0 white=0; expected black=0 white=0 (tail-clip pixels from the documented p0.5/p99.5 stretch) |
| determinism: two temp exports equal the final artifact (SHA-256 x3) | PASS | run1=d40feeb267230016..., run2=d40feeb267230016..., final=d40feeb267230016..., exit codes [0, 0]; temp dir removed |
| docs/sources.md Task 06 row complete (URL, DOI, WMTS, SHA, attribution) | PASS | all required fragments present |

## 10. Determinism result

The exporter ran twice into a temporary directory; exit codes 0 and 0;
SHA-256 of run 1 == run 2 == final artifact
(`d40feeb267230016a35b151378e19f5480412873a16134055611e1967b786282`). The temporary directory was removed;
the final artifact was not rewritten by this check. Re-exports on the pinned
environment are byte-identical.

## 11. Attribution (to display with the layer)

CTX basemap: NASA/MRO Context Camera - Mars 2020 TRN CTX orthomosaic 6 m (USGS Astrogeology, DOI 10.5066/P9GV1ND3; Fergason et al. 2020). Imagery courtesy NASA/JPL-Caltech/MSSS.

## 12. Untested behavior and limitations

- The DN=0 NoData mapping and warp-gap hard-fail paths are NOT exercised by
  data (0 zero pixels; 0 gaps); they are enforced by explicit abort guards in
  both scripts and verified by code review only (conservative stop-policy for
  re-runs that encounter zeros or gaps).
- JPEG determinism is proven for consecutive runs on this machine
  (rasterio/GDAL 3.10.3 libjpeg encoder); a different
  JPEG encoder version could produce byte-different (but visually equivalent)
  output; the pinned environment governs.
- The pure-black/pure-white pixels are the documented stretch tail-clip
  (~1% total), not missing data.
- Plain JPEG intentionally carries no georeferencing; the web layer is
  geolocated through `web/data/grid_meta.json` (pixel (row, col) maps exactly
  onto the shared decode grid).

## 13. Environment

- Python 3.11.0, rasterio 1.4.4, GDAL 3.10.3, numpy 2.4.6, Pillow 13.0.0
- Scripts: `pipeline/acquire_ctx_basemap.py` (acquisition),
  `pipeline/export_ctx_basemap.py` (exporter),
  `pipeline/verify_ctx_basemap.py` (this validator + report owner;
  rerunnable, deterministic report content)
