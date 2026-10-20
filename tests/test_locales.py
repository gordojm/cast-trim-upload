"""Every language file must match en.json, and every backend key must exist.

Adding a language: copy frontend/src/locales/en.json to <code>.json, translate it, and add
the code to frontend/src/i18n/languages.ts. These tests then check the new file too.
"""

import json
import re
from pathlib import Path

import pytest

from cast_trim_upload import messages
from cast_trim_upload.config import PROJECT_ROOT

LOCALES = PROJECT_ROOT / "frontend" / "src" / "locales"
LANGUAGES_TS = PROJECT_ROOT / "frontend" / "src" / "i18n" / "languages.ts"
PARAM_RE = re.compile(r"\{\{\s*(\w+)")
TAG_RE = re.compile(r"</?(\w+)>")


def _flatten(node: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in node.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _load(path: Path) -> dict[str, str]:
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


EN = _load(LOCALES / "en.json")
OTHERS = sorted(p for p in LOCALES.glob("*.json") if p.stem != "en")


def test_there_is_at_least_one_translation():
    assert OTHERS, "expected at least one locale besides en.json"


@pytest.mark.parametrize("path", OTHERS, ids=lambda p: p.stem)
def test_same_keys_as_english(path):
    other = _load(path)
    missing = sorted(EN.keys() - other.keys())
    extra = sorted(other.keys() - EN.keys())
    assert not missing and not extra, f"{path.name}: missing {missing}, extra {extra}"


@pytest.mark.parametrize("path", OTHERS, ids=lambda p: p.stem)
def test_same_params_and_tags_as_english(path):
    other = _load(path)
    problems = []
    for key, text in EN.items():
        if key not in other:
            continue
        if set(PARAM_RE.findall(text)) != set(PARAM_RE.findall(other[key])):
            problems.append(f"{key}: params {PARAM_RE.findall(text)} vs {PARAM_RE.findall(other[key])}")
        if sorted(TAG_RE.findall(text)) != sorted(TAG_RE.findall(other[key])):
            problems.append(f"{key}: tags differ")
        if not other[key].strip():
            problems.append(f"{key}: empty")
    assert not problems, f"{path.name}:\n" + "\n".join(problems)


@pytest.mark.parametrize("path", OTHERS, ids=lambda p: p.stem)
def test_language_is_registered(path):
    assert f'code: "{path.stem}"' in LANGUAGES_TS.read_text(encoding="utf-8"), (
        f"{path.name} exists but '{path.stem}' is not listed in {LANGUAGES_TS.name}"
    )


def test_every_backend_key_exists():
    missing = sorted(messages.all_keys() - EN.keys())
    assert not missing, f"keys used by the backend but missing from en.json: {missing}"


def test_backend_params_match_english_templates():
    # The English text doubles as the backend's log text; a key rendered with its params
    # must not leave any {{placeholder}} behind.
    m = messages.msg(messages.E_DURATION_MISMATCH, actual=12.0, expected=30.0)
    assert messages.english(m) == (
        "The audio is 12.0 s long, expected 30.0 s. Check that the end time is within the video."
    )
    nested = messages.msg(messages.E_UPLOAD_STEP_FAILED, step_key=messages.S_ARTWORK, detail="boom")
    assert messages.english(nested) == 'The Spotify upload failed at the "artwork" step: boom'
    assert messages.english(messages.msg(messages.RAW, text="plain")) == "plain"
