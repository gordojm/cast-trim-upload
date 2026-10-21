"""Twitch VODs via TwitchDownloaderCLI (audio-only .m4a, trimmed at download time)."""

import logging
import re
import subprocess
from pathlib import Path
from threading import Event

from .. import messages as M
from ..models import Message
from . import DownloadCancelled, DownloadError, ProgressFn

log = logging.getLogger(__name__)

# Output looks like "[STATUS] - Downloading 42% [2/4]", rewritten in place with \r.
_STATUS_RE = re.compile(r"\[STATUS\] - ([^\[\r\n%]*?)\s*(\d{1,3})%")


def build_command(
    cli: Path, vod_id: str, start: float, end: float, out: Path, ffmpeg: Path, temp: Path
) -> list[str]:
    return [
        str(cli), "videodownload",
        "--id", vod_id,
        "-b", f"{round(start * 1000)}ms",
        "-e", f"{round(end * 1000)}ms",
        "-o", str(out),
        "--trim-mode", "Exact",
        "--ffmpeg-path", str(ffmpeg),
        "--temp-path", str(temp),
        "--collision", "Overwrite",
        "--banner", "false",
    ]


_LABEL_KEYS = {
    "downloading": M.P_TWITCH_DOWNLOADING,
    "verifying parts": M.P_TWITCH_VERIFYING,
    "finalizing video": M.P_TWITCH_FINALIZING,
}


def status_message(label: str) -> Message:
    """Map a TwitchDownloaderCLI status label to a translatable message."""
    if key := _LABEL_KEYS.get(label.strip().lower()):
        return M.msg(key)
    return M.msg(M.P_TWITCH_OTHER, detail=label)


def parse_status(chunk: str) -> tuple[str, float] | None:
    """Return the last (label, fraction) found in a chunk of CLI output."""
    matches = _STATUS_RE.findall(chunk)
    if not matches:
        return None
    label, pct = matches[-1]
    return label.strip(" -") or "Downloading", int(pct) / 100


def download_section(
    cli: Path,
    vod_id: str,
    start: float,
    end: float,
    out_dir: Path,
    ffmpeg: Path,
    progress: ProgressFn | None = None,
    cancel: Event | None = None,
) -> Path:
    out = out_dir / "source.m4a"
    temp = out_dir / "twitch-cache"
    temp.mkdir(exist_ok=True)
    cmd = build_command(cli, vod_id, start, end, out, ffmpeg, temp)
    log.info("Running %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.stdout is not None
    tail = ""
    while True:
        raw = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
        if not raw:
            break
        chunk = raw.decode("utf-8", errors="replace")
        tail = (tail + chunk)[-4000:]
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise DownloadCancelled()
        if progress and (status := parse_status(chunk)):
            label, frac = status
            progress(frac, status_message(label))

    if proc.wait() != 0 or not out.exists():
        lines = [ln for ln in re.split(r"[\r\n]+", tail) if ln.strip()]
        errors = [ln for ln in lines if "[ERROR]" in ln or "Exception" in ln]
        raise DownloadError(M.E_TWITCH_FAILED, detail=" | ".join((errors or lines)[-3:]))
    return out
