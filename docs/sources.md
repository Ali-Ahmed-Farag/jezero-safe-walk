# Data Sources

Every data source we use must be listed here with its URL, size, download date, and license/terms. Cite every source, including open ones.

| Name | What it is | URL | Size | Downloaded on | License/terms | Used by |
| --- | --- | --- | --- | --- | --- | --- |
| Jezero CTX DEM 20 m | M20_JezeroCrater_CTXDEM_20m.tif | https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif | 87 MB | TBD | TBD | Terrain and slope analysis |
| Jezero HiRISE DEM 1 m | JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40 (TIF) | NASA Mars Trek: https://trek.nasa.gov/mars/ | size unknown | TBD | TBD | High-resolution terrain validation |
| Perseverance localized traverse | best_interp.csv (PDS Rover PLACES bundle, via Analyst's Notebook > Resources > Rover traverse and coordinate systems) | https://an.rsl.wustl.edu/m20/ | 8.28 MB | TBD | TBD | Validation against the real traverse |

## Area of interest

Longitude: 77.2229331 to 77.583964

Latitude: 18.3067994 to 18.669315

## Software Libraries & Analysis Tools (Data Science)

| Tool / Library | Version / Role | License | Used for |
| --- | --- | --- | --- |
| Python (NumPy, Rasterio) | Scientific computing & GeoTIFF raster processing | BSD-3-Clause (NumPy, Rasterio) | Horn 3×3 slope computation, coordinate projection, and rover telemetry validation |
| Node.js | JavaScript runtime | MIT License | Automated benchmarking and validation of `web/data/astar.js` |

## AI Assistance Disclosure
- **Tool Used:** Google Gemini (AI assistant)
- **Scope of Use:** Used by the Data Science role to assist with structuring Python validation scripts (`compute_slope.py`, `project_targets.py`, `validate_rover.py`), reviewing sign conventions in directional gradient projection, and drafting technical documentation (`docs/assumptions.md`). All generated code was executed, verified against real NASA PDS/JPL datasets, and validated by the team.