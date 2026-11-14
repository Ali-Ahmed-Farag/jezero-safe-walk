"""Acquire the original USGS Jezero CTX DEM into data/raw/ (Task 02).

Reliability behavior:
- Downloads to ``<dest>.part`` and renames to ``<dest>`` only after verification,
  so the destination never holds a partial file.
- Interrupted-download recovery: if ``<dest>.part`` exists and the server honors
  HTTP Range requests, the download resumes from the partial size; otherwise it
  restarts from zero.
- Verifies the HTTP status (200 fresh / 206 resumed) and compares bytes written
  against Content-Length when the server provides it.
- Computes and prints the SHA-256 checksum and writes a provenance sidecar JSON
  (URL, status, sizes, checksum, acquisition date) next to the destination.
- An existing complete destination file is validated and skipped, never
  silently overwritten. An existing INCOMPLETE file is only replaced after a
  fresh verified download succeeds (documented behavior).

Standard library only. Run inside the project venv:

    .venv\\Scripts\\python.exe pipeline\\acquire_dem.py
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

SOURCE_URL = (
    "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/"
    "ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif"
)
# SHA-256 of the pristine DEM, measured at acquisition on 2026-11-13. Any
# re-download must reproduce it; a mismatch means the upstream file changed or
# the transfer is corrupt, and the verified content is NOT installed (STOP for
# review instead of silently swapping the local DEM).
EXPECTED_SHA256 = "ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2"
DEFAULT_DEST = Path("data/raw/M20_JezeroCrater_CTXDEM_20m.tif")
USER_AGENT = "JezeroSafeWalk-DE1/1.0 (hackathon data acquisition)"
CHUNK = 1 << 20  # 1 MiB
PROGRESS_STEP = 16 * CHUNK
SOCKET_TIMEOUT = 120


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def head(url: str) -> dict | None:
    """Optional HEAD probe: returns status/length/accept-ranges or None."""
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


def download(dest: Path, info: dict | None) -> dict:
    """Download (or resume) to dest.part, verify, rename. Returns provenance."""
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
                raise RuntimeError(
                    f"206 response without parseable Content-Range header: "
                    f"{resp.headers.get('Content-Range')!r}"
                )
            if int(m[1]) != resume_from:
                raise RuntimeError(
                    f"server resumed at wrong offset {m[1]}, expected {resume_from}"
                )
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

    total = partial.stat().st_size  # actual on-disk size, valid for 200 and 206
    if status == 200:
        expected_total = content_length  # full body, even if Range was ignored
    elif content_length is not None:
        expected_total = resume_from + content_length
    else:
        expected_total = None
    if expected_total is not None and total != expected_total:
        raise RuntimeError(
            f"size mismatch: file is {total} bytes, expected {expected_total}; "
            "download is corrupt or incomplete"
        )
    else:
        if expected_total is None:
            print("[warn] server did not provide Content-Length; size verified by readability only")

    digest = sha256_of(partial)
    if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
        raise RuntimeError(
            f"SHA-256 mismatch: got {digest}, expected {EXPECTED_SHA256}. "
            "The upstream file changed or the transfer is corrupt; verified "
            f"content NOT installed; partial kept at {partial}"
        )
    os.replace(partial, dest)  # atomic on the same volume
    return {
        "url": SOURCE_URL,
        "final_url": final_url,
        "http_status": status,
        "content_length": content_length,
        "bytes_written_this_run": written,
        "resume_used": bool(resume_from),
        "resume_discarded": bool(partial_size and not resume_from),
        "partial_size_before": partial_size,
        "file_size": total,
        "sha256": digest,
        "acquired_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "server_last_modified": last_modified,
        "server_etag": etag,
        "tool": "pipeline/acquire_dem.py",
    }


def validate_existing(dest: Path, info: dict | None) -> dict | None:
    """Return provenance if dest is already complete; None if it must be (re)downloaded."""
    if not dest.exists():
        return None
    size = dest.stat().st_size
    expected = info.get("content_length") if info else None
    if size == 0:
        print(f"[warn] existing {dest} is empty; re-downloading")
        return None
    if expected is not None and size != expected:
        print(f"[warn] existing {dest} size {size} != Content-Length {expected}; re-downloading")
        return None
    digest = sha256_of(dest)
    if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
        print(
            f"[warn] existing {dest} is hash-invalid (sha256 {digest} != expected "
            f"{EXPECTED_SHA256}); re-downloading"
        )
        return None
    prov_path = dest.with_name(dest.name + ".provenance.json")
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.is_file() else {}
    recorded = prov.get("sha256")
    if recorded and recorded != digest:
        print(
            f"[warn] existing {dest} hash {digest} != provenance sidecar {recorded}; "
            "re-downloading"
        )
        return None
    print(f"[info] {dest} already present ({size} bytes) and hash-valid; skipping download")
    prov["sha256"] = digest
    prov["file_size"] = size
    return prov


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    info = head(SOURCE_URL)
    if info:
        print(
            f"[info] HEAD: status={info['status']}, "
            f"content-length={info['content_length']}, "
            f"accept-ranges={info['accept_ranges']}"
        )

    prov = validate_existing(args.dest, info)
    if prov is None:
        try:
            prov = download(args.dest, info)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, OSError) as exc:
            print(f"[error] download failed: {exc}", file=sys.stderr)
            partial = args.dest.with_name(args.dest.name + ".part")
            if partial.exists():
                print(f"[info] partial kept for resume: {partial} ({partial.stat().st_size} bytes)")
            return 1

    sidecar = args.dest.with_name(args.dest.name + ".provenance.json")
    sidecar.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")

    print("[done] acquisition verified:")
    print(f"  destination     : {args.dest}")
    print(f"  file size       : {prov['file_size']} bytes")
    print(f"  sha256          : {prov['sha256']}")
    print(f"  http status     : {prov['http_status']} (content-length={prov['content_length']})")
    print(f"  acquired on     : {prov['acquired_on']}")
    print(f"  provenance side : {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
