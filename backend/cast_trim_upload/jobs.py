"""Job runner: download → convert → review → upload, with live progress events."""

import asyncio
import json
import logging
import shutil
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from . import audio, tools, workspace
from . import messages as M
from .config import Settings
from .downloaders import DownloadCancelled, twitch, youtube
from .history import History
from .models import ACTIVE_STATUSES, EpisodeMeta, Job, JobCreate, JobStatus, Message, PublishMode
from .sources import SourceKind, detect_source
from .timeparse import parse_time

log = logging.getLogger(__name__)

PROGRESS_EVENT_INTERVAL_S = 0.25


class StatusReporter(Protocol):
    def __call__(self, status: JobStatus | None, message: Message, progress: float | None = None) -> None: ...


class Uploader(Protocol):
    async def upload(self, job: Job, report: StatusReporter, cancel: threading.Event) -> str | None: ...


class JobError(M.AppError):
    """A request that is invalid for the job's current state (maps to HTTP 409)."""


_UPLOADED = {
    PublishMode.DRAFT: M.P_UPLOADED_DRAFT,
    PublishMode.NOW: M.P_UPLOADED_NOW,
    PublishMode.SCHEDULE: M.P_UPLOADED_SCHEDULE,
}


def _now() -> datetime:
    return datetime.now(UTC)


