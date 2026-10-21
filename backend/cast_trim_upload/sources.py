"""Recognise which service a URL belongs to."""

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlparse


class SourceKind(StrEnum):
    YOUTUBE = "youtube"
    TWITCH = "twitch"


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    id: str

    @property
    def url(self) -> str:
        if self.kind is SourceKind.YOUTUBE:
            return f"https://www.youtube.com/watch?v={self.id}"
        return f"https://www.twitch.tv/videos/{self.id}"


class UnsupportedURLError(ValueError):
    pass


_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
_YT_PATH = re.compile(r"^/(?:live|shorts|embed|v)/([A-Za-z0-9_-]{11})")

_TWITCH_HOSTS = {"twitch.tv", "m.twitch.tv", "player.twitch.tv"}
_TWITCH_PATH = re.compile(r"^/(?:videos|[A-Za-z0-9_]+/v(?:ideo)?)/(\d+)")


def _host(netloc: str) -> str:
    host = netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def detect_source(url: str) -> Source:
    text = url.strip()
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    parsed = urlparse(text)
    host = _host(parsed.netloc)
    query = parse_qs(parsed.query)

    if host in _YT_HOSTS:
        if parsed.path == "/watch" and _YT_ID.match(query.get("v", [""])[0]):
            return Source(SourceKind.YOUTUBE, query["v"][0])
        if m := _YT_PATH.match(parsed.path):
            return Source(SourceKind.YOUTUBE, m.group(1))
    elif host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        if _YT_ID.match(vid):
            return Source(SourceKind.YOUTUBE, vid)
    elif host in _TWITCH_HOSTS:
        if m := _TWITCH_PATH.match(parsed.path):
            return Source(SourceKind.TWITCH, m.group(1))
        video = query.get("video", [""])[0].lstrip("v")
        if video.isdigit():
            return Source(SourceKind.TWITCH, video)

    raise UnsupportedURLError(
        "Unsupported URL. Paste a YouTube video link or a Twitch VOD link (twitch.tv/videos/…)."
    )
