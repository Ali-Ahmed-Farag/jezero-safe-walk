# DE1 Validation Report - Final (Task 10)

Jezero Safe Walk - Data Engineer 1 deliverables, Tasks 01-09.

Measurement status (REQUIRED distinction): values in this report tagged [MEASURED] were computed directly
from the repository files during the Task 10 audit session (2026-11-14, branch data @ d7f07f0). Values tagged
[HISTORICAL] are results recorded in the committed per-task reports under data/processed/ and are cited, NOT
re-executed here: the Task 10 work was read-only for existing deliverables and the validators were NOT rerun
during this task. Cross-checks between [HISTORICAL] claims and live files were performed wherever possible
(output SHA-256 comparisons - section 4).

Repository state [MEASURED]: branch data @ d7f07f04d7ab4e538b28a3c3412b62011cab4fe9, in sync with
origin/data; working tree clean except one untracked helper file (task09_diff.txt - a saved review copy of
the Task 09 sources.md diff; not a deliverable; keep-or-remove decision open).

## 1. Deliverable inventory [MEASURED]

| Path | Status | Bytes | SHA-256 |
| --- | --- | --- | --- |
| `data/processed/dem_20m_crop.tif` | committed | 4,377,084 | `b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae` |
| `data/processed/dem_inspection_report.md` | committed | 11,985 | `66fff7c809fa30356e00d5290597d5afb9ba49ff42a5d74aea0de75552049e49` |
| `data/processed/dem_crop_report.md` | committed | 7,402 | `fd679198f3935e22b265252fc20447af1ad0a6de97a2f9856f5a518587bdf1ef` |
| `data/processed/grid_meta_report.md` | committed | 8,061 | `5911380929d00244f3c9d0d06192296640a39017c0236bffc536b56627d51db9` |
| `data/processed/elev_bin_report.md` | committed | 10,258 | `afc6c05108866948f29e76d52842215b0b5c7856f83529e78bef1d9366be2313` |
| `data/processed/ctx_basemap_report.md` | committed | 10,330 | `303b2491c29fef4641228408a2ecaa7f923f78ee3b6170c034b53f4b7da2e750` |
| `data/processed/hillshade_report.md` | committed | 6,116 | `5d294c3ed6ea0904f9c065f27c819394e014ef8f947576fa9d8ad22f01417a71` |
| `data/processed/geologic_map_report.md` | committed | 8,334 | `21dec7f823c1d3068d995214ddb8376b63fdefc492990a25c6105d271d75941b` |
| `web/data/grid_meta.json` | committed | 3,068 | `007bc6df753ee72f9450996feab5d5049b58292b18c1b3b0a8da9cba0dd10b14` |
| `web/data/elev_dm_i16.bin` | committed | 2,184,400 | `30b016ce37fc962e6eadfe6f892fb8dbf76f3f197a9e2e34945037357bda82dc` |
| `web/data/ctx_basemap.jpg` | committed | 337,494 | `d40feeb267230016a35b151378e19f5480412873a16134055611e1967b786282` |
| `web/data/hillshade.png` | committed | 407,341 | `90b04c96443da2f4bed67a31349ad26eedd759c2eb699e2d397dcdff2f6936fe` |
| `web/data/geologic_map.png` | committed | 44,347 | `863a5cdbd5d10745d84024802d66dda9df570b2873587cc43a71fcde1112703e` |
| `web/data/geologic_map_legend.json` | committed | 5,308 | `404d6e3bc5cd7e3c484ff03803ac2cacb29a3f3d63d3aa43a1c7c9b40da7b02c` |
| `docs/sources.md` | committed | 13,360 | `7a315d52347dc072cea80cfd0d0d07c875f5ec11f0c4c1f02f1cabd0a2813c8b` |
| `requirements.txt` | committed | 530 | `01e4e7b2f76f1f047c721bea1a5afbd0a1711b49705001dad0bee2bfbd59ca90` |
| `data/raw/M20_JezeroCrater_CTXDEM_20m.tif` | on disk (gitignored raw) | 90,345,300 | `ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2` |
| `data/raw/M20_JezeroCrater_CTXDEM_20m.tif.provenance.json` | on disk (gitignored raw) | 735 | `454dd7a17a98db9a228d0831e18e960e44f31aafb2b78b834c7789f84005b406` |
| `data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif` | on disk (gitignored raw) | 36,269,402 | `842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615` |
| `data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif.provenance.json` | on disk (gitignored raw) | 1,308 | `0ab6f026197da8023a2a7988fe955319521ac698d237ad6f535ef9f482b884e8` |
| `data/raw/sim3464_database.zip` | on disk (gitignored raw) | 349,336,873 | `a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87` |
| `data/raw/sim3464_database.zip.provenance.json` | on disk (gitignored raw) | 1,403 | `f417d0546a011bada9f26c9961b2f3d26530734c351394f89b5cb5afbf810776` |

