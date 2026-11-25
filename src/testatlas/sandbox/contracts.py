from __future__ import annotations

import ipaddress
import re
from pathlib import PurePosixPath
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from testatlas.domain.setup import RepositorySetupPlan

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_ALLOWED_EGRESS_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid")
MAX_SINGLE_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_RUN_DURATION_MS = 30 * 60 * 1000


class SandboxLimits(BaseModel):
    """Per-run ceilings to be enforced by the backend outside untrusted processes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cpu_millis: int = Field(default=1000, ge=250, le=4000)
    memory_mib: int = Field(default=2048, ge=256, le=8192)
    pids_limit: int = Field(default=128, ge=16, le=512)
    wall_time_seconds: int = Field(default=600, ge=30, le=1800)
    workspace_bytes: int = Field(default=1024**3, ge=64 * 1024**2, le=4 * 1024**3)
    network_bytes: int = Field(default=0, ge=0, le=5 * 1024**3)
    network_connections: int = Field(default=0, ge=0, le=10_000)
    open_files_limit: int = Field(default=1024, ge=64, le=8192)
    log_bytes: int = Field(default=5 * 1024**2, ge=1024, le=20 * 1024**2)
    total_artifact_bytes: int = Field(
        default=MAX_TOTAL_ARTIFACT_BYTES,
        ge=1024,
        le=MAX_TOTAL_ARTIFACT_BYTES,
    )


class SandboxSecurityPolicy(BaseModel):
    """Required backend controls; literals make requests for weaker settings invalid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    image_ref: str = Field(pattern=r"^[a-z0-9.-]+(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$")
    platform: Literal["linux/amd64", "linux/arm64"]
    seccomp_profile_digest: str = Field(pattern=_SHA256_PATTERN.pattern)
    mandatory_lsm_profile_digest: str = Field(pattern=_SHA256_PATTERN.pattern)
    run_uid: int = Field(ge=10_000, le=2**31 - 1)
    read_only_rootfs: Literal[True] = True
    no_new_privileges: Literal[True] = True
    drop_all_capabilities: Literal[True] = True
    privileged: Literal[False] = False
    host_network: Literal[False] = False
    host_pid: Literal[False] = False
    host_ipc: Literal[False] = False
    docker_socket_mounted: Literal[False] = False
    host_mounts_allowed: Literal[False] = False
    devices_allowed: Literal[False] = False
    private_user_namespace: Literal[True] = True
    private_pid_namespace: Literal[True] = True
    private_ipc_namespace: Literal[True] = True
    private_network_namespace: Literal[True] = True
    ephemeral_workspace: Literal[True] = True
    tmpfs_for_temp_files: Literal[True] = True
    platform_secrets_available: Literal[False] = False
    checkout_credentials_available: Literal[False] = False
    network_egress: Literal["deny_all", "enforcing_proxy"] = "deny_all"
    egress_domains: tuple[str, ...] = ()

    @field_validator("egress_domains")
    @classmethod
    def validate_egress_domains(cls, domains: tuple[str, ...]) -> tuple[str, ...]:
        if len(domains) > 32 or len(set(domains)) != len(domains):
            raise ValueError("Egress domains must be unique and limited to 32 entries.")
        for domain in domains:
            if len(domain) > 253 or "*" in domain or domain.endswith(_ALLOWED_EGRESS_SUFFIXES):
                raise ValueError("Egress entries must be exact public DNS hostnames.")
            try:
                ipaddress.ip_address(domain)
            except ValueError:
                pass
            else:
                raise ValueError("IP literals are not valid egress allowlist entries.")
            labels = domain.rstrip(".").split(".")
            if len(labels) < 2 or any(not _HOST_LABEL_PATTERN.fullmatch(label) for label in labels):
                raise ValueError("Egress entries must be exact public DNS hostnames.")
        return domains

    @model_validator(mode="after")
    def validate_network_policy(self) -> SandboxSecurityPolicy:
        if self.network_egress == "deny_all" and self.egress_domains:
            raise ValueError("A deny-all network policy cannot include egress domains.")
        if self.network_egress == "enforcing_proxy" and not self.egress_domains:
            raise ValueError("Proxy egress requires an explicit allowlist.")
        return self


