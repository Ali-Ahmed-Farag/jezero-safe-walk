# B12 — Task 07 Ruling & Licensing / DOI Audit

- **Date:** 2026-11-14
- **Owner:** DE1 track (`data` branch)
- **Scope:** (1) rule whether "Task 07" is a separate deliverable or an artifact of execution numbering; (2) audit licenses, terms of use, DOIs and attribution requirements for every data source and library actually used; (3) separate used vs considered-not-used sources; (4) identify redistribution constraints.
- **Method:** evidence from `docs/PLAN.md`, `docs/sources.md`, the DE1 commit history on `origin/data`, official USGS pages fetched live (2026-11-14), and the license metadata of the exact installed library versions (`.venv` dist-info). **No license or DOI is invented; every unresolved item is marked UNVERIFIED.**

---

## 1. Task 07 ruling: **Task 07 does not exist as a separate deliverable**

### Evidence
1. **`docs/PLAN.md` contains no "Task 07".** The DE1 plan section (PLAN L332–358) is a Friday schedule with **named deliverables**, not numbered tasks 01–10. The inter-track delivery table (PLAN L320–331) numbers delivery **slots** 1–9 by deadline; slot 7 is `astar.js` (DS-owned, delivered in Task-06-era work by DS and B9-verified).
2. **DE1's numbered execution commits on `origin/data` skip 07:**
   ```
   ce5f31d Task 01  (env setup)
   e54fb87 Task 02  (DEM acquisition/inspection)
   ba73a93 Task 03  (crop + grid alignment)
   7cec0be Task 04  (grid metadata)
   a3da13e Task 05  (elevation binary)
   8837cae Task 06  (CTX basemap)
   c2bb681 Task 06  (hillshade)            <- second Task-06 commit
   6d9bb31          (fiona pin)
   ecda85c Task 08  (geologic overlay)
   d7f07f0 Task 09  (provenance register)
   68a1583 Task 10  (final validation report)
   ```
3. **`data/processed/hillshade_report.md` header:** "# Hillshade Report - `web/data/hillshade.png` (**Task 06, delivery slot 4**)" — the hillshade is explicitly a Task 06 deliverable.

### Ruling
"Task 07" was never defined by the PLAN; the numbering gap in DE1's execution history is a **bookkeeping artifact** (two Task 06 commits covering PLAN delivery slot 4: CTX basemap + hillshade, PLAN L325/L351/L210). **No deliverable is missing.** The historical hypothesis ("standalone hillshade delivered under Task 06") is **confirmed**: the hillshade is Task 06 work, and there is nothing owed under a "Task 07".

---

## 2. Licensing / DOI audit — sources actually USED

| # | Source (used) | Where used | License / terms (evidence, date) | DOI | Attribution requirement | Redistribution of derived outputs |
|---|---|---|---|---|---|---|
| 1 | USGS M20 Jezero CTX DEM 20 m (raw + crop) | All terrain products (grid, elevation binary, slope, hillshade) | **USGS: public domain** — verified on the official product page ("Use Constraints: public domain", "Access Constraints: please cite authors", fetched 2026-11-14: https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic); recorded in `docs/sources.md` §4 | **No DOI observed** on the product's Astropedia page (verified 2026-11-14) — recorded honestly, do not invent one | Cite USGS Astrogeology authors as recorded in `docs/sources.md` §1.1 | **Permitted** (public domain), with citation |
| 2 | USGS Mars 2020 TRN CTX orthomosaic 6 m (CTX basemap layer) | `web/data/ctx_basemap.jpg` | USGS public domain; product DOI **10.5066/P9GV1ND3** (`docs/sources.md` L12) | 10.5066/P9GV1ND3 ✓ | Cite authors | Permitted w/ citation |
| 3 | USGS SIM 3464 geologic map (P2 overlay) | `web/data/geologic_map.png` + legend | USGS public domain; map DOI **10.3133/sim3464** (`docs/sources.md` L13) | 10.3133/sim3464 ✓ | Cite Sun & Stack 2020 | Permitted w/ citation; known ~100–200 m positional caveat documented |
| 4 | NASA PDS PLACES bundle (best_interp.csv) | rover track, presets, distances | **NASA PDS: public access**; usage/license terms **to be verified before submission — UNVERIFIED** (deliberately NOT claimed public domain; `docs/sources.md` §2.1 L33, §4 L77) | **10.17189/btz6-5a82** ✓ (`docs/sources.md` L28) | NASA PDS attribution; cite release/version (Release 16 recorded) | **Derived outputs permitted for this project's use**; redistribution of the source CSV itself → pending terms (UNVERIFIED) |
| 5 | NASA Mars Trek WMTS (verification/fallback only, no tiles downloaded) | `docs/sources.md` L14 | NASA content — "Courtesy NASA/JPL-Caltech" credit (JPL image use policy, verified 2026-11-13) | n/a | Credit line | n/a (nothing redistributed) |
| 6 | Libraries (exact installed versions, license read from `.venv` dist-info METADATA, 2026-11-14) | pipeline + analysis | rasterio **1.4.4 → BSD**; fiona **1.10.1 → BSD 3-Clause**; numpy **2.4.6 → BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0**; Pillow **13.0.0 → MIT-CMU** — all **permissive** | n/a | Retain copyright/license notices in the venv; no attribution required in outputs | **Permitted** — no restriction on derived outputs |

## 3. Sources considered but NOT used (no obligations)

`docs/sources.md` §3: HiRISE 1 m DTM (`JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m…`), best_interp.csv for DE1-direct use (superseded by the DE2-supplied provenance path), MEDA thermal, raw Perseverance images, HiRISE 25 cm orthomosaic. **None are included in any deliverable → no license/DOI/redistribution obligation** (sizes/licenses recorded as unverified in the register, correctly scoped as not-used).

## 4. Redistribution constraints summary
- **USGS-derived deliverables** (DEM products, CTX basemap, hillshade, geologic overlay): **free to redistribute** (public domain) with author citation.
- **NASA/JPL imagery**: credit line required where used.
- **PDS-derived deliverables** (rover track, presets, science targets): project may publish its **derived** products; the **source CSV** itself should not be redistributed until PDS usage terms are confirmed (**UNVERIFIED — the only open licensing item**).
- **No restricted-licence third-party data** is embedded in any deliverable.

## 5. Open items
| Item | Status | To close |
|---|---|---|
| NASA PDS usage/redistribution terms | **UNVERIFIED** | Read/quote the PDS data-use policy for `urn:nasa:pds:mars2020_rover_places` (or contact PDS) before final submission |
| DOI for the DEM mosaic itself | Not observed on official page (not invented) | Optional: ask USGS or cite the page + retrieval date (already recorded) |
| Fergason et al. 2020 LPSC abstract text (B8 DEP-1 residual) | UNVERIFIED (PDF) | Same item as B8 DEP-1 — not a licensing item |
