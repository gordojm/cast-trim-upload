import os
import struct
import time
import zlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cast_trim_upload import messages as M
from cast_trim_upload import workspace
from cast_trim_upload.downloaders.twitch import build_command, parse_status, status_message
from cast_trim_upload.history import History
from cast_trim_upload.imaging import image_info
from cast_trim_upload.models import EpisodeMeta, Job, JobCreate, JobStatus, PublishMode
from cast_trim_upload.sources import SourceKind


def _meta(**kw):
    return {"title": "T", "description": "D", "explicit": False, **kw}


def test_job_create_validates_range_and_url():
    JobCreate(url="https://youtu.be/jNQXAC9IVRw", start="0:10", end="0:20", meta=_meta())
    with pytest.raises(ValidationError, match="end must be after start"):
        JobCreate(url="https://youtu.be/jNQXAC9IVRw", start="0:20", end="0:10", meta=_meta())
    with pytest.raises(ValidationError, match="Unsupported URL"):
        JobCreate(url="https://vimeo.com/1", start="0", end="1", meta=_meta())
    with pytest.raises(ValidationError, match="Invalid time"):
        JobCreate(url="https://youtu.be/jNQXAC9IVRw", start="x", end="1", meta=_meta())


def test_schedule_rules():
    future = datetime.now(UTC) + timedelta(days=1)
    past = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(ValidationError, match="publish_at is required"):
        EpisodeMeta(**_meta(publish_mode="schedule"))
    with pytest.raises(ValidationError, match="must be in the future"):
        JobCreate(url="https://youtu.be/jNQXAC9IVRw", start="0", end="1",
                  meta=_meta(publish_mode="schedule", publish_at=past.isoformat()))
    # Stored meta may hold a past date (e.g. restored from history) without failing.
    stored = EpisodeMeta(**_meta(publish_mode="schedule", publish_at=past))
    assert stored.schedule_in_past()
    assert not EpisodeMeta(**_meta(publish_mode="schedule", publish_at=future)).schedule_in_past()
    # publish_at is dropped when not scheduling
    assert EpisodeMeta(**_meta(publish_mode="now", publish_at=future)).publish_at is None


def test_blank_title_rejected():
    with pytest.raises(ValidationError):
        EpisodeMeta(**_meta(title="   "))


def test_twitch_command_and_progress(tmp_path):
    cmd = build_command("cli", "123", 1800.25, 1830.5, tmp_path / "o.m4a", "ffmpeg", tmp_path)
    assert cmd[cmd.index("-b") + 1] == "1800250ms"
    assert cmd[cmd.index("-e") + 1] == "1830500ms"
    assert cmd[cmd.index("--collision") + 1] == "Overwrite"
    chunk = "[STATUS] - Downloading 10% [1/4]\r[STATUS] - Downloading 42% [1/4]\r"
    assert parse_status(chunk) == ("Downloading", 0.42)
    assert parse_status("[STATUS] - Finalizing Video 97%") == ("Finalizing Video", 0.97)
    assert parse_status("[INFO] nothing here") is None
    assert status_message("Verifying Parts").key == M.P_TWITCH_VERIFYING
    assert status_message("Something New") == M.msg(M.P_TWITCH_OTHER, detail="Something New")


def test_legacy_plain_text_messages_load():
    # History rows from before messages became keys hold plain English strings.
    now = datetime.now(UTC)
    job = Job.model_validate({
        "id": "old", "created_at": now, "updated_at": now, "url": "u", "source_kind": "youtube",
        "source_id": "x", "start_s": 0, "end_s": 1, "meta": _meta(),
        "status": "failed", "error": "ffmpeg failed: boom", "message": "Ready: 1.0s, 320 kbps",
    })
    assert job.error == M.msg(M.RAW, text="ffmpeg failed: boom")
    assert job.message.params["text"] == "Ready: 1.0s, 320 kbps"


def _png(w, h):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def test_image_info():
    assert image_info(_png(1400, 1400)) == (".png", 1400, 1400)
    jpeg = (b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00"
            + b"\xff\xc0" + struct.pack(">HBHH", 11, 8, 900, 1600) + b"\x03\x00\x00\x00")
    assert image_info(jpeg) == (".jpg", 1600, 900)
    assert image_info(b"GIF89a....") is None


def test_workspace_sweep(tmp_path):
    old = workspace.create(tmp_path, "old")
    kept = workspace.create(tmp_path, "kept")
    fresh = workspace.create(tmp_path, "fresh")
    stale = time.time() - 48 * 3600
    for d in (old, kept):
        os.utime(d, (stale, stale))
    assert workspace.sweep_stale(tmp_path, 24, keep={"kept"}) == 1
    assert not old.exists() and kept.exists() and fresh.exists()


def _job(job_id, status, episode=None, created=None):
    now = created or datetime.now(UTC)
    return Job(id=job_id, created_at=now, updated_at=now, url="u", source_kind=SourceKind.YOUTUBE,
               source_id="x", start_s=0, end_s=1, status=status,
               meta=EpisodeMeta(**_meta(season=2, episode=episode)))


def test_history_roundtrip_and_suggest(tmp_path):
    h = History(tmp_path / "h.db")
    assert h.suggest_next() == {"season": None, "episode": None}
    base = datetime.now(UTC)
    h.save(_job("a", JobStatus.DONE, episode=7, created=base))
    h.save(_job("b", JobStatus.DONE, episode=8, created=base + timedelta(seconds=1)))
    pending = _job("c", JobStatus.READY, episode=9, created=base + timedelta(seconds=2))
    pending.audio_path = tmp_path / "c.mp3"
    h.save(pending)
    assert h.suggest_next() == {"season": 2, "episode": 9}
    assert h.get("b").meta.episode == 8 and h.get("missing") is None
    [restored] = h.unfinished()
    assert restored.id == "c" and restored.audio_path == tmp_path / "c.mp3"
    assert [j.id for j in h.list()] == ["c", "b", "a"]
    h.delete("a")
    assert [j.id for j in h.list()] == ["c", "b"]
    h.close()


def test_publish_mode_values():
    assert {m.value for m in PublishMode} == {"draft", "now", "schedule"}
