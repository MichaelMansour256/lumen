"""Storage abstraction. Keys look like 'originals/<32 hex>.png'; nothing
user-supplied ever becomes part of a path. Swap LocalStorage for a cloud
implementation of the same interface later."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional, Protocol

_KEY_RE = re.compile(r"^(originals|results|previews)/[0-9a-f]{32}\.(png|jpg|webp)$")


class Storage(Protocol):
    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def delete(self, key: str) -> None: ...
    def local_path(self, key: str) -> Optional[Path]: ...
    def purge_older_than(self, seconds: float) -> int: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        for sub in ("originals", "results", "previews"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def local_path(self, key: str) -> Optional[Path]:
        path = self._path(key)
        return path if path.is_file() else None

    def purge_older_than(self, seconds: float) -> int:
        cutoff = time.time() - seconds
        removed = 0
        for sub in ("originals", "results", "previews"):
            for item in (self.root / sub).iterdir():
                try:
                    if item.is_file() and item.stat().st_mtime < cutoff:
                        item.unlink()
                        removed += 1
                except OSError:
                    continue
        return removed
