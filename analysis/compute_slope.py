import os
import json
import numpy as np
import rasterio


def compute_horn_slope(dem: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """
    Compute terrain slope in degrees using Horn's 3x3 weighted gradient method.
    Edges are padded with edge values so output shape matches input (H, W).
    """
    padded = np.pad(dem.astype(np.float64), pad_width=1, mode="edge")

    z1 = padded[:-2, :-2]
    z2 = padded[:-2, 1:-1]
    z3 = padded[:-2, 2:]
    z4 = padded[1:-1, :-2]
    z6 = padded[1:-1, 2:]
    z7 = padded[2:, :-2]
    z8 = padded[2:, 1:-1]
    z9 = padded[2:, 2:]

    dz_dx = ((z3 + 2.0 * z6 + z9) - (z1 + 2.0 * z4 + z7)) / (8.0 * dx)
    dz_dy = ((z7 + 2.0 * z8 + z9) - (z1 + 2.0 * z2 + z3)) / (8.0 * dy)

    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    return np.degrees(slope_rad)


def main():
    dem_path = os.path.join("data", "processed", "dem_20m_crop.tif")
    out_bin_path = os.path.join("web", "data", "slope_u8.bin")
    out_stats_path = os.path.join("analysis", "slope_stats.json")

    os.makedirs(os.path.dirname(out_bin_path), exist_ok=True)
    os.makedirs(os.path.dirname(out_stats_path), exist_ok=True)

    with rasterio.open(dem_path) as src:
        dem = src.read(1)
        nodata = src.nodata
        dx, dy = src.res
        width, height = src.width, src.height

    # Invalid-pixel census (approved B6 policy: NO interpolation, NO masking,
    # NO substitution). Exact equality against the declared finite NoData value;
    # NaN and both infinities are detected separately. The run ABORTS before any
    # gradient calculation if the DEM is not fully valid.
    exact_nodata = (dem == np.float32(nodata)) if nodata is not None else np.zeros(dem.shape, dtype=bool)
    nan_mask = np.isnan(dem)
    pos_inf_mask = np.isposinf(dem)
    neg_inf_mask = np.isneginf(dem)
    invalid_census = {
        "width": int(width),
        "height": int(height),
        "nodata_pixels": int(exact_nodata.sum()),
        "nan_pixels": int(nan_mask.sum()),
        "pos_inf_pixels": int(pos_inf_mask.sum()),
        "neg_inf_pixels": int(neg_inf_mask.sum()),
        "total_invalid": int(exact_nodata.sum() + nan_mask.sum() + pos_inf_mask.sum() + neg_inf_mask.sum()),
    }
    print(json.dumps({"invalid_pixel_census": invalid_census}, indent=2))
    if invalid_census["total_invalid"]:
        raise SystemExit(
            "[error] DEM contains invalid pixels (census above). The approved slope "
            "contract forbids interpolation across NoData - aborting before gradients. "
            "Escalate: the shared grid is contractually complete."
        )

    slope_deg = compute_horn_slope(dem, dx=float(dx), dy=float(dy))

    slope_scale = 4
    slope_u8 = np.clip(np.round(slope_deg * slope_scale), 0, 255).astype(np.uint8)
    slope_u8.tofile(out_bin_path)

    stats = {
        "source_dem": dem_path,
        "output_bin": out_bin_path,
        "width": int(width),
        "height": int(height),
        "total_pixels": int(width * height),
        "pixel_size_m": {"x": float(dx), "y": float(dy)},
        "slope_scale": slope_scale,
        "file_size_bytes": int(os.path.getsize(out_bin_path)),
        "slope_deg_min": round(float(np.min(slope_deg)), 4),
        "slope_deg_max": round(float(np.max(slope_deg)), 4),
        "slope_deg_mean": round(float(np.mean(slope_deg)), 4),
        "slope_deg_median": round(float(np.median(slope_deg)), 4),
        "slope_deg_p90": round(float(np.percentile(slope_deg, 90)), 4),
        "slope_deg_p95": round(float(np.percentile(slope_deg, 95)), 4),
        "slope_deg_p99": round(float(np.percentile(slope_deg, 99)), 4),
        "pct_under_10deg": round(float(np.mean(slope_deg <= 10.0) * 100.0), 2),
        "pct_under_16deg": round(float(np.mean(slope_deg <= 16.0) * 100.0), 2),
        "pct_over_25deg": round(float(np.mean(slope_deg > 25.0) * 100.0), 2),
    }

    with open(out_stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()