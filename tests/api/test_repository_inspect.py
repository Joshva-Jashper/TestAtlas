from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from testatlas.config import Settings
from testatlas.main import create_app

REPOSITORY = "saucelabs/sample-app-web"
COMMIT_SHA = "a" * 40
PACKAGE_JSON = json.dumps(
    {
        "engines": {"node": ">=24.9.0"},
        "dependencies": {"react": "^19.0.0"},
        "devDependencies": {"vite": "^8.3.5"},
        "scripts": {"start": "vite", "build": "vite build"},
    }
)
NVMRC = "24.9.0\n"
VITE_CONFIG = "export default { server: { port: 3000, open: true } };"


def github_repository_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 1234,
        "name": "sample-app-web",
        "full_name": REPOSITORY,
        "html_url": f"https://github.com/{REPOSITORY}",
        "description": "A sample web application for browser testing.",
        "default_branch": "main",
        "language": "JavaScript",
        "private": False,
        "archived": False,
        "size": 4210,
        "pushed_at": "2026-11-24T15:42:36Z",
        "license": {"spdx_id": "MIT"},
    }
    payload.update(overrides)
    return payload


def content_payload(name: str, content: str) -> dict[str, Any]:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return {
        "name": name,
        "path": name,
        "sha": "b" * 40,
        "size": len(content.encode("utf-8")),
        "encoding": "base64",
        "content": encoded,
    }


def make_client(handler: Any) -> TestClient:
    transport = httpx.MockTransport(handler)
    return TestClient(create_app(github_transport=transport))


def successful_github_handler(requested: list[httpx.Request] | None = None) -> Any:
    files = {
        "package.json": PACKAGE_JSON,
        ".nvmrc": NVMRC,
        "vite.config.js": VITE_CONFIG,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if requested is not None:
            requested.append(request)
        path = request.url.path
        if path == f"/repos/{REPOSITORY}":
            return httpx.Response(200, json=github_repository_payload())
        if path == f"/repos/{REPOSITORY}/commits":
            assert request.url.params["sha"] == "main"
            assert request.url.params["per_page"] == "1"
            return httpx.Response(200, json=[{"sha": COMMIT_SHA}])
        if path == f"/repos/{REPOSITORY}/contents":
            assert request.url.params["ref"] == COMMIT_SHA
            return httpx.Response(
                200,
                json=[
                    {"name": name, "path": name, "type": "file", "size": len(value)}
                    for name, value in files.items()
                ]
                + [
                    {
                        "name": "package-lock.json",
                        "path": "package-lock.json",
                        "type": "file",
                        "size": 570_986,
                    }
                ],
            )
        prefix = f"/repos/{REPOSITORY}/contents/"
        if path.startswith(prefix):
            name = path.removeprefix(prefix)
            assert request.url.params["ref"] == COMMIT_SHA
            if name in files:
                return httpx.Response(200, json=content_payload(name, files[name]))
        return httpx.Response(404, json={"message": "Not Found"})

    return handler


def test_liveness_endpoint() -> None:
    with make_client(lambda request: httpx.Response(500)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inspect_returns_commit_pinned_setup_evidence_without_running_source() -> None:
    requests: list[httpx.Request] = []
    with make_client(successful_github_handler(requests)) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": f"https://github.com/{REPOSITORY}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == REPOSITORY
    assert body["canonical_url"] == f"https://github.com/{REPOSITORY}"
    assert body["default_branch"] == "main"
    assert body["commit_sha"] == COMMIT_SHA
    assert body["primary_language"] == "JavaScript"
    assert body["license_spdx_id"] == "MIT"
    assert body["setup_plan"]["status"] == "ready"
    assert body["setup_plan"]["runtime_version"] == "24.9.0"
    assert body["setup_plan"]["install_command"] == "npm ci"
    assert body["setup_plan"]["start_command"] == "npm run start"
    assert body["setup_plan"]["port"] == 3000
    assert any(item["source_path"] == ".nvmrc" for item in body["setup_plan"]["evidence"])
    assert "no repository code was executed" in body["next_step"]
    assert [request.url.host for request in requests] == ["api.github.com"] * 6
    assert all("/git/" not in request.url.path for request in requests)


def test_invalid_url_is_rejected_before_calling_github() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=github_repository_payload())

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://attacker.example/owner/repo"},
        )

    assert response.status_code == 422
    assert calls == 0


def test_unavailable_repository_returns_non_disclosing_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/private-repo"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository not found or private access is not connected."


def test_github_rate_limit_is_reported_as_retryable_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "0"},
            json={"message": "rate limit details"},
        )

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo"},
        )

    assert response.status_code == 503
    assert "try again later" in response.json()["detail"]


def test_github_upstream_failure_does_not_leak_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"message": "sensitive upstream diagnostic"})

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "GitHub is temporarily unavailable."
    assert "sensitive" not in response.text


def test_github_connection_failure_is_reported_without_internal_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("internal network detail", request=request)

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not reach GitHub."
    assert "internal network" not in response.text


def test_invalid_upstream_metadata_is_reported_as_gateway_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "GitHub returned invalid repository metadata."


def test_github_forbidden_response_is_not_exposed_as_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "private upstream detail"})

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/private-repo"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository access is not authorized."
    assert "private upstream" not in response.text


def test_oversized_package_manifest_is_reported_as_a_blocker_without_download() -> None:
    handler = successful_github_handler()

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{REPOSITORY}/contents":
            response = handler(request)
            root = response.json()
            for entry in root:
                if entry["name"] == "package.json":
                    entry["size"] = 70_000
            return httpx.Response(200, json=root)
        if request.url.path.endswith("/contents/package.json"):
            raise AssertionError("Oversized package.json must not be downloaded")
        return handler(request)

    with make_client(oversized_handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": f"https://github.com/{REPOSITORY}"},
        )

    assert response.status_code == 200
    plan = response.json()["setup_plan"]
    assert plan["status"] == "unsupported"
    assert any("package.json" in blocker for blocker in plan["blockers"])


def test_unknown_request_fields_are_rejected() -> None:
    with make_client(lambda request: httpx.Response(500)) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo", "command": "rm -rf /"},
        )

    assert response.status_code == 422


def test_malformed_github_root_listing_returns_gateway_error() -> None:
    handler = successful_github_handler()

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{REPOSITORY}/contents":
            return httpx.Response(200, json={"unexpected": "object"})
        return handler(request)

    with make_client(malformed_handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": f"https://github.com/{REPOSITORY}"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "GitHub returned an invalid repository file listing."


def test_oversized_file_content_response_is_rejected() -> None:
    handler = successful_github_handler()

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents/package.json"):
            return httpx.Response(200, content=b"x" * (128 * 1024 + 1))
        return handler(request)

    with make_client(oversized_handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": f"https://github.com/{REPOSITORY}"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "GitHub returned data larger than the inspection limit."


def test_total_inspection_timeout_maps_to_gateway_timeout() -> None:
    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=github_repository_payload())

    app = create_app(
        settings=Settings(github_total_timeout_seconds=0.001),
        github_transport=SlowTransport(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": f"https://github.com/{REPOSITORY}"},
        )

    assert response.status_code == 504
    assert "exceeded the time limit" in response.json()["detail"]
