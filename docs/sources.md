# Data Sources

Every data source we use must be listed here with its URL, size, download date, and license/terms. Cite every source, including open ones.

| Name | What it is | URL | Size | Downloaded on | License/terms | Used by |
| --- | --- | --- | --- | --- | --- | --- |
| Jezero CTX DEM 20 m | M20_JezeroCrater_CTXDEM_20m.tif | https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif | 87 MB | TBD | TBD | Terrain and slope analysis |
| Jezero HiRISE DEM 1 m | JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40 (TIF) | NASA Mars Trek: https://trek.nasa.gov/mars/ | size unknown | TBD | TBD | High-resolution terrain validation |
| Perseverance localized traverse | best_interp.csv (PDS Rover PLACES bundle, via Analyst's Notebook > Resources > Rover traverse and coordinate systems) | https://an.rsl.wustl.edu/m20/ | 8.28 MB | TBD | TBD | Validation against the real traverse |
| Jezero CTX orthomosaic 6 m | JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif — Mars 2020 Terrain Relative Navigation CTX orthorectified image mosaic (USGS Astrogeology, DOI 10.5066/P9GV1ND3). Same product NASA Mars Trek streams as its "MRO CTX, Jezero Mosaic, Controlled" WMTS layer (layer ID identical to the file name). | Primary: https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif — Mars Trek WMTS equivalent (verification/fallback): https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml | 36,269,402 bytes (35 MB); sha256 842b457afee7c2672022b66e3f60be836c6d52e99474015bfd9ced60099b8615 | 2026-11-13 (UTC) | Public domain (USGS; access constraints none; use constraint "please cite authors"). Cite Fergason et al. 2020 (LPSC 51; product DOI 10.5066/P9GV1ND3) and Malin et al. 2007 (doi:10.1029/2006JE002808). Imagery courtesy NASA/JPL-Caltech/MSSS | CTX basemap background (Task 06) |
| Jezero geologic map (SIM 3464) | sim3464_database.zip — Sun, V., and Stack, K., 2020, Geologic map of Jezero crater and the Nili Planum region, Mars, USGS Scientific Investigations Map 3464, 1 sheet, scale 1:75,000 (DOI 10.3133/sim3464). GIS database (ESRI file geodatabase Nili.gdb, layer GeoUnits_v1: 1,304 unit polygons; Mars TM clon 77.5E on the Mars 2000 sphere). NOTE: digitized on a semi-controlled mosaic predating the controlled CTX mosaic (10.5066/P9GV1ND3) — unit boundaries carry ~100–200 m random offsets vs our grid. | https://pubs.usgs.gov/sim/3464/ (direct: https://pubs.usgs.gov/sim/3464/sim3464_database.zip) | 349,336,873 bytes (~333 MB); sha256 a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87 | 2026-11-14 (UTC) | Public domain (USGS; access constraints none; fees none). Cite Sun & Stack 2020 (SIM 3464, doi:10.3133/sim3464). Map funded by NASA, published by USGS | Geologic map overlay layer (Task 08, P2 optional) |

## Area of interest

Longitude: 77.2229331 to 77.583964

Latitude: 18.3067994 to 18.669315
