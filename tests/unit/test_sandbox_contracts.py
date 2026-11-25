from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from testatlas.domain.setup import RepositorySetupPlan, SetupEvidence
from testatlas.sandbox.contracts import (
    DisabledSandboxRunner,
    EvidenceArtifact,
    SandboxExecutionDisabled,
    SandboxLimits,
    SandboxRunResult,
    SandboxSecurityPolicy,
    SandboxStep,
    build_sandbox_run_request,
    validate_result_for_request,
)

COMMIT_SHA = "a" * 40


def ready_plan(**overrides: object) -> RepositorySetupPlan:
    values: dict[str, object] = {
        "status": "ready",
        "profile": "node-npm-vite",
        "commit_sha": COMMIT_SHA,
        "runtime": "node",
        "runtime_version": "24.9.0",
        "package_manager": "npm",
        "install_command": "npm ci",
        "build_command": "npm run build",
        "start_command": "npm run start",
        "port": 3000,
        "health_check_path": "/",
        "evidence": (
            SetupEvidence(
                field="package_manager",
                value="npm",
                source_path="package-lock.json",
                confidence="high",
            ),
            SetupEvidence(
                field="runtime_version",
                value="24.9.0",
                source_path=".nvmrc",
                confidence="high",
            ),
            SetupEvidence(
                field="start_command",
                value="npm run start",
                source_path="package.json#scripts.start",
                confidence="high",
            ),
            SetupEvidence(
                field="build_command",
                value="npm run build",
                source_path="package.json#scripts.build",
                confidence="high",
            ),
            SetupEvidence(
                field="framework",
                value="Vite",
                source_path="vite.config.js",
                confidence="high",
            ),
            SetupEvidence(
                field="port",
                value="3000",
                source_path="vite.config.js",
                confidence="high",
            ),
        ),
    }
    values.update(overrides)
    return RepositorySetupPlan(**values)


def policy(**overrides: object) -> SandboxSecurityPolicy:
    values: dict[str, object] = {
        "image_ref": "ghcr.io/testatlas/node-runner@sha256:" + "a" * 64,
        "platform": "linux/amd64",
        "seccomp_profile_digest": "sha256:" + "b" * 64,
        "mandatory_lsm_profile_digest": "sha256:" + "d" * 64,
        "run_uid": 10001,
    }
    values.update(overrides)
    return SandboxSecurityPolicy(**values)


def build_request(**overrides: object):
    values: dict[str, object] = {
        "run_id": uuid4(),
        "repository": "saucelabs/sample-app-web",
        "setup_plan": ready_plan(),
        "limits": SandboxLimits(),
        "security": policy(),
    }
    values.update(overrides)
    return build_sandbox_run_request(**values)


def test_builds_immutable_argv_plan_with_exact_commit_and_profile() -> None:
    request = build_request()

    assert request.commit_sha == COMMIT_SHA
    assert request.runtime_version == "24.9.0"
    assert request.port == 3000
    assert request.health_check_path == "/"
    assert [(step.name, step.argv) for step in request.steps] == [
        ("install", ("npm", "ci")),
        ("build", ("npm", "run", "build")),
        ("start", ("npm", "run", "start")),
    ]
    assert request.steps[0].provenance == "package-lock.json"


def test_builds_plan_without_optional_build_step() -> None:
    request = build_request(setup_plan=ready_plan(build_command=None))

    assert tuple(step.name for step in request.steps) == ("install", "start")


def test_run_request_rejects_invalid_step_order() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    payload["steps"] = [payload["steps"][0], payload["steps"][0]]

    with pytest.raises(ValidationError, match="Steps must be install"):
        request.__class__.model_validate(payload)


def test_runner_request_has_no_secret_or_mutable_ref_fields() -> None:
    request = build_request()

    with pytest.raises(ValidationError):
        request.__class__.model_validate(
            {**request.model_dump(mode="json"), "github_token": "secret"}
        )

    with pytest.raises(ValidationError):
        request.__class__.model_validate({**request.model_dump(mode="json"), "branch": "main"})


