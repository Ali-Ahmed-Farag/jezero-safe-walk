#!/usr/bin/env python3
"""DE2 — Rover data cleaning: raw PLACES best_interp.csv -> rover_track_clean.csv.

Input  : data/raw/best_interp.csv  (+ label data/raw/best_interp.csv.xml)
Output : data/processed/rover_track_clean.csv   (PLAN section 5.2 deliverable)

Rules (PLAN sections 4/5.2; evidence: PDS4 label + Mars2020_Rover_PLACES_PDS_SIS.pdf
sections 2.1.4, 3.9.1-3.9.3, 5.1.3):
  1. Keep frame == ROVER (SITE rows are localization references, not traverse data).
  2. AOI clip on the exact PLAN section 5.1 geographic frame (project-lead ruled
     2026-11-14), half-open decode domain per grid_meta.json notes:
        lon in [77.2229, 77.5840)   and   lat in (18.3068, 18.6693]
     using columns `longitude` and `planetocentric_latitude` (the planetocentric
     convention of the DEM grid; see grid_meta crs +proj=eqc +lat_ts=18.4663).
     The requested frame lies fully inside DE1's outward-snapped grid
     (grid_meta.bounds + margins, dem_crop_report.md section 7), so every kept
     point still maps to a valid DEM pixel.
  3. Required fields (DS validation + spatial pipeline): frame, sol, easting,
     northing, longitude, planetocentric_latitude, pitch, roll, yaw, elevation.
     Drop a row if any required field fails to parse or equals the documented
     -9999 missing sentinel.
  4. Optional documented-sentinel fields (landing_x/y/z, planetodetic_latitude,
     quat_s/v1/v2/v3, areoid, radius): if -9999, replace with an empty field
     (consistent representation, no invalid numeric sentinel in the CSV).
     Never delete a row solely for an optional missing value.
  5. -1 in site/drive/pose is the documented not_applicable constant, not a
     missing coordinate: preserved verbatim.
  6. All kept values are copied verbatim from source tokens (no float
     re-serialization, no reformatting); source row order (traverse order) is
     preserved; no sorting, no joins, no dedup (none found), no interpolation.
  7. easting/northing are PLACES projected meters on the DEM's exact CRS
     (equirectangular, standard parallel 18.4663, sphere R=3396190, Airy-0):
     passed through unchanged — no transformation required (SIS sections 3.9.1-3.9.2).

Cross-check (diagnostic only): replicates the Data Science `validate_rover.py`
pixel-index acceptance (round of inverse-affine coords, 0<=col<width,
0<=row<height) on the retained rows to explain any count difference vs DS.
"""
import csv, hashlib, os, sys

RAW = os.path.join("data", "raw", "best_interp.csv")
OUT = os.path.join("data", "processed", "rover_track_clean.csv")

# AOI bounds — exact PLAN section 5.1 geographic frame (approved 2026-11-14)
LON_MIN, LON_MAX = 77.2229, 77.5840
LAT_MIN, LAT_MAX = 18.3068, 18.6693
# Grid geometry from origin/data:web/data/grid_meta.json (a3da13e) — used only by
# the diagnostic DS pixel-acceptance cross-check below (not for clipping).
WIDTH, HEIGHT = 1016, 1075
# Crop projected extents (DE1 dem_crop_report.md section 6): x from 4341660, y from 1106620, res 20 m
X0, Y1, RES = 4341659.999999998, 1106620.0000000028, 20.0

SENTINEL = "-9999"
REQUIRED_SENT = ["longitude", "planetocentric_latitude", "pitch", "roll", "yaw", "elevation"]
REQUIRED_PARSE = ["easting", "northing", "sol"]
OPTIONAL_SENT = ["landing_x", "landing_y", "landing_z", "planetodetic_latitude",
                 "quat_s", "quat_v1", "quat_v2", "quat_v3", "areoid", "radius"]

def is_sent(v):  # documented missing constant (values look like -9999.000 / -9999.000000000)
    return v == SENTINEL or v.startswith(SENTINEL + ".")

def main():
    stats = {"total": 0, "site": 0, "rover": 0, "drop_required": 0,
             "drop_aoi": 0, "kept": 0, "blanked": 0,
             "aoi_west": 0, "aoi_east": 0, "aoi_south": 0, "aoi_north": 0}
    by_field = {k: 0 for k in REQUIRED_SENT + REQUIRED_PARSE + OPTIONAL_SENT}
    kept_rows, header = [], None
    with open(RAW, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd)
        assert len(header) == 28, header
        idx = {c: i for i, c in enumerate(header)}
        for row in rd:
            assert len(row) == 28, row
            stats["total"] += 1
            if row[idx["frame"]] == "SITE":
                stats["site"] += 1
                continue
            stats["rover"] += 1
            if any(is_sent(row[idx[c]]) for c in REQUIRED_SENT) or \
               any(_bad_parse(row[idx[c]]) for c in REQUIRED_PARSE):
                for c in REQUIRED_SENT:
                    if is_sent(row[idx[c]]): by_field[c] += 1
                for c in REQUIRED_PARSE:
                    if _bad_parse(row[idx[c]]): by_field[c] += 1
                stats["drop_required"] += 1
                continue
            lon = float(row[idx["longitude"]]); lat = float(row[idx["planetocentric_latitude"]])
            if not (LON_MIN <= lon < LON_MAX and LAT_MIN < lat <= LAT_MAX):
                if lon < LON_MIN: stats["aoi_west"] += 1
                elif lon >= LON_MAX: stats["aoi_east"] += 1
                if lat <= LAT_MIN: stats["aoi_south"] += 1
                elif lat > LAT_MAX: stats["aoi_north"] += 1
                stats["drop_aoi"] += 1
                continue
            for c in OPTIONAL_SENT:
                if is_sent(row[idx[c]]):
                    row[idx[c]] = ""
                    by_field[c] += 1
                    stats["blanked"] += 1
            kept_rows.append(row)
            stats["kept"] += 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(kept_rows)

    # Diagnostic: replicate DS pixel acceptance to explain count differences
    ds_reject = 0
    for row in kept_rows:
        e = float(row[idx["easting"]]); n = float(row[idx["northing"]])
        col = round((e - X0) / RES); r = round((Y1 - n) / RES)
        if not (0 <= col < WIDTH and 0 <= r < HEIGHT):
            ds_reject += 1
    h = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    print(f"total={stats['total']} site={stats['site']} rover={stats['rover']}")
    print(f"drop_required={stats['drop_required']} drop_aoi={stats['drop_aoi']} kept={stats['kept']}")
    print(f"aoi_drops_by_edge: west(lon<{LON_MIN})={stats['aoi_west']} east(lon>={LON_MAX})={stats['aoi_east']} "
          f"south(lat<={LAT_MIN})={stats['aoi_south']} north(lat>{LAT_MAX})={stats['aoi_north']}")
    print(f"optional_values_blanked={stats['blanked']}")
    print("per-field hits:", {k: v for k, v in by_field.items() if v})
    print(f"ds_pixel_rounding_rejects_within_kept={ds_reject}")
    print(f"output={OUT} bytes={os.path.getsize(OUT)} sha256={h}")
    return 0

def _bad_parse(v):
    try:
        float(v); return False
    except ValueError:
        return True

if __name__ == "__main__":
    sys.exit(main())
