# Geologic Map Layer Report - `web/data/geologic_map.png` (Task 08, P2 optional)

Task 08 deliverable evidence - written by `pipeline/verify_geologic_map.py`
after the exporter (`pipeline/export_geologic_map.py`) and every independent
validation check (including the double-export determinism proof) passed.
Deterministic content: no timestamps; all values are measured from the files
listed below.

## 1. Contract and approved decisions

- Output: `web/data/geologic_map.png`, **RGBA PNG, <= 3 MB, DE1**
  (docs/PLAN.md line 211, P2 optional; overlay on the CTX basemap).
- Source: **USGS SIM 3464** - Sun, V., and Stack, K., 2020, Geologic map of
  Jezero crater and the Nili Planum region, Mars, USGS Scientific
  Investigations Map 3464, scale 1:75,000, doi:10.3133/sim3464
  (USGS public domain; access constraints none; fees none).
- Target grid: EXACTLY the shared grid (`grid_meta.json` + Task 03 DEM
  transform): 1016 x 1075 px @ 20 m projected,
  equirectangular lat_ts=18.4663, R=3396190, row 0 = north, col 0 = west.
- Reprojection: Mars TM (central meridian 77.5E, k=1, R=3396190) -> grid eqc
  via PROJ vertex transformation, then direct rasterization on the target
  grid (no intermediate resampling).
- Anti-aliasing: 4x supersampling (5 m/px) + deterministic
  majority vote (ties: lowest unit id first, background last).
- Background: TRANSPARENT (alpha 0) so the CTX basemap shows
  through; mapped units opaque (alpha 255).
- Colors: fixed documented palette (the source ``Color_ID`` field is an
  ArcMap symbol index, NOT a color - values collide across units).
- Machine-readable legend: `web/data/geologic_map_legend.json` (Full Stack).

## 2. Source identity

| Item | Value |
|---|---|
| Archive | `data/raw/sim3464_database.zip` |
| Archive size / SHA-256 | 349336873 bytes / `a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87` (pin match) |
| Citation | Sun, V., and Stack, K., 2020, USGS SIM 3464, doi:10.3133/sim3464 |
| Feature layer | `GeoUnits_v1` (1,304 MultiPolygon features), `Nili.gdb` |
| Source CRS | Mars TM, central meridian 77.5E, k=1, Mars 2000 sphere R=3396190, metres |
| Mapped area | exactly 1 deg x 1 deg: lon 76.8-77.8E, lat 17.7-18.7N (contains the grid) |

## 3. Output identity

| Item | Value |
|---|---|
| Output | `web/data/geologic_map.png` |
| File size | 44347 bytes (43.3 KiB; limit 3145728 = 3 MB) |
| SHA-256 | `863a5cdbd5d10745d84024802d66dda9df570b2873587cc43a71fcde1112703e` |
| Dimensions / mode | 1016 x 1075 px, RGBA (transparent background) |
| Legend | `web/data/geologic_map_legend.json` |

## 4. Rendering measurements (independently re-derived)

| Item | Value |
|---|---|
| Supersampled raster | 4064 x 4300 @ 5 m/px |
| Paint-order invariance (ascending vs descending) | 0 differing subpixels (disjoint partition) |
| Background (unmapped) pixels in the grid | 0 of 1092200 |
| Full-array equality vs independent derivation | 4368800/4368800 values equal (0 differing) |

## 5. Unit legend (all 14 source units; counts measured from the decoded PNG)

| Unit | Name | Symbol | Color | Pixels in grid | Present in this grid |
|---|---|---|---|---|---|
| 0 | Jezero fan 2 unit | NHjf2 | #F5C58A | 67892 (yes) |
| 1 | Jezero fan 1 unit | NHjf1 | #E8A75C | 26243 (yes) |
| 2 | Jezero floor unit | Njf | #A6D8E8 | 266342 (yes) |
| 3 | Lower etched unit | Nle | #C98A4B | 81918 (yes) |
| 4 | Nili Planum fan unit | Hnpf | #E8E3B0 | 0 (no (outside this grid)) |
| 5 | Nili Planum 2 unit | Nnp2 | #B5C98A | 2494 (yes) |
| 6 | Nili Planum 1 unit | Nnp1 | #8FA36B | 15407 (yes) |
| 7 | Eolian bedform unit | Aeb | #F2E14C | 150285 (yes) |
| 8 | Smooth unit, undivided | su | #D9D9D9 | 36935 (yes) |
| 9 | Rugged bright unit | Nrb | #F4F4F4 | 2729 (yes) |
| 10 | Upper etched unit | Nue | #C77F5B | 314658 (yes) |
| 11 | Crater rim unit | cr | #B04A4A | 127297 (yes) |
| 12 | Crater ejecta unit | ce | #E2B6B6 | 0 (no (outside this grid)) |
| 13 | Crater interior unit | ci | #6E4F4F | 0 (no (outside this grid)) |

