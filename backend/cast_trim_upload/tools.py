"""Locate and install the external programs the pipeline needs."""

import io
import logging
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import messages as M
from .config import Settings

log = logging.getLogger(__name__)

EXE = ".exe" if sys.platform == "win32" else ""
TWITCH_RELEASES_API = "https://api.github.com/repos/lay295/TwitchDownloader/releases/latest"


class ToolMissingError(M.AppError):
    def __init__(self, tool: str) -> None:
        super().__init__(M.E_TOOL_MISSING, tool=tool)


def _first_existing(*candidates: Path | str | None) -> Path | None:
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    return None


def find_ffmpeg(settings: Settings) -> Path | None:
    return _first_existing(
        settings.ffmpeg_path,
        settings.tools_dir / f"ffmpeg{EXE}",
        shutil.which("ffmpeg"),
    )


def find_twitch_cli(settings: Settings) -> Path | None:
    return _first_existing(
        settings.twitch_cli_path,
        settings.tools_dir / f"TwitchDownloaderCLI{EXE}",
        shutil.which("TwitchDownloaderCLI"),
    )


def add_tools_to_path(settings: Settings) -> None:
    """Expose data/tools on PATH for this process.

    yt-dlp's section downloader checks for ffmpeg on PATH and ignores ``ffmpeg_location``.
    """
    dirs = [str(settings.tools_dir)]
    if settings.ffmpeg_path:
        dirs.insert(0, str(Path(settings.ffmpeg_path).parent))
    current = os.environ.get("PATH", "")
    missing = [d for d in dirs if d not in current.split(os.pathsep)]
    if missing:
        os.environ["PATH"] = os.pathsep.join([*missing, current])


def js_runtimes() -> dict[str, dict]:
    """JS runtime config for yt-dlp (YouTube needs one to solve its player challenges)."""
    for name in ("deno", "node", "bun"):
        if path := shutil.which(name):
            return {name: {"path": path}}
    return {}


def require_ffmpeg(settings: Settings) -> Path:
    if path := find_ffmpeg(settings):
        return path
    raise ToolMissingError("ffmpeg")


def require_twitch_cli(settings: Settings) -> Path:
    if path := find_twitch_cli(settings):
        return path
    raise ToolMissingError("TwitchDownloaderCLI")


def _playwright_chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


@dataclass
class ToolStatus:
    ffmpeg: str | None
    twitch_cli: str | None
    js_runtime: str | None
    chromium: bool
    yt_dlp_version: str

    @property
    def ok(self) -> bool:
        return bool(self.ffmpeg and self.twitch_cli and self.js_runtime and self.chromium)


def tool_status(settings: Settings, check_chromium: bool = True) -> ToolStatus:
    from yt_dlp.version import __version__ as ytdlp_version

    ff = find_ffmpeg(settings)
    tw = find_twitch_cli(settings)
    rt = js_runtimes()
    return ToolStatus(
        ffmpeg=str(ff) if ff else None,
        twitch_cli=str(tw) if tw else None,
        js_runtime=next(iter(rt), None),
        chromium=_playwright_chromium_installed() if check_chromium else False,
        yt_dlp_version=ytdlp_version,
    )


# ---------------------------------------------------------------- installation


def _twitch_asset_suffix() -> str:
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "win32":
        return "Windows-x64.zip"
    if sys.platform == "darwin":
        return "MacOSArm64.zip" if arm else "MacOS-x64.zip"
    return "LinuxArm64.zip" if arm else "Linux-x64.zip"


def install_twitch_cli(settings: Settings, force: bool = False) -> Path:
    target = settings.tools_dir / f"TwitchDownloaderCLI{EXE}"
    if target.exists() and not force:
        return target
    settings.tools_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True, timeout=120) as client:
        release = client.get(TWITCH_RELEASES_API).raise_for_status().json()
        suffix = _twitch_asset_suffix()
        asset = next(
            a for a in release["assets"]
            if a["name"].startswith("TwitchDownloaderCLI") and a["name"].endswith(suffix)
        )
        log.info("Downloading %s", asset["name"])
        data = client.get(asset["browser_download_url"]).raise_for_status().content

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        member = next(n for n in zf.namelist() if Path(n).name == target.name)
        target.write_bytes(zf.read(member))
    target.chmod(0o755)
    return target


def install_ffmpeg(settings: Settings) -> Path:
    """Use ffmpeg from PATH if present, otherwise let TwitchDownloaderCLI fetch a build."""
    if path := find_ffmpeg(settings):
        return path
    cli = require_twitch_cli(settings)
    log.info("Downloading ffmpeg via TwitchDownloaderCLI")
    subprocess.run([str(cli), "ffmpeg", "--download", "--banner", "false"],
                   cwd=settings.tools_dir, check=True)
    return require_ffmpeg(settings)


def install_chromium() -> None:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def update_yt_dlp() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"], check=True)


def setup(settings: Settings, update: bool = False) -> ToolStatus:
    settings.ensure_dirs()
    install_twitch_cli(settings, force=update)
    install_ffmpeg(settings)
    install_chromium()
    if update:
        update_yt_dlp()
    return tool_status(settings)
