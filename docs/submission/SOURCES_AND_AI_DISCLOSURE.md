# Sources, Licenses & AI Disclosure (submission support file)

Consolidated from `docs/sources.md` (Task 09 register, DE1), `docs/B12_TASK07_LICENSING_AUDIT.md`, `docs/B8_VERTICAL_DATUM_AUDIT.md`, and the DE2/DS handoffs. Full details live in the register of record on the `data` branch.

## 1. Data sources (used)

| Source | Publisher | License / terms | DOI / link |
|---|---|---|---|
| M20 Jezero Crater CTX DEM 20 m | USGS Astrogeology | **Public domain** (verified on official product page, 2026-11-14); cite authors | page: https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic (no DOI observed on the page — not invented) |
| Mars 2020 TRN CTX orthomosaic 6 m | USGS Astrogeology | Public domain; cite authors | DOI **10.5066/P9GV1ND3** |
| Geologic map SIM 3464 (Sun & Stack, 2020) | USGS | Public domain; cite authors | DOI **10.3133/sim3464** |
| PLACES bundle (best_interp.csv, Release 16) | NASA PDS | **Public access; usage/redistribution terms UNVERIFIED — to be confirmed before submission** (deliberately not claimed public domain) | DOI **10.17189/btz6-5a82**; https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_interp.csv |
| Mars Trek WMTS (metadata access only) | NASA/JPL-Caltech | NASA content; credit "Courtesy NASA/JPL-Caltech" | https://trek.nasa.gov |
| M20 First Weather Report (thermal extrema citation) | NASA/JPL | Credit NASA/JPL | https://mars.nasa.gov/resources/25641/perseverances-first-weather-report/ |

## 2. Software libraries (exact installed versions; licenses read from the installed distributions)

rasterio 1.4.4 (BSD) · fiona 1.10.1 (BSD 3-Clause) · numpy 2.4.6 (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0) · Pillow 13.0.0 (MIT-CMU). All permissive; no restriction on derived outputs.

## 3. Considered but NOT used (no obligation)
HiRISE 1 m DTM (MOLAtopography/DeltaGeoid family), MEDA daily thermal data, raw Perseverance images, HiRISE 25 cm orthomosaic — none included in any deliverable.

## 4. Vertical datum statement (B8, verified 2026-11-14)
PLACES elevations reference the **MOLA areoid** (proven arithmetically: elevation = radius − areoid across all 32,003 records). The DEM is officially documented as **vertically localized to MOLA** ("Control Net: MOLA"); its PDS4 label does not explicitly name the areoid (residual documentation caveat). No vertical datum transformation was applied anywhere; empirical compatibility: mean bias −0.576 m over 32,003 colocated points (supporting evidence).

## 5. AI-use disclosure (per track, as required by PLAN L775)
- **DE1** (DEM, imagery, provenance, Proposal): pipeline acquisition/processing/validator scripts were authored with AI-assistant support under engineer direction; every output independently validated (reports in `data/processed/`); no AI-generated data values enter any deliverable.
- **DE2** (rover track, presets, targets, slides): pipeline scripts authored with AI-assistant support under engineer direction; every value traced to the PDS source (SIS-accurate distances, exact CSV row/sol provenance); disclosure statement owned by DE2.
- **DS** (slope, validation, A*): scripts authored with AI-assistant support under engineer direction; all scientific outputs independently validated (validation reports, B6/B9 audits); disclosure statement owned by DS.

## 6. Open licensing item before submission (owner: team)
- Confirm NASA PDS usage/redistribution terms for the PLACES-derived data (currently **UNVERIFIED** by deliberate policy — no license was invented). Derived outputs (our visualizations/routes) are the deliverables; the source CSV itself is not redistributed in the submission package.
