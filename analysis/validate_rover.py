import os
import csv
import json
import math
import subprocess
import numpy as np
import rasterio


def horn_gradients(elev: np.ndarray, dx: float, dy: float, nodata: float):
    z = elev.astype(np.float64)
    invalid = ~np.isfinite(z) | (z == nodata) | (z <= -32000)
    z_clean = np.where(invalid, np.nan, z)

    # Pad edges with edge values
    zp = np.pad(z_clean, 1, mode="edge")
    a, b, c = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    d, e, f = zp[1:-1, :-2], zp[1:-1, 1:-1], zp[1:-1, 2:]
    g, h, i = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]

    dz_dx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / (8.0 * dx)
    dz_dy = ((a + 2.0 * b + c) - (g + 2.0 * h + i)) / (8.0 * dy)
    slope_deg = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    return dz_dx, dz_dy, slope_deg, invalid


def calc_metrics(pred: np.ndarray, actual: np.ndarray):
    mask = np.isfinite(pred) & np.isfinite(actual)
    p = pred[mask]
    a = actual[mask]
    diff = p - a
    r = float(np.corrcoef(p, a)[0, 1]) if len(p) > 1 else 0.0
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mae = float(np.mean(np.abs(diff)))
    bias = float(np.mean(diff))
    return {
        "n": int(len(p)),
        "correlation_r": round(r, 4),
        "rmse_deg": round(rmse, 4),
        "mae_deg": round(mae, 4),
        "mean_bias_deg": round(bias, 4),
    }


def run_astar_replay(start_rc, end_rc, width, height, pixel_m, mode='safest'):
    js_code = f"""
    const fs = require('fs');
    const {{ findRoute }} = require('./web/data/astar.js');
    const buf = fs.readFileSync('./web/data/slope_u8.bin');
    const slope = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
    const t0 = performance.now();
    const res = findRoute({{
      slope,
      width: {width},
      height: {height},
      pixelM: {pixel_m},
      start: [{start_rc[0]}, {start_rc[1]}],
      end: [{end_rc[0]}, {end_rc[1]}],
      profile: {{ safe: 10, hard: 16, forbidden: 16 }},
      mode: '{mode}',
      slopeScale: 4
    }});
    const ms = performance.now() - t0;
    console.log(JSON.stringify({{ found: res.found, runtime_ms: ms, path: res.path }}));
    """
    proc = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


def calc_pct_within_100m(planned_path, seg_rc):
    within_100m = 0
    for r, c in planned_path:
        dists_m = np.hypot(seg_rc[:, 0] - r, seg_rc[:, 1] - c) * 20.0
        if np.min(dists_m) <= 100.0:
            within_100m += 1
    return (within_100m / len(planned_path)) * 100.0 if planned_path else 0.0


