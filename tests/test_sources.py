import pytest

from cast_trim_upload.sources import SourceKind, UnsupportedURLError, detect_source


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/watch?v=jNQXAC9IVRw&t=42s",
        "https://m.youtube.com/watch?feature=share&v=jNQXAC9IVRw",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw?si=abc&t=10",
        "https://www.youtube.com/live/jNQXAC9IVRw?feature=shared",
        "https://www.youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "youtube.com/watch?v=jNQXAC9IVRw",
    ],
)
def test_youtube(url):
    src = detect_source(url)
    assert src.kind is SourceKind.YOUTUBE
    assert src.id == "jNQXAC9IVRw"
    assert src.url == "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.twitch.tv/videos/2902385151",
        "https://twitch.tv/videos/2902385151?t=1h2m3s",
        "https://m.twitch.tv/videos/2902385151",
        "https://www.twitch.tv/somechannel/v/2902385151",
        "https://player.twitch.tv/?video=v2902385151&parent=example.com",
        "twitch.tv/videos/2902385151",
    ],
)
def test_twitch(url):
    src = detect_source(url)
    assert src.kind is SourceKind.TWITCH
    assert src.id == "2902385151"
    assert src.url == "https://www.twitch.tv/videos/2902385151"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://vimeo.com/123",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/@channel",
        "https://www.twitch.tv/somechannel",
        "https://clips.twitch.tv/SomeClip",
        "https://evil.com/videos/123?youtube.com",
    ],
)
def test_unsupported(url):
    with pytest.raises(UnsupportedURLError):
        detect_source(url)
