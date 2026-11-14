"""Export the Jezero Safe Walk geological map layer (Task 08, P2 optional).

Reads the official USGS SIM 3464 GIS database (acquired by
``pipeline/acquire_geologic_map.py``), reprojects the ``GeoUnits_v1`` unit
polygons onto the EXACT shared grid, and writes:

- ``web/data/geologic_map.png``      - 1016 x 1075 RGBA PNG, unit polygons
  colorized with a fixed documented palette, transparent background,
  <= 3 MB (docs/PLAN.md line 211).
- ``web/data/geologic_map_legend.json`` - machine-readable unit -> color
  legend for the Full Stack team (unit ids, names, symbols, colors,
  per-unit pixel counts, parameters, provenance).

Source (Sun, V., and Stack, K., 2020, USGS SIM 3464, doi:10.3133/sim3464):
- Feature dataset ``Mars2000Sphere_MTM_Clon77_5E`` in ``Nili.gdb``; layer
  ``GeoUnits_v1`` (1,304 MultiPolygon features); CRS: Mars Transverse
  Mercator, central meridian 77.5E, scale factor 1, on the Mars 2000 sphere
  (a=b=c=3396190 m), units metres.
- 14 mapped units (ids "0".."13") with names/symbols taken verbatim from the
  source attributes - no classification is invented or altered.

Processing decisions (documented; PLAN specifies no rendering details):

- Grid: EXACTLY the existing shared grid (``grid_meta.json`` + the Task 03
  DEM transform; 1016 x 1075 @ 20 m projected, eqc lat_ts=18.4663,
  R=3396190, row 0 = north, col 0 = west). Never recreated.
- Reprojection: MTM (clon 77.5) -> grid eqc via PROJ (same sphere; pure
  PROJ transformation of polygon vertices, then rasterization directly on
  the target grid - no intermediate resampling of the raster).
- Anti-aliasing: 4x supersampling (5 m/px rasterization) followed by a
  deterministic majority vote per output pixel over its 16 subpixels;
  ties resolved by the LOWEST unit id first, background LAST (background
  wins only with a strictly greater count). Measured property of this
  dataset: the units form a DISJOINT partition of the map area (ascending
  vs descending paint order produce identical rasters; zero background
  pixels inside the grid), so paint order is irrelevant to the result.
- NoData/background: unmapped pixels (none inside this grid, by
  measurement) are TRANSPARENT (alpha 0) so the CTX basemap shows through;
  mapped pixels are opaque (alpha 255). The map is an overlay layer.
- Colors: fixed qualitative palette (documented hex values below and in
  the legend JSON). The source ``Color_ID`` field is an ArcMap symbol
  index, NOT a color (values collide across units, e.g. 74 is shared by
  units 5 and 10), so it cannot drive colors.
- KNOWN LIMITATION (documented, per the official README/FGDC metadata):
  the map was digitized on a SEMI-CONTROLLED mosaic that predates the
  controlled mosaic (DOI 10.5066/P9GV1ND3) used for this project's CTX
  basemap; unit boundaries carry random offsets of about 100-200 metres
  from our grid and are NOT exactly aligned with the CTX basemap.

Report ownership: ``data/processed/geologic_map_report.md`` is written by
the INDEPENDENT validator ``pipeline/verify_geologic_map.py`` after every
check (including the double-export determinism proof) passes. This exporter
prints its full evidence to stdout.

Run from the repository root::

    .venv\\Scripts\\python.exe pipeline\\export_geologic_map.py
"""

from __future__ import annotations

import argparse
import fiona
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as rtransform

DEFAULT_ARCHIVE = Path("data/raw/sim3464_database.zip")
DEFAULT_GDB = Path("data/raw/sim3464_database/sim3464_JezeroNili_FINAL/Geodatabase/Nili.gdb")
DEFAULT_LAYER = "GeoUnits_v1"
DEFAULT_RASTER = Path("data/processed/dem_20m_crop.tif")
DEFAULT_META = Path("web/data/grid_meta.json")
DEFAULT_DEST = Path("web/data/geologic_map.png")
DEFAULT_LEGEND = Path("web/data/geologic_map_legend.json")

# Pinned identities (house pattern: duplicated in verify_geologic_map.py and
# the provenance sidecars - update all together).
EXPECTED_ARCHIVE_SHA256 = "a88bd53a5573743cc4a20036c10e585106d08a433ad2f34af269e9cea1529f87"
EXPECTED_ARCHIVE_SIZE = 349_336_873
EXPECTED_RASTER_SHA256 = "b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae"

