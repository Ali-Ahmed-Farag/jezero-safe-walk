const fs = require('fs');
const { findRoute } = require('../web/data/astar.js');
const { pathMetrics } = require('../web/data/metrics.js');
const slope = new Uint8Array(fs.readFileSync('./web/data/slope_u8.bin'));
const elev = new Int16Array(fs.readFileSync('./web/data/elev_dm_i16.bin').buffer);
const presets = JSON.parse(fs.readFileSync('./analysis/presets_fixed.json'));
const profiles = { Standard: {safe:10, hard:16, forbidden:16} };

const test_ids = ['scenario_1', 'scenario_3', 'scenario_5'];
const results = [];

for (let id of test_ids) {
    const p = presets.find(x => x.id === id);
    const sr = Math.round((18.669315 - p.start[0]) / (18.669315 - 18.3067994) * 1074);
    const sc = Math.round((p.start[1] - 77.2229331) / (77.583964 - 77.2229331) * 1015);
    const er = Math.round((18.669315 - p.end[0]) / (18.669315 - 18.3067994) * 1074);
    const ec = Math.round((p.end[1] - 77.2229331) / (77.583964 - 77.2229331) * 1015);
    
    const res = findRoute({ slope, width:1016, height:1075, pixelM:20, start:[sr,sc], end:[er,ec], profile:profiles.Standard, mode:'safest', slopeScale:4 });
    if (res.found) {
        const metrics = pathMetrics({ path: res.path, slope, elev, width:1016, pixelM:20, profile:profiles.Standard, speedKmh:2 });
        results.push({ id, ...metrics });
    }
}
console.log(JSON.stringify(results, null, 2));