# G3 — Source Consolidation & Closure Report

- **Date:** 2026-11-14
- **Owner:** DE1 track (`data` branch) — G3 was assigned to DE1 in `docs/de2/DE2_FINAL_HANDOFF_2026-11-14.md` (§"G3/DE1")
- **Inputs reviewed:** `docs/sources.md` (Task 09 register @ `origin/data` @ `a535d0f`), DE2 final handoff, DE1 provenance reports (`data/processed/*_report.md`), DS validation artifacts (`origin/analysis` @ `5f570a6`), FS data dependencies (`origin/web-amr` @ `f96274f`), B12 licensing audit.

---

## 1. G3 acceptance criteria — VERIFIED (9/9 PASS)

G3 (from DE2 final handoff): *"merge `docs/sources.md` provenance diff into unified file. Owner: DE1. Acceptance: DOI 10.17189/btz6-5a82 + SIS refs + checksums present in final sources.md; then DE2 tree diff can be discarded after merge."*

| # | Criterion | Result | Evidence in `docs/sources.md` |
|---|---|---|---|
| G3-A | PLACES DOI `10.17189/btz6-5a82` present | ✅ PASS | §2.1 DOI row |
| G3-B | SIS references present | ✅ PASS | L48 (SIS §3.9.2 easting correction), L51/L55 (XML/SIS missing-value semantics) |
| G3-C | `best_interp.csv` SHA-256 checksum | ✅ PASS | §2.1 L34 (`58FBC62F…BCC4CC`, 8,684,070 bytes) |
| G3-D | `best_interp.csv.xml` SHA-256 checksum | ✅ PASS | §2.1 L34 (`03A38204…C70B`, 15,890 bytes) |
| G3-E | DEM two-hash rule preserved (raw vs crop never interchanged) | ✅ PASS | raw `ba7f706e…d1ba2` + crop `b7467953…41ae` both present, separately labeled |
| G3-F | License/usage-terms section | ✅ PASS | §4 (USGS public domain verified; NASA credit; PDS terms scoped UNVERIFIED) |
| G3-G | AI-assistance disclosure | ✅ PASS | §5 (DE1-scoped statement; DE2/DS own their statements) |
| G3-H | Considered-but-not-used section | ✅ PASS | §3 (HiRISE 1 m, MEDA, raw images, HiRISE 25 cm) |
| G3-I | Vertical-datum row updated to B8 verified wording | ✅ PASS | §2.1 elevation-datum row (B8 audit 2026-11-14) |

**G3 status: CLOSED.** The DE2-supplied PLACES provenance is fully merged into the unified register; the DE2-side working-tree diff of `docs/sources.md` can now be **discarded by DE2** (their local action — the remote branch `de2-implementation-ali` @ `3a4e8aa` never contained it).

## 2. Central source → output map (single authoritative consolidation; supersedes scattered mentions)

| Source | Registered at | Consuming files / outputs | Status |
|---|---|---|---|
| USGS M20 Jezero CTX DEM 20 m (raw) | `docs/sources.md` §1.1 | `pipeline/crop_dem.py` → `data/processed/dem_20m_crop.tif` → everything terrain | USED; USGS public domain; no DOI observed (honest record) |
| Cropped DEM `dem_20m_crop.tif` (SHA `b7467953…`) | §1.1 + `grid_meta.json` provenance | `web/data/grid_meta.json`, `elev_dm_i16.bin`, `slope_u8.bin` (via DS), `hillshade.png`, `ctx_basemap.jpg` frame | USED |
| USGS TRN CTX orthomosaic 6 m (DOI 10.5066/P9GV1ND3) | §1.2 | `web/data/ctx_basemap.jpg` | USED |
| USGS SIM 3464 (DOI 10.3133/sim3464) | §1.3 | `web/data/geologic_map.png`, `geologic_map_legend.json` | USED (P2; ~100–200 m offset documented) |
| NASA Mars Trek WMTS | §1.4 | verification/fallback only | USED (metadata access only) |
| NASA PDS PLACES (DOI 10.17189/btz6-5a82) | §2.1 | DE2: `rover_track.geojson`, `presets.json`, `science_targets.geojson`; DS: `validate_rover.py`, `projected_points.json`; FS: consumes all three | USED |
| Libraries (rasterio 1.4.4 BSD; fiona 1.10.1 BSD-3; numpy 2.4.6 BSD-3/0BSD/MIT/Zlib/CC0-1.0; Pillow 13.0.0 MIT-CMU) | §1.5; B12 audit (installed-version licenses verified) | all pipeline/analysis code | USED |
| HiRISE 1 m DTM, MEDA, raw images, HiRISE 25 cm | §3 | none | CONSIDERED, NOT USED |

## 3. Provenance status per dataset (all verified this session or by recorded checks)
- **DE1 deliverables** (`grid_meta.json`, `elev_dm_i16.bin`, `ctx_basemap.jpg`, `hillshade.png`, geologic overlay): validated by per-task reports + Task 10 final report; blob identities re-verified in B1.
- **DE2 deliverables** (`rover_track.geojson`, `presets.json`, `science_targets.geojson`, `thermal.json`): hash-verified (B1: blob-identical across FS), SIS distances re-verified arithmetically (B3 audit: 41,202.9 m total; preset rows/sols exact).
- **DS deliverables** (`slope_u8.bin`, `validation_results.json`, `astar.js`, `metrics.js`): regression identity `5d7d0396…`; B6 hard-fail policy; B9 optimality proofs.
- **Elevation semantics** (vertical datum): B8 closed (PLACES proven areoid-referenced; DEM MOLA-localized; compatibility −0.576 m; `docs/sources.md` updated).

## 4. Duplication removal (documentation only)
No data removed. Redundant scattered mentions are now superseded by this single map; `docs/sources.md` remains the register of record (its per-source rows are the primary evidence; this file is the cross-track index). No contradictory statements exist between the register and this map (checked: vertical-datum row, license rows, hash rows all consistent as of `a535d0f`).
