# Jezero Safe Walk — Demo Deck (7 slides, content draft v2)

**Structure per `docs/PLAN.md` §8.3. All numbers below are the validated project numbers** (sources: `web/data/validation_results.json` (n = 32,003), `analysis/scenario_matrix.csv` (24/24 combos found), `docs/G3_SOURCE_CONSOLIDATION.md`). Slides need screenshots + PDF export before submission.

---

## Slide 1 — The Problem (Impact)
The first astronauts on Mars will walk kilometres in a heavy suit. **Where do they go, and how do they stay safe?**
- Jezero Crater terrain is strewn with slopes, ridges and hazard fields: Perseverance's own route shows a maximum DEM slope of 14.4° along a 4 km drive and actively avoids terrain above 16°.
- Who benefits: mission planners (route pre-screening), astronauts (EVA planning), education (real NASA data, real algorithms).
- `[_SCREENSHOT_: map view of Jezero with slope overlay]`

## Slide 2 — Our Solution (Presentation)
**Jezero Safe Walk** — a web tool that plans safe walking routes on real NASA terrain data.
Three pillars: **safe route planning** (A* on a real DEM), **suit profiles** (Conservative / Standard / Extended slope thresholds), **scientific proof** (validated against Perseverance telemetry).
- `[_SCREENSHOT_: full UI with route + Mission Brief]`

## Slide 3 — The NASA data we used (Relevance)
| Dataset | Mission / source | Role in the tool |
|---|---|---|
| CTX DEM 20 m | MRO / USGS Astrogeology (public domain) | terrain grid, elevation, slope |
| CTX orthomosaic 6 m | MRO / USGS (DOI 10.5066/P9GV1ND3) | visual basemap layer |
| PLACES rover traverse | Mars 2020 / NASA PDS (DOI 10.17189/btz6-5a82) | rover track, science targets, route scenarios, validation ground truth |
| SIM 3464 geologic map (P2, optional layer) | USGS (DOI 10.3133/sim3464) | context layer (documented ~100–200 m offset) |
| Mars Trek WMTS | NASA | basemap verification |
Grid: **1016 × 1075 cells @ 20 m/pixel** — one shared contract across every layer.

## Slide 4 — How it works (Validity)
**DEM → slope → cost → A* → Mission Brief.**
- Slope from Horn 3×3 gradients (ground metres, not degrees-latitude); encoded slope_deg = byte/4, 255 = forbidden edge.
- Step cost: safest `d × (1 + (s/safe)²)`, shortest `d`; forbidden cells rejected; heuristic proven admissible & consistent (B9: A\* == Dijkstra cost exactly on all test grids).
- Suit profiles: Conservative <6°/<10°, Standard <10°/<16° (anchored: >99% of Perseverance's traverse below 16°), Extended <14°/<20°.
- Mission Brief: distance, time, max slope, ascent/descent, risk level, elevation profile.
- Route scenarios from the real rover traverse: Short/Medium/Advanced/Long = first track points at **1.002 / 3.001 / 5.001 / 8.003 km** of true SIS ground distance.

## Slide 5 — The Proof (Validity)
Validation against **all 32,003 Perseverance positioning records** (Sols 0–1815, NASA PDS):
- DEM-projected **pitch** vs rover telemetry: r = **0.8858**, RMSE **2.78°**
- **roll**: r = **0.8612**, RMSE **2.94°**
- elevation: mean bias **−0.58 m**, RMSE **3.11 m** (bias-corrected) — same MOLA-areoid reference
- **Rover replay** (Sols 537–719): our **safest** route 1,514.8 m vs the rover's 4,000.6 m of driving, mean slope 4.96° vs 4.85°, max 9.86° vs 14.40°, **73.8% of our route within 100 m** of the real traverse — while the shortest baseline takes max slopes of 16.1°.
- `[_SCREENSHOT_: validation scatter + slope-bin chart]`

## Slide 6 — What's different (Creativity)
- **Safest vs shortest comparison mode** — same start/target, two routes, side-by-side metrics.
- **Suit profiles** change what "safe" means — one click re-colours the terrain.
- **Thermal extrema cards** (NASA M20 First Weather Report: Day High −22 °C, Night Low −83 °C, Sols 43–44 — cited archival data, clearly labeled, no forecast claims).
- Rover replay benchmark built from real odometry.
- `[_SCREENSHOT_: route comparison modal + thermal cards]`

## Slide 7 — Limitations, impact, sources (Impact + compliance)
**Honest limitations:** 20 m/pixel DEM smooths sub-pixel rocks and wheel-scale (~3 m) roughness; rover replay distances use raw projected spacing (~0.37% effect); geologic map layer carries a documented ~100–200 m offset; replay segment is one 4 km window; thermal data are cited extrema, not measurements.
**Impact:** a reusable, source-honest pattern for planning human EVA on planetary terrain with open data.
**Next steps:** 1 m HiRISE DEM, other landing sites, radiation layer, integration with real mission tools.
**Sources & AI disclosure:** see `SOURCES_AND_AI_DISCLOSURE.md` (all sources cited; AI use disclosed per track).
**Links:** site `[PLACEHOLDER]` · repo `[PLACEHOLDER]` · proposal `[PLACEHOLDER]`.
