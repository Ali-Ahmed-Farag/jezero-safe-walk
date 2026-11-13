# Pipeline — Data Processing Environment

Setup and conventions for the `pipeline/` Python scripts (DEM/imagery processing, DE1 scope).

## Python environment

Python **3.11** in a project-local virtual environment (`.venv`, already covered by `.gitignore`).
All installs and all pipeline scripts run **only inside `.venv`** — global site-packages is not used.

### One-time setup (PowerShell, repo root)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Activation (optional; alternatively call `.venv\Scripts\python.exe` directly)

```powershell
.venv\Scripts\Activate.ps1
```

> If PowerShell refuses activation with *"running scripts is disabled on this system"*, skip activation and call `.venv\Scripts\python.exe` directly, or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

`py -3.11` requires the python.org launcher (standard on python.org installs). If it is unavailable, use whichever `python` resolves to 3.11 on PATH: `python -m venv .venv`.

### Verify

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe pipeline\verify_env.py
```

`verify_env.py` validates versions and the exact operations DE1 depends on: rasterio GeoTIFF write/read roundtrip (both single-band write idioms), numpy Int16/Uint8 binary-export dtypes, and Pillow JPEG q85 / PNG output. Exit code 0 = pass.

Quick import sanity check (metadata + native stack):

```powershell
.venv\Scripts\python.exe -c "import rasterio, numpy, PIL; print(rasterio.__version__, rasterio.__gdal_version__, numpy.__version__, PIL.__version__)"
```

## Pinned dependencies (verified set)

| Package | Version | Purpose | Notes |
|---|---|---|---|
| rasterio | 1.4.4 | GeoTIFF read/crop/write (DEM tasks) | Bundles **GDAL 3.10.3** — no separate system GDAL install needed on Windows |
| numpy | 2.4.6 | Raster arrays, Int16/Uint8 binary exports | |
| pillow | 13.0.0 | JPEG q85 basemap + PNG hillshade output | |

`requirements.txt` pins the **top-level** versions for reproducibility; rasterio's transitive dependencies (affine, click, cligj, …) resolve to whatever pip selects at install time. All three packages ship prebuilt `cp311 win_amd64` wheels, so a teammate on Windows + Python 3.11 needs no compiler and no system GDAL. Note: rasterio publishes no `win-arm64` wheels — a Windows ARM64 machine would need a different approach.

`requirements.txt` covers **DE1 only** (per `docs/PLAN.md` §6: rasterio/GDAL, NumPy, Pillow). Other roles add their own tooling when needed — e.g. pandas (DE2), SciPy/matplotlib (DS) are intentionally not listed here. Whether DS/DE2 reuse this `.venv` or create their own is a team decision, not assumed here.

QGIS is an optional desktop inspection tool per PLAN §6; it is not a pip package and is not required by any pipeline script.

## Version of record (2026-11-13)

- Python: CPython 3.11.0 (`.venv\Scripts\python.exe`)
- pip (in venv): 26.3 (latest at time of setup — the setup step upgrades pip)
- Verification: 18/18 checks passed via `pipeline\verify_env.py` (includes the no-pyproj coordinate-math checks; pyproj is intentionally absent).

## Known gotchas (verified on this set)

1. **Single-band `rasterio` writes:** `dst.write(arr)` without an index requires a 3D array shaped `(bands, height, width)`. A 2D `(h, w)` array works either reshaped (`dst.write(arr.reshape(1, h, w))`) or with an explicit band index (`dst.write(arr, 1)`).
2. **Close Pillow image handles before deleting their files on Windows.** `Image.open()` is lazy; an unclosed handle locks the file (`PermissionError: WinError 32`) and breaks temp-dir cleanup. Use `img.close()` or a `with` block.
