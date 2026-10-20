import asyncio
import shutil

import pytest

from cast_trim_upload import jobs as jobs_mod
from cast_trim_upload import messages as M
from cast_trim_upload.audio import AudioInfo
from cast_trim_upload.history import History
from cast_trim_upload.jobs import JobError, JobManager
from cast_trim_upload.models import JobCreate, JobStatus


class FakeUploader:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = []

    async def upload(self, job, report, cancel):
        self.calls.append(job.id)
        report(None, M.msg(M.P_UPLOADING_AUDIO))
        if self.fail:
            raise RuntimeError("boom")
        return "https://creators.spotify.com/pod/show/x/episode/e1"


def _req(**meta):
    return JobCreate(url="https://youtu.be/jNQXAC9IVRw", start="0:05", end="0:15",
                     meta={"title": "Ep", "description": "Desc", "explicit": False, **meta})


@pytest.fixture
def fake_download(monkeypatch, ffmpeg):
    def fetch_mp3(url, start, end, dst, ffmpeg_path, progress=None, cancel=None):
        progress(0.5, M.msg(M.P_DOWNLOADING_SECTION))
        dst.write_bytes(b"ID3fake")
        return AudioInfo(duration_s=end - start, bitrate_kbps=320, cbr=True)

    monkeypatch.setattr(jobs_mod.youtube, "fetch_mp3", fetch_mp3)


async def _wait_for(job, *statuses, timeout=5.0):
    async with asyncio.timeout(timeout):
        while job.status not in statuses:
            await asyncio.sleep(0.01)


async def _manager(settings, uploader):
    m = JobManager(settings, History(settings.db_path), uploader)
    await m.start()
    return m


async def test_full_flow_cleans_up(settings, fake_download):
    up = FakeUploader()
    m = await _manager(settings, up)
    events = m.subscribe()

    job = m.create(_req())
    await _wait_for(job, JobStatus.READY)
    assert job.audio_ready and job.audio_duration_s == 10
    workdir = job.workdir

    m.start_upload(job.id)
    await _wait_for(job, JobStatus.DONE)
    assert up.calls == [job.id]
    assert job.spotify_url.endswith("/episode/e1")
    assert job.message.key == M.P_UPLOADED_DRAFT
    assert not workdir.exists(), "temp folder must be removed after upload"
    assert job.id not in m.jobs
    assert m.history.suggest_next() == {"season": None, "episode": None}

    seen = set()
    while not events.empty():
        seen.add(__import__("json").loads(events.get_nowait())["job"]["status"])
    assert {"downloading", "ready_for_review", "uploading", "done"} <= seen
    await m.stop()


async def test_failed_upload_keeps_audio_for_retry(settings, fake_download):
    up = FakeUploader(fail=True)
    m = await _manager(settings, up)
    job = m.create(_req(episode=3))
    await _wait_for(job, JobStatus.READY)
    m.start_upload(job.id)
    await _wait_for(job, JobStatus.FAILED)
    assert job.error.key == M.RAW and job.error.params["text"] == "boom" and job.audio_ready

    up.fail = False
    m.retry(job.id)
    await _wait_for(job, JobStatus.DONE)
    assert len(up.calls) == 2
    assert m.history.suggest_next()["episode"] == 4
    await m.stop()


async def test_discard_removes_workspace(settings, fake_download):
    m = await _manager(settings, FakeUploader())
    job = m.create(_req())
    await _wait_for(job, JobStatus.READY)
    await m.discard(job.id)
    assert job.status is JobStatus.CANCELLED
    assert not job.workdir.exists()
    with pytest.raises(KeyError):
        m.get(job.id)
    await m.stop()


async def test_download_failure_and_state_guards(settings, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("video unavailable")

    monkeypatch.setattr(jobs_mod.youtube, "fetch_mp3", broken)
    monkeypatch.setattr(jobs_mod.tools, "require_ffmpeg", lambda s: "ffmpeg")
    m = await _manager(settings, FakeUploader())
    job = m.create(_req())
    await _wait_for(job, JobStatus.FAILED)
    assert "video unavailable" in job.error.params["text"]
    with pytest.raises(JobError):
        m.start_upload(job.id)
    await m.stop()


async def test_restart_restores_ready_jobs(settings, fake_download):
    m = await _manager(settings, FakeUploader())
    ready = m.create(_req())
    await _wait_for(ready, JobStatus.READY)
    await m.stop()

    # Simulate a crash mid-download for a second job.
    interrupted = ready.model_copy(update={"id": "crashed", "status": JobStatus.DOWNLOADING,
                                           "audio_path": None})
    m.history.save(interrupted)

    m2 = await _manager(settings, FakeUploader())
    assert m2.get(ready.id).status is JobStatus.READY
    assert m2.get("crashed").status is JobStatus.FAILED
    assert m2.get("crashed").error.key == M.E_INTERRUPTED
    await m2.stop()
    shutil.rmtree(settings.tmp_dir, ignore_errors=True)
