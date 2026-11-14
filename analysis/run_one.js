const fs = require('fs');
const { findRoute } = require('../web/data/astar.js');
const { loadMeta, latLonToRowCol, pixelM } = require('./grid_contract.js');

// B3: canonical sources only — DE2 web/data/presets.json + DE1 web/data/grid_meta.json.
// No hardcoded bounds, no (W-1)/(H-1) scaling, no fixture files, no coordinate edits.
const [id, profName, mode] = process.argv.slice(2);

const meta = loadMeta();
const width = meta.width, height = meta.height, pixelMeters = pixelM();

const slope = new Uint8Array(fs.readFileSync('./web/data/slope_u8.bin'));
const presets = JSON.parse(fs.readFileSync('./web/data/presets.json', 'utf8'));
const profiles = {
    Conservative: {safe:6, hard:10, forbidden:10},
    Standard: {safe:10, hard:16, forbidden:16},
    Extended: {safe:14, hard:20, forbidden:20}
};

const p = presets.find(x => x.id === id);
if (!p) { console.error("Preset not found"); process.exit(1); }

// Canonical projection (grid_meta contract): floor-based, range-checked.
const start = latLonToRowCol(p.start[0], p.start[1]);
const end = latLonToRowCol(p.end[0], p.end[1]);

const t0 = performance.now();
const res = findRoute({ slope, width, height, pixelM: pixelMeters, start: [start.row, start.col], end: [end.row, end.col], profile: profiles[profName], mode, slopeScale: 4 });
const ms = performance.now() - t0;

let dist = 0, max_s = 0;
if (res.found && res.path.length > 0) {
    max_s = slope[res.path[0][0]*width + res.path[0][1]]/4.0;
    for (let i=1; i<res.path.length; i++) {
        dist += Math.hypot((res.path[i][1]-res.path[i-1][1])*pixelMeters, (res.path[i][0]-res.path[i-1][0])*pixelMeters);
        let s = slope[res.path[i][0]*width + res.path[i][1]]/4.0;
        if (s > max_s) max_s = s;
    }
}

console.log(JSON.stringify({
    scenario: p.id,
    profile: profName,
    mode: mode,
    found: res.found,
    reason: res.reason || '',
    length_km: (dist/1000).toFixed(2),
    time_ms: ms.toFixed(2),
    max_slope: max_s.toFixed(2)
}));
