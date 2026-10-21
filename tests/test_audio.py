import subprocess

import pytest

from cast_trim_upload import audio
from cast_trim_upload import messages as M


@pytest.fixture
def tone(tmp_path, ffmpeg):
    """A 20 s stereo test tone as WAV."""
    path = tmp_path / "tone.wav"
    subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=20:sample_rate=48000",
         "-ac", "2", str(path)],
        check=True,
    )
    return path


def test_convert_full(tmp_path, ffmpeg, tone):
    seen = []
    info = audio.to_mp3(ffmpeg, tone, tmp_path / "out.mp3", 20.0,
                        progress=lambda p, m: seen.append(p))
    assert info.duration_s == pytest.approx(20.0, abs=0.1)
    assert info.bitrate_kbps in (319, 320)
    assert info.cbr
    assert seen and seen[-1] == pytest.approx(1.0, abs=0.05)


def test_convert_trimmed(tmp_path, ffmpeg, tone):
    info = audio.to_mp3(ffmpeg, tone, tmp_path / "cut.mp3", 7.5, trim=(5.0, 12.5))
    assert info.duration_s == pytest.approx(7.5, abs=0.1)


def test_duration_mismatch_detected(tmp_path, ffmpeg, tone):
    # Asking for 15..40 of a 20 s file only yields 5 s.
    with pytest.raises(audio.AudioError) as err:
        audio.to_mp3(ffmpeg, tone, tmp_path / "short.mp3", 25.0, trim=(15.0, 40.0))
    assert err.value.message.key == M.E_DURATION_MISMATCH
    assert err.value.message.params == {"actual": pytest.approx(5.0, abs=0.1), "expected": 25.0}
    assert "expected 25.0 s" in str(err.value)  # English text for the logs


def test_ffmpeg_error(tmp_path, ffmpeg):
    bad = tmp_path / "not-audio.wav"
    bad.write_text("nope")
    with pytest.raises(audio.AudioError, match="ffmpeg failed") as err:
        audio.to_mp3(ffmpeg, bad, tmp_path / "x.mp3", 1.0)
    assert err.value.message.key == M.E_FFMPEG_FAILED and err.value.message.params["detail"]


def test_command_has_trim_before_input(tmp_path):
    cmd = audio.build_mp3_command("ffmpeg", tmp_path / "in.m4a", tmp_path / "o.mp3", trim=(10, 70))
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-t") + 1] == "60.000"
    assert cmd[cmd.index("-b:a") + 1] == "320k"