All 22 audited files exist; zero SHA-256 mismatches were found between any stored report and any live file
(section 4).

## 2. Task 01 - environment

[HISTORICAL + MEASURED] `requirements.txt` pins: rasterio==1.4.4, numpy==2.4.6, pillow==13.0.0,
fiona==1.10.1 (fiona added via approved commit 6d9bb31 after the Task 08 reproducibility audit).
Live environment [MEASURED]: rasterio 1.4.4 (bundled GDAL 3.10.3), fiona 1.10.1 (bundled GDAL 3.9.1),
numpy, Pillow 13.0.0.
A clean installation was NOT performed during this audit; what is stated here is the MEASURED installed
package versions and the pinned `requirements.txt` (the Task 08 dependency gap is closed by the pin).
Library LICENSE rows remain "to be verified before submission" in `docs/sources.md` section 1.5
(open item).

## 3. Task 02 - raw DEM acquisition

[MEASURED] `data/raw/M20_JezeroCrater_CTXDEM_20m.tif`: 90,345,300 bytes, SHA-256
`ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2` - equals the acquisition pin
(`pipeline/acquire_dem.py`, line 43), the provenance sidecar (`:10`), `web/data/grid_meta.json` (line 44) and
both DE1 reports. Sidecar [MEASURED]: primary URL + S3 mirror, server Last-Modified 2022-11-10,
acquired_on 2026-11-13 (UTC-derived; sidecar records date only).

Known limitation: the raw DEM is gitignored by repository policy - the repository's reproducible
acquisition path is the committed `pipeline/acquire_dem.py` (pinned URL, pinned size 90,345,300, pinned
SHA enforced; partial-download resume).

## 4. Task 03 - cropped DEM (`data/processed/dem_20m_crop.tif`)

All values in this section [MEASURED]:

- Dimensions: 1016 x 1075 px, 1 band, float32.
- CRS: `+proj=eqc +lat_ts=18.4663 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs=True`
- Transform: a=20.0, b=0.0, c=4341659.999999998, d=0.0, e=-20.0, f=1106620.0000000028 (20 m projected, north-up, unrotated).
- Bounds (projected m): (4341660.0, 1085120.0, 4361980.0, 1106620.0)
- NoData: record -3.4028234663852886e+38; census: 0 NoData, 0 NaN, 0 +/-Inf of 1,092,200 pixels
  (the grid is fully valid; NoData handlers downstream are unexercised by data).
- Elevation range: -2683.66162109375 .. -1650.4349365234375 m (mean -2363.689 m).
- Provenance tags: 6/6 present; SOURCE_SHA256 == raw DEM SHA-256 (chain intact).

Limitations: terrain resolution is 20 m/px (the 1 m HiRISE DEM was considered, not acquired - P2); the
source map's own horizontal displacement is ~9.6 m average (USGS-stated).

## 5. Task 04 - shared grid contract (`web/data/grid_meta.json`)

[MEASURED] 8/8 contract cross-checks against the live DEM PASS: width, height, CRS tokens,
pixel_size_projected_m == transform, elev_range_m == measured range, nodata_elev_dem == raster record,
provenance.dem_sha256 == live cropped DEM, provenance.source_dem_sha256 == live raw DEM.
pixel_size_m.x ground correction verified: 20 m x cos(18.5 deg)/cos(18.4663 deg) =
19.99606821438402 == recorded 19.99606821438402.

