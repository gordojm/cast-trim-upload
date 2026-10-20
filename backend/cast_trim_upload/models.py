from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from .sources import SourceKind, detect_source
from .timeparse import parse_time

# Spotify for Creators form limits. Verified against the live form; keep in sync with
# frontend/src/lib/schema.ts.
TITLE_MAX = 200
DESCRIPTION_MAX = 4000


class PublishMode(StrEnum):
    DRAFT = "draft"
    NOW = "now"
    SCHEDULE = "schedule"


class EpisodeType(StrEnum):
    FULL = "full"
    TRAILER = "trailer"
    BONUS = "bonus"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    READY = "ready_for_review"
    LOGIN_REQUIRED = "login_required"
    UPLOADING = "uploading"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {JobStatus.DONE, JobStatus.CANCELLED}
ACTIVE_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.DOWNLOADING,
    JobStatus.CONVERTING,
    JobStatus.LOGIN_REQUIRED,
    JobStatus.UPLOADING,
}


class Message(BaseModel):
    """A translatable message: the page looks ``key`` up in its locale files."""

    key: str
    params: dict[str, str | int | float | None] = Field(default_factory=dict)


class EpisodeMeta(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    season: int | None = Field(default=None, ge=1)
    episode: int | None = Field(default=None, ge=1)
    episode_type: EpisodeType = EpisodeType.FULL
    explicit: bool
    sponsored: bool = False
    publish_mode: PublishMode = PublishMode.DRAFT
    publish_at: datetime | None = None

    @field_validator("title", "description")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def _check_schedule(self) -> "EpisodeMeta":
        if self.publish_mode is PublishMode.SCHEDULE:
            if self.publish_at is None:
                raise ValueError("publish_at is required when scheduling")
            if self.publish_at.tzinfo is None:
                self.publish_at = self.publish_at.replace(tzinfo=UTC)
        else:
            self.publish_at = None
        return self

    def schedule_in_past(self) -> bool:
        return self.publish_mode is PublishMode.SCHEDULE and self.publish_at <= datetime.now(UTC)


class EpisodeMetaInput(EpisodeMeta):
    """Meta coming from the UI: a scheduled date must still be in the future."""

    @model_validator(mode="after")
    def _future(self) -> "EpisodeMetaInput":
        if self.schedule_in_past():
            raise ValueError("publish_at must be in the future")
        return self


class JobCreate(BaseModel):
    url: str
    start: str
    end: str
    meta: EpisodeMetaInput

    @field_validator("url")
    @classmethod
    def _valid_url(cls, v: str) -> str:
        detect_source(v)
        return v.strip()

    @model_validator(mode="after")
    def _check_range(self) -> "JobCreate":
        if parse_time(self.end) <= parse_time(self.start):
            raise ValueError("end must be after start")
        return self


class Job(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    url: str
    source_kind: SourceKind
    source_id: str
    source_title: str | None = None
    start_s: float
    end_s: float
    meta: EpisodeMeta
    status: JobStatus = JobStatus.QUEUED
    progress: float | None = None  # 0..1, None = indeterminate
    message: Message | None = None
    error: Message | None = None
    has_artwork: bool = False
    audio_duration_s: float | None = None
    spotify_url: str | None = None

    # Internal, not sent to the UI
    workdir: Path | None = Field(default=None, exclude=True)
    audio_path: Path | None = Field(default=None, exclude=True)
    artwork_path: Path | None = Field(default=None, exclude=True)

    @field_validator("message", "error", mode="before")
    @classmethod
    def _legacy_text(cls, v):
        # History rows written before messages became keys hold plain English text.
        if isinstance(v, str):
            return {"key": "server.raw", "params": {"text": v}}
        return v

    @computed_field
    @property
    def audio_ready(self) -> bool:
        return self.audio_path is not None and self.audio_path.exists()


class ProbeRequest(BaseModel):
    url: str


class ProbeResult(BaseModel):
    kind: SourceKind
    id: str
    title: str | None = None
    duration_s: float | None = None
    thumbnail: str | None = None
    uploader: str | None = None
