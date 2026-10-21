"""Real downloads. Run with: pytest -m network"""

import pytest

from cast_trim_upload import audio, tools
from cast_trim_upload.config import Settings
from cast_trim_upload.downloaders import twitch, youtube

pytestmark = pytest.mark.network


def test_youtube_section(tmp_path, ffmpeg):
    out = tmp_path / "yt.mp3"
    info = youtube.fetch_mp3("https://www.youtube.com/watch?v=aqz-KE-bpKQ", 300, 330, out, ffmpeg)
    assert info.duration_s == pytest.approx(30, abs=0.2)
    assert info.bitrate_kbps in (319, 320)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["yt.mp3"]


def test_youtube_end_past_video_reports_duration(tmp_path, ffmpeg):
    # 10:00-11:00 of a 10:35 video: the clip comes out short, which must be reported as
    # such instead of falling back to a full download.
    from cast_trim_upload import messages as M

    with pytest.raises(audio.AudioError) as err:
        youtube.fetch_mp3("https://www.youtube.com/watch?v=aqz-KE-bpKQ", 600, 660, tmp_path / "x.mp3", ffmpeg)
    assert err.value.message.key == M.E_DURATION_MISMATCH
    assert err.value.message.params["expected"] == 60.0


def test_twitch_section(tmp_path, ffmpeg):
    cli = tools.find_twitch_cli(Settings(_env_file=None))
    if not cli:
        pytest.skip("TwitchDownloaderCLI not installed")
    # A recent VOD from the official Twitch channel; VODs expire, so pick a fresh one.
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "playlistend": 5}) as ydl:
        listing = ydl.extract_info("https://www.twitch.tv/twitch/videos?filter=archives&sort=time",
                                   download=False)
    vod = next(e for e in listing["entries"] if (e.get("duration") or 0) > 120)
    vod_id = str(vod["id"]).lstrip("v")
    m4a = twitch.download_section(cli, vod_id, 60, 90, tmp_path, ffmpeg)
    info = audio.to_mp3(ffmpeg, m4a, tmp_path / "tw.mp3", 30)
    assert info.duration_s == pytest.approx(30, abs=0.2)
