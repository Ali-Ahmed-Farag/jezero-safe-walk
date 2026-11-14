const fs = require('fs');
const { findRoute } = require('../web/data/astar.js');
const { pathMetrics } = require('../web/data/metrics.js');
const { loadMeta, latLonToRowCol, pixelM } = require('./grid_contract.js');
// B3: canonical presets (web/data/presets.json) + canonical grid contract — no fixtures.
// Tests ALL canonical scenarios; rover_distance_km is echoed unchanged for verification.
const slope = new Uint8Array(fs.readFileSync('./web/data/slope_u8.bin'));
const elev = new Int16Array(fs.readFileSync('./web/data/elev_dm_i16.bin').buffer);
const presets = JSON.parse(fs.readFileSync('./web/data/presets.json', 'utf8'));
const profiles = { Standard: {safe:10, hard:16, forbidden:16} };

const meta = loadMeta();
const results = [];

for (let p of presets) {
    const s = latLonToRowCol(p.start[0], p.start[1]);
    const e = latLonToRowCol(p.end[0], p.end[1]);

    const res = findRoute({ slope, width: meta.width, height: meta.height, pixelM: pixelM(), start: [s.row, s.col], end: [e.row, e.col], profile: profiles.Standard, mode: 'safest', slopeScale: 4 });
    if (res.found) {
        const metrics = pathMetrics({ path: res.path, slope, elev, width: meta.width, pixelM: pixelM(), profile: profiles.Standard, speedKmh: 2 });
        results.push({ id: p.id, rover_distance_km: p.rover_distance_km, ...metrics });
    } else {
        results.push({ id: p.id, rover_distance_km: p.rover_distance_km, found: false, reason: res.reason || '' });
    }
}
console.log(JSON.stringify(results, null, 2));