def test_rejects_weakened_container_policy_and_invalid_egress() -> None:
    with pytest.raises(ValidationError):
        policy(image_ref="ghcr.io/testatlas/node-runner:latest")
    with pytest.raises(ValidationError, match="Deny-all execution"):
        build_request(limits=SandboxLimits(network_bytes=1024, network_connections=1))

    for weakened in (
        {"privileged": True},
        {"host_network": True},
        {"host_pid": True},
        {"docker_socket_mounted": True},
        {"devices_allowed": True},
        {"platform_secrets_available": True},
        {"checkout_credentials_available": True},
    ):
        with pytest.raises(ValidationError):
            policy(**weakened)

    with pytest.raises(ValidationError):
        policy(network_egress="enforcing_proxy")
    with pytest.raises(ValidationError):
        build_request(
            security=policy(
                network_egress="enforcing_proxy",
                egress_domains=("registry.npmjs.org",),
            )
        )
    with pytest.raises(ValidationError):
        policy(network_egress="deny_all", egress_domains=("registry.npmjs.org",))
    with pytest.raises(ValidationError):
        policy(network_egress="enforcing_proxy", egress_domains=("*.npmjs.org",))
    with pytest.raises(ValidationError):
        policy(network_egress="enforcing_proxy", egress_domains=("169.254.169.254",))
    with pytest.raises(ValidationError):
        policy(network_egress="enforcing_proxy", egress_domains=("metadata.internal",))
    with pytest.raises(ValidationError):
        policy(
            network_egress="enforcing_proxy",
            egress_domains=("registry.npmjs.org", "registry.npmjs.org"),
        )
    with pytest.raises(ValidationError):
        policy(network_egress="enforcing_proxy", egress_domains=("bad_name.example",))


def test_allows_only_explicit_public_hostnames_for_proxy_egress() -> None:
    configured = policy(
        network_egress="enforcing_proxy",
        egress_domains=("registry.npmjs.org",),
    )
    request = build_request(
        security=configured,
        limits=SandboxLimits(network_bytes=100_000_000, network_connections=100),
    )

    assert request.security.egress_domains == ("registry.npmjs.org",)
    assert request.limits.network_connections == 100


def test_rejects_unready_or_unsupported_setup_plans() -> None:
    with pytest.raises(ValueError, match="Only a ready"):
        build_request(setup_plan=ready_plan(status="needs_review"))
    with pytest.raises(ValueError, match="does not match"):
        build_request(setup_plan=ready_plan(start_command="sh -c 'npm run start'"))
    with pytest.raises(ValueError, match="lacks evidence"):
        build_request(setup_plan=ready_plan(evidence=()))
    with pytest.raises(ValidationError):
        build_request(repository="https://github.com/saucelabs/sample-app-web")
    with pytest.raises(ValueError, match="full lowercase commit SHA"):
        build_request(setup_plan=ready_plan(commit_sha="A" * 40))
    with pytest.raises(ValueError, match="unsupported build command"):
        build_request(setup_plan=ready_plan(build_command="bash build.sh"))


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("runtime_version", "exact runtime version"),
        ("start_command", "start script"),
        ("framework", "Vite configuration evidence"),
        ("build_command", "build script"),
    ],
)
def test_runner_plan_requires_evidence_for_each_executable_step(
    field: str,
    message: str,
) -> None:
    plan = ready_plan()
    evidence = tuple(item for item in plan.evidence if item.field != field)

    with pytest.raises(ValueError, match=message):
        build_request(setup_plan=plan.model_copy(update={"evidence": evidence}))


def test_step_schema_rejects_shell_syntax_or_unapproved_argv() -> None:
    with pytest.raises(ValidationError):
        SandboxStep(
            name="start",
            argv=("sh", "-c", "npm run start"),
            provenance="package.json#scripts.start",
        )
    with pytest.raises(ValidationError):
        SandboxStep(
            name="install",
            argv=("npm", "ci", "&& touch /tmp/pwned"),
            provenance="package-lock.json",
        )


