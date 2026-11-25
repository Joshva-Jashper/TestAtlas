from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from testatlas.domain.repository import GitHubRepositoryRef

GITHUB_API_BASE_URL = "https://api.github.com"


class RepositoryLicense(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spdx_id: str | None = None


class GitHubRepositoryMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    full_name: str
    html_url: HttpUrl
    description: str | None = None
    default_branch: str
    language: str | None = None
    private: bool
    archived: bool = False
    size_kb: int = Field(alias="size", ge=0)
    pushed_at: datetime | None = None
    license: RepositoryLicense | None = None


class GitHubMetadataError(Exception):
    """Base error for failures retrieving repository metadata."""


class RepositoryUnavailable(GitHubMetadataError):
    pass


class GitHubRateLimited(GitHubMetadataError):
    pass


class GitHubUpstreamUnavailable(GitHubMetadataError):
    pass


class GitHubMetadataClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def inspect(self, repository: GitHubRepositoryRef) -> GitHubRepositoryMetadata:
        owner = quote(repository.owner, safe="")
        name = quote(repository.name, safe="")
        try:
            response = await self._client.get(f"/repos/{owner}/{name}")
        except httpx.TimeoutException as exc:
            raise GitHubUpstreamUnavailable("GitHub did not respond before the timeout.") from exc
        except httpx.RequestError as exc:
            raise GitHubUpstreamUnavailable("Could not reach GitHub.") from exc

        if response.status_code == 404:
            raise RepositoryUnavailable("Repository not found or private access is not connected.")
        if response.status_code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                raise GitHubRateLimited("GitHub API rate limit reached; try again later.")
            raise RepositoryUnavailable("Repository access is not authorized.")
        if response.status_code >= 500:
            raise GitHubUpstreamUnavailable("GitHub is temporarily unavailable.")
        if response.status_code != 200:
            raise GitHubUpstreamUnavailable("GitHub returned an unexpected metadata response.")

        try:
            return GitHubRepositoryMetadata.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            raise GitHubUpstreamUnavailable("GitHub returned invalid repository metadata.") from exc


def build_github_http_client(
    *,
    timeout_seconds: float,
    user_agent: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0))
    return httpx.AsyncClient(
        base_url=GITHUB_API_BASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": user_agent},
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
    )
