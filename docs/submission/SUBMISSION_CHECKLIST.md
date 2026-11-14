# Submission Checklist (PLAN §18, live status 2026-11-14)

Legend: ✅ done · 🟡 pending (owner named) · ⬜ not yet started

## Before Feature Freeze (Sat 8:00 AM)
- [x] End-to-end route flow works (pick two points → shortest+safest → Mission Brief) — verified on committed code (B1/B9); **live-site recheck 🟡 FS owner**
- [x] ≥3 layers with toggle + opacity (CTX, hillshade, slope canvas, geologic P2, rover, targets) — code verified
- [x] Validation panel with real numbers and charts (`validation_results.json`: 32,003 points, r=0.8858/0.8612, replay) — done
- [x] Sources modal + limitations modal present — code verified; **final wording recheck 🟡**
- [x] Science targets named on map with short description + source (3 canonical targets, provenance popups) — done
- [ ] **Site published on a public link, working on mobile** — 🟡 FS owner `[PLACEHOLDER: live URL]`
- [x] `sources.md` covers every source + library + license — done (Task 09 + B12/B14)

## Before submission (Sat 11:30 AM)
- [ ] **7 slides as PDF on a public link** — 🟡 content done (`DEMO_DECK_7_SLIDES.md`); needs screenshots + PDF + upload `[PLACEHOLDER: demo link]`
- [ ] Video (optional) — ⬜ optional per PLAN
- [ ] **Proposal (PDF) on a public link** — ⬜ DE1 draft exists in PLAN §8.4 structure; export+upload pending 🟡 `[PLACEHOLDER: proposal link]`
- [ ] **Site + repo public, README + LICENSE present** — repo has README/LICENSE on all branches ✅; public access 🟡
- [ ] **Every link tested logged-out on a second device/network** — ⬜ after links exist
- [x] Complete source/data list with licenses documented — done (B12/B14/G3)
- [x] Usage terms per source recorded in `sources.md` (USGS / Mars Trek / PDS / P2) — done; PDS terms flagged UNVERIFIED by policy
- [x] AI-use disclosure written — done (per-track statements; `SOURCES_AND_AI_DISCLOSURE.md` §5)
- [x] Assumptions & limitations written clearly — done (slide 7 + validation reports)
- [x] No personal data / commercial promotion — verified (no names in materials; names only on Team Page)
- [ ] **Every form field reviewed by two people** — ⬜ team action
- [ ] Upload before deadline (target 12:00 PM) — ⬜

## Form fields (PLAN §7.4 table)
| Field | Content | Status |
|---|---|---|
| Demo Link | public 7-slide PDF (or 30 s video) | 🟡 pending PDF export/upload |
| Proposal Link | public PDF | 🟡 pending |
| **Official Team Page URL** | `[PLACEHOLDER: Official Team Page URL]` | 🟡 DE2 (all members registered & visible on the page) |
| **Subjects** | proposed (PLAN §8.5): Mars, Jezero Crater, Perseverance, Digital Elevation Model, Terrain Analysis, Path Planning, Remote Sensing, Human Space Exploration, Data Visualization — **re-check against official form guide before entry** | 🟡 |
| Team name / members | on Official Team Page only | 🟡 |

## Data-ready guarantees backing the submission
- All four tracks publish canonical, hash-verified deliverables (see `docs/FINAL_INTEGRATION_READINESS.md`).
- Every number in the deck is traceable to a committed validation artifact (no invented figures).
