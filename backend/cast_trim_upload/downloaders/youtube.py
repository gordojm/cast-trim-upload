"""YouTube (and metadata probing for any source) via the yt-dlp library.

yt-dlp resolves the direct audio stream URL; ffmpeg then seeks into it and encodes only
[start, end] to MP3. This fetches just the section and cuts sample-accurately (yt-dlp's own
section download stream-copies, which snaps to packet boundaries).
"""

import logging
from pathlib import Path
from threading import Event

import yt_dlp

from .. import audio
from .. import messages as M
from ..tools import js_runtimes
from . import DownloadCancelled, DownloadError, ProgressFn, check_cancel

log = logging.getLogger(__name__)

_DIRECT_PROTOCOLS = {"http", "https"}


class _Logger:
    def debug(self, msg: str) -> None:
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


def _base_opts(ffmpeg: Path | None) -> dict:
    opts: dict = {
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": _Logger(),
        "js_runtimes": js_runtimes(),
    }
    if ffmpeg:
        opts["ffmpeg_location"] = str(ffmpeg)
    return opts


def _failed(e: Exception) -> DownloadError:
    return DownloadError(M.E_DOWNLOAD_FAILED, detail=str(e).removeprefix("ERROR: "))


def probe(url: str, ffmpeg: Path | None = None) -> dict:
    """Return yt-dlp metadata (title, duration, thumbnail…) without downloading."""
    try:
        with yt_dlp.YoutubeDL(_base_opts(ffmpeg) | {"skip_download": True}) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise _failed(e) from e


def _resolve_audio_format(url: str, ffmpeg: Path) -> dict:
    opts = _base_opts(ffmpeg) | {"format": "bestaudio/best", "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise _failed(e) from e
    fmt = (info.get("requested_formats") or [info])[0]
    if not fmt.get("url"):
        raise DownloadError(M.E_NO_AUDIO_STREAM)
    return fmt


def _ffmpeg_header_args(headers: dict[str, str]) -> list[str]:
    if not headers:
        return []
    blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    return ["-headers", blob]


def _download_full(url: str, out_dir: Path, ffmpeg: Path, progress, cancel) -> Path:
    def hook(d: dict) -> None:
        check_cancel(cancel)
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            progress(done / total if total else None,
                     M.msg(M.P_DOWNLOADING_MB, mb=round(done / 1_048_576, 1)))

    opts = _base_opts(ffmpeg) | {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "progress_hooks": [hook],
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadCancelled:
        raise
    except yt_dlp.utils.DownloadError as e:
        if isinstance(e.exc_info[1] if e.exc_info else None, DownloadCancelled):
            raise DownloadCancelled() from e
        raise _failed(e) from e
    downloads = info.get("requested_downloads") or []
    if not downloads or not Path(downloads[0]["filepath"]).exists():
        raise DownloadError(M.E_NO_FILE)
    return Path(downloads[0]["filepath"])


def fetch_mp3(
    url: str,
    start: float,
    end: float,
    dst: Path,
    ffmpeg: Path,
    progress: ProgressFn | None = None,
    cancel: Event | None = None,
) -> audio.AudioInfo:
    """Write [start, end] of the video's audio to ``dst`` as MP3 320 kbps."""
    duration = end - start
    if progress:
        progress(None, M.msg(M.P_RESOLVING_STREAM))
    fmt = _resolve_audio_format(url, ffmpeg)
    check_cancel(cancel)

    if fmt.get("protocol") in _DIRECT_PROTOCOLS:
        try:
            return audio.to_mp3(
                ffmpeg, fmt["url"], dst, duration,
                trim=(start, end),
                input_args=_ffmpeg_header_args(fmt.get("http_headers") or {}),
                progress=progress, cancel=cancel,
                label=M.msg(M.P_DOWNLOADING_SECTION),
            )
        except audio.AudioCancelled as e:
            raise DownloadCancelled() from e
        except audio.AudioError as e:
            # A clip that came out short means the end time is past the video; a full
            # download would end the same way, so report it directly.
            if e.message.key == M.E_DURATION_MISMATCH:
                raise
            log.warning("Direct section encode failed (%s); falling back to full download", e)

    # Fallback (segmented streams, or the direct read failed): full audio, then cut locally.
    if progress:
        progress(None, M.msg(M.P_DOWNLOADING_FULL))
    src = _download_full(url, dst.parent, ffmpeg, progress, cancel)
    try:
        return audio.to_mp3(ffmpeg, src, dst, duration, trim=(start, end),
                            progress=progress, cancel=cancel)
    except audio.AudioCancelled as e:
        raise DownloadCancelled() from e
    finally:
        src.unlink(missing_ok=True)