Line-ending note [MEASURED]: the worktree file is a CRLF checkout; its SHA-256 differs from the LF blob
(`10da77dd...` == the sha recorded in `data/processed/grid_meta_report.md` and == `git show HEAD:`)
purely by line endings - content-identical after normalization. Not a defect.

## 6. Task 05 - elevation binary (`web/data/elev_dm_i16.bin`)

[MEASURED] 2,184,400 bytes = exactly 1016 x 1075 x 2; decoded Int16 little-endian and compared against
the live DEM:

- Full-array equality vs the half-even re-derivation: 1092200 of 1092200 elements equal
  (0 differing).
- Max decode error |int16/10 - DEM|: 0.0500000000001819 m (bound 0.05 m + 1e-9 m - exactly the quantization bound).
- Sentinel -32768 count: 0 (matches the 0 source-invalid pixels; the sentinel path is unexercised).
- Stored range: -26837 .. -16504 dm (bracket [-26837, -16504]).

[HISTORICAL] `data/processed/elev_bin_report.md`: double-export determinism (SHA-256 x3), layout/endianness
hypothesis matrix (exactly one PASS), rounding-mode fingerprint and half-even tie invariant - all PASS.

## 7. Task 06 - CTX basemap (`web/data/ctx_basemap.jpg`) and hillshade (`web/data/hillshade.png`)

[MEASURED]

- `ctx_basemap.jpg`: 337,494 bytes (<= 5 MB), mode RGB, 1016 x 1075;
  source SHA-256 `842b457a...` matches the provenance sidecar.
- `hillshade.png`: 407,341 bytes (<= 3 MB), mode L, 1016 x 1075.

[HISTORICAL] Task 06 validators: CTX - full-image comparison vs independently derived expectation
(max |diff| 25 DN, mean 3.05, PSNR 36.11 dB, blur3x3 0.56 - q85 lossy bounds justified by an
independent-encoder measurement); double-export determinism SHA x3. Hillshade - EXACT full-array
equality vs independent derivation (PNG lossless, 0 differing), Horn/315deg/45deg/z=1.0, determinism SHA x3.
Both validators' recorded output hashes equal the live files (section 4).

Limitations: the basemap is a LOSSY JPEG (q85 per PLAN; measured deviations are display-only); JPEG/PNG
layers carry NO georeferencing - geolocation is via `web/data/grid_meta.json` (see section 13).

## 8. Task 08 - geological map layer (`web/data/geologic_map.png` + legend)

[MEASURED]

- `geologic_map.png`: 44,347 bytes (<= 3 MB), mode RGBA, 1016 x 1075.
- `geologic_map_legend.json`: 14 units; unit pixel counts sum to 1,092,200 (+ background 0) - complete
  cover; units present in this grid: [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11]; outside: [4, 12, 13].
- Raw archive `sim3464_database.zip`: 349,336,873 bytes, SHA-256 `a88bd53a...` (sidecar + report match).

[HISTORICAL] Task 08 validator: EXACT full-array equality vs independent re-derivation (PNG lossless,
0 differing), alpha semantics (only 0/255), legend consistency, determinism SHA x3.

KNOWN POSITIONAL LIMITATION [documented in sources.md + report]: the source map was digitized on a
semi-controlled mosaic predating our controlled CTX basemap - unit boundaries carry ~100-200 m random
offsets and are NOT exactly aligned with the CTX basemap. The transparent-background path is unexercised
(the units tile 100% of this grid).

## 9. Task 09 - provenance register (`docs/sources.md`)

[HISTORICAL, committed blob spot-checked this session] Register contains: corrected raw DEM row (verified
SHA-256 + two-hash rule), CTX orthomosaic + SIM 3464 records (incl. the 100-200 m offset caveat), the
DE2-supplied PLACES provenance (Bundle LID `urn:nasa:pds:mars2020_rover_places`, full LIDVID
`urn:nasa:pds:mars2020_rover_places::16.0`, DOI 10.17189/btz6-5a82, Release 16.0 dated 2026-08-11, exact
per-file URLs, historical source checksums as recorded in sources.md section 2.1, full CRS/axis/
SIS-distance documentation), considered-but-not-used sources, usage-terms summary, and the DE1-scoped
AI disclosure.
Spot-checks PASS: raw DEM hash, PDS DOI, CSV checksum, AI-disclosure heading (committed blob).

