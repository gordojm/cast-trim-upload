"""SQLite-backed episode history. Every job state change is upserted here."""

import json
import sqlite3
import threading
from pathlib import Path

from .models import Job, JobStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    data        TEXT NOT NULL,      -- full Job JSON, including internal paths
    episode     INTEGER,
    season      INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at DESC);
"""


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    @staticmethod
    def _dump(job: Job) -> str:
        data = job.model_dump(mode="json")
        # Persist internal paths too, so a job can be resumed after a restart.
        for key in ("workdir", "audio_path", "artwork_path"):
            value = getattr(job, key)
            data[key] = str(value) if value else None
        return json.dumps(data)

    @staticmethod
    def _load(raw: str) -> Job:
        return Job.model_validate(json.loads(raw))

    def save(self, job: Job) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO jobs (id, created_at, updated_at, status, data, episode, season)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,
                     status=excluded.status, data=excluded.data,
                     episode=excluded.episode, season=excluded.season""",
                (job.id, job.created_at.isoformat(), job.updated_at.isoformat(), job.status,
                 self._dump(job), job.meta.episode, job.meta.season),
            )

    def list(self, limit: int = 100) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._load(r["data"]) for r in rows]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._load(row["data"]) if row else None

    def unfinished(self) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM jobs WHERE status NOT IN (?, ?)",
                (JobStatus.DONE, JobStatus.CANCELLED),
            ).fetchall()
        return [self._load(r["data"]) for r in rows]

    def delete(self, job_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def suggest_next(self) -> dict[str, int | None]:
        """Season of the latest uploaded episode and the episode number after it."""
        with self._lock:
            row = self._conn.execute(
                """SELECT season, episode FROM jobs
                   WHERE status = ? AND episode IS NOT NULL
                   ORDER BY created_at DESC LIMIT 1""",
                (JobStatus.DONE,),
            ).fetchone()
        if not row:
            return {"season": None, "episode": None}
        return {"season": row["season"], "episode": row["episode"] + 1}

    def close(self) -> None:
        self._conn.close()
