"""Keys for every message the backend shows in the app.

The backend never sends sentences: it sends ``{"key": ..., "params": {...}}`` and the page
translates the key with frontend/src/locales/<lang>.json. tests/test_locales.py checks that
every key below exists in every locale file.

Conventions:
- ``detail`` params carry raw text from external tools (ffmpeg, yt-dlp…), shown as-is.
- Params whose name ends in ``_key`` hold another message key; it is translated first.
"""

import json
import re
from functools import lru_cache

from .config import PROJECT_ROOT
from .models import Message

LOCALES_DIR = PROJECT_ROOT / "frontend" / "src" / "locales"

# Raw text that has no translation (unexpected exceptions, legacy history rows)
RAW = "server.raw"

# ---- progress
P_STARTING_DOWNLOAD = "server.progress.starting_download"
P_RESOLVING_STREAM = "server.progress.resolving_stream"
P_DOWNLOADING_SECTION = "server.progress.downloading_section"
P_DOWNLOADING_FULL = "server.progress.downloading_full"
P_DOWNLOADING_MB = "server.progress.downloading_mb"
P_CONVERTING = "server.progress.converting"
P_TWITCH_DOWNLOADING = "server.progress.twitch_downloading"
P_TWITCH_VERIFYING = "server.progress.twitch_verifying"
P_TWITCH_FINALIZING = "server.progress.twitch_finalizing"
P_TWITCH_OTHER = "server.progress.twitch_other"
P_READY = "server.progress.ready"
P_DISCARDED = "server.progress.discarded"
P_WAITING_UPLOAD = "server.progress.waiting_upload"
P_OPENING_SPOTIFY = "server.progress.opening_spotify"
P_LOGIN_REQUIRED = "server.progress.login_required"
P_LOGGED_IN = "server.progress.logged_in"
P_OPENING_WIZARD = "server.progress.opening_wizard"
P_UPLOADING_AUDIO = "server.progress.uploading_audio"
P_FILLING_DETAILS = "server.progress.filling_details"
P_UPLOADING_ARTWORK = "server.progress.uploading_artwork"
P_FILLING_NUMBERS = "server.progress.filling_numbers"
P_CONTENT_CHECKS = "server.progress.content_checks"
P_GOING_TO_REVIEW = "server.progress.going_to_review"
P_SAVING_DRAFT = "server.progress.saving_draft"
P_PUBLISHING = "server.progress.publishing"
P_SCHEDULING = "server.progress.scheduling"
P_WAITING_SAVE = "server.progress.waiting_save"
P_UPLOADED_DRAFT = "server.progress.uploaded_draft"
P_UPLOADED_NOW = "server.progress.uploaded_now"
P_UPLOADED_SCHEDULE = "server.progress.uploaded_schedule"

# ---- Spotify wizard steps (named in upload errors)
S_OPEN_WIZARD = "server.step.open_wizard"
S_PREPARE_PAGE = "server.step.prepare_page"
S_UPLOAD_AUDIO = "server.step.upload_audio"
S_TITLE = "server.step.title"
S_DESCRIPTION = "server.step.description"
S_ARTWORK = "server.step.artwork"
S_NUMBERS = "server.step.season_episode"
S_CONTENT_CHECKS = "server.step.content_checks"
S_NEXT = "server.step.next"
S_SAVE_DRAFT = "server.step.save_draft"
S_PUBLISH = "server.step.publish"
S_SCHEDULE = "server.step.schedule"
S_CONFIRM = "server.step.confirm"

# ---- errors
E_INTERRUPTED = "server.error.interrupted"
E_CANCELLED = "server.error.cancelled"
E_CANNOT_EDIT_DETAILS = "server.error.cannot_edit_details"
E_CANNOT_EDIT_ARTWORK = "server.error.cannot_edit_artwork"
E_AUDIO_NOT_READY = "server.error.audio_not_ready"
E_AUDIO_UNAVAILABLE = "server.error.audio_unavailable"
E_NO_ARTWORK = "server.error.no_artwork"
E_SCHEDULE_IN_PAST = "server.error.schedule_in_past"
E_ONLY_FAILED_RETRY = "server.error.only_failed_retry"
E_CANNOT_DISCARD_UPLOADED = "server.error.cannot_discard_uploaded"
E_WAIT_FOR_UPLOAD = "server.error.wait_for_upload"
E_JOB_NOT_FOUND = "server.error.job_not_found"
E_DISCARD_FIRST = "server.error.discard_first"
E_TOOL_MISSING = "server.error.tool_missing"
E_DOWNLOAD_FAILED = "server.error.download_failed"
E_NO_AUDIO_STREAM = "server.error.no_audio_stream"
E_NO_FILE = "server.error.no_file"
E_TWITCH_FAILED = "server.error.twitch_failed"
E_FFMPEG_FAILED = "server.error.ffmpeg_failed"
E_DURATION_MISMATCH = "server.error.duration_mismatch"
E_PROBE_FAILED = "server.error.probe_failed"
E_UNSUPPORTED_URL = "server.error.unsupported_url"
E_SPOTIFY_BUSY = "server.error.spotify_busy"
E_SPOTIFY_NOT_LOADED = "server.error.spotify_not_loaded"
E_LOGIN_WINDOW_CLOSED = "server.error.login_window_closed"
E_LOGIN_TIMEOUT = "server.error.login_timeout"
E_UPLOAD_STEP_FAILED = "server.error.upload_step_failed"
E_UPLOAD_STEP_FAILED_SHOT = "server.error.upload_step_failed_screenshot"
E_FIELD_MISSING = "server.error.field_missing"
E_CALENDAR_DAY_MISSING = "server.error.calendar_day_missing"
E_WIZARD_STUCK = "server.error.wizard_stuck"
F_SEASON = "server.field.season"
F_EPISODE = "server.field.episode"

# ---- artwork checks (shared with the page's own validation)
V_ARTWORK_TYPE = "validation.artwork_type"
V_ARTWORK_TOO_BIG = "validation.artwork_too_big"
V_ARTWORK_NOT_SQUARE = "validation.artwork_not_square"
V_ARTWORK_TOO_SMALL = "validation.artwork_too_small"


def msg(key: str, **params: str | int | float | None) -> Message:
    return Message(key=key, params=params)


def all_keys() -> set[str]:
    return {v for k, v in globals().items() if k.isupper() and isinstance(v, str) and "." in v}


# ---------------------------------------------------------------- English for logs


@lru_cache
def _english() -> dict[str, str]:
    try:
        data = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    flat: dict[str, str] = {}

    def walk(node: dict, prefix: str) -> None:
        for k, v in node.items():
            if isinstance(v, dict):
                walk(v, f"{prefix}{k}.")
            else:
                flat[f"{prefix}{k}"] = v

    walk(data, "")
    return flat


def english(m: Message) -> str:
    """Render a message in English, for terminal logs and exception text."""
    if m.key == RAW:
        return str(m.params.get("text", ""))
    template = _english().get(m.key)
    if template is None:
        return f"{m.key} {m.params}" if m.params else m.key
    params = {
        k: english(Message(key=str(v))) if k.endswith("_key") and v else v
        for k, v in m.params.items()
    }
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda g: str(params.get(g.group(1), "")), template)


class AppError(RuntimeError):
    """An error the app can show translated. ``str()`` is English, for logs."""

    def __init__(self, key: str, **params: str | int | float | None):
        self.message = msg(key, **params)
        super().__init__(english(self.message))


def to_message(e: BaseException) -> Message:
    if isinstance(e, AppError):
        return e.message
    return msg(RAW, text=str(e) or type(e).__name__)
