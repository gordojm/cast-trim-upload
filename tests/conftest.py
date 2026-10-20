import pytest

from cast_trim_upload import tools
from cast_trim_upload.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path / "data", _env_file=None)
    s.ensure_dirs()
    return s


@pytest.fixture(scope="session")
def ffmpeg():
    real = Settings(_env_file=None)
    tools.add_tools_to_path(real)
    path = tools.find_ffmpeg(real)
    if not path:
        pytest.skip("ffmpeg not installed (run: cast-trim-upload setup)")
    return path
