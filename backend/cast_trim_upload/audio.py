"""ffmpeg conversion to MP3 320 kbps CBR, with optional trimming."""

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from mutagen.mp3 import MP3, BitrateMode

from . import messages as M
from .models import Message

ProgressFn = Callable[[float | None, Message], None]

MP3_BITRATE = "320k"
DURATION_TOLERANCE_S = 1.5

_OUT_TIME_RE = re.compile(r"^out_time_us=(\d+)$")


class AudioError(M.AppError):
    pass


class AudioCancelled(AudioError):
    def __init__(self) -> None:
        super().__init__(M.E_CANCELLED)


@dataclass
class AudioInfo:
    duration_s: float
    bitrate_kbps: int
    cbr: bool


def build_mp3_command(
    ffmpeg: Path,
    src: Path | str,
    dst: Path,
    trim: tuple[float, float] | None = None,
    input_args: Sequence[str] = (),
) -> list[str]:
    cmd = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *input_args]
    if trim:
        start, end = trim
        # Input seeking (-ss before -i) is sample-accurate when transcoding audio, and on
        # HTTP sources it uses range requests, so only the needed part is fetched.
        cmd += ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"]
    cmd += [
        "-i", str(src),
        "-vn", "-sn", "-dn",
        "-map_metadata", "-1",
        "-c:a", "libmp3lame", "-b:a", MP3_BITRATE, "-ar", "44100",
        "-progress", "pipe:1", "-nostats",
        str(dst),
    ]
    return cmd


def to_mp3(
    ffmpeg: Path,
    src: Path | str,
    dst: Path,
    expected_duration_s: float,
    trim: tuple[float, float] | None = None,
    input_args: Sequence[str] = (),
    progress: ProgressFn | None = None,
    cancel: Event | None = None,
    label: Message | None = None,
) -> AudioInfo:
    label = label or M.msg(M.P_CONVERTING)
    cmd = build_mp3_command(ffmpeg, src, dst, trim, input_args)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise AudioCancelled()
        if progress and (m := _OUT_TIME_RE.match(line.strip())):
            done = int(m.group(1)) / 1_000_000
            progress(min(done / expected_duration_s, 1.0), label)
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise AudioError(M.E_FFMPEG_FAILED, detail=stderr.strip()[-800:])

    info = inspect_mp3(dst)
    if abs(info.duration_s - expected_duration_s) > DURATION_TOLERANCE_S:
        raise AudioError(M.E_DURATION_MISMATCH, actual=round(info.duration_s, 1),
                         expected=round(expected_duration_s, 1))
    return info


def inspect_mp3(path: Path) -> AudioInfo:
    info = MP3(path).info
    return AudioInfo(
        duration_s=info.length,
        bitrate_kbps=info.bitrate // 1000,
        cbr=info.bitrate_mode in (BitrateMode.CBR, BitrateMode.UNKNOWN),
    )
