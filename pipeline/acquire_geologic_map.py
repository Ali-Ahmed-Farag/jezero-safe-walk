"""Acquire the official USGS SIM 3464 GIS database into data/raw/ (Task 08).

Product: Sun, V., and Stack, K., 2020, Geologic map of Jezero crater and the
Nili Planum region, Mars, USGS Scientific Investigations Map 3464,
DOI 10.3133/sim3464. The archive ``sim3464_database.zip`` contains the ESRI
file geodatabase (feature dataset ``Mars2000Sphere_MTM_Clon77_5E`` incl. the
``GeoUnits_v1`` unit polygons) and supporting rasters/shapefiles, projected
in Mars Transverse Mercator (central meridian 77.5E) on the Mars 2000 sphere
(R = 3396190 m).

Reliability behavior (mirrors pipeline/acquire_dem.py / acquire_ctx_basemap.py):
- Downloads to ``<dest>.part`` and renames to ``<dest>`` only after
  verification, so the destination never holds a partial file.
- Interrupted-download recovery via HTTP Range resume of ``<dest>.part``.
- Verifies the HTTP status (200 fresh / 206 resumed) and the pinned size
  (349,336,873 bytes, HEAD-verified), plus Content-Length when provided.
- Computes and prints the SHA-256 checksum and writes a provenance sidecar
  JSON. The FIRST verified download's SHA-256 becomes the enforced pin for
  re-runs via the sidecar.
- An existing complete destination is validated (size + sidecar SHA) and
  skipped, never silently overwritten. The archive is never committed
  (data/raw/* is gitignored by repository policy).

Standard library only. Run inside the project venv:

    .venv\\Scripts\\python.exe pipeline\\acquire_geologic_map.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://pubs.usgs.gov/sim/3464/sim3464_database.zip"
# Pinned size (bytes), HEAD-verified 2026-11-14 against pubs.usgs.gov
# (directory listing reports 333M).
EXPECTED_SIZE = 349_336_873
DEFAULT_DEST = Path("data/raw/sim3464_database.zip")
USER_AGENT = "JezeroSafeWalk-DE1/1.0 (hackathon data acquisition)"
CHUNK = 1 << 20  # 1 MiB
PROGRESS_STEP = 16 * CHUNK
SOCKET_TIMEOUT = 120

PRODUCT = "USGS SIM 3464 geologic database (Sun & Stack 2020)"
DOI = "10.3133/sim3464"
ATTRIBUTION = (
    "Geologic map layer: Sun, V., and Stack, K., 2020, Geologic map of Jezero "
    "crater and the Nili Planum region, Mars, USGS Scientific Investigations "
    "Map 3464, scale 1:75,000, doi:10.3133/sim3464. USGS public domain. "
    "Imagery courtesy NASA/JPL-Caltech/MSSS."
)
KNOWN_OFFSET_NOTE = (
    "Per the official README/FGDC metadata, the map was digitized on a "
    "semi-controlled CTX mosaic that predates the controlled mosaic "
    "(DOI 10.5066/P9GV1ND3) used for this project's basemap; unit boundaries "
    "carry random offsets of about 100-200 metres from our grid and are NOT "
    "exactly aligned with the CTX basemap."
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sidecar(dest: Path) -> dict:
    sidecar = dest.with_name(dest.name + ".provenance.json")
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {}


def head(url: str) -> dict | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT) as resp:
            return {
                "status": getattr(resp, "status", resp.getcode()),
                "content_length": int(resp.headers["Content-Length"])
                if resp.headers.get("Content-Length") else None,
                "accept_ranges": resp.headers.get("Accept-Ranges"),
                "final_url": resp.geturl(),
                "last_modified": resp.headers.get("Last-Modified"),
                "etag": resp.headers.get("ETag"),
            }
    except Exception as exc:  # HEAD is optional information only
        print(f"[warn] HEAD probe failed ({exc}); continuing without it")
        return None


def download(dest: Path, info: dict | None, expected_sha: str | None) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    partial_size = partial.stat().st_size if partial.exists() else 0
    server_ranges = bool(info and info.get("accept_ranges"))
    resume_from = partial_size if (partial_size and server_ranges) else 0

    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    if resume_from:
        req.add_header("Range", f"bytes={resume_from}-")
        print(f"[info] resuming from byte {resume_from} (.part had {partial_size} bytes)")
    else:
        print("[info] starting fresh download")

    with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT) as resp:
        status = getattr(resp, "status", resp.getcode())
        if status not in (200, 206):
            raise RuntimeError(f"unexpected HTTP status {status}")
        if status == 206 and not resume_from:
            raise RuntimeError("server returned 206 without a requested Range")
        if status == 206:
            m = re.match(r"bytes (\d+)-(\d+)/(\d+|\*)", resp.headers.get("Content-Range") or "")
            if not m:
                raise RuntimeError("206 response without parseable Content-Range header")
            if int(m[1]) != resume_from:
                raise RuntimeError(f"server resumed at wrong offset {m[1]}, expected {resume_from}")
        content_length = int(resp.headers["Content-Length"]) if resp.headers.get("Content-Length") else None
        final_url = resp.geturl()
        last_modified = resp.headers.get("Last-Modified")
        etag = resp.headers.get("ETag")
        mode = "ab" if (status == 206 and resume_from) else "wb"
        written = 0
        with partial.open(mode) as fh:
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                fh.write(block)
                written += len(block)
                if written // PROGRESS_STEP != (written - len(block)) // PROGRESS_STEP:
                    print(f"[download] {(resume_from + written) / (1 << 20):.1f} MiB")

    total = partial.stat().st_size
    if status == 200:
        expected_total = content_length
    elif content_length is not None:
        expected_total = resume_from + content_length
    else:
        expected_total = None
    if expected_total is not None and total != expected_total:
        raise RuntimeError(f"size mismatch: file is {total} bytes, expected {expected_total}")
    if EXPECTED_SIZE is not None and total != EXPECTED_SIZE:
        raise RuntimeError(
            f"pinned-size mismatch: got {total} bytes, expected {EXPECTED_SIZE}; "
            "upstream changed or transfer corrupt; content NOT installed"
        )

    digest = sha256_of(partial)
    if expected_sha and digest != expected_sha:
        raise RuntimeError(
            f"SHA-256 mismatch: got {digest}, expected {expected_sha}; content NOT installed"
        )
    os.replace(partial, dest)
    return {
        "url": SOURCE_URL,
        "final_url": final_url,
        "http_status": status,
        "content_length": content_length,
        "bytes_written_this_run": written,
        "resume_used": bool(resume_from),
        "partial_size_before": partial_size,
        "file_size": total,
        "expected_size": EXPECTED_SIZE,
        "sha256": digest,
        "sha256_pin_source": "first verified acquisition (pin enforced on re-runs)"
        if not expected_sha else "sidecar pin (re-run enforced)",
        "acquired_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "server_last_modified": last_modified,
        "server_etag": etag,
        "tool": "pipeline/acquire_geologic_map.py",
        "product": PRODUCT,
        "doi": DOI,
        "attribution": ATTRIBUTION,
        "known_offset_note": KNOWN_OFFSET_NOTE,
    }


def validate_existing(dest: Path, info: dict | None, expected_sha: str | None) -> dict | None:
    if not dest.exists():
        return None
    size = dest.stat().st_size
    if size == 0:
        print(f"[warn] existing {dest} is empty; re-downloading")
        return None
    if EXPECTED_SIZE is not None and size != EXPECTED_SIZE:
        print(f"[warn] existing {dest} size {size} != pinned {EXPECTED_SIZE}; re-downloading")
        return None
    digest = sha256_of(dest)
    if expected_sha and digest != expected_sha:
        print(f"[warn] existing {dest} hash {digest} != expected {expected_sha}; re-downloading")
        return None
    prov_path = dest.with_name(dest.name + ".provenance.json")
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.is_file() else {}
    recorded = prov.get("sha256")
    if recorded and recorded != digest:
        print(f"[warn] existing {dest} hash {digest} != sidecar {recorded}; re-downloading")
        return None
    print(f"[info] {dest} already present ({size} bytes) and hash-valid; skipping download")
    prov["sha256"] = digest
    prov["file_size"] = size
    return prov


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    old_sidecar = load_sidecar(args.dest)
    expected_sha = (old_sidecar.get("sha256") or "").strip().lower() or None
    if expected_sha:
        print(f"[info] sidecar SHA pin present; re-runs must reproduce {expected_sha}")

    info = head(SOURCE_URL)
    if info:
        print(
            f"[info] HEAD: status={info['status']}, content-length={info['content_length']}, "
            f"accept-ranges={info['accept_ranges']}"
        )

    prov = validate_existing(args.dest, info, expected_sha)
    if prov is None:
        try:
            prov = download(args.dest, info, expected_sha)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, OSError) as exc:
            print(f"[error] download failed: {exc}", file=sys.stderr)
            partial = args.dest.with_name(args.dest.name + ".part")
            if partial.exists():
                print(f"[info] partial kept for resume: {partial} ({partial.stat().st_size} bytes)")
            return 1

    sidecar_path = args.dest.with_name(args.dest.name + ".provenance.json")
    sidecar_path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")

    print("[done] acquisition verified:")
    print(f"  destination     : {args.dest}")
    print(f"  file size       : {prov['file_size']} bytes")
    print(f"  sha256          : {prov['sha256']}")
    print(f"  http status     : {prov['http_status']} (content-length={prov['content_length']})")
    print(f"  acquired on     : {prov['acquired_on']}")
    print(f"  provenance side : {sidecar_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
