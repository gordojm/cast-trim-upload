"""Parse and format episode timestamps.

Accepted inputs: ``hh:mm:ss[.fff]``, ``mm:ss[.fff]`` or plain seconds (``5400``, ``12.5``).
"""

import re

_NUMBER = r"\d+(?:\.\d+)?"
_CLOCK_RE = re.compile(rf"^(?:(\d+):)?(\d{{1,2}}):({_NUMBER})$")
_SECONDS_RE = re.compile(rf"^{_NUMBER}$")


class TimeFormatError(ValueError):
    pass


def parse_time(value: str) -> float:
    text = value.strip()
    if _SECONDS_RE.match(text):
        return float(text)

    m = _CLOCK_RE.match(text)
    if not m:
        raise TimeFormatError(f"Invalid time '{value}'. Use hh:mm:ss, mm:ss or seconds.")
    hours = int(m.group(1)) if m.group(1) is not None else 0
    minutes = int(m.group(2))
    seconds = float(m.group(3))
    if seconds >= 60 or (m.group(1) is not None and minutes >= 60):
        raise TimeFormatError(f"Invalid time '{value}': minutes and seconds must be below 60.")
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds: float) -> str:
    """Format as ``h:mm:ss`` (with ``.fff`` only when there is a fractional part)."""
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    base = f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{base}.{ms:03d}" if ms else base
