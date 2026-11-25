from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RepositoryInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_url: str = Field(min_length=1, max_length=2048)


class RepositoryInspectResponse(BaseModel):
    full_name: str
    canonical_url: HttpUrl
    html_url: HttpUrl
    description: str | None
    default_branch: str
    primary_language: str | None
    is_private: bool
    is_archived: bool
    size_kb: int
    pushed_at: datetime | None
    license_spdx_id: str | None
    next_step: str
