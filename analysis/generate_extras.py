import os
import json
import subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm


def main():
    os.makedirs(os.path.join("analysis", "charts"), exist_ok=True)
    os.makedirs(os.path.join("web", "data"), exist_ok=True)

    # 1. Generate web/data/slope_meta.json
    slope_meta = {
        "file": "slope_u8.bin",
        "dtype": "uint8",
        "width": 1016,
        "height": 1075,
        "pixel_size_m": {"x": 20.0, "y": 20.0},
        "slope_scale": 4,
        "unit": "degrees",
        "max_valid_deg": 63.5,
        "nodata_or_border_u8": 255,
        "nodata_or_border_deg": 63.75,
        "method": "Horn 3x3 finite-difference gradient",
        "row0": "north"
    }
    with open(os.path.join("web", "data", "slope_meta.json"), "w", encoding="utf-8") as f:
        json.dump(slope_meta, f, indent=2)

    # 2. Generate web/data/cost_default.json (Suit profiles, colors, and risk indicator rules)
    cost_default = {
        "default_profile": "Standard",
        "default_mode": "safest",
        "default_walking_speed_kmh": 2.0,
        "cost_formula": {
            "safest": "d * (1 + (s_avg / safe_deg)^2)",
            "shortest": "d",
            "rejection_rule": "s_cell > forbidden_deg or s_avg > forbidden_deg"
        },
        "profiles": {
            "Conservative": {
                "safe_deg": 6.0,
                "hard_deg": 10.0,
                "forbidden_deg": 10.0,
                "description": "High safety margin for cautious EVA traversal"
            },
            "Standard": {
                "safe_deg": 10.0,
                "hard_deg": 16.0,
                "forbidden_deg": 16.0,
                "description": "Anchored to Perseverance traverse (>99% below 16 deg)"
            },
            "Extended": {
                "safe_deg": 14.0,
                "hard_deg": 20.0,
                "forbidden_deg": 20.0,
                "description": "Extended capability up to 20 deg steep terrain"
            }
        },
        "terrain_classes_ui": [
            {"id": "safe", "label": "Safe", "color": "#22c55e", "meaning": "Low slope, nominal energy cost"},
            {"id": "difficult", "label": "Difficult", "color": "#eab308", "meaning": "Moderate slope, elevated energy & slip risk"},
            {"id": "forbidden", "label": "Forbidden", "color": "#ef4444", "meaning": "Steep/NoData hazard, blocked from routing"}
        ],
        "risk_indicator_rules": {
            "Low": ">= 90% of route length in Safe class AND max_slope <= 14 deg",
            "Moderate": "Not Low, with 0% of route in Forbidden class",
            "High": "> 30% of route length in Difficult class OR max_slope > hard_deg",
            "disclaimer": "Estimated preliminary route metrics; not certified for real-time navigation."
        }
    }
    with open(os.path.join("web", "data", "cost_default.json"), "w", encoding="utf-8") as f:
        json.dump(cost_default, f, indent=2)

    # 3. Generate web/data/route_bank.json (Fallback precomputed routes across profiles & modes)
    js_script = """
    const fs = require('fs');
    const { findRoute } = require('./web/data/astar.js');
    const buf = fs.readFileSync('./web/data/slope_u8.bin');
    const slope = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
    const width = 1016, height = 1075, pixelM = 20.0, slopeScale = 4;

    let targets = [];
    if (fs.existsSync('./analysis/projected_points.json')) {
      const proj = JSON.parse(fs.readFileSync('./analysis/projected_points.json', 'utf8'));
      const pts = Array.isArray(proj) ? proj : (proj.targets || proj.points || []);
      targets = pts.filter(p => p.row !== undefined && p.col !== undefined).slice(0, 4);
    }
    if (targets.length < 2) {
      targets = [
        { name: 'Octavia E. Butler Landing', row: 625, col: 523 },
        { name: 'Neretva Vallis Delta Front', row: 573, col: 477 },
        { name: 'Seitah South Traverse', row: 660, col: 495 }
      ];
    }

    const profiles = {
      Conservative: { safe: 6, hard: 10, forbidden: 10 },
      Standard: { safe: 10, hard: 16, forbidden: 16 },
      Extended: { safe: 14, hard: 20, forbidden: 20 }
    };
    const modes = ['safest', 'shortest'];
    const routes = [];

    const start = targets[0];
    for (let i = 1; i < targets.length; i++) {
      const end = targets[i];
      for (const [pName, prof] of Object.entries(profiles)) {
        for (const mode of modes) {
          const t0 = performance.now();
          const res = findRoute({
            slope, width, height, pixelM,
            start: [start.row, start.col],
            end: [end.row, end.col],
            profile: prof, mode, slopeScale
          });
          const ms = +(performance.now() - t0).toFixed(2);
          let distM = 0, maxSlope = 0, sumSlope = 0;
          if (res.found && res.path.length > 0) {
            for (let k = 0; k < res.path.length; k++) {
              const [r, c] = res.path[k];
              const sDeg = slope[r * width + c] / slopeScale;
              sumSlope += sDeg;
              if (sDeg > maxSlope) maxSlope = sDeg;
              if (k > 0) {
                const [pr, pc] = res.path[k - 1];
                distM += Math.hypot((c - pc) * pixelM, (r - pr) * pixelM);
              }
            }
          }
          routes.push({
            id: `${start.name || 'Start'}_to_${end.name || 'Target_' + i}_${pName}_${mode}`.replace(/\\s+/g, '_'),
            from: start.name || 'Start',
            to: end.name || `Target ${i}`,
            profile: pName,
            mode,
            found: res.found,
            runtime_ms: ms,
            distance_km: +(distM / 1000).toFixed(3),
            mean_slope_deg: res.path.length ? +(sumSlope / res.path.length).toFixed(2) : null,
            max_slope_deg: res.path.length ? +maxSlope.toFixed(2) : null,
            waypoints_count: res.path.length,
            path: res.path
          });
        }
      }
    }
    fs.writeFileSync('./web/data/route_bank.json', JSON.stringify({ generated_by: 'astar.js', routes }, null, 2));
    console.log('Generated route_bank.json with ' + routes.length + ' routes');
    """
    subprocess.run(["node", "-e", js_script], check=True)

    # 4. Generate analysis/charts/slope_map.png (Classified Terrain Map)
    slope_u8 = np.fromfile(os.path.join("web", "data", "slope_u8.bin"), dtype=np.uint8).reshape((1075, 1016))
    slope_deg = slope_u8.astype(np.float32) / 4.0

    cmap = ListedColormap(["#22c55e", "#eab308", "#ef4444", "#1e293b"])
    bounds = [0.0, 10.0, 16.0, 63.6, 65.0]
    norm = BoundaryNorm(bounds, cmap.N)

    fig, ax = plt.subplots(figsize=(9, 9.5), dpi=300)
    im = ax.imshow(slope_deg, cmap=cmap, norm=norm, origin="upper")
    cbar = plt.colorbar(im, ax=ax, fraction=0.036, pad=0.03, ticks=[5, 13, 39.8, 64.3])
    cbar.ax.set_yticklabels([
        "Safe (< 10°)",
        "Difficult (10°–16°)",
        "Forbidden (> 16°)",
        "NoData / Border"
    ])
    ax.set_title("Jezero Crater Terrain Traversability (Standard Profile, 20 m DEM)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Grid Column (20 m/pixel)")
    ax.set_ylabel("Grid Row (20 m/pixel)")
    plt.tight_layout()
    plt.savefig(os.path.join("analysis", "charts", "slope_map.png"), dpi=300)
    plt.close(fig)

    # 5. Generate analysis/charts/validation_charts.png (Scatter + Slope Bins + Rover Replay)
    with open(os.path.join("web", "data", "validation_results.json"), "r", encoding="utf-8") as f:
        val = json.load(f)

    samples = val["samples"]
    p_dem = [s["pitch_dem"] for s in samples]
    p_rov = [s["pitch_rover"] for s in samples]
    r_dem = [s["roll_dem"] for s in samples]
    r_rov = [s["roll_rover"] for s in samples]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), dpi=300)

    # Panel A: Pitch
    axes[0].scatter(p_dem, p_rov, s=6, alpha=0.35, color="#2563eb")
    axes[0].plot([-20, 20], [-20, 20], "r--", linewidth=1.2, label="1:1 Ideal")
    pm = val["metrics"]["pitch"]
    axes[0].set_title(f"Directional Pitch (r = {pm['correlation_r']}, RMSE = {pm['rmse_deg']}°)", fontsize=10, fontweight="bold")
    axes[0].set_xlabel("DEM Projected Pitch (deg)")
    axes[0].set_ylabel("Perseverance Telemetry Pitch (deg)")
    axes[0].set_xlim(-20, 20)
    axes[0].set_ylim(-20, 20)
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()

    # Panel B: Roll
    axes[1].scatter(r_dem, r_rov, s=6, alpha=0.35, color="#059669")
    axes[1].plot([-20, 20], [-20, 20], "r--", linewidth=1.2, label="1:1 Ideal")
    rm = val["metrics"]["roll"]
    axes[1].set_title(f"Directional Roll (r = {rm['correlation_r']}, RMSE = {rm['rmse_deg']}°)", fontsize=10, fontweight="bold")
    axes[1].set_xlabel("DEM Projected Roll (deg)")
    axes[1].set_ylabel("Perseverance Telemetry Roll (deg)")
    axes[1].set_xlim(-20, 20)
    axes[1].set_ylim(-20, 20)
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()

    # Panel C: Slope Bins comparison
    bins = val["slope_bins"]
    labels = [b["bin"].replace(" deg", "°") for b in bins]
    dem_means = [b["mean_dem_slope_deg"] for b in bins]
    rov_means = [b["mean_rover_tilt_deg"] for b in bins]
    x = np.arange(len(labels))
    w = 0.36
    axes[2].bar(x - w / 2, dem_means, width=w, label="Mean DEM Slope", color="#64748b")
    axes[2].bar(x + w / 2, rov_means, width=w, label="Mean Rover Tilt", color="#f59e0b")
    axes[2].set_title("DEM Slope vs. Actual Rover Tilt by Bin", fontsize=10, fontweight="bold")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(labels)
    axes[2].set_ylabel("Tilt / Slope (deg)")
    axes[2].grid(True, axis="y", alpha=0.25)
    axes[2].legend()

    plt.tight_layout()
    plt.savefig(os.path.join("analysis", "charts", "validation_charts.png"), dpi=300)
    plt.close(fig)
    print("All extra deliverables generated successfully!")


if __name__ == "__main__":
    main()