class SandboxStep(BaseModel):
    """One supported, non-shell step derived from the initial npm/Vite profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["install", "build", "start"]
    argv: tuple[str, ...] = Field(min_length=2, max_length=3)
    working_directory: Literal["/workspace"] = "/workspace"
    provenance: Literal[
        "package-lock.json",
        "npm-shrinkwrap.json",
        "package.json#scripts.build",
        "package.json#scripts.start",
    ]

    @model_validator(mode="after")
    def validate_supported_step(self) -> SandboxStep:
        expected = {
            "install": (("npm", "ci"), ("package-lock.json", "npm-shrinkwrap.json")),
            "build": (("npm", "run", "build"), ("package.json#scripts.build",)),
            "start": (("npm", "run", "start"), ("package.json#scripts.start",)),
        }
        expected_argv, expected_sources = expected[self.name]
        if self.argv != expected_argv or self.provenance not in expected_sources:
            raise ValueError("Step argv or provenance is not allowed for this profile.")
        return self


class SandboxRunRequest(BaseModel):
    """Immutable input for a future trusted sandbox adapter; it contains no credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["1"] = "1"
    run_id: UUID
    repository: str = Field(pattern=_REPOSITORY_PATTERN.pattern)
    commit_sha: str = Field(pattern=_COMMIT_PATTERN.pattern)
    runtime: Literal["node"]
    runtime_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    profile: Literal["node-npm-vite"]
    port: int = Field(ge=1, le=65535)
    health_check_path: Literal["/"]
    steps: tuple[SandboxStep, ...] = Field(min_length=2, max_length=3)
    limits: SandboxLimits
    security: SandboxSecurityPolicy

    @model_validator(mode="after")
    def validate_run_plan(self) -> SandboxRunRequest:
        names = tuple(step.name for step in self.steps)
        if names not in (("install", "start"), ("install", "build", "start")):
            raise ValueError("Steps must be install, optional build, then start.")
        if self.security.network_egress == "deny_all":
            if self.limits.network_bytes or self.limits.network_connections:
                raise ValueError("Deny-all execution cannot request network budgets.")
        elif self.limits.network_bytes < 1024 or self.limits.network_connections < 1:
            raise ValueError("Proxy egress requires bounded byte and connection budgets.")
        return self


def build_sandbox_run_request(
    *,
    run_id: UUID,
    repository: str,
    setup_plan: RepositorySetupPlan,
    limits: SandboxLimits,
    security: SandboxSecurityPolicy,
) -> SandboxRunRequest:
    """Create a strict initial-profile request; reject anything needing a caller override."""
    if setup_plan.status != "ready" or setup_plan.profile != "node-npm-vite":
        raise ValueError("Only a ready initial-profile setup plan may enter runner planning.")
    if setup_plan.commit_sha != setup_plan.commit_sha.lower() or not _COMMIT_PATTERN.fullmatch(
        setup_plan.commit_sha
    ):
        raise ValueError("The setup plan must be bound to a full lowercase commit SHA.")
    if (
        setup_plan.runtime != "node"
        or setup_plan.runtime_version is None
        or not re.fullmatch(r"\d+\.\d+\.\d+", setup_plan.runtime_version)
        or setup_plan.package_manager != "npm"
        or setup_plan.install_command != "npm ci"
        or setup_plan.start_command != "npm run start"
        or setup_plan.port is None
        or setup_plan.health_check_path != "/"
    ):
        raise ValueError("The setup plan does not match the supported execution contract.")
    if setup_plan.build_command not in (None, "npm run build"):
        raise ValueError("The setup plan contains an unsupported build command.")

    install_file = next(
        (
            item.source_path
            for item in setup_plan.evidence
            if item.field == "package_manager"
            and item.value == "npm"
            and item.source_path in {"package-lock.json", "npm-shrinkwrap.json"}
        ),
        None,
    )
    if install_file is None:
        raise ValueError("The setup plan lacks evidence for an npm lockfile.")
    evidence = setup_plan.evidence
    if not any(
        item.field == "runtime_version"
        and item.value == setup_plan.runtime_version
        and item.source_path in {".nvmrc", "package.json#volta.node"}
        and item.confidence == "high"
        for item in evidence
    ):
        raise ValueError("The setup plan lacks evidence for its exact runtime version.")
    if not any(
        item.field == "start_command"
        and item.value == "npm run start"
        and item.source_path == "package.json#scripts.start"
        and item.confidence == "high"
        for item in evidence
    ):
        raise ValueError("The setup plan lacks evidence for its start script.")
    vite_config_sources = {
        item.source_path
        for item in evidence
        if item.field == "framework"
        and item.value == "Vite"
        and re.fullmatch(r"vite\.config\.(?:[cm]?[jt]s)", item.source_path)
        and item.confidence == "high"
    }
    if not vite_config_sources or not any(
        item.field == "port"
        and item.value == str(setup_plan.port)
        and item.source_path in vite_config_sources
        and item.confidence == "high"
        for item in evidence
    ):
        raise ValueError("The setup plan lacks Vite configuration evidence for its port.")
    if setup_plan.build_command is not None and not any(
        item.field == "build_command"
        and item.value == "npm run build"
        and item.source_path == "package.json#scripts.build"
        and item.confidence == "high"
        for item in evidence
    ):
        raise ValueError("The setup plan lacks evidence for its build script.")

    steps = [
        SandboxStep(
            name="install",
            argv=("npm", "ci"),
            provenance=install_file,
        )
    ]
    if setup_plan.build_command is not None:
        steps.append(
            SandboxStep(
                name="build",
                argv=("npm", "run", "build"),
                provenance="package.json#scripts.build",
            )
        )
    steps.append(
        SandboxStep(
            name="start",
            argv=("npm", "run", "start"),
            provenance="package.json#scripts.start",
        )
    )

    return SandboxRunRequest(
        run_id=run_id,
        repository=repository,
        commit_sha=setup_plan.commit_sha,
        runtime=setup_plan.runtime,
        runtime_version=setup_plan.runtime_version,
        profile="node-npm-vite",
        port=setup_plan.port,
        health_check_path=setup_plan.health_check_path,
        steps=tuple(steps),
        limits=limits,
        security=security,
    )