# Pinned source contract (official README/FGDC metadata + measured).
EXPECTED_SRC_CRS_TOKENS = ("+proj=tmerc", "+lon_0=77.5", "+k=1", "+R=3396190", "+units=m")
GDB_LAYER = DEFAULT_LAYER

MAX_BYTES = 3 * 1024 * 1024  # PLAN line 211: <= 3 MB
AXIS_TOL = 1e-9
SUPER_SAMPLE = 4  # 5 m/px rasterization, majority-downsampled to 20 m/px

# Fixed unit palette (documented; deterministic; distinct qualitative colors
# following common USGS geologic-map color conventions: reddish/brown
# bedrock, light fans, yellow eolian cover, gray smooth, white bright).
UNIT_PALETTE = {
    0: ("NHjf2", "#F5C58A"),   # Jezero fan 2 unit
    1: ("NHjf1", "#E8A75C"),   # Jezero fan 1 unit
    2: ("Njf", "#A6D8E8"),     # Jezero floor unit (lake sediments - cyan)
    3: ("Nle", "#C98A4B"),     # Lower etched unit
    4: ("Hnpf", "#E8E3B0"),    # Nili Planum fan unit
    5: ("Nnp2", "#B5C98A"),    # Nili Planum 2 unit
    6: ("Nnp1", "#8FA36B"),    # Nili Planum 1 unit
    7: ("Aeb", "#F2E14C"),     # Eolian bedform unit (sand - yellow)
    8: ("su", "#D9D9D9"),      # Smooth unit, undivided
    9: ("Nrb", "#F4F4F4"),     # Rugged bright unit
    10: ("Nue", "#C77F5B"),    # Upper etched unit
    11: ("cr", "#B04A4A"),     # Crater rim unit
    12: ("ce", "#E2B6B6"),     # Crater ejecta unit
    13: ("ci", "#6E4F4F"),     # Crater interior unit
}
BACKGROUND_ALPHA = 0
UNIT_ALPHA = 255

DOI = "10.3133/sim3464"
CITATION = (
    "Sun, V., and Stack, K., 2020, Geologic map of Jezero crater and the "
    "Nili Planum region, Mars: U.S. Geological Survey Scientific "
    "Investigations Map 3464, pamphlet 14 p., 1 sheet, scale 1:75,000, "
    "https://doi.org/10.3133/sim3464"
)
OFFSET_NOTE = (
    "Known limitation (official README/FGDC metadata): the map was digitized "
    "on a semi-controlled CTX mosaic predating the controlled mosaic "
    "(DOI 10.5066/P9GV1ND3) used for this project's basemap; unit boundaries "
    "carry random offsets of about 100-200 metres from our grid and are NOT "
    "exactly aligned with the CTX basemap."
)

REQUIRED_META_KEYS = ("width", "height", "crs", "provenance")

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20


