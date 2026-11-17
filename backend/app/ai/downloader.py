"""Model weight downloader. Only fetches the official HTTPS release URLs from
the registry, checks the size against the expected value and records a SHA-256
(trust on first use) in models/checksums.json for later verification."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .registry import ModelSpec

ALLOWED_HOST_PREFIXES = ("https://github.com/",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksums(models_dir: Path) -> dict:
    path = models_dir / "checksums.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def verify(spec: ModelSpec, models_dir: Path) -> Optional[bool]:
    """True/False when a recorded checksum exists, None when nothing is recorded."""
    recorded = _checksums(models_dir).get(spec.filename)
    path = spec.path(models_dir)
    if not recorded or not path.is_file():
        return None
    return sha256_file(path) == recorded


def download(spec: ModelSpec, models_dir: Path,
             progress: Optional[Callable[[int, int], None]] = None) -> Path:
    if not spec.url.startswith(ALLOWED_HOST_PREFIXES):
        raise RuntimeError(f"Refusing to download {spec.id}: URL is not an allowed source")
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = spec.path(models_dir)
    if dest.is_file():
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(spec.url, headers={"User-Agent": "ai-image-enhancer"})
    with urllib.request.urlopen(request, timeout=60) as resp, open(part, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    size_mb = part.stat().st_size / 2 ** 20
    if not (spec.size_mb * 0.7 <= size_mb <= spec.size_mb * 1.3):
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"{spec.filename}: downloaded {size_mb:.1f} MB but expected about "
            f"{spec.size_mb} MB - file rejected")
    os.replace(part, dest)
    sums = _checksums(models_dir)
    sums[spec.filename] = sha256_file(dest)
    (models_dir / "checksums.json").write_text(json.dumps(sums, indent=2))
    return dest