class JobManager:
    def __init__(self, settings: Settings, history: History, uploader: Uploader):
        self.settings = settings
        self.history = history
        self.uploader = uploader
        self.jobs: dict[str, Job] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._upload_lock = asyncio.Lock()
        self._last_emit: dict[str, float] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        keep: set[str] = set()
        for job in self.history.unfinished():
            if job.status in ACTIVE_STATUSES:
                job.status = JobStatus.READY if job.audio_ready else JobStatus.FAILED
                job.progress = None
                job.message = None
                if job.status is JobStatus.FAILED:
                    job.error = M.msg(M.E_INTERRUPTED)
                self.history.save(job)
            self.jobs[job.id] = job
            keep.add(job.id)
        removed = workspace.sweep_stale(self.settings.tmp_dir, self.settings.stale_tmp_hours, keep)
        if removed:
            log.info("Removed %d stale workspace(s)", removed)

    async def stop(self) -> None:
        for event in self._cancel.values():
            event.set()
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    # ------------------------------------------------------------ events

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, payload: dict) -> None:
        data = json.dumps(payload, default=str)
        for q in list(self._subscribers):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                self._subscribers.discard(q)

    def _emit(self, job: Job, persist: bool = True) -> None:
        job.updated_at = _now()
        if persist:
            self.history.save(job)
        self._broadcast({"type": "job", "job": job.model_dump(mode="json")})

    def _set(self, job: Job, *, persist: bool = False, **fields) -> None:
        status_changed = "status" in fields and fields["status"] != job.status
        for key, value in fields.items():
            setattr(job, key, value)
        self._emit(job, persist=persist or status_changed or "error" in fields)

    def _progress_cb(self, job: Job):
        """Thread-safe progress callback, throttled to a few events per second."""
        assert self._loop is not None

        def apply(p: float | None, message: Message) -> None:
            job.progress, job.message = p, message
            now = time.monotonic()
            if now - self._last_emit.get(job.id, 0) >= PROGRESS_EVENT_INTERVAL_S:
                self._last_emit[job.id] = now
                self._emit(job, persist=False)

        return lambda p, m: self._loop.call_soon_threadsafe(apply, p, m)

    def _reporter(self, job: Job) -> StatusReporter:
        """Status callback for the uploader; safe to call from its worker thread."""
        assert self._loop is not None

        def apply(status: JobStatus | None, message: Message, progress: float | None) -> None:
            fields = {"message": message, "progress": progress}
            if status is not None:
                fields["status"] = status
            self._set(job, **fields)

        def report(status: JobStatus | None, message: Message, progress: float | None = None) -> None:
            self._loop.call_soon_threadsafe(apply, status, message, progress)

        return report

    # ------------------------------------------------------------ public API

    def get(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]

    def list_jobs(self) -> list[Job]:
        """In-memory jobs plus finished ones from history, newest first."""
        merged = {j.id: j for j in self.history.list()}
        merged.update(self.jobs)
        return sorted(merged.values(), key=lambda j: j.created_at, reverse=True)

    def create(self, req: JobCreate, source_title: str | None = None) -> Job:
        source = detect_source(req.url)
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            created_at=_now(),
            updated_at=_now(),
            url=source.url,
            source_kind=source.kind,
            source_id=source.id,
            source_title=source_title,
            start_s=parse_time(req.start),
            end_s=parse_time(req.end),
            meta=EpisodeMeta.model_validate(req.meta.model_dump()),
            workdir=workspace.create(self.settings.tmp_dir, job_id),
        )
        self.jobs[job_id] = job
        self._emit(job)
        self._spawn(job, self._run_pipeline(job))
        return job

    def update_meta(self, job_id: str, meta: EpisodeMeta) -> Job:
        job = self.get(job_id)
        if job.status in (JobStatus.UPLOADING, JobStatus.LOGIN_REQUIRED, JobStatus.DONE):
            raise JobError(M.E_CANNOT_EDIT_DETAILS)
        self._set(job, persist=True, meta=EpisodeMeta.model_validate(meta.model_dump()))
        return job

    def set_artwork(self, job_id: str, data: bytes, ext: str) -> Job:
        job = self.get(job_id)
        if job.status in (JobStatus.UPLOADING, JobStatus.LOGIN_REQUIRED, JobStatus.DONE):
            raise JobError(M.E_CANNOT_EDIT_ARTWORK)
        if job.artwork_path:
            job.artwork_path.unlink(missing_ok=True)
        path = job.workdir / f"artwork{ext}"
        path.write_bytes(data)
        self._set(job, persist=True, artwork_path=path, has_artwork=True)
        return job

    def clear_artwork(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.artwork_path:
            job.artwork_path.unlink(missing_ok=True)
        self._set(job, persist=True, artwork_path=None, has_artwork=False)
        return job

    def start_upload(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in (JobStatus.READY, JobStatus.FAILED) or not job.audio_ready:
            raise JobError(M.E_AUDIO_NOT_READY)
        if job.meta.schedule_in_past():
            raise JobError(M.E_SCHEDULE_IN_PAST)
        self._spawn(job, self._run_upload(job))
        return job

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status is not JobStatus.FAILED:
            raise JobError(M.E_ONLY_FAILED_RETRY)
        if job.audio_ready:
            return self.start_upload(job_id)
        job.workdir = workspace.create(self.settings.tmp_dir, job.id)
        self._set(job, status=JobStatus.QUEUED, error=None, progress=None, message=None)
        self._spawn(job, self._run_pipeline(job))
        return job

    async def discard(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status is JobStatus.DONE:
            raise JobError(M.E_CANNOT_DISCARD_UPLOADED)
        if job.status in (JobStatus.UPLOADING, JobStatus.LOGIN_REQUIRED):
            # The browser runs in a worker thread that can't be interrupted mid-step.
            raise JobError(M.E_WAIT_FOR_UPLOAD)
        if event := self._cancel.get(job_id):
            event.set()
        if task := self._tasks.get(job_id):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        workspace.remove(job.workdir)
        self._set(job, status=JobStatus.CANCELLED, progress=None, message=M.msg(M.P_DISCARDED),
                  audio_path=None, artwork_path=None)
        self.jobs.pop(job_id, None)
        return job

    # ------------------------------------------------------------ work

    def _spawn(self, job: Job, coro) -> None:
        self._cancel[job.id] = threading.Event()
        task = asyncio.create_task(coro, name=f"job-{job.id}")
        self._tasks[job.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.id, None))

    async def _run_pipeline(self, job: Job) -> None:
        cancel = self._cancel[job.id]
        progress = self._progress_cb(job)
        duration = job.end_s - job.start_s
        dst = job.workdir / "episode.mp3"
        try:
            ffmpeg = tools.require_ffmpeg(self.settings)
            self._set(job, status=JobStatus.DOWNLOADING, progress=None,
                      message=M.msg(M.P_STARTING_DOWNLOAD), error=None)
            if job.source_kind is SourceKind.YOUTUBE:
                info = await asyncio.to_thread(
                    youtube.fetch_mp3, job.url, job.start_s, job.end_s, dst, ffmpeg, progress, cancel)
            else:
                cli = tools.require_twitch_cli(self.settings)
                m4a = await asyncio.to_thread(
                    twitch.download_section, cli, job.source_id, job.start_s, job.end_s,
                    job.workdir, ffmpeg, progress, cancel)
                self._set(job, status=JobStatus.CONVERTING, progress=0.0,
                          message=M.msg(M.P_CONVERTING))
                info = await asyncio.to_thread(
                    audio.to_mp3, ffmpeg, m4a, dst, duration, None, (), progress, cancel)
                m4a.unlink(missing_ok=True)
                shutil.rmtree(job.workdir / "twitch-cache", ignore_errors=True)

            await asyncio.sleep(0)  # let queued progress callbacks run before the final state
            self._set(job, status=JobStatus.READY, progress=1.0, audio_path=dst,
                      audio_duration_s=info.duration_s,
                      message=M.msg(M.P_READY, seconds=round(info.duration_s, 1),
                                    kbps=info.bitrate_kbps))
        except (DownloadCancelled, audio.AudioCancelled, asyncio.CancelledError):
            log.info("Job %s cancelled", job.id)
        except Exception as e:
            log.exception("Job %s failed", job.id)
            self._set(job, status=JobStatus.FAILED, error=M.to_message(e), progress=None, message=None)

    async def _run_upload(self, job: Job) -> None:
        report = self._reporter(job)
        try:
            if self._upload_lock.locked():
                report(JobStatus.UPLOADING, M.msg(M.P_WAITING_UPLOAD))
            async with self._upload_lock:
                self._set(job, status=JobStatus.UPLOADING, error=None, progress=None,
                          message=M.msg(M.P_OPENING_SPOTIFY))
                url = await self.uploader.upload(job, report, self._cancel[job.id])
            await asyncio.sleep(0)  # flush status reports queued by the uploader thread
            workspace.remove(job.workdir)
            self._set(job, status=JobStatus.DONE, progress=1.0, spotify_url=url,
                      audio_path=None, artwork_path=None,
                      message=M.msg(_UPLOADED[job.meta.publish_mode]))
            self.jobs.pop(job.id, None)
        except asyncio.CancelledError:
            log.info("Upload of %s cancelled", job.id)
        except Exception as e:
            log.exception("Upload of %s failed", job.id)
            self._set(job, status=JobStatus.FAILED, error=M.to_message(e), progress=None, message=None)

    def audio_file(self, job_id: str) -> Path:
        job = self.get(job_id)
        if not job.audio_ready:
            raise JobError(M.E_AUDIO_UNAVAILABLE)
        return job.audio_path
