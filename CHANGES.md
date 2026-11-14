# CHANGES.md — Full Stack Modifications

This file documents all modifications made by the Full Stack team to the files provided by the Data Scientist (DS) or Data Engineers (DE), as required by the project rules.

## 1. `web/data/astar.js`
**Modification:** Changed the export mechanism at the end of the file.
**Reason:** The original file was written for Node.js using `module.exports`. The frontend uses ES Modules (`import`/`export`). To use the A* algorithm in the browser without changing its internal logic, the last line was changed from `if (typeof module !== 'undefined') module.exports = { findRoute };` to `export { findRoute };`.

## 2. `web/data/metrics.js`
**Modification:** Changed the export mechanism and handled `NoData` (-32768) values.
**Reason:** 
1. Changed `module.exports` to `export { pathMetrics };` to work in the browser.
2. Added a check `elev[idx] !== -32768` when reading elevation. The original code would divide `-32768` by 10, resulting in `-3276.8m`, which would ruin the ascent/descent calculations and profile chart. Now, it correctly treats `-32768` as a gap (`null`) in the chart and ignores it in ascent/descent calculations.

## 3. Temporary Files
The following files are currently temporary and awaiting final confirmation from DE2:
- `web/data/presets.json` (sourced from DS `presets_fixed.json`). The frontend calculates the approximate rover distance dynamically using Haversine on the `rover_track.geojson` because the final `rover_distance_km` field is not yet available.
- `web/data/thermal.json` (sourced from NASA M20 First Weather Report). It contains only two cited points (Day/Night) as per instructions to avoid inventing curves.