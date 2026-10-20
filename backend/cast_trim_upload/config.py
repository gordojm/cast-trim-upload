from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="CTU_", extra="ignore"
    )

    data_dir: Path = PROJECT_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True

    spotify_show_id: str | None = None
    spotify_headless: bool = False
    # Generous: uploading + Spotify-side processing of a 2 h MP3 can take a while.
    spotify_upload_timeout_s: int = 20 * 60
    spotify_login_timeout_s: int = 10 * 60

    ffmpeg_path: Path | None = None
    twitch_cli_path: Path | None = None

    stale_tmp_hours: int = 24

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def tools_dir(self) -> Path:
        return self.data_dir / "tools"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def browser_profile_dir(self) -> Path:
        return self.data_dir / "browser-profile"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "history.db"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.tmp_dir, self.tools_dir, self.logs_dir, self.browser_profile_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
