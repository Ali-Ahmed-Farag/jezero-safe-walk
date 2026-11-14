# Data Sources

Every data source we use must be listed here with its URL, size, download date, and license/terms. Cite every source, including open ones.

Status conventions (Task 09): acquisition dates are UTC-derived (acquisition sidecars record the date only, no timezone marker). License entries marked "to be verified before submission" have not yet been checked against an authoritative source and must be reviewed per the PLAN submission checklist. Section 1 lists sources actually used by DE1; section 3 lists sources considered but not used.

## 1. Datasets used by DE1

| Name | What it is | URL | Size | Downloaded on | License/terms | Used by |
| --- | --- | --- | --- | --- | --- | --- |
| Jezero CTX DEM 20 m (raw source) | M20_JezeroCrater_CTXDEM_20m.tif - USGS Mars 2020 Science Investigation CTX DEM (USGS Astrogeology Science Center) | Primary: https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif ; mirror: https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif ; record: https://astrogeology.usgs.gov/ckan/dataset/f8ef46b8-d512-4c46-b825-fe9633c38e1c/ | 90,345,300 bytes; sha256 of the RAW SOURCE: ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2. TWO-HASH RULE: the cropped grid DEM (data/processed/dem_20m_crop.tif) has its own hash b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae (web/data/grid_meta.json provenance.dem_sha256) - do not interchange | 2026-11-13 (UTC-derived; acquisition sidecar records date only) | USGS public domain; cite authors (Fergason et al., 2020). Product DOI: unverified - confirm before submission | Tasks 02-05 (acquisition, inspection, crop, grid metadata, elevation binary); Task 06 hillshade source |
| Jezero CTX orthomosaic 6 m | JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif — Mars 2020 Terrain Relative Navigation CTX orthorectified image mosaic (USGS Astrogeology, DOI 10.5066/P9GV1ND3). Same product NASA Mars Trek streams as its "MRO CTX, Jezero Mosaic, Controlled" WMTS layer (layer ID identical to the file name). | Primary: https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif — Mars Trek WMTS equivalent (verification/fallback): https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml | 36,269,402 bytes (35 MB); sha256 842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615 | 2026-11-13 (UTC) | Public domain (USGS; access constraints none; use constraint "please cite authors"). Cite Fergason et al. 2020 (LPSC 51; product DOI 10.5066/P9GV1ND3) and Malin et al. 2007 (doi:10.1029/2006JE002808). Imagery courtesy NASA/JPL-Caltech/MSSS | CTX basemap background (Task 06) |
| Jezero geologic map (SIM 3464) | sim3464_database.zip — Sun, V., and Stack, K., 2020, Geologic map of Jezero crater and the Nili Planum region, Mars, USGS Scientific Investigations Map 3464, 1 sheet, scale 1:75,000 (DOI 10.3133/sim3464). GIS database (ESRI file geodatabase Nili.gdb, layer GeoUnits_v1: 1,304 unit polygons; Mars TM clon 77.5E on the Mars 2000 sphere). NOTE: digitized on a semi-controlled mosaic predating the controlled CTX mosaic (10.5066/P9GV1ND3) — unit boundaries carry ~100–200 m random offsets vs our grid. | https://pubs.usgs.gov/sim/3464/ (direct: https://pubs.usgs.gov/sim/3464/sim3464_database.zip) | 349,336,873 bytes (~333 MB); sha256 a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87 | 2026-11-14 (UTC) | Public domain (USGS; access constraints none; fees none). Cite Sun & Stack 2020 (SIM 3464, doi:10.3133/sim3464). Map funded by NASA, published by USGS | Geologic map overlay layer (Task 08, P2 optional) |
| NASA Mars Trek WMTS service | Streaming service used for VERIFICATION/FALLBACK of the CTX orthomosaic above; service metadata inspected, no tiles downloaded | https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml | n/a (no tiles downloaded) | 2026-11-13 (metadata access) | NASA content; imagery credit "Courtesy NASA/JPL-Caltech" (JPL image use policy, verified 2026-11-13) | Task 06 verification/fallback |
| Software libraries (DE1) | rasterio==1.4.4; numpy==2.4.6; pillow==13.0.0; fiona==1.10.1 (pinned in requirements.txt). rasterio bundles GDAL 3.10.3; fiona bundles its own GDAL 3.9.1 (no system GDAL needed) | PyPI project pages (https://pypi.org/project/rasterio/, https://pypi.org/project/numpy/, https://pypi.org/project/pillow/, https://pypi.org/project/fiona/) | n/a (pip-installed) | installed with the project environment 2026-11-13 (fiona: 2026-11-14) | License terms TO BE VERIFIED before submission (per PLAN's sources.md convention). Installed-version licenses verified 2026-11-14 (B12 audit, .venv dist-info): rasterio BSD; fiona BSD-3-Clause; numpy BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; pillow MIT-CMU — all permissive | All DE1 processing and validation scripts |
| Software libraries (DS track, as recorded by DS) | scipy 1.14.1 (BSD-3-Clause); matplotlib 3.10.1 (PSF/BSD); pandas 2.2.3 (BSD-3-Clause) — matplotlib used by analysis/generate_extras.py charts | DS track sources register (merged from DS docs/sources.md at integration, 2026-11-14); PyPI project pages | n/a | DS environment | Permissive (BSD/PSF) — attribution per license terms | DS analysis scripts and charts |
| Frontend libraries (FS track, as recorded by DS/FS) | Leaflet 1.9.4 (BSD-2-Clause); Chart.js 4.x (MIT); Inter font via Google Fonts (SIL Open Font License 1.1) — Inter entry added from FS's register at integration | DS/FS track sources registers (merged at integration, 2026-11-14); Leaflet/Chart.js/Google-Fonts official pages | n/a | bundled with the web app | Permissive (BSD-2/MIT/OFL-1.1) — attribution per license terms | web UI (map + charts + typography) |

## 2. Datasets provided by other tracks - provenance as supplied by DE2

> Provenance below reflects DE2's latest technical verification - PLACES follow-up (supplied to the team 2026-11-14), cross-referenced against DE2's committed artifacts on branch de2-implementation-ali. Items marked [DE2-supplied] are not independently verifiable on this branch (the raw PLACES files are not committed to this repository). All checksums below are HISTORICAL verification records from DE2's 2026-11-13 acquisition, NOT freshly recalculated on branch data.

### 2.1 NASA PDS Rover PLACES bundle - best_interp.csv (+ .xml)

| Item | Value |
| --- | --- |
| What it is | Perseverance rover traverse telemetry (PDS Rover PLACES bundle); used for rover-track cleaning and downstream validation |
| Bundle LID | urn:nasa:pds:mars2020_rover_places [DE2-supplied; corroborated in-repo: origin/de2-implementation-ali:pipeline/make_geojson.py line 81 and the web/data/rover_track.geojson source property on that branch] |
| Bundle LIDVID | urn:nasa:pds:mars2020_rover_places::16.0 [DE2-supplied] |
| DOI | 10.17189/btz6-5a82 [DE2-supplied] |
| Release | 16.0, released 2026-08-11 [DE2-supplied] |
| Source | NASA PDS Geosciences Node - official PDS bundle, with the NASA PDS metadata references as supplied in DE2's latest technical verification |
| URL | Official per-file URLs: best_interp.csv - https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_interp.csv ; best_interp.csv.xml - https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_interp.csv.xml (also reachable via NASA PDS Analyst's Notebook > Resources > Rover traverse and coordinate systems) |
| Access date | 2026-11-13 |
| License/terms | NASA PDS archive - public access; usage/license terms to be verified before submission (NOT claimed public domain; no CC0 claim) |
| Source file sizes / SHA-256 (HISTORICAL verification records from the 2026-11-13 acquisition; NOT freshly recalculated on branch data) | best_interp.csv: 8,684,070 bytes; SHA-256 58FBC62F2676195A00B40B2DA53A797A70284A8D2344B288C999D325B7CCB4CC. best_interp.csv.xml: 15,890 bytes; SHA-256 03A382042C73D7A7EACED1C32F64108ED42C07F2139BBCC815CB4AB882EAC70B (values transcribed verbatim, uppercase, exactly as supplied by DE2) |
| Coordinate conventions (CRS) | Equirectangular projection; standard parallel 18.4663 deg planetocentric; central meridian 0 deg; east-positive longitude; sphere radius 3,396,190 m; metre units; false easting/northing 0. Identical to the DE1 grid CRS (+proj=eqc +lat_ts=18.4663 +R=3396190 +units=m; web/data/grid_meta.json) [DE2-supplied; CRS identity cross-checkable in-repo against the grid contract] |
| Axis convention | PLACES files: +X Northing, +Y Easting, +Z Down. GIS raster convention: X Easting, Y Northing. [DE2-supplied] |
| Elevation datum | VERIFIED (B8 audit 2026-11-14; see B8_VERTICAL_DATUM_AUDIT.md) — PLACES elevations reference the MOLA areoid (proven: PDS4 label semantics + arithmetic identity elevation = radius − areoid across all 32,003 retained rows). The DEM is officially documented by USGS as vertically localized/controlled to MOLA ("Control Net: MOLA"; "the added DEMs were localized to the Mars MOLA dataset vertically"); the extended mosaic's own PDS4 label does not explicitly name the areoid (residual documentation caveat). No vertical datum transformation was applied anywhere in the project. Empirical validation across 32,003 colocated rover points supports compatibility (mean bias −0.576 m; supporting evidence, not a standalone datum proof). DS compatibility sign-off recorded 2026-11-14 (B8 audit §DEP-2) |

Coverage and record counts (DE2-supplied; DE2 cross-checked the record count against the source XML <records> element):

- Source coverage: Sols 0-1897.
- Source records: 33,458 (matches the source XML <records> element) = 33,370 frame==ROVER rows + 88 frame==SITE rows (SITE rows are localization references, not traverse data; excluded).
- 1,367 records excluded as outside the AOI - all on the western edge, Sols 1816-1897; 0 excluded on the other three edges.
- Retained (processed) ROVER coverage: Sols 0-1815; 32,003 records; non-decreasing Sol order preserved (no sorting, no interpolation, original value formatting preserved).

Axis/distance handling (DE2-supplied; corroborated in-repo):

- Easting true-distance correction: true_east_dx = delta_easting * cos(phi_mid) / cos(18.4663 deg); northing differences are already true metres. Per PLACES SIS section 3.9.2, as applied by DE2 (origin/de2-implementation-ali:pipeline/make_geojson.py: "true_dx = delta_easting * cos(phi_mid) / cos(18.4663deg)"; measured total traverse length 41,202.9 m in web/data/rover_track.geojson on that branch).
- Relevance: rover-distance calculations (PLAN 5.6) must use ground-corrected eastings, NOT raw projected metres. This is consistent with web/data/grid_meta.json pixel_size_m.x = 19.99606821438402 (= 20 m x cos(18.5 deg) / cos(18.4663 deg)) vs pixel_size_projected_m = 20 m. No Earth-based haversine formula is used anywhere.

Field-specific missing-value semantics (DE2-supplied, from the XML/SIS as cited by DE2):

- -9999: declared missing constant for the REQUIRED fields (sol, easting, northing, longitude, planetocentric_latitude, pitch, roll, yaw, elevation) - a row is dropped if any of these is -9999/unparseable; 0 retained rows were affected.
- -9999 in OPTIONAL fields (landing_x/y/z, planetodetic_latitude, quat_s/v1/v2/v3, areoid, radius) is represented as an EMPTY CELL (no invalid numeric sentinel in the delivered CSV); a row is never deleted solely for an optional missing value. Documented exception: landing_y at record 24,571 (Sol 1351) had source value -9999.282 - represented empty by DE2; the Data Science copy retains the raw value (documented 1-cell difference).
- -1 in site/drive/pose: documented not-applicable constant (per XML/SIS as cited by DE2); preserved as-is, NOT treated as missing (pose = -1 in all 32,003 retained rows; no -1 appears in any coordinate column).

DE2 output provenance (attributed to DE2, not DE1; DE2-supplied):

- File: data/processed/rover_track_clean.csv - 8,306,012 bytes; sha256 71c1b04e9f461107167fe2b414a7aa05f334a15a9d2c299d6f276f26fe35dbdd; 32,004 lines (header + 32,003 records); ASCII, LF-only; produced by pipeline/clean_track.py (deterministic, rerunnable; committed on branch de2-implementation-ali).
- Downstream DE2 outputs (branch de2-implementation-ali): web/data/rover_track.geojson (PLAN 5.2; LineString + ~50 m points; SIS-corrected traverse length 41,202.9 m), web/data/presets.json (4 scenarios with SIS true-ground distances), web/data/thermal.json (cited Mars thermal extrema).
- Usage: consumed by Data Science validation and Full Stack. DE1 does NOT consume these outputs in its current pipeline (DE1 Tasks 01-08 are independent of it).

## 3. Sources considered but not used

| Name | What it is | Status (as of 2026-11-14) |
| --- | --- | --- |
| Jezero HiRISE DEM 1 m | JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40 (TIF), via NASA Mars Trek | Considered for high-resolution terrain validation; NOT downloaded or used (P2 alternative). Size/license: unverified |
| best_interp.csv (+ .xml) - for DE1 | NASA PDS PLACES traverse | NOT used by DE1 directly; see section 2.1 for the DE2-supplied provenance of DE2's use |
| MEDA (daily thermal curve) | NASA PDS Analyst's Notebook | Considered by DE2; DE2 used cited Mars thermal extrema instead (thermal.json) - see origin/de2-data-pipeline:docs/sources.md |
| Mars Perseverance raw images | NASA (links only, P2) | Considered by DE2; not used |
| HiRISE 25 cm orthomosaic | JEZ_hirise_soc_006_orthoMosaic_25cm (NASA Mars Trek) | Considered P2 alternative for the geological overlay context (PLAN line 353); not used |

## 4. Usage terms and attribution summary

- USGS products (raw DEM, CTX orthomosaic, SIM 3464): public domain; cite the authors as recorded in rows 1.1-1.3 above (verified from the official USGS records/pages listed there).
- NASA/JPL imagery (including Mars Trek layers): usable for any purpose without prior permission, credit "Courtesy NASA/JPL-Caltech" (JPL image use policy, verified 2026-11-13).
- NASA PDS (PLACES): public access; usage/license terms to be verified before submission (section 2.1 - NOT claimed public domain; no CC0 claim).
- Every image or statement in public materials must carry its source (PLAN line 500).

## 5. AI assistance disclosure (DE1 scope only)

DE1's acquisition, processing, and validator scripts (pipeline/acquire_*.py, pipeline/export_*.py, pipeline/verify_*.py) were authored with AI-assistant support under engineer direction. Every output was independently validated (reports under data/processed/), and no AI-generated data values enter any deliverable. This statement covers DE1 ONLY; Data Engineer 2 and Data Science provide their own disclosures (DE2's statement: branch de2-implementation-ali, docs/submission/SOURCES_AND_AI_DISCLOSURE.md §5; DS's statement preserved below).

### DS AI disclosure (preserved verbatim from DS's sources register at integration, 2026-11-14)

تم استخدام نماذج الذكاء الاصطناعي (Gemini و Claude و DeepSeek) كمساعدين في كتابة الأكواد (JavaScript و Python)، وتصحيح الأخطاء (Debugging)، وتوثيق المنهجية، واقتراح تحسينات على خوارزمية A*. لم يتم استخدامها لتوليد أي أرقام أو نتائج علمية، وكل الأرقام المذكورة في التقرير تم استخراجها من تشغيل الكود على بيانات حقيقية بواسطة أعضاء الفريق.

### FS AI disclosure (preserved verbatim from FS's sources register at integration, 2026-11-14)

- **Code Generation:** The frontend (HTML, CSS, JavaScript) was developed with the assistance of AI tools (DeepSeek and Claude) to accelerate UI development, implement the Canvas charting logic, and integrate the A* algorithm.
- **Data Science & Engineering:** The core algorithms (`astar.js`, `metrics.js`), data processing (DEM cropping, slope calculation), and validation metrics were developed by the team's Data Scientist and Data Engineers. AI was used for documentation review and formatting.


## Area of interest

Longitude: 77.2229331 to 77.583964

Latitude: 18.3067994 to 18.669315