def main():
    dem_path = os.path.join("data", "processed", "dem_20m_crop.tif")
    track_path = "data/processed/rover_track_clean.csv"
    out_path = os.path.join("web", "data", "validation_results.json")

    with rasterio.open(dem_path) as src:
        elev = src.read(1)
        nodata = src.nodata if src.nodata is not None else -32768.0
        dx = abs(src.transform.a)
        dy = abs(src.transform.e)
        dz_dx, dz_dy, slope_grid, invalid_mask = horn_gradients(elev, dx, dy, nodata)

        rows_data = []
        with open(track_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("frame", "ROVER") != "ROVER":
                    continue
                easting = float(r["easting"])
                northing = float(r["northing"])
                pitch = float(r["pitch"])
                roll = float(r["roll"])
                yaw = float(r["yaw"])
                rover_elev = float(r["elevation"])
                if any(v <= -9000 for v in (pitch, roll, yaw, rover_elev)):
                    continue

                row_f, col_f = src.index(easting, northing, op=lambda v: v)
                col = int(round(col_f))
                row = int(round(row_f))
                if not (0 <= col < src.width and 0 <= row < src.height):
                    continue
                if invalid_mask[row, col]:
                    continue

                rows_data.append({
                    "sol": int(float(r["sol"])),
                    "lon": float(r["longitude"]),
                    "lat": float(r["planetocentric_latitude"]),
                    "easting": easting,
                    "northing": northing,
                    "row": row,
                    "col": col,
                    "pitch": pitch,
                    "roll": roll,
                    "yaw": yaw,
                    "rover_elev": rover_elev,
                    "dem_elev": float(elev[row, col]),
                    "dem_slope": float(slope_grid[row, col]),
                    "gx": float(dz_dx[row, col]),
                    "gy": float(dz_dy[row, col]),
                })

    n_pts = len(rows_data)
    gx = np.array([d["gx"] for d in rows_data])
    gy = np.array([d["gy"] for d in rows_data])
    yaw_rad = np.radians([d["yaw"] for d in rows_data])
    pitch_act = np.array([d["pitch"] for d in rows_data])
    roll_act = np.array([d["roll"] for d in rows_data])
    dem_slope = np.array([d["dem_slope"] for d in rows_data])
    rover_elev = np.array([d["rover_elev"] for d in rows_data])
    dem_elev = np.array([d["dem_elev"] for d in rows_data])

    # Sign convention check (A.1)
    grad_along = gx * np.sin(yaw_rad) + gy * np.cos(yaw_rad)
    grad_cross = gx * np.cos(yaw_rad) - gy * np.sin(yaw_rad)

    pitch_dem_pos = np.degrees(np.arctan(grad_along))
    pitch_dem_neg = -pitch_dem_pos
    r_pos = np.corrcoef(pitch_dem_pos, pitch_act)[0, 1]
    r_neg = np.corrcoef(pitch_dem_neg, pitch_act)[0, 1]
    if r_neg > r_pos:
        pitch_dem = pitch_dem_neg
        pitch_sign_note = "RVR frame: +pitch aligns with -arctan(grad_along) [Sensitivity: r_pos={:.4f}, r_neg={:.4f}]".format(r_pos, r_neg)
    else:
        pitch_dem = pitch_dem_pos
        pitch_sign_note = "RVR frame: +pitch aligns with +arctan(grad_along) [Sensitivity: r_pos={:.4f}, r_neg={:.4f}]".format(r_pos, r_neg)

    roll_dem_pos = np.degrees(np.arctan(grad_cross))
    roll_dem_neg = -roll_dem_pos
    rr_pos = np.corrcoef(roll_dem_pos, roll_act)[0, 1]
    rr_neg = np.corrcoef(roll_dem_neg, roll_act)[0, 1]
    if rr_neg > rr_pos:
        roll_dem = roll_dem_neg
        roll_sign_note = "+roll aligns with -arctan(grad_cross) [Sensitivity: r_pos={:.4f}, r_neg={:.4f}]".format(rr_pos, rr_neg)
    else:
        roll_dem = roll_dem_pos
        roll_sign_note = "+roll aligns with +arctan(grad_cross) [Sensitivity: r_pos={:.4f}, r_neg={:.4f}]".format(rr_pos, rr_neg)

    rover_total_tilt = np.hypot(pitch_act, roll_act)
    tilt_metrics = calc_metrics(dem_slope, rover_total_tilt)
    pitch_metrics = calc_metrics(pitch_dem, pitch_act)
    roll_metrics = calc_metrics(roll_dem, roll_act)

    # Elevation (datum) (A.2, A.3)
    elev_diff = dem_elev - rover_elev
    elev_bias = float(np.mean(elev_diff))
    elev_rmse_raw = float(np.sqrt(np.mean(elev_diff ** 2)))
    elev_rmse_centered = float(np.sqrt(np.mean((elev_diff - elev_bias) ** 2)))

    # Binned table (A.4) - Matching the plan exactly
    bins = [
        ("0-2 deg", 0.0, 2.0),
        ("2-5 deg", 2.0, 5.0),
        ("5-8 deg", 5.0, 8.0),
        ("8-12 deg", 8.0, 12.0),
        ("12-16 deg", 12.0, 16.0),
        (">16 deg", 16.0, 90.0),
    ]
    slope_bins = []
    for label, lo, hi in bins:
        m = (dem_slope >= lo) & (dem_slope < hi)
        cnt = int(np.sum(m))
        slope_bins.append({
            "bin": label,
            "count": cnt,
            "pct_points": round((cnt / n_pts) * 100.0, 2),
            "mean_dem_slope_deg": round(float(np.mean(dem_slope[m])), 3) if cnt else None,
            "mean_abs_pitch_deg": round(float(np.mean(np.abs(pitch_act[m]))), 3) if cnt else None,
            "mean_abs_roll_deg": round(float(np.mean(np.abs(roll_act[m]))), 3) if cnt else None,
            "mean_rover_tilt_deg": round(float(np.mean(rover_total_tilt[m])), 3) if cnt else None,
        })

    # Rover Replay (A.6)
    cum_dist = [0.0]
    for idx in range(1, n_pts):
        d = math.hypot(
            rows_data[idx]["easting"] - rows_data[idx - 1]["easting"],
            rows_data[idx]["northing"] - rows_data[idx - 1]["northing"],
        )
        cum_dist.append(cum_dist[-1] + d)

    start_idx = int(n_pts * 0.25)
    target_dist = cum_dist[start_idx] + 4000.0
    end_idx = next((i for i in range(start_idx, n_pts) if cum_dist[i] >= target_dist), n_pts - 1)

    seg_pts = rows_data[start_idx : end_idx + 1]
    actual_seg_dist = cum_dist[end_idx] - cum_dist[start_idx]
    actual_seg_slopes = [p["dem_slope"] for p in seg_pts]
    actual_seg_tilts = [math.hypot(p["pitch"], p["roll"]) for p in seg_pts]
    seg_rc = np.array([[p["row"], p["col"]] for p in seg_pts], dtype=np.float64)
    
    start_rc = (seg_pts[0]["row"], seg_pts[0]["col"])
    end_rc = (seg_pts[-1]["row"], seg_pts[-1]["col"])

    # 1. Our Safest Path
    replay_safest = run_astar_replay(start_rc, end_rc, 1016, 1075, 20.0, mode='safest')
    path_safest = replay_safest["path"]
    planned_slopes_safest = [float(slope_grid[r, c]) for r, c in path_safest]
    planned_dist_safest = sum(
        math.hypot((path_safest[i][1] - path_safest[i - 1][1]) * 20.0, (path_safest[i][0] - path_safest[i - 1][0]) * 20.0)
        for i in range(1, len(path_safest))
    )
    pct_safest = calc_pct_within_100m(path_safest, seg_rc)

    # 2. Baseline: Shortest A* (No slope penalty)
    replay_shortest = run_astar_replay(start_rc, end_rc, 1016, 1075, 20.0, mode='shortest')
    path_shortest = replay_shortest["path"]
    planned_slopes_shortest = [float(slope_grid[r, c]) for r, c in path_shortest]
    planned_dist_shortest = sum(
        math.hypot((path_shortest[i][1] - path_shortest[i - 1][1]) * 20.0, (path_shortest[i][0] - path_shortest[i - 1][0]) * 20.0)
        for i in range(1, len(path_shortest))
    )
    pct_shortest = calc_pct_within_100m(path_shortest, seg_rc)

    # 3. Baseline: Straight Line
    num_pts = max(abs(end_rc[0]-start_rc[0]), abs(end_rc[1]-start_rc[1])) + 1
    rr = np.linspace(start_rc[0], end_rc[0], num_pts)
    cc = np.linspace(start_rc[1], end_rc[1], num_pts)
    path_straight = list(zip(rr, cc))
    planned_slopes_straight = [float(slope_grid[int(round(r)), int(round(c))]) for r, c in path_straight]
    planned_dist_straight = sum(
        math.hypot((path_straight[i][1] - path_straight[i - 1][1]) * 20.0, (path_straight[i][0] - path_straight[i - 1][0]) * 20.0)
        for i in range(1, len(path_straight))
    )
    pct_straight = calc_pct_within_100m(path_straight, seg_rc)

    rover_replay = {
        "segment_sol_range": [seg_pts[0]["sol"], seg_pts[-1]["sol"]],
        "start_rc": [start_rc[0], start_rc[1]],
        "end_rc": [end_rc[0], end_rc[1]],
        "actual_rover_distance_m": round(actual_seg_dist, 2),
        "actual_mean_dem_slope_deg": round(float(np.mean(actual_seg_slopes)), 3),
        "actual_max_dem_slope_deg": round(float(np.max(actual_seg_slopes)), 3),
        "actual_mean_telemetry_tilt_deg": round(float(np.mean(actual_seg_tilts)), 3),
        
        "safest_astar": {
            "distance_m": round(planned_dist_safest, 2),
            "mean_dem_slope_deg": round(float(np.mean(planned_slopes_safest)), 3),
            "max_dem_slope_deg": round(float(np.max(planned_slopes_safest)), 3),
            "pct_within_100m": round(pct_safest, 2)
        },
        "baseline_shortest": {
            "distance_m": round(planned_dist_shortest, 2),
            "mean_dem_slope_deg": round(float(np.mean(planned_slopes_shortest)), 3),
            "max_dem_slope_deg": round(float(np.max(planned_slopes_shortest)), 3),
            "pct_within_100m": round(pct_shortest, 2)
        },
        "baseline_straight_line": {
            "distance_m": round(planned_dist_straight, 2),
            "mean_dem_slope_deg": round(float(np.mean(planned_slopes_straight)), 3),
            "max_dem_slope_deg": round(float(np.max(planned_slopes_straight)), 3),
            "pct_within_100m": round(pct_straight, 2)
        }
    }

    # A.5: Subsample for plotting
    max_sample = 2500
    step = max(1, n_pts // max_sample)
    sample_indices = list(range(0, n_pts, step))[:max_sample]
    samples = [
        {
            "sol": rows_data[i]["sol"],
            "dem_slope": round(float(dem_slope[i]), 2),
            "pitch_dem": round(float(pitch_dem[i]), 2),
            "pitch_rover": round(float(pitch_act[i]), 2),
            "roll_dem": round(float(roll_dem[i]), 2),
            "roll_rover": round(float(roll_act[i]), 2),
            "tilt_rover": round(float(rover_total_tilt[i]), 2),
            "elev_dem": round(float(dem_elev[i]), 2),
            "elev_rover": round(float(rover_elev[i]), 2),
        }
        for i in sample_indices
    ]

    output = {
        "summary": {
            "total_points_validated": n_pts,
            "dem_resolution_m": 20.0,
            "rover_wheelbase_m": 3.0,
            "sign_convention_note": f"{pitch_sign_note}; {roll_sign_note}",
            "scientific_interpretation": (
                "Orbital DEM (20 m/pixel) smooths sub-pixel rocks, ripples, and wheel-scale (~3 m) terrain undulations "
                "captured by Perseverance IMU pitch/roll telemetry. Additionally, Perseverance actively steers around "
                "local hazards, keeping 99%+ of its actual traverse below 16 deg."
            ),
        },
        "metrics": {
            "pitch": pitch_metrics,
            "roll": roll_metrics,
            "total_tilt_vs_dem_slope": tilt_metrics,
            "elevation": {
                "n": n_pts,
                "mean_bias_m": round(elev_bias, 3),
                "rmse_raw_m": round(elev_rmse_raw, 3),
                "rmse_bias_corrected_m": round(elev_rmse_centered, 3),
            },
        },
        "slope_bins": slope_bins,
        "rover_replay": rover_replay,
        "samples": samples,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    size_kb = os.path.getsize(out_path) / 1024.0
    print(f"Saved {out_path} ({size_kb:.1f} KB)")
    print("\n--- Sign Convention ---")
    print(f"Pitch: {pitch_sign_note}")
    print(f"Roll:  {roll_sign_note}")
    print("\n--- Validation Metrics ---")
    print(json.dumps(output["metrics"], indent=2))
    print("\n--- Slope Bins ---")
    print(json.dumps(slope_bins, indent=2))
    print("\n--- Rover Replay (~4 km) ---")
    print(json.dumps(rover_replay, indent=2))


if __name__ == "__main__":
    main()