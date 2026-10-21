import pytest

from cast_trim_upload.timeparse import TimeFormatError, format_time, parse_time


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0", 0),
        ("90", 90),
        ("12.5", 12.5),
        ("1:30", 90),
        ("01:30", 90),
        ("1:02:03", 3723),
        ("10:00:00.250", 36000.25),
        (" 0:00:05 ", 5),
        ("100:00:00", 360000),
    ],
)
def test_parse(text, seconds):
    assert parse_time(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "abc", "1:60", "1:60:00", "1::00", "-5", "1:2:3:4", "1:00:60"])
def test_parse_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_time(text)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0, "0:00:00"), (90, "0:01:30"), (3723, "1:02:03"), (36000.25, "10:00:00.250")],
)
def test_format(seconds, text):
    assert format_time(seconds) == text
    assert parse_time(format_time(seconds)) == pytest.approx(seconds)