def die(msg: str) -> None:
    raise SystemExit(f"[error] {msg}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def hex_to_rgb(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def reproject_coords(obj, src_crs: CRS, dst_crs: CRS):
    """Structure-agnostic walker: recurse until a ring (list of points)."""
    if (
        isinstance(obj, (list, tuple)) and obj
        and isinstance(obj[0], (list, tuple)) and len(obj[0]) >= 2
        and isinstance(obj[0][0], (int, float))
    ):
        xs = [float(p[0]) for p in obj]
        ys = [float(p[1]) for p in obj]
        tx, ty = rtransform(src_crs, dst_crs, xs, ys)
        return [list(xy) for xy in zip(tx, ty)]
    return [reproject_coords(o, src_crs, dst_crs) for o in obj]


def validate_dest(dest: Path, overwrite: bool) -> None:
    if dest.suffix.lower() != ".png":
        die(f"--dest must end with '.png' (got {dest.name!r}); refusing unsafe destination")
    if not dest.parent.is_dir():
        die(f"--dest parent directory does not exist: {dest.parent}")
    parts_lower = {p.lower() for p in dest.parts}
    for guarded in ("pipeline", "docs", "analysis"):
        if guarded in parts_lower:
            die(f"--dest must not live under {guarded}/: {dest}")
    try:
        rel = dest.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = None
    if rel is not None and len(rel.parts) >= 2 and rel.parts[0] == "data" and rel.parts[1] == "raw":
        die(f"--dest must not live under data/raw/: {dest}")
    if dest.exists() and not overwrite:
        die(
            f"destination already exists: {dest}\n"
            "       re-run with --overwrite to replace it deliberately"
        )


def load_meta(path: Path) -> dict:
    if not path.is_file():
        die(f"metadata file not found: {path}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        die(f"metadata file is not readable JSON: {exc}")
    missing = [k for k in REQUIRED_META_KEYS if k not in meta]
    if missing:
        die(f"metadata is missing required keys: {', '.join(missing)}")
    print(f"[ok] metadata loaded: {path.as_posix()}")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--gdb", type=Path, default=DEFAULT_GDB)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--legend", type=Path, default=DEFAULT_LEGEND)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="deliberately replace an existing destination file",
    )
    args = parser.parse_args()

    resolves = {p.resolve() for p in (args.raster, args.meta, args.dest, args.legend, args.archive, args.gdb)}
    if len(resolves) < 6:
        die("--archive, --gdb, --raster, --meta, --dest and --legend must be distinct paths")

    # --------------------------------------------- 1: destination safety
    validate_dest(args.dest, args.overwrite)
    if args.legend.suffix.lower() != ".json":
        die(f"--legend must end with '.json' (got {args.legend.name!r})")

    # --------------------------------------------- 2: contracts
    meta = load_meta(args.meta)
    if not args.archive.is_file():
        die(f"source archive not found: {args.archive} (run pipeline/acquire_geologic_map.py first)")
    if not args.gdb.is_dir():
        die(
            f"geodatabase not found: {args.gdb} "
            "(extract data/raw/sim3464_database.zip first)"
        )
    archive_sha = sha256_of(args.archive)
    if archive_sha != EXPECTED_ARCHIVE_SHA256:
        die(f"archive SHA-256 mismatch: got {archive_sha}, expected pinned {EXPECTED_ARCHIVE_SHA256}")
    print(f"[ok] archive identity: sha256={archive_sha}, {args.archive.stat().st_size} bytes")

    if not args.raster.is_file():
        die(f"target DEM raster not found: {args.raster}")
    raster_sha = sha256_of(args.raster)
    if raster_sha != EXPECTED_RASTER_SHA256:
        die(f"DEM SHA-256 mismatch: got {raster_sha}, expected pinned {EXPECTED_RASTER_SHA256}")
    prov = meta.get("provenance")
    if not isinstance(prov, dict) or raster_sha != prov.get("dem_sha256"):
        die("DEM SHA-256 disagrees with metadata provenance.dem_sha256")
    print(f"[ok] DEM identity: sha256={raster_sha} matches pin + metadata (DEM untouched)")

    ds = rasterio.open(args.raster)
    if (ds.width, ds.height) != (int(meta["width"]), int(meta["height"])):
        die(f"DEM dims {ds.width}x{ds.height} != metadata {meta['width']}x{meta['height']}")
    t = ds.transform
    if abs(t.b) > AXIS_TOL or abs(t.d) > AXIS_TOL or t.a <= 0 or t.e >= 0:
        die("DEM grid rotated/sheared or not north-up")
    crs_tokens_meta = str(meta.get("crs", "")).split()
    crs_tokens_ras = (ds.crs.to_proj4() or "").split()
    absent = [tok for tok in crs_tokens_meta if tok not in crs_tokens_ras]
    if absent:
        die(f"DEM CRS is missing metadata CRS tokens: {', '.join(absent)}")
    print(
        f"[ok] target grid geometry: {ds.width}x{ds.height} @ {t.a!r}/{abs(t.e)!r} m projected, "
        f"north-up, unrotated"
    )

    # --------------------------------------------- 3: read + validate source units
    if not GDB_LAYER in fiona.listlayers(str(args.gdb)):
        die(f"layer {GDB_LAYER!r} not found in {args.gdb}; layers={fiona.listlayers(str(args.gdb))}")
    with fiona.open(str(args.gdb), layer=GDB_LAYER) as src:
        src_crs_str = src.crs.to_proj4() if hasattr(src.crs, "to_proj4") else str(src.crs)
        src_crs = CRS.from_proj4(src_crs_str)
        absent = [tok for tok in EXPECTED_SRC_CRS_TOKENS if tok not in src_crs_str.split()]
        if absent:
            die(f"source CRS is missing pinned tokens: {', '.join(absent)} (got {src_crs_str})")
        gcrs = CRS.from_proj4(ds.crs.to_proj4())
        feats = [(dict(f["properties"]), f["geometry"]) for f in src]
    print(
        f"[ok] source layer: {GDB_LAYER}, {len(feats)} features, "
        f"CRS {src_crs_str} (tokens verified: MTM clon 77.5, Mars sphere R=3396190)"
    )
    unit_names = {}
    for p, _ in feats:
        unit_names.setdefault(int(p["unit"]), (str(p["name"]), str(p["symbol"])))
    if sorted(unit_names) != sorted(UNIT_PALETTE):
        die(
            "source unit ids disagree with the palette contract: "
            f"source={sorted(unit_names)}, palette={sorted(UNIT_PALETTE)}"
        )
    for u, (name, symbol) in unit_names.items():
        exp_sym = UNIT_PALETTE[u][0]
        if symbol != exp_sym:
            die(f"unit {u} symbol {symbol!r} != palette contract {exp_sym!r}")
    print(f"[ok] source units: {len(unit_names)} ids {sorted(unit_names)}; symbols match the palette contract")

    # --------------------------------------------- 4: reproject vertices
    src_crs = CRS.from_proj4(src_crs_str)
    reproj = [
        (p, {"type": g["type"], "coordinates": reproject_coords(g["coordinates"], src_crs, gcrs)})
        for p, g in feats
    ]
    print(f"[ok] reprojected {len(reproj)} MultiPolygon features MTM(clon 77.5) -> grid eqc")

    # --------------------------------------------- 5: supersampled rasterization
    width, height = int(meta["width"]), int(meta["height"])
    up_shape = (height * SUPER_SAMPLE, width * SUPER_SAMPLE)
    up_transform = from_origin(
        t.c, t.f, t.a / SUPER_SAMPLE, abs(t.e) / SUPER_SAMPLE
    )
    unit_ids = sorted(UNIT_PALETTE)
    shapes = []
    for p, g in sorted(reproj, key=lambda pg: (int(pg[0]["unit"]), int(pg[0]["ORIG_FID"]))):
        shapes.append((g, int(p["unit"])))
    up = rasterize(shapes, out_shape=up_shape, transform=up_transform, fill=-1, dtype="int16")
    bg_up = int((up == -1).sum())
    print(
        f"[ok] supersampled rasterization: {up_shape[1]}x{up_shape[0]} @ "
        f"{t.a / SUPER_SAMPLE:.2f} m/px; background {bg_up} of {up.size} subpixels "
        f"({100.0 * bg_up / up.size:.6f}%)"
    )

    # paint-order invariance evidence (dataset property, measured here)
    shapes_desc = shapes[::-1]
    up_desc = rasterize(shapes_desc, out_shape=up_shape, transform=up_transform, fill=-1, dtype="int16")
    order_diff = int((up != up_desc).sum())
    print(
        f"[ok] paint-order invariance measured: {order_diff} differing subpixels between "
        f"ascending/descending paint orders (disjoint partition => order irrelevant)"
    )
    del up_desc

    # --------------------------------------------- 6: majority downsample
    counts = np.zeros((len(unit_ids) + 1, height, width), dtype=np.uint8)
    for k in range(SUPER_SAMPLE * SUPER_SAMPLE):
        dr, dc = k // SUPER_SAMPLE, k % SUPER_SAMPLE
        sub = up[dr::SUPER_SAMPLE, dc::SUPER_SAMPLE]
        for i, u in enumerate(unit_ids):
            counts[i] += (sub == u)
    counts[len(unit_ids)] = SUPER_SAMPLE * SUPER_SAMPLE - counts[: len(unit_ids)].sum(axis=0)
    bg_total = int(counts[len(unit_ids)].sum())
    chosen_idx = counts.argmax(axis=0)  # first max wins: lowest unit id, background last
    print(
        f"[ok] majority downsample (4x -> 1x): background {bg_total} of {height * width} "
        f"output pixels ({100.0 * bg_total / (height * width):.6f}%); "
        f"tie policy: lowest unit id first, background last"
    )
    unit_out_counts = {u: int((chosen_idx == i).sum()) for i, u in enumerate(unit_ids)}
    print(f"[ok] per-unit output pixel counts: {unit_out_counts}")

    # --------------------------------------------- 7: colorize + alpha
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for i, u in enumerate(unit_ids):
        mask = chosen_idx == i
        r8, g8, b8 = hex_to_rgb(UNIT_PALETTE[u][1])
        rgba[mask, 0] = r8
        rgba[mask, 1] = g8
        rgba[mask, 2] = b8
        rgba[mask, 3] = UNIT_ALPHA
    rgba[chosen_idx == len(unit_ids), 3] = BACKGROUND_ALPHA
    if not rgba.flags["C_CONTIGUOUS"]:
        die("RGBA array is not C-contiguous")
    opaque = int((rgba[:, :, 3] == UNIT_ALPHA).sum())
    print(
        f"[ok] colorized: {opaque} opaque unit pixels "
        f"({100.0 * opaque / (height * width):.4f}%), "
        f"{height * width - opaque} transparent background pixels"
    )
    ds.close()

    # --------------------------------------------- 8: atomic writes
    partial = args.dest.with_name(args.dest.name + ".part")
    try:
        Image.fromarray(rgba, mode="RGBA").save(partial, format="PNG")
    except Exception as exc:  # noqa: BLE001
        die(f"PNG encode failed: {exc}")
    size = partial.stat().st_size
    if size > MAX_BYTES:
        print(
            f"[error] partial PNG is {size} bytes > {MAX_BYTES} limit; kept at {partial}",
            file=sys.stderr,
        )
        return 1
    try:
        os.replace(partial, args.dest)  # atomic on the same volume
    except OSError as exc:
        print(f"[error] promoting the partial PNG failed: {exc}", file=sys.stderr)
        return 1

    with Image.open(args.dest) as img:
        img.load()
        out_ok = img.mode == "RGBA" and img.size == (width, height)
    if not out_ok:
        die("promoted PNG failed re-open verification (mode/dims)")
    dest_sha = sha256_of(args.dest)
    print(f"[ok] promoted: {args.dest.as_posix()} ({size} bytes = {size / 1024:.1f} KiB)")

    # --------------------------------------------- 9: machine-readable legend
    legend = {
        "product": "Jezero Safe Walk geological map layer",
        "grid": {"width": width, "height": height, "pixel_size_projected_m": 20,
                 "crs": str(meta.get("crs", "")), "row0": "north", "col0": "west",
                 "layout": "row_major"},
        "source": {
            "citation": CITATION,
            "doi": DOI,
            "url": "https://pubs.usgs.gov/sim/3464/",
            "archive_sha256": archive_sha,
            "scale": "1:75,000",
            "license": "USGS public domain (access constraints: none; fees: none)",
        },
        "known_offset_note": OFFSET_NOTE,
        "rendering": {
            "reprojection": "Mars TM (clon 77.5E, R=3396190) -> equirectangular lat_ts=18.4663 (R=3396190)",
            "supersample": SUPER_SAMPLE,
            "downsample": "majority vote over 16 subpixels; ties: lowest unit id first, background last",
            "background": {"alpha": BACKGROUND_ALPHA, "meaning": "unmapped area (transparent; CTX basemap shows through)"},
            "unit_alpha": UNIT_ALPHA,
        },
        "units": [
            {
                "unit": u,
                "name": unit_names[u][0],
                "symbol": unit_names[u][1],
                "color_hex": UNIT_PALETTE[u][1],
                "rgb": list(hex_to_rgb(UNIT_PALETTE[u][1])),
                "alpha": UNIT_ALPHA,
                "pixel_count_in_grid": unit_out_counts.get(u, 0),
                "in_this_grid": unit_out_counts.get(u, 0) > 0,
            }
            for u in unit_ids
        ],
        "background_pixel_count_in_grid": bg_total,
    }
    args.legend.write_text(
        json.dumps(legend, indent=2, ensure_ascii=True, sort_keys=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"[ok] legend written: {args.legend.as_posix()}")
    print(
        f"[summary] archive_sha256={archive_sha}, units={len(unit_ids)}, "
        f"features={len(reproj)}, supersample={SUPER_SAMPLE}x, "
        f"order_invariant_diff={order_diff}, background={bg_total}, "
        f"dest={args.dest.as_posix()} (RGBA {width}x{height}, {size} bytes), "
        f"dest_sha256={dest_sha}, legend={args.legend.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
