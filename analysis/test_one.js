const fs = require('fs');
const { findRoute } = require('../web/data/astar.js');
const { loadMeta, latLonToRowCol, pixelM } = require('./grid_contract.js');
// B3: canonical presets (web/data/presets.json) + canonical grid contract — no fixtures.
const slope = new Uint8Array(fs.readFileSync('./web/data/slope_u8.bin'));
const presets = JSON.parse(fs.readFileSync('./web/data/presets.json', 'utf8'));
const [id, profName, mode] = process.argv.slice(2);
const meta = loadMeta();
const profiles = { Conservative:{safe:6,hard:10,forbidden:10}, Standard:{safe:10,hard:16,forbidden:16}, Extended:{safe:14,hard:20,forbidden:20} };
const p = presets.find(x => x.id === id);
if (!p) { console.error("Preset not found"); process.exit(1); }
const s = latLonToRowCol(p.start[0], p.start[1]);
const e = latLonToRowCol(p.end[0], p.end[1]);
console.log('start', [s.row, s.col], 'slope', slope[s.row*meta.width+s.col]/4, '| end', [e.row, e.col], 'slope', slope[e.row*meta.width+e.col]/4);
const t0 = performance.now();
const res = findRoute({ slope, width: meta.width, height: meta.height, pixelM: pixelM(), start: [s.row, s.col], end: [e.row, e.col], profile: profiles[profName], mode, slopeScale: 4 });
console.log('found', res.found, 'reason', res.reason || '', 'steps', res.path ? res.path.length : 0, 'ms', (performance.now()-t0).toFixed(1));
