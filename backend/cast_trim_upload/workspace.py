"""Per-job temporary folders."""

import logging
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)


def create(tmp_root: Path, job_id: str) -> Path:
    path = tmp_root / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove(path: Path | None) -> None:
    if path and path.exists():
        shutil.rmtree(path, ignore_errors=True)
        log.info("Removed workspace %s", path)


def sweep_stale(tmp_root: Path, max_age_hours: float, keep: set[str] = frozenset()) -> int:
    """Delete job folders older than ``max_age_hours`` that are not in ``keep``."""
    if not tmp_root.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for child in tmp_root.iterdir():
        if child.is_dir() and child.name not in keep and child.stat().st_mtime < cutoff:
            remove(child)
            removed += 1
    return removed
