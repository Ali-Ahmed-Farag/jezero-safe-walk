#!/usr/bin/env python3
"""DE2 — Rover Track GeoJSON generator (Phase 3, approved design 2026-11-14).

Input : data/processed/rover_track_clean.csv  (32,003 ROVER rows x 28 source
        columns, cleaned per Phase 2.1; PLAN section 5.2 deliverable)
Output: web/data/rover_track.geojson          (PLAN section 5.2 deliverable,
        consumed by web/js/app.js via projectGeoJSON + L.geoJSON on the
        frontend branch)

Algorithm (deterministic, approved pre-implementation design):
  A. Coordinates  : [longitude, planetocentric_latitude] (RFC 7946 order;
                    planetocentric per grid_meta/DE1 CRS — NOT planetodetic),
                    rounded to 6 decimals (~0.06 m, << 20 m pixel).
  B. Distance     : cumulative true ground meters per PLACES SIS section 3.9.2:
                        true_dx = delta_easting * cos(phi_mid)/cos(18.4663deg)
                        dy      = delta_northing      (true meters)
                    computed from projected easting/northing columns.
                    No Earth-based haversine.
  C. Points       : greedy real-row selection every >= 50 m along the traverse
                    (always row 0 and the final row; no interpolation).
                    properties: sol, pitch, roll, elevation (source precision),
                    dist_m (cumulative, 1 decimal), track_index (CSV row index).
  D. LineString   : greedy deterministic 10 m vertex stride (first+last
                    vertices always kept), source traversal order preserved.
  E. Structure    : FeatureCollection; features[0] = LineString with dataset
                    metadata properties; remaining = Points in traversal order.
                    Matches the frontend-consumed de-facto schema
                    (web-amr rover_track.geojson): LineString first, Point
                    features with {sol,pitch,roll,elevation,dist_m}.

Output is byte-deterministic: same input CSV -> identical file (validated).
"""
import csv, json, math, os

IN  = os.path.join("data", "processed", "rover_track_clean.csv")
OUT = os.path.join("web", "data", "rover_track.geojson")

PHI_TS = math.radians(18.4663)          # SIS standard parallel (equirectangular)
POINT_INTERVAL_M = 50.0                 # PLAN: points every ~50 m
VERTEX_STRIDE_M  = 10.0                 # approved simplification stride
COORD_DECIMALS   = 6

def main():
    with open(IN, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 32003, len(rows)

    lon = [round(float(r["longitude"]), COORD_DECIMALS) for r in rows]
    lat = [round(float(r["planetocentric_latitude"]), COORD_DECIMALS) for r in rows]
    E   = [float(r["easting"])  for r in rows]
    N   = [float(r["northing"]) for r in rows]

    # Cumulative SIS true-ground distance along the traverse.
    dist = [0.0] * len(rows)
    for i in range(1, len(rows)):
        dx = (E[i] - E[i-1]) * math.cos(math.radians((lat_safe(rows, i)))) / math.cos(PHI_TS)
        dy = N[i] - N[i-1]
        dist[i] = dist[i-1] + math.hypot(dx, dy)
    total_m = dist[-1]

    def greedy(interval, keep_all_props_every):
        """First row, then first row whose cumulative distance is >= last
        selected + interval; always include the final row."""
        sel = [0]
        nxt = interval
        for i in range(1, len(rows) - 1):
            if dist[i] >= nxt:
                sel.append(i)
                nxt = dist[i] + interval
        if sel[-1] != len(rows) - 1:
            sel.append(len(rows) - 1)
        return sel

    point_idx = greedy(POINT_INTERVAL_M, True)
    vertex_idx = greedy(VERTEX_STRIDE_M, False)

    line_feature = {
        "type": "Feature",
        "properties": {
            "name": "Perseverance traverse",
            "source": "NASA PDS PLACES best_interp.csv v16.0 (urn:nasa:pds:mars2020_rover_places)",
            "traverse_length_m": round(total_m, 1),
            "vertex_stride_m": int(VERTEX_STRIDE_M),
            "point_interval_m": int(POINT_INTERVAL_M),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon[i], lat[i]] for i in vertex_idx],
        },
    }

    point_features = []
    for i in point_idx:
        r = rows[i]
        point_features.append({
            "type": "Feature",
            "properties": {
                "sol": int(float(r["sol"])),
                "pitch": float(r["pitch"]),
                "roll": float(r["roll"]),
                "elevation": float(r["elevation"]),
                "dist_m": round(dist[i], 1),
                "track_index": i,
            },
            "geometry": {"type": "Point", "coordinates": [[lon[i], lat[i]]][0]},
        })

    fc = {"type": "FeatureCollection", "features": [line_feature] + point_features}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=True, indent=None,
                  separators=(", ", ": "))
        f.write("\n")

    print(f"input_rows={len(rows)} total_length_m={total_m:.1f}")
    print(f"linestring_vertices={len(vertex_idx)} sampled_points={len(point_idx)}")
    print(f"output={OUT} bytes={os.path.getsize(OUT)}")

def lat_safe(rows, i):
    """Midpoint latitude (planetocentric degrees) between rows i-1 and i."""
    return 0.5 * (float(rows[i-1]["planetocentric_latitude"])
                  + float(rows[i]["planetocentric_latitude"]))

if __name__ == "__main__":
    main()