## 6. KNOWN POSITIONAL LIMITATION (documented, not hidden)

Per the official README/FGDC metadata of SIM 3464, the map was digitized on
a **semi-controlled** CTX mosaic that predates the controlled mosaic
(DOI 10.5066/P9GV1ND3) used for this project's CTX basemap. Unit boundaries
therefore carry **random offsets of about 100-200 metres** (5-10 px at
20 m/px) relative to our grid and are **NOT exactly aligned** with the CTX
basemap. This layer is an optional qualitative overlay; the offset is a
property of the source map, not of our processing.

## 7. Validator results

| Check | Result | Measured detail |
|---|---|---|
| metadata loads with required keys | PASS | web/data/grid_meta.json (21 keys) |
| DEM SHA-256 chain (pin + metadata + provenance path) - existing deliverables unchanged | PASS | b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae (pin match=True, provenance match=True, path match=True) |
| archive SHA-256 pin + provenance sidecar | PASS | a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87 (pin=True, size=349336873/349336873=True, sidecar keys=True, sidecar sha match=True) |
| source layer CRS tokens + unit/name/symbol agreement with the palette contract | PASS | 1304 features, 14 units; crs tokens=True, unit ids match=True, symbols match=True |
| output size <= 3145728 bytes (3 MB) | PASS | 44347 bytes (43.3 KiB), sha256=863a5cdbd5d10745d84024802d66dda9df570b2873587cc43a71fcde1112703e |
| Pillow decode (mode RGBA, exact dims) | PASS | mode='RGBA' (RGBA required), size=(1016, 1075) (1016x1075 required) |
| FULL-array EXACT equality vs independently derived RGBA (PNG lossless, zero tolerance) | PASS | 4368800/4368800 values equal (0 differing) - this is the target-grid alignment proof: every pixel equals the contract rendering on the exact DEM grid |
| alpha semantics: opaque exactly where a unit is mapped | PASS | opaque 1092200 px, transparent 0 px, of 1092200 pixels (only alpha 0/255 present - no partial alphas) |
| per-unit decoded pixel counts (informational) | PASS | {"0": 67892, "1": 26243, "2": 266342, "3": 81918, "4": 0, "5": 2494, "6": 15407, "7": 150285, "8": 36935, "9": 2729, "10": 314658, "11": 127297, "12": 0, "13": 0} |
| legend JSON complete and consistent (units, colors, names, counts, offset note) | PASS | 14 legend entries; colors/names/counts match decoded PNG=True; doi+offset present=True |
| determinism: two temp exports equal the final artifact (SHA-256 x3) | PASS | run1=863a5cdbd5d10745..., run2=863a5cdbd5d10745..., final=863a5cdbd5d10745..., exit codes [0, 0]; temp dir removed |
| docs/sources.md SIM 3464 row complete (archive, DOI, authors, SHA) | PASS | all required fragments present |

## 8. Determinism result

The exporter ran twice into a temporary directory; exit codes 0 and 0;
SHA-256 of run 1 == run 2 == final artifact (`863a5cdbd5d10745d84024802d66dda9df570b2873587cc43a71fcde1112703e`).
The temporary directory was removed; the final artifact was not rewritten.

## 9. Attribution (to display with the layer)

Geologic map layer: Sun, V., and Stack, K., 2020, Geologic map of Jezero
crater and the Nili Planum region, Mars, USGS SIM 3464, scale 1:75,000,
doi:10.3133/sim3464. USGS public domain. Imagery courtesy
NASA/JPL-Caltech/MSSS.

## 10. Untested behavior and limitations

- The transparent-background path is NOT exercised by data (0 background
  pixels - the map tiles the entire grid); the mechanism is verified by the
  alpha-semantics check and code review.
- The unit palette is a documented design decision (the source provides no
  authoritative RGB symbology outside ArcMap .lyr files).
- Determinism proven for consecutive runs on this machine (numpy
  2.4.6, rasterio 1.4.4, GDAL 3.10.3, fiona GDAL 3.9.1,
  Pillow 13.0.0); re-exports assume the pinned environment.
- Environment note: `fiona==1.10.1` was installed into the project venv for
  vector reading (OpenFileGDB/Shapefile drivers); `requirements.txt` was
  intentionally NOT modified (Task 01 deliverable).

## 11. Environment

- Python 3.11.0, rasterio 1.4.4, GDAL 3.10.3, numpy 2.4.6,
  fiona 1.10.1, Pillow 13.0.0
- Scripts: `pipeline/acquire_geologic_map.py` (acquisition),
  `pipeline/export_geologic_map.py` (exporter),
  `pipeline/verify_geologic_map.py` (this validator + report owner;
  rerunnable, deterministic report content)
