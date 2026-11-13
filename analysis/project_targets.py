import os
import json
import csv
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform


def extract_mars_geo_crs(proj_crs: CRS) -> CRS:
    wkt = proj_crs.to_wkt()
    start = wkt.find("GEOGCS[")
    depth = 0
    for i in range(start, len(wkt)):
        if wkt[i] == "[":
            depth += 1
        elif wkt[i] == "]":
            depth -= 1
            if depth == 0:
                return CRS.from_wkt(wkt[start : i + 1])
    raise ValueError("GEOGCS block not found in CRS WKT")


def main():
    dem_path = os.path.join("data", "processed", "dem_20m_crop.tif")
    targets_path = "science_targets.geojson"
    track_path = "rover_track_clean.csv"
    out_path = os.path.join("analysis", "projected_points.json")

    with rasterio.open(dem_path) as src:
        proj_crs = src.crs
        geo_crs = extract_mars_geo_crs(proj_crs)
        elev_band = src.read(1)

        with open(targets_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        targets_out = []
        for feat in geojson["features"]:
            lon, lat = feat["geometry"]["coordinates"][:2]
            xs, ys = transform(geo_crs, proj_crs, [lon], [lat])
            x, y = xs[0], ys[0]
            row_f, col_f = src.index(x, y, op=lambda v: v)
            col = int(round(col_f))
            row = int(round(row_f))
            in_bounds = (0 <= col < src.width) and (0 <= row < src.height)
            targets_out.append({
                "name": feat["properties"].get("name", "Unknown"),
                "lon": lon,
                "lat": lat,
                "x_m": round(x, 3),
                "y_m": round(y, 3),
                "col": col,
                "row": row,
                "in_bounds": in_bounds,
            })

        track_out = []
        if os.path.exists(track_path):
            with open(track_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if rows:
                lons = [float(r["longitude"]) for r in rows]
                lats = [float(r["planetocentric_latitude"]) for r in rows]
                xs, ys = transform(geo_crs, proj_crs, lons, lats)
                for r, x, y in zip(rows, xs, ys):
                    row_f, col_f = src.index(x, y, op=lambda v: v)
                    col = int(round(col_f))
                    row = int(round(row_f))
                    in_bounds = (0 <= col < src.width) and (0 <= row < src.height)
                    elev_val = float(elev_band[row, col]) if in_bounds else None
                    track_out.append({
                        "sol": int(float(r["sol"])),
                        "site": int(float(r["site"])),
                        "drive": int(float(r["drive"])),
                        "lon": float(r["longitude"]),
                        "lat": float(r["planetocentric_latitude"]),
                        "rover_elev_m": float(r["elevation"]),
                        "roll_deg": float(r["roll"]),
                        "pitch_deg": float(r["pitch"]),
                        "col": col,
                        "row": row,
                        "in_bounds": in_bounds,
                        "dem_elev_m": round(elev_val, 3) if elev_val is not None else None,
                    })

    result = {
        "grid_width": 1016,
        "grid_height": 1075,
        "pixel_size_m": 20.0,
        "targets": targets_out,
        "rover_track_count": len(track_out),
        "rover_track_in_bounds": sum(1 for t in track_out if t["in_bounds"]),
        "rover_track": track_out,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("Targets:")
    print(json.dumps(targets_out, indent=2))
    print(f"\nRover track points: {len(track_out)} (in bounds: {result['rover_track_in_bounds']})")


if __name__ == "__main__":
    main()