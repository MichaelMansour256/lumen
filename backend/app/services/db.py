"""SQLite persistence for image and job metadata (stdlib only)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, format TEXT NOT NULL,
    width INTEGER NOT NULL, height INTEGER NOT NULL, size_bytes INTEGER NOT NULL,
    has_alpha INTEGER NOT NULL DEFAULT 0, analysis TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, image_id TEXT NOT NULL, status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT '',
    settings TEXT NOT NULL, error TEXT, result TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, started_at REAL, finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_image ON jobs(image_id);
"""
_JSON_COLS = {"analysis", "settings", "error", "result"}


class Database:
    def __init__(self, path: Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        out = dict(row)
        for col in _JSON_COLS & out.keys():
            out[col] = json.loads(out[col]) if out[col] else None
        if "has_alpha" in out:
            out["has_alpha"] = bool(out["has_alpha"])
        return out

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(sql, tuple(params))

    def _one(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        with self._conn() as conn:
            return self._row(conn.execute(sql, tuple(params)).fetchone())

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list:
        with self._conn() as conn:
            return [self._row(r) for r in conn.execute(sql, tuple(params)).fetchall()]

    # images -----------------------------------------------------------
    def add_image(self, rec: dict) -> None:
        self._exec(
            "INSERT INTO images (id,name,format,width,height,size_bytes,has_alpha,analysis,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (rec["id"], rec["name"], rec["format"], rec["width"], rec["height"],
             rec["size_bytes"], int(rec["has_alpha"]),
             json.dumps(rec.get("analysis")) if rec.get("analysis") else None, time.time()))

    def get_image(self, image_id: str) -> Optional[dict]:
        return self._one("SELECT * FROM images WHERE id=?", (image_id,))

    def set_analysis(self, image_id: str, analysis: dict) -> None:
        self._exec("UPDATE images SET analysis=? WHERE id=?", (json.dumps(analysis), image_id))

    def delete_image(self, image_id: str) -> list:
        """Delete an image and its jobs; returns the removed job ids."""
        job_ids = [j["id"] for j in self._all("SELECT id FROM jobs WHERE image_id=?", (image_id,))]
        self._exec("DELETE FROM jobs WHERE image_id=?", (image_id,))
        self._exec("DELETE FROM images WHERE id=?", (image_id,))
        return job_ids

    def images_older_than(self, seconds: float) -> list:
        return self._all("SELECT id FROM images WHERE created_at < ?", (time.time() - seconds,))

    # jobs -------------------------------------------------------------
    def add_job(self, job_id: str, image_id: str, settings: dict) -> None:
        self._exec(
            "INSERT INTO jobs (id,image_id,status,settings,created_at) VALUES (?,?,?,?,?)",
            (job_id, image_id, "queued", json.dumps(settings), time.time()))

    def get_job(self, job_id: str) -> Optional[dict]:
        return self._one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols, vals = [], []
        for key, value in fields.items():
            cols.append(f"{key}=?")
            vals.append(json.dumps(value) if key in _JSON_COLS and value is not None else value)
        self._exec(f"UPDATE jobs SET {', '.join(cols)} WHERE id=?", (*vals, job_id))

    def unfinished_jobs(self) -> list:
        return self._all("SELECT * FROM jobs WHERE status IN ('queued','processing')")
