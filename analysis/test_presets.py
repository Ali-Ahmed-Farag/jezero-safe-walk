import subprocess
import json

# السيناريوهات الـ 4 الرسمية من DE2
presets = [
  {"id": "scenario_1", "title": "Short (approx. 1 km)", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4520, "end_lon": 77.4430, "dist": 1.2},
  {"id": "scenario_3", "title": "Medium (approx. 3 km)", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4700, "end_lon": 77.4250, "dist": 3.1},
  {"id": "scenario_5", "title": "Advanced (approx. 5 km)", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.4900, "end_lon": 77.4000, "dist": 5.4},
  {"id": "scenario_8", "title": "Long / Scientific (approx. 8 km)", "lat": 18.4446, "lon": 77.4509, "end_lat": 18.5200, "end_lon": 77.3800, "dist": 8.2}
]

# حدود خريطتنا من PLAN.md
lon_min, lon_max = 77.2229331, 77.583964
lat_min, lat_max = 18.3067994, 18.669315
width, height = 1016, 1075

def latlon_to_rowcol(lat, lon):
    col = int(round((lon - lon_min) / (lon_max - lon_min) * (width - 1)))
    row = int(round((lat_max - lat) / (lat_max - lat_min) * (height - 1)))
    return row, col

print("Testing A* on Official DE2 Presets...\n")

for p in presets:
    start_rc = latlon_to_rowcol(p["lat"], p["lon"])
    end_rc = latlon_to_rowcol(p["end_lat"], p["end_lon"])

    js_code = f"""
    const fs = require('fs');
    const {{ findRoute }} = require('./web/data/astar.js');
    const buf = fs.readFileSync('./web/data/slope_u8.bin');
    const slope = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
    const t0 = performance.now();
    const res = findRoute({{
      slope, width: {width}, height: {height}, pixelM: 20.0,
      start: {list(start_rc)}, end: {list(end_rc)},
      profile: {{ safe: 10, hard: 16, forbidden: 16 }},
      mode: 'safest', slopeScale: 4
    }});
    const ms = performance.now() - t0;
    let dist = 0;
    if (res.found && res.path.length > 0) {{
        for (let k = 1; k < res.path.length; k++) {{
            const [r1, c1] = res.path[k-1];
            const [r2, c2] = res.path[k];
            dist += Math.hypot((c2-c1)*20, (r2-r1)*20);
        }}
    }}
    console.log(JSON.stringify({{ found: res.found, ms: ms.toFixed(2), dist_km: (dist/1000).toFixed(2), waypoints: res.path ? res.path.length : 0 }}));
    """
    proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"Error: {proc.stderr}")
        continue

    res = json.loads(proc.stdout.strip())
    print(f"🚀 [{p['id']}] {p['title']}")
    print(f"   Start [row, col]: {start_rc} | End [row, col]: {end_rc}")
    print(f"   - Rover Actual Distance : {p['dist']} km")
    print(f"   - A* Planned Distance   : {res['dist_km']} km (Waypoints: {res['waypoints']})")
    print(f"   - A* Computation Time   : {res['ms']} ms")
    print(f"   - Status                : {'✅ SUCCESS' if res['found'] else '❌ FAILED'}\n")