class EvidenceArtifact(BaseModel):
    """Bounded metadata for an artifact staged by an untrusted sandbox."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal[
        "application/json",
        "application/xml",
        "application/zip",
        "image/png",
        "text/plain",
    ]
    size_bytes: int = Field(ge=1, le=MAX_SINGLE_ARTIFACT_BYTES)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if "\\" in value or ":" in value or "\x00" in value:
            raise ValueError("Artifact paths must use safe relative POSIX paths.")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or str(path) != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("Artifact paths must use normalized relative POSIX paths.")
        return value


class SandboxRunResult(BaseModel):
    """Typed, size-bounded terminal result from a future sandbox adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    commit_sha: str = Field(pattern=_COMMIT_PATTERN.pattern)
    status: Literal["succeeded", "failed", "blocked", "cancelled", "timed_out"]
    duration_ms: int = Field(ge=0, le=MAX_RUN_DURATION_MS)
    exit_code: int | None = Field(default=None, ge=0, le=255)
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    artifacts: tuple[EvidenceArtifact, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_result(self) -> SandboxRunResult:
        total = sum(artifact.size_bytes for artifact in self.artifacts)
        if total > MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("Aggregate evidence exceeds the result size limit.")
        if self.status == "succeeded" and self.exit_code != 0:
            raise ValueError("A successful run must report exit code zero.")
        if self.status == "failed" and self.exit_code == 0:
            raise ValueError("A failed run cannot report exit code zero.")
        return self


def validate_result_for_request(
    request: SandboxRunRequest,
    result: SandboxRunResult,
) -> SandboxRunResult:
    """Bind untrusted backend output to the exact run and commit that were requested."""
    if request.run_id != result.run_id:
        raise ValueError("Sandbox result run ID does not match the request.")
    if request.commit_sha != result.commit_sha:
        raise ValueError("Sandbox result commit does not match the request.")
    if result.duration_ms > request.limits.wall_time_seconds * 1000:
        raise ValueError("Sandbox result exceeds the requested wall-clock limit.")
    if (
        sum(artifact.size_bytes for artifact in result.artifacts)
        > request.limits.total_artifact_bytes
    ):
        raise ValueError("Sandbox result exceeds the requested artifact budget.")
    return result


class SandboxRunner(Protocol):
    """Backend port only; an adapter must not be enabled until separately reviewed."""

    async def execute(self, request: SandboxRunRequest) -> SandboxRunResult: ...

    async def cancel(self, run_id: UUID) -> bool: ...


class SandboxExecutionDisabled(RuntimeError):
    """Raised while no reviewed isolated execution backend is configured."""


class DisabledSandboxRunner:
    """Fail-closed placeholder. It never starts a process or falls back to local execution."""

    async def execute(self, request: SandboxRunRequest) -> SandboxRunResult:
        del request
        raise SandboxExecutionDisabled(
            "Repository execution is disabled until a reviewed isolated backend is configured."
        )

    async def cancel(self, run_id: UUID) -> bool:
        del run_id
        return False
