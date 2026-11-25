from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["high", "medium", "low"]
SetupStatus = Literal["ready", "needs_review", "unsupported"]


class SetupSnapshot(BaseModel):
    """Bounded, commit-pinned repository facts supplied to setup inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    root_files: frozenset[str]
    package_json: str | None = None
    nvmrc: str | None = None
    vite_config_path: str | None = None
    vite_config: str | None = None
    unreadable_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class SetupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    value: str
    source_path: str
    confidence: Confidence
    note: str | None = None


class RepositorySetupPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SetupStatus
    profile: str | None = None
    commit_sha: str
    runtime: str | None = None
    runtime_version: str | None = None
    package_manager: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    start_command: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    health_check_path: str | None = None
    evidence: tuple[SetupEvidence, ...] = ()
    blockers: tuple[str, ...] = ()
