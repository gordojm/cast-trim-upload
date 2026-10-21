"""FastAPI app: JSON API under /api, the built frontend at /."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import messages as M
from . import tools
from .config import PROJECT_ROOT, get_settings
from .downloaders import DownloadError
from .downloaders import youtube as ytdl
from .history import History
from .imaging import image_info
from .jobs import JobError, JobManager
from .models import EpisodeMetaInput, Job, JobCreate, ProbeRequest, ProbeResult
from .sources import UnsupportedURLError, detect_source
from .spotify.uploader import SpotifyUploader, UploadError

log = logging.getLogger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
ARTWORK_MAX_BYTES = 10 * 1024 * 1024
ARTWORK_MIN_PX = 1400  # Spotify's recommended minimum for square artwork
SSE_KEEPALIVE_S = 15


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    tools.add_tools_to_path(settings)
    history = History(settings.db_path)
    uploader = SpotifyUploader(settings)
    manager = JobManager(settings, history, uploader)
    await manager.start()
    app.state.settings = settings
    app.state.history = history
    app.state.uploader = uploader
    app.state.manager = manager
    app.state.tool_status = await asyncio.to_thread(tools.tool_status, settings)
    try:
        yield
    finally:
        await manager.stop()
        history.close()


app = FastAPI(title="cast-trim-upload", lifespan=lifespan)


def _manager(request: Request) -> JobManager:
    return request.app.state.manager


def _error(status: int, key: str, **params) -> HTTPException:
    """An HTTP error whose detail the page translates: {"key": ..., "params": {...}}."""
    return HTTPException(status, M.msg(key, **params).model_dump())


def _job(request: Request, job_id: str) -> Job:
    try:
        return _manager(request).get(job_id)
    except KeyError:
        raise _error(404, M.E_JOB_NOT_FOUND) from None


@app.exception_handler(JobError)
async def _job_error(_: Request, exc: JobError):
    return JSONResponse({"detail": exc.message.model_dump()}, status_code=409)


# ---------------------------------------------------------------- status


@app.get("/api/health")
async def health(request: Request, refresh: bool = False):
    if refresh:
        request.app.state.tool_status = await asyncio.to_thread(
            tools.tool_status, request.app.state.settings)
    status = request.app.state.tool_status
    return {**status.__dict__, "ok": status.ok}


@app.post("/api/probe", response_model=ProbeResult)
async def probe(req: ProbeRequest, request: Request):
    try:
        source = detect_source(req.url)
    except UnsupportedURLError:
        raise _error(422, M.E_UNSUPPORTED_URL) from None
    ffmpeg = tools.find_ffmpeg(request.app.state.settings)
    try:
        info = await asyncio.to_thread(ytdl.probe, source.url, ffmpeg)
    except DownloadError as e:
        raise _error(502, M.E_PROBE_FAILED, detail=e.message.params.get("detail", str(e))) from None
    thumb = info.get("thumbnail")
    if thumb and "0x0" in thumb:  # Twitch thumbnail template
        thumb = thumb.replace("0x0", "640x360")
    return ProbeResult(
        kind=source.kind,
        id=source.id,
        title=info.get("title"),
        duration_s=info.get("duration"),
        thumbnail=thumb,
        uploader=info.get("uploader") or info.get("channel"),
    )


@app.get("/api/suggest")
async def suggest(request: Request):
    return request.app.state.history.suggest_next()


# ---------------------------------------------------------------- jobs


@app.get("/api/jobs", response_model=list[Job])
async def list_jobs(request: Request):
    return _manager(request).list_jobs()


@app.post("/api/jobs", response_model=Job, status_code=201)
async def create_job(req: JobCreate, request: Request, source_title: str | None = None):
    return _manager(request).create(req, source_title)


@app.get("/api/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, request: Request):
    # Finished jobs leave memory but stay readable from history.
    if job_id in _manager(request).jobs:
        return _manager(request).jobs[job_id]
    if job := request.app.state.history.get(job_id):
        return job
    raise _error(404, M.E_JOB_NOT_FOUND)


@app.put("/api/jobs/{job_id}/meta", response_model=Job)
async def update_meta(job_id: str, meta: EpisodeMetaInput, request: Request):
    _job(request, job_id)
    return _manager(request).update_meta(job_id, meta)


@app.post("/api/jobs/{job_id}/artwork", response_model=Job)
async def upload_artwork(job_id: str, request: Request, file: UploadFile = File(...)):
    _job(request, job_id)
    data = await file.read(ARTWORK_MAX_BYTES + 1)
    if len(data) > ARTWORK_MAX_BYTES:
        raise _error(422, M.V_ARTWORK_TOO_BIG, mb=ARTWORK_MAX_BYTES // (1024 * 1024))
    info = image_info(data)
    if not info:
        raise _error(422, M.V_ARTWORK_TYPE)
    ext, width, height = info
    if width != height:
        raise _error(422, M.V_ARTWORK_NOT_SQUARE, w=width, h=height)
    if width < ARTWORK_MIN_PX:
        raise _error(422, M.V_ARTWORK_TOO_SMALL, min=ARTWORK_MIN_PX)
    return _manager(request).set_artwork(job_id, data, ext)


@app.delete("/api/jobs/{job_id}/artwork", response_model=Job)
async def delete_artwork(job_id: str, request: Request):
    _job(request, job_id)
    return _manager(request).clear_artwork(job_id)


@app.get("/api/jobs/{job_id}/artwork")
async def get_artwork(job_id: str, request: Request):
    job = _job(request, job_id)
    if not job.artwork_path or not job.artwork_path.exists():
        raise _error(404, M.E_NO_ARTWORK)
    return FileResponse(job.artwork_path)


@app.get("/api/jobs/{job_id}/audio")
async def get_audio(job_id: str, request: Request):
    _job(request, job_id)
    path: Path = _manager(request).audio_file(job_id)
    return FileResponse(path, media_type="audio/mpeg", filename=f"{job_id}.mp3",
                        content_disposition_type="inline")


@app.post("/api/jobs/{job_id}/upload", response_model=Job)
async def start_upload(job_id: str, request: Request):
    _job(request, job_id)
    return _manager(request).start_upload(job_id)


@app.post("/api/jobs/{job_id}/retry", response_model=Job)
async def retry(job_id: str, request: Request):
    _job(request, job_id)
    return _manager(request).retry(job_id)


@app.delete("/api/jobs/{job_id}", response_model=Job)
async def discard(job_id: str, request: Request):
    _job(request, job_id)
    return await _manager(request).discard(job_id)


@app.delete("/api/history/{job_id}", status_code=204)
async def delete_history(job_id: str, request: Request):
    if job_id in _manager(request).jobs:
        raise _error(409, M.E_DISCARD_FIRST)
    request.app.state.history.delete(job_id)


# ---------------------------------------------------------------- spotify


def _session_payload(up: SpotifyUploader) -> dict:
    return {
        "logged_in": up.logged_in,
        "checked_at": up.checked_at.isoformat() if up.checked_at else None,
        "busy": up.busy,
    }


@app.get("/api/spotify/session")
async def spotify_session(request: Request, refresh: bool = False):
    up: SpotifyUploader = request.app.state.uploader
    if refresh and not up.busy:
        try:
            await up.check_session()
        except UploadError as e:
            raise HTTPException(502, e.message.model_dump()) from None
    return _session_payload(up)


@app.post("/api/spotify/login")
async def spotify_login(request: Request):
    up: SpotifyUploader = request.app.state.uploader
    if up.busy:
        raise _error(409, M.E_SPOTIFY_BUSY)
    try:
        await up.login()
    except UploadError as e:
        raise HTTPException(400, e.message.model_dump()) from None
    return _session_payload(up)


# ---------------------------------------------------------------- events


@app.get("/api/events")
async def events(request: Request):
    manager = _manager(request)
    queue = manager.subscribe()

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_S)
                    yield f"data: {data}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            manager.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- frontend

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
