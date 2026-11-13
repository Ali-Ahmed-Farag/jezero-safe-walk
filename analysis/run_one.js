const fs = require('fs');
const { findRoute } = require('../web/data/astar.js');

// parse args
const [id, profName, mode] = process.argv.slice(2);

const slope = new Uint8Array(fs.readFileSync('./web/data/slope_u8.bin'));
const presets = JSON.parse(fs.readFileSync('./analysis/presets_fixed.json'));
const profiles = { 
    Conservative: {safe:6, hard:10, forbidden:10}, 
    Standard: {safe:10, hard:16, forbidden:16}, 
    Extended: {safe:14, hard:20, forbidden:20} 
};

const p = presets.find(x => x.id === id);
if (!p) { console.error("Preset not found"); process.exit(1); }

// lat/lon to row/col (same as run_matrix_and_fix.py)
const sr = Math.round((18.669315 - p.start[0]) / (18.669315 - 18.3067994) * 1074);
const sc = Math.round((p.start[1] - 77.2229331) / (77.583964 - 77.2229331) * 1015);
const er = Math.round((18.669315 - p.end[0]) / (18.669315 - 18.3067994) * 1074);
const ec = Math.round((p.end[1] - 77.2229331) / (77.583964 - 77.2229331) * 1015);

const t0 = performance.now();
const res = findRoute({ slope, width:1016, height:1075, pixelM:20, start:[sr,sc], end:[er,ec], profile:profiles[profName], mode, slopeScale:4 });
const ms = performance.now() - t0;

let dist = 0, max_s = 0;
if (res.found && res.path.length > 0) {
    max_s = slope[res.path[0][0]*1016 + res.path[0][1]]/4.0;
    for (let i=1; i<res.path.length; i++) {
        dist += Math.hypot((res.path[i][1]-res.path[i-1][1])*20, (res.path[i][0]-res.path[i-1][0])*20);
        let s = slope[res.path[i][0]*1016 + res.path[i][1]]/4.0;
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