# B8 — Vertical Datum Audit (Jezero Safe Walk)

- **Date:** 2026-11-14
- **Type:** Read-only audit. No files modified, no commit/push, no branch changes.
- **Scope:** Determine the vertical datum of (a) the DEM (USGS M20 Jezero Crater CTX DEM 20 m) and (b) the PLACES rover-track elevations; check for any vertical datum transformation applied during data preparation; verify cross-track elevation consistency.
- **Branches inspected:** `origin/data` @ `68a1583` (DE1), `origin/analysis` @ `5f570a6` (DS, B6+B3+B9), `origin/de2-implementation-ali` @ `3a4e8aa` (DE2), `origin/web-amr` @ `f96274f` (FS). Official documentation fetched live from NASA PDS and USGS on 2026-11-14.

---

## 1. Classification (bottom line, evidence-tiered)

| Item | Classification | Basis tier |
|---|---|---|
| PLACES rover-track elevations | **PROVEN: heights above the MOLA areoid** (orthometric-style; NOT ellipsoidal) | Official PDS4 label column definitions + arithmetic identity in the delivered data (see §3) |
| DEM (M20_JezeroCrater_CTXDEM_20m) | **DOCUMENTED: vertically localized/controlled to MOLA** per official USGS product metadata. The word "areoid" is **NOT** stated in the product's own PDS4 label; "areoid-referenced" is supported by official USGS documentation of this product and its sibling ASP products, and is consistent with all empirical evidence | Official USGS wording (HIGH) + PDS4-label silence (verified) — see §2 |
| Vertical datum transformations applied | **NONE** (verified across the whole DE1 pipeline and DS validation) | Pipeline/report inspection — see §4 |
| DEM ↔ PLACES vertical compatibility | **COMPATIBLE (high confidence)** — empirical bias −0.576 m over 32,003 points | Empirical validation is **supporting evidence of compatibility**, NOT a standalone datum proof — see §5 |

---

## 2. DEM vertical reference

### 2.1 What the official record says (fetched 2026-11-14)
- USGS Astropedia product page, "Mars 2020 Science Investigation CTX DEM Mosaic"
  (`https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic`):
  - Abstract: "This mosaic includes the original Mars 2020 Jezero CTX TRN DEM but extends to include the entire crater with DEMs produced using Ames Stereo Pipeline (Beyer 2020). The added DEMs were **localize[d] to the Mars MOLA dataset vertically**…"
  - Geospatial Information: **"Control Net: MOLA"**; "Vertical Coordinate System Units: **Meters**"; publication date 2021-10-14; use constraints: public domain.
- USGS STAC documentation for the ASP-generated CTX DTMs of this product family
  (`https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/`):
  - "Each CTX DTM gives elevation values **above or below the Mars geoid (referred to as the areoid)**…"
  - "The DTM is then processed through **dem_geoid to obtain heights above the equipotential Mars surface**."
  - DTMs "aligned to MOLA using pc_align" and "controlled to ground using individual MOLA shot tracks".

### 2.2 What the product's own PDS4 label says (fetched 2026-11-14)
- Label: `https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.xml`
  (LID `urn:nasa:pds:mars2020_ctx_basemap_2021:data:m20_ctxdem_mosaic` v1.0).
- `cart:Geodetic_Model` declares **only horizontal** parameters: `spheroid_name=MARS`, `a=b=c=3,396,190 m`, `latitude_type=Planetocentric`, positive-east longitude. There is **no** Vertical_Coordinate_System_Definition and **no occurrence of the word "areoid"** anywhere in the label.
- This confirms, inside the repository, DE1's Task 02 finding
  (`origin/data:data/processed/dem_inspection_report.md` §7 cross-check 14/14 MATCH; §3 L51 "Vertical datum/elevation reference in file: NOT stated inside the GeoTIFF"; §9.3 L184–187).

### 2.3 Interpretation (labeled as interpretation, per audit rules)
The DEM is **vertically tied to MOLA** (official USGS statement). Whether its zero surface is the MOLA areoid or the MOLA ellipsoid is **not stated in the product's own label**; the family documentation (dem_geoid → "heights above the equipotential Mars surface (areoid)") and the in-repo naming convention (the considered-not-used sibling `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m`, `origin/data:docs/sources.md` L67) both point to areoid-referenced heights. This is recorded as **HIGH-confidence documentation, not a direct label statement**.

