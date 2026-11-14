import json
import numpy as np
import subprocess
import csv
import math
import os

# B3 (canonical presets integration): presets come from DE2's web/data/presets.json and
# every coordinate conversion uses DE1's web/data/grid_meta.json contract.
# No hardcoded bounds, no (W-1)/(H-1) scaling, no endpoint snapping, and NO
# presets_fixed.json output — the pre-canonical fixture is retired from this workflow
# (the committed file stays untouched for history; nothing here reads or writes it).

with open('web/data/grid_meta.json', encoding='utf-8') as f:
    meta = json.load(f)
with open('web/data/presets.json', encoding='utf-8') as f:
    presets = json.load(f)

assert meta.get('bounds_are') == 'outer_corners', 'non-canonical grid contract'
bounds = meta['bounds']
width, height = meta['width'], meta['height']
deg_x = (bounds['lon_max'] - bounds['lon_min']) / width
deg_y = (bounds['lat_max'] - bounds['lat_min']) / height

def latlon_to_rc(lat, lon):
    # grid_meta.notes contract: floor-based mapping over the half-open domain
    # [lon_min, lon_max) x (lat_min, lat_max]; row 0 = north, col 0 = west.
    c = math.floor((lon - bounds['lon_min']) / deg_x)
    r = math.floor((bounds['lat_max'] - lat) / deg_y)
    if not (0 <= r < height and 0 <= c < width):
        raise ValueError(f'lat/lon outside grid: ({lat}, {lon}) -> row={r}, col={c}')
    return r, c

slope_u8 = np.fromfile('web/data/slope_u8.bin', dtype=np.uint8).reshape((height, width))
slope_deg = slope_u8.astype(np.float64) / 4.0

# Write the CSV header BEFORE any preset validation, so a validation failure can never
# leave a stale previous-run CSV in place (B3 review note: the header-only file makes an
# aborted run obviously incomplete instead of misleadingly fresh).
csv_file = 'analysis/scenario_matrix.csv'
with open(csv_file, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['scenario', 'profile', 'mode', 'found', 'reason', 'length_km', 'time_ms', 'max_slope'])

print("1. Canonical sources loaded (no fixture generation, no endpoint edits).")
for p in presets:
    sr, sc = latlon_to_rc(p['start'][0], p['start'][1])
    er, ec = latlon_to_rc(p['end'][0], p['end'][1])
    print(f"   {p['id']}: start=({sr},{sc}) end=({er},{ec}) "
          f"rover_distance_km={p['rover_distance_km']}")

print("\n2. Running 24 A* matrix combinations (separate processes)...")

profiles = ['Conservative', 'Standard', 'Extended']
modes = ['safest', 'shortest']
scenarios = [p['id'] for p in presets]

for scen in scenarios:
    for prof in profiles:
        for mode in modes:
            cmd = ['node', 'analysis/run_one.js', scen, prof, mode]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"ERROR running {scen} {prof} {mode}: {result.stderr}")
                row = [scen, prof, mode, False, 'process_error', '0', '0', '0']
            else:
                try:
                    data = json.loads(result.stdout)
                    row = [data['scenario'], data['profile'], data['mode'], data['found'], data['reason'], data['length_km'], data['time_ms'], data['max_slope']]
                except json.JSONDecodeError:
                    print(f"Failed to parse JSON for {scen} {prof} {mode}: {result.stdout}")
                    row = [scen, prof, mode, False, 'json_error', '0', '0', '0']

            # Print immediately
            print(f"[{scen}] {prof:12} {mode:8} | found={row[3]:5} | dist={row[5]:>6}km | time={row[6]:>7}ms | max_slope={row[7]:>5}° | reason={row[4]}")

            # Write and flush immediately
            with open(csv_file, 'a', newline='') as f:
                w = csv.writer(f)
                w.writerow(row)
                f.flush()
                os.fsync(f.fileno())

print(f"\n-> Saved {csv_file}")

# Step 3: Verify scenario_3 end slope <= 16 (informational check on the canonical endpoint)
print("\n3. Verifying scenario_3 end slope...")
scen3 = next(p for p in presets if p['id'] == 'scenario_3')
er, ec = latlon_to_rc(scen3['end'][0], scen3['end'][1])
end_slope = slope_deg[er, ec]
print(f"scenario_3 end slope is {end_slope:.2f}° (Target: <= 16.0°)")
if end_slope <= 16.0:
    print("-> PASS: End slope is safe for Standard profile.")
else:
    print("-> FAIL: End slope exceeds 16°!")
