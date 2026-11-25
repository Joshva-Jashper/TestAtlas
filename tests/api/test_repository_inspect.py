from __future__ import annotations

from typing import Any

import httpx
from fastapi.testclient import TestClient

from testatlas.main import create_app


def github_repository_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 1234,
        "name": "sample-app-web",
        "full_name": "saucelabs/sample-app-web",
        "html_url": "https://github.com/saucelabs/sample-app-web",
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


def make_client(handler: Any) -> TestClient:
    transport = httpx.MockTransport(handler)
    return TestClient(create_app(github_transport=transport))


def test_liveness_endpoint() -> None:
    with make_client(lambda request: httpx.Response(500)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inspect_repository_returns_metadata_without_running_source() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json=github_repository_payload())

    with make_client(handler) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/saucelabs/sample-app-web"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "saucelabs/sample-app-web"
    assert body["canonical_url"] == "https://github.com/saucelabs/sample-app-web"
    assert body["default_branch"] == "main"
    assert body["primary_language"] == "JavaScript"
    assert body["license_spdx_id"] == "MIT"
    assert "not enabled yet" in body["next_step"]
    assert requested_urls == ["https://api.github.com/repos/saucelabs/sample-app-web"]


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


def test_unknown_request_fields_are_rejected() -> None:
    with make_client(lambda request: httpx.Response(500)) as client:
        response = client.post(
            "/api/v1/repositories/inspect",
            json={"repository_url": "https://github.com/example/repo", "command": "rm -rf /"},
        )

    assert response.status_code == 422
