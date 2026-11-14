// analysis/grid_contract.js — B3: single shared reader for the canonical grid contract.
//
// Sources of truth (read from the DS tree directly, no fixture files, no hardcoded bounds):
//   - web/data/grid_meta.json  (DE1 contract, blob 2d908027..., bounds_are = "outer_corners")
//   - web/data/presets.json    (DE2 canonical scenarios, blob d737edd5...)
//
// Projection per grid_meta.notes: floor-based mapping over the half-open domain
// [lon_min, lon_max) x (lat_min, lat_max]; row 0 = north, col 0 = west;
// linear index = row * width + col. Every coordinate is range-checked.
const fs = require('fs');

let _meta = null;

function loadMeta() {
  if (_meta) return _meta;
  const meta = JSON.parse(fs.readFileSync('./web/data/grid_meta.json', 'utf8'));
  if (meta.bounds_are !== 'outer_corners') {
    throw new Error('grid_meta.json: bounds_are != "outer_corners" (non-canonical contract)');
  }
  const b = meta.bounds;
  meta._deg_per_px_x = (b.lon_max - b.lon_min) / meta.width;
  meta._deg_per_px_y = (b.lat_max - b.lat_min) / meta.height;
  _meta = meta;
  return _meta;
}

function latLonToRowCol(lat, lon) {
  const m = loadMeta();
  const col = Math.floor((lon - m.bounds.lon_min) / m._deg_per_px_x);
  const row = Math.floor((m.bounds.lat_max - lat) / m._deg_per_px_y);
  if (!Number.isInteger(row) || !Number.isInteger(col) ||
      row < 0 || row >= m.height || col < 0 || col >= m.width) {
    throw new Error(`lat/lon outside grid (half-open domain): (${lat}, ${lon}) -> row=${row}, col=${col}`);
  }
  return { row, col };
}

// Contract-designated scalar for astar.js (grid_meta.notes / PLAN 5.5).
function pixelM() {
  return loadMeta().pixel_m;
}

module.exports = { loadMeta, latLonToRowCol, pixelM };
