"""Verify the pipeline Python environment (Task 01 setup).

Run with the project venv:
    .venv\\Scripts\\python.exe pipeline\\verify_env.py

Checks the exact capability types DE1 relies on:
  1. Versions (Python 3.11, rasterio/GDAL, numpy, Pillow)
  2. rasterio: GeoTIFF write/read roundtrip (GTiff driver, CRS, bounds, NoData, values),
     using both supported write idioms for single-band data
  3. numpy: Int16/Uint8 dtype behavior used by the binary exports (grid contract)
  4. Pillow: JPEG (quality 85) and PNG write/read

Writes only inside the system temp directory; never touches project data.
Exit code 0 = all checks passed.
"""

import os
import platform
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image

failures = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    print("=== Versions ===")
    py_ver = platform.python_version()
    impl = platform.python_implementation()
    print(f"python       : {impl} {py_ver} ({sys.executable})")
    print(f"rasterio     : {rasterio.__version__}")
    print(f"GDAL bundled : {rasterio.__gdal_version__}")
    print(f"numpy        : {np.__version__}")
    print(f"Pillow       : {Image.__version__}")

    check("python is 3.11", py_ver.startswith("3.11"), py_ver)

    print("\n=== rasterio GeoTIFF roundtrip (5x5, float32, EPSG:4326) ===")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "probe.tif")
        arr = np.arange(25, dtype="float32").reshape(5, 5)
        arr[0, 0] = -9999.0  # NoData-like value

        # Idiom A: 3D array (bands, h, w) with no index argument.
        with rasterio.open(
            path, "w", driver="GTiff", height=5, width=5, count=1,
            dtype="float32", crs="EPSG:4326",
            transform=from_bounds(77.0, 18.0, 78.0, 19.0, 5, 5),
            nodata=-9999.0,
        ) as dst:
            dst.write(arr.reshape(1, 5, 5))
        with rasterio.open(path) as src:
            check("driver", src.driver == "GTiff", src.driver)
            check("crs", src.crs.to_epsg() == 4326, str(src.crs))
            check("shape", (src.height, src.width) == (5, 5), f"{src.width}x{src.height}")
            check("transform bounds",
                  abs(src.bounds.left - 77.0) < 1e-9 and abs(src.bounds.top - 19.0) < 1e-9,
                  str(tuple(round(v, 4) for v in src.bounds)))
            check("nodata", src.nodata == -9999.0, str(src.nodata))
            check("values (3D write)", np.array_equal(src.read(1), arr))

        # Idiom B: 2D array with an explicit band index.
        with rasterio.open(path, "r+") as dst:
            dst.write(arr, 1)
        with rasterio.open(path) as src:
            check("values (2D write, explicit band)", np.array_equal(src.read(1), arr))

    print("\n=== numpy Int16/Uint8 dtype behavior (binary-export primitives) ===")
    v = np.array([-25860, -17860], dtype=np.int16)  # decimeter elevations, PLAN range
    check("int16 range holds dm values", v[0] == -25860 and v[1] == -17860, str(v.dtype))
    check("nodata sentinel fits int16", np.int16(-32768) == -32768)
    u = np.array([63 * 4], dtype=np.uint8)  # slope*4 max, PLAN §5.3
    check("uint8 holds slope*4", int(u[0]) == 252)
    le = np.array([-1], dtype="<i2")
    check("little-endian int16 available",
          le.dtype.byteorder in ("<", "=") and sys.byteorder == "little", sys.byteorder)

    print("\n=== Coordinate math without pyproj (GDAL/PROJ bundled in rasterio) ===")
    import importlib.util
    import math
    print("pyproj:", "installed" if importlib.util.find_spec("pyproj")
          else "not installed (intentional - bundled GDAL/PROJ covers CRS math)")
    from rasterio.warp import transform as warp_transform

    lon0, lat0, d = 77.4, 18.5, 0.001  # probe span in degrees
    exp_m_per_deg_lon = 2 * math.pi * 6378137 / 360  # Web Mercator sphere, x direction
    exp_m_per_deg_lat = exp_m_per_deg_lon / math.cos(math.radians(18.5))
    xs, _ = warp_transform("EPSG:4326", "EPSG:3857", [lon0, lon0 + d], [lat0, lat0])
    m_per_deg_lon = (xs[1] - xs[0]) / d
    _, ys = warp_transform("EPSG:4326", "EPSG:3857", [lon0, lon0], [lat0, lat0 + d])
    m_per_deg_lat = (ys[1] - ys[0]) / d
    check("deg->m transform (lon @18.5N)", abs(m_per_deg_lon - exp_m_per_deg_lon) < 1.0,
          f"{m_per_deg_lon:.2f} m/deg (expected ~{exp_m_per_deg_lon:.2f})")
    check("deg->m transform (lat @18.5N)", abs(m_per_deg_lat - exp_m_per_deg_lat) < 5.0,
          f"{m_per_deg_lat:.2f} m/deg (expected ~{exp_m_per_deg_lat:.2f})")

    print("\n=== Pillow JPEG q85 + PNG roundtrip ===")
    with tempfile.TemporaryDirectory() as tmp:
        img = Image.new("RGB", (64, 64), (200, 80, 40))
        jp = os.path.join(tmp, "probe.jpg")
        png = os.path.join(tmp, "probe.png")
        img.save(jp, "JPEG", quality=85)
        img.save(png, "PNG")
        j2, p2 = Image.open(jp), Image.open(png)
        check("jpeg format/size", j2.format == "JPEG" and j2.size == (64, 64), f"{j2.format} {j2.size}")
        check("png format/size", p2.format == "PNG" and p2.size == (64, 64), f"{p2.format} {p2.size}")
        j2.close()  # close lazy handles before temp-dir cleanup (Windows file lock)
        p2.close()

    print("\n=== Summary ===")
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
