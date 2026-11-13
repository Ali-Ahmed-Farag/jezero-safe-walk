import json
import numpy as np
import subprocess
import csv
import math
import os

# إحداثيات السيناريوهات الأصلية
presets = [
  {"id": "scenario_1", "title": "Short", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4520, "end_lon": 77.4430},
  {"id": "scenario_3", "title": "Medium", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4700, "end_lon": 77.4250},
  {"id": "scenario_5", "title": "Advanced", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4900, "end_lon": 77.4000},
  {"id": "scenario_8", "title": "Long", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.5200, "end_lon": 77.3800}
]

lon_min, lon_max = 77.2229331, 77.583964
lat_min, lat_max = 18.3067994, 18.669315
width, height = 1016, 1075

def latlon_to_rc(lat, lon):
    c = int(round((lon - lon_min) / (lon_max - lon_min) * (width - 1)))
    r = int(round((lat_max - lat) / (lat_max - lat_min) * (height - 1)))
    return r, c

def rc_to_latlon(r, c):
    lat = lat_max - (r / (height - 1)) * (lat_max - lat_min)
    lon = lon_min + (c / (width - 1)) * (lon_max - lon_min)
    return round(lat, 5), round(lon, 5)

slope_u8 = np.fromfile('web/data/slope_u8.bin', dtype=np.uint8).reshape((height, width))
slope_deg = slope_u8 / 4.0

def find_nearest_safe(r, c, limit=16.0, preferred=10.0, max_radius=8):
    if slope_deg[r, c] <= limit:
        return r, c
    
    best_rc = None
    min_dist = float('inf')
    
    for rr in range(max(0, r - max_radius), min(height, r + max_radius + 1)):
        for cc in range(max(0, c - max_radius), min(width, c + max_radius + 1)):
            s = slope_deg[rr, cc]
            if s <= limit:
                d = math.hypot(rr - r, cc - c)
                penalty = 0 if s <= preferred else 100 
                score = d + penalty
                
                if score < min_dist:
                    min_dist = score
                    best_rc = (rr, cc)
                    
    return best_rc if best_rc else (r, c)

print("1. Fixing endpoints...")
fixed_presets = []
for p in presets:
    sr, sc = latlon_to_rc(p['lat'], p['lon'])
    er, ec = latlon_to_rc(p['end_lat'], p['end_lon'])
    
    ns_r, ns_c = find_nearest_safe(sr, sc)
    ne_r, ne_c = find_nearest_safe(er, ec)
    
    fixed_start = rc_to_latlon(ns_r, ns_c)
    fixed_end = rc_to_latlon(ne_r, ne_c)
    
    fixed_presets.append({
        "id": p["id"],
        "title": p["title"],
        "start": [fixed_start[0], fixed_start[1]],
        "end": [fixed_end[0], fixed_end[1]]
    })

with open('analysis/presets_fixed.json', 'w') as f:
    json.dump(fixed_presets, f, indent=2)
print("-> Saved analysis/presets_fixed.json")

print("\n2. Running 24 A* matrix combinations (separate processes)...")

profiles = ['Conservative', 'Standard', 'Extended']
modes = ['safest', 'shortest']
scenarios = [p['id'] for p in fixed_presets]

csv_file = 'analysis/scenario_matrix.csv'

# Create CSV and write header
with open(csv_file, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['scenario', 'profile', 'mode', 'found', 'reason', 'length_km', 'time_ms', 'max_slope'])

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

# Step 3: Verify scenario_3 end slope <= 16
print("\n3. Verifying scenario_3 end slope...")
scen3 = [p for p in fixed_presets if p['id'] == 'scenario_3'][0]
er, ec = latlon_to_rc(scen3['end'][0], scen3['end'][1])
end_slope = slope_deg[er, ec]
print(f"scenario_3 end slope is {end_slope:.2f}° (Target: <= 16.0°)")
if end_slope <= 16.0:
    print("-> PASS: End slope is safe for Standard profile.")
else:
    print("-> FAIL: End slope exceeds 16°!")