"""Public API models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerateMusicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=10_000)
    wait: bool = Field(
        default=False,
        description="Wait until Flow Music finishes instead of returning a pending job.",
    )
    wait_timeout_s: Optional[float] = Field(
        default=None,
        ge=10,
        le=3600,
        description="Maximum wait time. Defaults to FLOWMUSIC_POLL_TIMEOUT.",
    )


class Clip(BaseModel):
    id: str
    download_url: str
    wav_download_url: str
    duration_s: Optional[float] = None


class MusicJobResponse(BaseModel):
    id: str
    status: str
    project_id: Optional[str] = None
    clips: Optional[list[Clip]] = None
    progress: Optional[float] = None
    error: Optional[Any] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
