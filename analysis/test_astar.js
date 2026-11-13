const fs = require("fs");
const path = require("path");
const { performance } = require("perf_hooks");
const { findRoute } = require("../web/data/astar.js");

const slopePath = path.join("web", "data", "slope_u8.bin");
const projectedPath = path.join("analysis", "projected_points.json");
const outPath = path.join("analysis", "astar_test_results.json");

const slopeBuf = fs.readFileSync(slopePath);
const slope = new Uint8Array(slopeBuf.buffer, slopeBuf.byteOffset, slopeBuf.byteLength);

const projected = JSON.parse(fs.readFileSync(projectedPath, "utf-8"));
const width = projected.grid_width;
const height = projected.grid_height;
const pixelM = projected.pixel_size_m;
const slopeScale = 4;

const landing = projected.targets[0];
const destinations = projected.targets.slice(1);

function evaluatePath(routePath) {
  if (!routePath || routePath.length === 0) return null;
  let distM = 0;
  let maxSlope = 0;
  let sumSlope = 0;
  let over10Count = 0;

  for (let i = 0; i < routePath.length; i++) {
    const [r, c] = routePath[i];
    const deg = slope[r * width + c] / slopeScale;
    if (deg > maxSlope) maxSlope = deg;
    sumSlope += deg;
    if (deg > 10.0) over10Count++;

    if (i > 0) {
      const [pr, pc] = routePath[i - 1];
      distM += Math.hypot((c - pc) * pixelM, (r - pr) * pixelM);
    }
  }

  return {
    waypoints: routePath.length,
    distance_m: Number(distM.toFixed(2)),
    max_slope_deg: Number(maxSlope.toFixed(2)),
    mean_slope_deg: Number((sumSlope / routePath.length).toFixed(2)),
    pct_steps_over_10deg: Number(((over10Count / routePath.length) * 100).toFixed(2)),
  };
}

const scenarios = [
  { label: "Astronaut EVA (safest)", profile: { safe: 10, hard: 15, forbidden: 15 }, mode: "safest" },
  { label: "Astronaut EVA (shortest)", profile: { safe: 10, hard: 15, forbidden: 15 }, mode: "shortest" },
  { label: "Rover Max Slope (safest)", profile: { safe: 15, hard: 25, forbidden: 25 }, mode: "safest" },
];

const results = [];

for (const dest of destinations) {
  for (const sc of scenarios) {
    const t0 = performance.now();
    const res = findRoute({
      slope,
      width,
      height,
      pixelM,
      start: [landing.row, landing.col],
      end: [dest.row, dest.col],
      profile: sc.profile,
      mode: sc.mode,
      slopeScale,
    });
    const elapsedMs = Number((performance.now() - t0).toFixed(2));
    const metrics = evaluatePath(res.path);

    results.push({
      from: landing.name,
      to: dest.name,
      scenario: sc.label,
      found: res.found,
      runtime_ms: elapsedMs,
      under_1s_target: elapsedMs < 1000,
      metrics,
      path: res.path,
    });
  }
}

fs.writeFileSync(outPath, JSON.stringify({ width, height, pixelM, runs: results }, null, 2));

console.table(
  results.map((r) => ({
    Destination: r.to,
    Scenario: r.scenario,
    Found: r.found,
    "Time (ms)": r.runtime_ms,
    "Dist (m)": r.metrics?.distance_m,
    "Max Slope (°)": r.metrics?.max_slope_deg,
    "Mean Slope (°)": r.metrics?.mean_slope_deg,
    ">10° Steps (%)": r.metrics?.pct_steps_over_10deg,
  }))
);