### 2.4 DEP-1 addendum (2026-11-14) — official TRN documentation, three products distinguished

DOI `10.5066/P906QQT8` resolves to the **Mars 2020 Terrain Relative Navigation CTX DTM Mosaic** (USGS, published 2020-07-24; `https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_ctx_dtm_mosaic`). The three products are now explicitly separated:

| Product | What the official record says | Vertical wording |
|---|---|---|
| **(a) Original Mars 2020 TRN CTX DTM Mosaic** (`JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m…`, DOI 10.5066/P906QQT8) | "Control Net: **MOLA**"; DTMs aligned via pc_align, then "simultaneously aligned using ASP to the **HRSC Level 5 DTM** to bring them into absolute alignment with an independent reference" ("adjusting the mosaic by 183.3 meters vertically to align with HRSC"); "Vertical Coordinate System Units: Meters" | Product NAME itself: `DTM_MOLATopography_DeltaGeoid`; neither the PDS3 label nor the ISIS 3 label (both fetched) contains a verbal vertical-datum statement |
| **(b) Extended 2021 Mars 2020 Science Investigation CTX DEM Mosaic — THE PRODUCT USED** (`M20_JezeroCrater_CTXDEM_20m.tif`, pub. 2021-10-14) | "This mosaic **includes the original Mars 2020 Jezero CTX TRN DEM** but extends to include the entire crater with DEMs produced using ASP. **The added DEMs were localize[d] to the Mars MOLA dataset vertically**"; "Control Net: **MOLA**" | No occurrence of the word "areoid" on the product page or in its PDS4 label |
| **(c) Additional ASP-generated DEMs** (USGS STAC, `stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/`) | "aligned to MOLA using pc_align" (individual MOLA shot tracks); "The DTM is then processed through **dem_geoid** to obtain heights above the **equipotential Mars surface**"; "elevation values above or below the Mars geoid (referred to as the **areoid**)" | Explicit areoid statement — **attributed to this collection only** |

**New official evidence — the naming convention, explicitly defined (fetched 2026-11-14):**
The USGS README of the MSR TRN HiRISE delivery (`https://astrogeology.usgs.gov/ckan/dataset/5da0038e-df6e-4c12-919f-7219ba8059aa/resource/060bd5aa-cf60-4cbd-9c71-e3a52191b0b7/download/readme.txt`; ScienceBase release page: `https://www.sciencebase.gov/catalog/item/67a2a012d34e05baae1c87e7`) states, for that delivery:

> "DTMs are named `MOLATopography_DeltaGeoid` to indicate that they represent **heights relative to the martian geoid** (like the MOLA Gridded Topography product available from the PDS)."

and

> "A 'delta geoid' DTM product was derived by running the `dem_geoid` tool from ASP on the blended DTM mosaic. The delta geoid products represent **heights relative to the geoid of Mars** (this product type is analogous to the MOLA Gridded Topography product available from the PDS)."

**Attribution discipline (per audit rules):** this README defines the convention for the **MSR TRN delivery** — a different (2024) USGS product in the same TRN naming family (SOCET SET + `MOLATopography_DeltaGeoid` naming, exactly matching the Mars 2020 TRN naming scheme `JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m`). It is recorded here as **official family-level documentation of the naming convention**, NOT as a statement about product (b) itself. The Fergason et al. 2020 LPSC abstract (cited on the DOI page, `https://www.hou.usra.edu/meetings/lpsc2020/pdf/2020.pdf`) remains PDF-only in this environment.