## 10. Shared-grid compatibility matrix

| Layer | Path | Format | Dims | Mode/dtype | Grid-aligned |
| --- | --- | --- | --- | --- | --- |
| Cropped DEM | `data/processed/dem_20m_crop.tif` | GeoTIFF | 1016 x 1075 | float32 | YES (authoritative) |
| Elevation binary | `web/data/elev_dm_i16.bin` | Int16-LE flat | 1016 x 1075 | int16 | YES (exact array) |
| CTX basemap | `web/data/ctx_basemap.jpg` | JPEG q85 | 1016 x 1075 | RGB | YES |
| Hillshade | `web/data/hillshade.png` | PNG lossless | 1016 x 1075 | L | YES |
| Geologic layer | `web/data/geologic_map.png` | PNG lossless | 1016 x 1075 | RGBA | YES |
| Grid contract | `web/data/grid_meta.json` | JSON | 1016 x 1075 | - | YES (8/8 checks) |

All six share the identical grid: CRS `+proj=eqc +lat_ts=18.4663 +R=3396190 +units=m`, 20 m projected
pixels, row 0 = north, col 0 = west, row-major, bounds as in section 4. Zero discrepancies.
Georeferencing note: the JPEG/PNG layers carry NO georeferencing metadata. Their alignment to the grid
is established by the production and validation evidence (sections 6-8), and consumers MUST use
`web/data/grid_meta.json` for geolocation.

## 11. Interface contracts

### Full Stack

- Geolocation: the JPEG/PNG layers carry NO coordinates. Decode recipe (in `web/data/grid_meta.json` notes):
  col = floor((lon - bounds.lon_min) / deg_per_px_x); row = floor((bounds.lat_max - lat) / deg_per_px_y);
  pixel-center decode is half-open ([lon_min, lon_max) x (lat_min, lat_max]).
- Layer composition: ctx_basemap.jpg (RGB, opaque base) + hillshade.png (L) + geologic_map.png (RGBA overlay,
  alpha 0 = transparent background, alpha 255 = mapped unit) + DE2 vector layers. Legend for the geologic
  layer: `web/data/geologic_map_legend.json` (unit id/name/symbol/color/count).
- Elevation: `elev_dm_i16.bin` decode elev_m = int16_le / 10; -32768 = Missing (exclude from stats, render as
  gap, never interpolate; 0 occurrences in this data).
- The JPEG is lossy (visual layer only); PNG layers are lossless.

### Data Science

- `elev_dm_i16.bin` consumption per the same decode recipe; vertical values are metres/10.
- `slope_u8.bin` (PLAN 5.2) is Data-Science-owned and NOT on branch data - not audited here.
- Vertical datum: PLACES elevation = MOLA areoid (DE2-supplied); compatibility with the DEM vertical
  reference is UNVERIFIED and requires DS confirmation (documented in sources.md section 2.1).
- PLACES coordinate conventions documented in sources.md section 2.1 (DE2-supplied, incl. the easting
  true-distance correction per SIS 3.9.2 and the easting/northing pass-through).

## 12. Cross-track dependencies and unresolved questions

1. `slope_u8.bin` (DS) is not on branch data - FS slope-layer integration depends on DS delivery.
2. DE2 outputs (`rover_track_clean.csv`, `rover_track.geojson`, `presets.json`, `thermal.json`) live on
   `de2-implementation-ali` / `de2-data-pipeline`, not merged to `data` - provenance is documented in
   `docs/sources.md` section 2 (DE2-supplied); cross-track merge decision pending.
3. Vertical-datum compatibility (PLACES MOLA areoid vs DEM reference) - DS confirmation pending.
4. Licenses to verify before submission: rasterio/numpy/pillow/fiona + DEM product DOI + PDS terms
   (flagged in sources.md; not blockers for the tool).