def test_artifacts_reject_traversal_and_oversized_metadata() -> None:
    base: dict[str, object] = {
        "relative_path": "evidence/screenshot.png",
        "sha256": "c" * 64,
        "media_type": "image/png",
        "size_bytes": 128,
    }
    artifact = EvidenceArtifact(**base)
    assert artifact.relative_path == "evidence/screenshot.png"

    for path in ("../secrets", "/etc/passwd", "C:\\temp\\secret", "safe/../secret"):
        with pytest.raises(ValidationError):
            EvidenceArtifact(**{**base, "relative_path": path})

    with pytest.raises(ValidationError):
        EvidenceArtifact(**{**base, "size_bytes": 5 * 1024 * 1024 + 1})


def test_result_is_bound_to_run_commit_time_and_artifact_budget() -> None:
    request = build_request()
    result = SandboxRunResult(
        run_id=request.run_id,
        commit_sha=COMMIT_SHA,
        status="succeeded",
        duration_ms=1000,
        exit_code=0,
        artifacts=(),
    )
    assert validate_result_for_request(request, result) is result

    with pytest.raises(ValueError, match="run ID"):
        validate_result_for_request(
            request,
            result.model_copy(update={"run_id": uuid4()}),
        )
    with pytest.raises(ValueError, match="commit"):
        validate_result_for_request(
            request,
            result.model_copy(update={"commit_sha": "d" * 40}),
        )
    with pytest.raises(ValueError, match="wall-clock"):
        validate_result_for_request(
            request,
            result.model_copy(update={"duration_ms": 601_000}),
        )

    small_budget_request = build_request(limits=SandboxLimits(total_artifact_bytes=1024))
    artifact = EvidenceArtifact(
        relative_path="evidence/log.txt",
        sha256="c" * 64,
        media_type="text/plain",
        size_bytes=1025,
    )
    oversized = SandboxRunResult(
        run_id=small_budget_request.run_id,
        commit_sha=COMMIT_SHA,
        status="succeeded",
        duration_ms=1000,
        exit_code=0,
        artifacts=(artifact,),
    )
    with pytest.raises(ValueError, match="artifact budget"):
        validate_result_for_request(small_budget_request, oversized)


def test_sandbox_runner_placeholder_fails_closed_without_local_execution() -> None:
    async def exercise() -> None:
        runner = DisabledSandboxRunner()
        with pytest.raises(SandboxExecutionDisabled):
            await runner.execute(build_request())
        assert await runner.cancel(uuid4()) is False

    asyncio.run(exercise())


def test_result_schema_rejects_inconsistent_success_and_excess_artifacts() -> None:
    run_id = uuid4()
    with pytest.raises(ValidationError):
        SandboxRunResult(
            run_id=run_id,
            commit_sha=COMMIT_SHA,
            status="succeeded",
            duration_ms=100,
            exit_code=1,
            artifacts=(),
        )

    artifact = {
        "relative_path": "evidence/report.json",
        "sha256": "c" * 64,
        "media_type": "application/json",
        "size_bytes": 5 * 1024 * 1024,
    }
    with pytest.raises(ValidationError, match="Aggregate evidence"):
        SandboxRunResult(
            run_id=run_id,
            commit_sha=COMMIT_SHA,
            status="succeeded",
            duration_ms=100,
            exit_code=0,
            artifacts=tuple(EvidenceArtifact(**artifact) for _ in range(5)),
        )

    with pytest.raises(ValidationError, match="failed run cannot report exit code zero"):
        SandboxRunResult(
            run_id=run_id,
            commit_sha=COMMIT_SHA,
            status="failed",
            duration_ms=100,
            exit_code=0,
            artifacts=(),
        )