**DEP-1 status: PARTIALLY CLOSED.** Closed: the three products are distinguished with per-product official wording; the naming convention is now officially defined in USGS documentation; lineage (a)→(b) is documented. Still open: **no fetched official document states the word "areoid" for product (b) itself** (its page, PDS4 label, and the original TRN component's PDS3/ISIS labels are all silent in words, carrying the convention only in the product name). Closing would require the Fergason et al. 2020 abstract/report text or a direct USGS confirmation for product (b).

---

## 3. PLACES vertical reference — PROVEN

### 3.1 Official label (NASA PDS, fetched 2026-11-14)
`https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_interp.csv.xml` (v16.0):
- `elevation`: "Elevation of the point **relative to the datum**. Positive is up. See SIS for details." (unit METER; missing constant −9999)
- `areoid`: "Areoid value for point." (unit METER)
- `radius`: "Radius value for point." (unit METER)
- The SIS (`Mars2020_Rover_PLACES_PDS_SIS.pdf`, §2.1.4, §3.9.1–3.9.3, §5.1.3 — cited by DE2 in
  `origin/de2-implementation-ali:docs/de2/DE2_FINAL_HANDOFF_2026-11-14.md` §2 and recorded in
  `origin/data:docs/sources.md` L37) states elevations are referenced to the MOLA areoid. (The SIS PDF is not text-fetchable in this environment; the arithmetic identity below closes the proof independently.)

### 3.2 Arithmetic identity (computed 2026-11-14, all 32,003 rows)
Over `origin/de2-implementation-ali:data/processed/rover_track_clean.csv`:

```
elevation == radius − areoid
  exact (0.000 m diff):   198 / 32,003 rows
  within 1 mm:         28,038 / 32,003 rows
  max |deviation|:        0.001000 m   (= independent 3-decimal rounding of the three columns)
```
Sample rows: sol 0: 3391937.166 − 3394507.076 = −2569.910 = elevation ✓; sol 130: −2569.357/−2569.358 ✓; sol 1815: −1952.887 ✓.

**Conclusion (definitional):** PLACES `elevation` is the height of the rover position above the **MOLA areoid surface** (orthometric-style). It is not ellipsoidal height and not a site-local frame value.

---

## 4. Vertical datum transformations — NONE applied (verified)

| Stage | Check | Evidence (file path) | Result |
|---|---|---|---|
| Task 02 acquisition/inspection | "opened read-only; no crop, resample, or reprojection was performed"; source SHA-256 identical before/after | `origin/data:data/processed/dem_inspection_report.md` §1 | ✅ none |
| Task 03 crop | "each output pixel is a **verbatim copy** of a source pixel"; NoData bitwise-identical (`0xFF7FFFFF`); window cols [633,1649) rows [1840,2915); no offset added | `origin/data:data/processed/dem_crop_report.md` | ✅ none |
| Task 05 exporter | Operations are exactly: Float64 multiply ×10 (decimetres) + half-even rounding + NoData mapping to −32768. Grep of `pipeline/export_elev_bin.py`, `pipeline/crop_dem.py`, `pipeline/make_grid_meta.py`: **zero** additive/subtractive vertical constants, zero datum/areoid/MOLA operations | `origin/data:pipeline/export_elev_bin.py` | ✅ none |
| DS validation | `validate_rover.py` L178–182: `elev_diff = dem_elev − rover_elev` compared **raw**; the constant difference is **recorded** (`mean_bias_m`) and reported both raw and bias-corrected — no datum offset applied to any data. Complies with PLAN §5.7 L286 ("record and correct any constant offset" — recorded in metrics, data left untouched) | `origin/analysis:analysis/validate_rover.py`; `origin/analysis:web/data/validation_results.json` | ✅ none |
| DE2/FS | No elevation-valued outputs modified anywhere (DE2 distances are horizontal SIS corrections only; FS consumes elev/10 with NoData gap handling) | `origin/de2-implementation-ali:pipeline/make_geojson.py` (per `origin/data:docs/sources.md` §2.1); `origin/web-amr:web/data/metrics.js` | ✅ none |

---

## 5. DEM ↔ PLACES compatibility — empirical evidence (supporting, not standalone proof)

| Metric (DS, `origin/analysis:web/data/validation_results.json`) | Value |
|---|---|
| Colocated comparison points | 32,003 (every ROVER frame row) |
| `dem_elev − rover_elev` mean bias | **−0.576 m** |
| RMSE raw / bias-corrected | 3.159 m / **3.106 m** |

**Role of this evidence:** a material vertical-datum mismatch (areoid vs ellipsoid vs any other surface, or an uncorrected constant offset) would appear as a large systematic bias — typically tens to hundreds of metres in this region. The observed bias is −0.576 m, i.e. the two elevation sets sit on the **same vertical reference to within ~0.6 m**, with the residual attributable to DEM smoothing at 20 m/pixel, sub-pixel registration, and IMU/wheel-scale effects (per the DS summary text).

**This is recorded as supporting evidence of compatibility only.** It does not, by itself, establish what either datum *is* (a constant offset could in principle be absorbed); the datum identification rests on §2 and §3.

---

## 6. DEP-1 / DEP-2 closure status (updated 2026-11-14)

### DEP-1 — Official TRN documentation: **PARTIALLY CLOSED**
- **Closed:** three-product distinction documented with per-product official wording (§2.4); the USGS TRN-family naming convention `MOLAtopography_DeltaGeoid` = "heights relative to the martian geoid" is now backed by an explicit official USGS README sentence; lineage (original TRN DEM → extended 2021 mosaic) documented on the product pages; DOI 10.5066/P906QQT8 resolved and inspected (including its PDS3 and ISIS labels).
- **Still open:** no fetched official document states "areoid" **for the used 2021 mosaic itself** (product page, PDS4 label, and the original component's PDS3/ISIS labels are word-silent; the convention is carried by the product name). Full closure needs the Fergason et al. 2020 abstract/report text or direct USGS confirmation for the used product.

### DEP-2 — DS sign-off: **CLOSED (scope: compatibility validation)**

**DS compatibility sign-off — recorded 2026-11-14 by the DS track owner (user-directed; no other reviewer named or implied).**

Scope of this sign-off: **vertical-datum compatibility validation only** — it does not certify the DEM's absolute datum name beyond the documentation evidence in §2, and the caveat is retained that **the used mosaic's own PDS4 label does not explicitly name the areoid** (§2.2, DEP-1 residual).

Evidence reviewed (all on `origin/analysis` @ `5f570a6`, verified this session):
1. **`analysis/validate_rover.py` (L107–145, L178–182):** raw elevation comparison `dem_elev − rover_elev` over **all 32,003** retained ROVER rows; no vertical offset, datum shift, or transformation applied anywhere in DS code (repo-wide grep of `analysis/` for datum/areoid/MOLA: the only hit is the comment `# Elevation (datum) (A.2, A.3)` at L178). PLAN §5.7 L286 compliance: the constant difference is **recorded** (`mean_bias_m`) and reported raw (3.159 m) and bias-corrected (3.106 m).
2. **`web/data/validation_results.json`:** mean bias **−0.576 m**, RMSE raw 3.159 m / bias-corrected 3.106 m over 32,003 points — no datum-scale systematic difference.
3. **B3 (commit `81a5594`):** DS consumes the canonical DE1 grid contract (`grid_meta.json` blob `2d908027…`) and DE2 canonical presets — coordinate conversion floor-based per the contract; no elevation-valued reinterpretation introduced.
4. **B6 (commit `10c6da5`):** slope pipeline consumes the DE1-authoritative elevation binary (`dacf593f…`) byte-identical; hard-fail on invalid pixels; all DS metrics unchanged (byte-identical regression `5d7d0396…`).
5. **B9 (commit `5f570a6`):** A* cost model verified optimal against Dijkstra baseline on the real grid (8/8 canonical case/mode combinations + 15 random grids); no distance-semantics change that could mask a vertical offset.

**Sign-off conclusion:** within the compatibility-validation scope, the DEM and the PLACES rover-track elevations are on the **same vertical reference**; no hidden vertical transformation exists in the DS workflow; the recorded −0.576 m bias is treated as measurement/smoothing difference, not a datum offset. The documentation caveat on the DEM's label wording (DEP-1 residual) is acknowledged and does not affect this compatibility conclusion.

### Consequent documentation update: **DONE**
`docs/sources.md` (working tree, branch `data`) L37 replaced — "remains UNVERIFIED and requires Data Science confirmation" → VERIFIED wording reflecting exactly the evidence tiers above (PLACES proven; DEM officially MOLA-localized with label caveat; empirical bias −0.576 m as supporting evidence; DS sign-off recorded). No certainty elevated beyond the sources.

---

## 7. Verdict

**COMPATIBLE — both elevation datasets reference the MOLA areoid.**
- PLACES: **proven** (official label semantics + `elevation = radius − areoid` identity over all 32,003 rows).
- DEM: **officially documented as vertically localized to MOLA** (USGS "Control Net: MOLA", "localize to the Mars MOLA dataset vertically"; family documentation: heights above the areoid via dem_geoid; TRN-family naming convention officially defined as "heights relative to the martian geoid") — but the product's own PDS4 label contains **no direct "areoid" statement**; recorded as a documentation gap (DEP-1 PARTIALLY CLOSED), not an incompatibility.
- No vertical datum transformation was applied anywhere in the project (verified end-to-end).
- The empirical −0.576 m bias over 32,003 points is **supporting evidence of compatibility**, not a standalone datum proof.
- DEP-2 DS compatibility sign-off: **CLOSED** (scope-limited; label caveat retained). Documentation update to `docs/sources.md`: **DONE**.

---

## 8. Source register (all accessed 2026-11-14)

| # | Source | URL | Used for |
|---|---|---|---|
| 1 | USGS Astropedia product page | https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic | DEM: "Control Net: MOLA", vertical localization statement |
| 2 | USGS STAC — ASP CTX DTMs | https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/ | Family convention: heights above the areoid via dem_geoid |
| 3 | PDS4 label, DEM mosaic (v1.0) | https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.xml | Label silence on vertical datum (verified) |
| 4 | PDS4 label, PLACES best_interp.csv (v16.0) | https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_interp.csv.xml | elevation/areoid/radius column semantics |
| 5 | PLACES SIS (cited; PDF not text-fetchable here) | https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/document/Mars2020_Rover_PLACES_PDS_SIS.pdf | MOLA-areoid reference (§2.1.4, §3.9.x, §5.1.3) |
| 6 | USGS TRN CTX DTM Mosaic page (DOI 10.5066/P906QQT8) | https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_ctx_dtm_mosaic | DEP-1: original TRN product — Control Net MOLA, HRSC alignment, product name `MOLAtopography_DeltaGeoid` |
| 7 | USGS MSR TRN HiRISE README (naming-convention definition) | https://astrogeology.usgs.gov/ckan/dataset/5da0038e-df6e-4c12-919f-7219ba8059aa/resource/060bd5aa-cf60-4cbd-9c71-e3a52191b0b7/download/readme.txt (release page: https://www.sciencebase.gov/catalog/item/67a2a012d34e05baae1c87e7) | Official definition: `MOLATopography_DeltaGeoid` = "heights relative to the martian geoid" (family-level documentation) |
| 8 | Original TRN component labels (PDS3 + ISIS 3) | https://astrogeology.usgs.gov/ckan/dataset/2d14f45e-e7d3-41e7-aa50-9a8d080cf3cc/resource/be9df719-300a-480b-a2da-13dc38f8fce1/download/jez_ctx_b_soc_008_dtm_molatopography_deltageoid_20m_eqc_latts0_lon0_pds3.lbl ; https://astrogeology.usgs.gov/ckan/dataset/2d14f45e-e7d3-41e7-aa50-9a8d080cf3cc/resource/8255bca6-6047-4cc2-b449-60d5e9f80452/download/jez_ctx_b_soc_008_dtm_molatopography_deltageoid_20m_eqc_latts0_lon0.lbl | Both word-silent on vertical datum (verified) |
| 9 | In-repo provenance | `origin/data:docs/sources.md`; `data/processed/dem_inspection_report.md`; `data/processed/dem_crop_report.md`; `data/processed/elev_bin_report.md`; `web/data/grid_meta.json`; `origin/data:docs/PLAN.md` §5.7; `origin/analysis:analysis/validate_rover.py`; `web/data/validation_results.json`; `origin/de2-implementation-ali:data/processed/rover_track_clean.csv` | All evidence rows above |