5. `task09_diff.txt` (untracked, repo root) - keep-or-remove hygiene decision.
6. The SIS document (Mars2020_Rover_PLACES_PDS_SIS.pdf) referenced by DE2 is not in the repository.

## 13. Limitations and unexercised code paths (compiled)

- NoData/NaN/Inf handlers: 0 occurrences in any DE1 input (all paths verified by abort-guards + code review only).
- Warp-gap hard-fail (CTX) and PNG transparent-background: unexercised (0 gaps, 0 background pixels).
- Sentinel -32768 mapping (elevation binary): unexercised (0 source-invalid pixels).
- [HISTORICAL] Determinism proven for consecutive runs on the pinned environment in each task's own
  validator (validators were NOT rerun during Task 10); re-exports assume the pinned environment.
- Elevation quantization: 0.05 m (half-even) - by contract, not an error.
- Terrain resolution 20 m/px; geologic overlay ~100-200 m positional offset; basemap JPEG q85 lossiness.

## 14. Reproducibility constraints

- Environment: `pip install -r requirements.txt` (rasterio, numpy, pillow, fiona - all pinned; GDAL bundled in
  the wheels; no system GDAL).
- Raw datasets are NOT in Git (policy): reproduce via the committed acquirers (pinned URLs + sizes + SHA-256).
- Validators are rerunnable and own the deterministic per-task reports; double-export determinism is proven
  historically per task and was not re-executed in this Task 10 session.
- Line endings: autocrlf=true on this machine; worktree CRLF checkouts differ from LF blobs by endings only
  (affects naive SHA-256 comparisons of text files - use `git show HEAD:<path>` for blob-exact hashes).

## 15. Discrepancy analysis (previous reports vs current files)

- Output-hash comparisons: 5/5 reports match their live files exactly (dem_crop, elev_bin, ctx, hillshade,
  geologic_map). Zero hash mismatches across all 22 audited files.
- `grid_meta_report.md` recorded sha `10da77dd...` == the committed LF blob (`git show HEAD:`) exactly; the
  CRLF worktree copy hashes differently - line-ending artifact, explained and not a defect.
- No other discrepancies found.

## 16. Verdict

DE1 deliverables (Tasks 01-09) are complete, measured, hash-consistent with their validation reports,
mutually grid-aligned, and documented [MEASURED].
Full end-to-end integration is NOT yet blocker-free: it still depends on pending cross-track deliverables
and confirmations - slope_u8.bin (Data Science, not on branch data), DE2 branch integration
(rover-track/geojson/presets/thermal outputs), and vertical-datum compatibility confirmation
(PLACES MOLA areoid vs the DEM reference) - see section 12. Submission-hygiene items remain in section 12.

## 17. Evidence index

- Per-task reports: `data/processed/dem_inspection_report.md`, `data/processed/dem_crop_report.md`,
  `data/processed/grid_meta_report.md`, `data/processed/elev_bin_report.md`, `data/processed/ctx_basemap_report.md`,
  `data/processed/hillshade_report.md`, `data/processed/geologic_map_report.md`
- Validators: `pipeline/verify_env.py`, `pipeline/verify_elev_bin.py`, `pipeline/verify_ctx_basemap.py`,
  `pipeline/verify_hillshade.py`, `pipeline/verify_geologic_map.py`; acquirers and exporters alongside.
- Provenance sidecars: `data/raw/M20_JezeroCrater_CTXDEM_20m.tif.provenance.json`,
  `data/raw/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif.provenance.json`,
  `data/raw/sim3464_database.zip.provenance.json` (3 files, all on disk).
- Provenance register: `docs/sources.md` (Task 09).
- This report was generated from direct measurements on branch data @ d7f07f04d7ab4e538b28a3c3412b62011cab4fe9
  during the 2026-11-14 Task 10 audit session; it contains no invented values.

## 18. Area of interest

Longitude: 77.2229331 to 77.583964

Latitude: 18.3067994 to 18.669315
