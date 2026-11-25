from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from testatlas.domain.repository import GitHubRepositoryRef
from testatlas.domain.setup import SetupSnapshot

GITHUB_API_BASE_URL = "https://api.github.com"
MAX_METADATA_BYTES = 256 * 1024
MAX_DIRECTORY_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024
MAX_CONTENT_RESPONSE_BYTES = 128 * 1024
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_VITE_CONFIG_PATTERN = re.compile(r"^vite\.config\.(?:[cm]?[jt]s)$")


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
    default_branch: str = Field(min_length=1, max_length=255)
    language: str | None = None
    private: bool
    archived: bool = False
    size_kb: int = Field(alias="size", ge=0)
    pushed_at: datetime | None = None
    license: RepositoryLicense | None = None


class GitHubCommit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha: str


class GitHubRootEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    path: str
    type: Literal["file", "dir", "symlink", "submodule"]
    size: int = Field(default=0, ge=0)


class GitHubMetadataError(Exception):
    """Base error for failures retrieving repository metadata or setup files."""


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
        owner, name = self._repository_path(repository)
        payload = await self._get_json(
            f"/repos/{owner}/{name}",
            max_bytes=MAX_METADATA_BYTES,
        )
        try:
            return GitHubRepositoryMetadata.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise GitHubUpstreamUnavailable("GitHub returned invalid repository metadata.") from exc

    async def inspect_setup(
        self,
        repository: GitHubRepositoryRef,
        default_branch: str,
    ) -> SetupSnapshot:
        """Resolve a branch to a commit and read only bounded root setup files."""
        commit_sha = await self._resolve_commit(repository, default_branch)
        owner, name = self._repository_path(repository)
        root_payload = await self._get_json(
            f"/repos/{owner}/{name}/contents",
            params={"ref": commit_sha},
            max_bytes=MAX_DIRECTORY_BYTES,
            not_found_ok=True,
        )

        if root_payload is None:
            root_payload = []
        if not isinstance(root_payload, list):
            raise GitHubUpstreamUnavailable("GitHub returned an invalid repository file listing.")
        try:
            entries = [GitHubRootEntry.model_validate(item) for item in root_payload]
        except (ValueError, TypeError) as exc:
            raise GitHubUpstreamUnavailable(
                "GitHub returned an invalid repository file listing."
            ) from exc

        files = {entry.name: entry for entry in entries if entry.type == "file"}
        vite_configs = sorted(name for name in files if _VITE_CONFIG_PATTERN.fullmatch(name))
        warnings: list[str] = []
        if len(vite_configs) > 1:
            warnings.append(
                "Multiple root Vite config files were found; config selection is ambiguous."
            )
            vite_config_path = None
        else:
            vite_config_path = vite_configs[0] if vite_configs else None

        requested: list[tuple[str, str, int]] = []
        if "package.json" in files:
            requested.append(("package_json", "package.json", MAX_FILE_BYTES))
        if ".nvmrc" in files:
            requested.append(("nvmrc", ".nvmrc", 256))
        if vite_config_path is not None:
            requested.append(("vite_config", vite_config_path, MAX_FILE_BYTES))

        contents = await asyncio.gather(
            *(
                self._read_root_file(
                    repository=repository,
                    commit_sha=commit_sha,
                    entry=files[path],
                    max_file_bytes=max_file_bytes,
                )
                for _, path, max_file_bytes in requested
            )
        )
        content_by_name = {requested[index][1]: contents[index] for index in range(len(requested))}
        unreadable_files = tuple(
            path
            for _, path, max_file_bytes in requested
            if files[path].size > max_file_bytes or content_by_name[path] is None
        )

        return SetupSnapshot(
            commit_sha=commit_sha,
            root_files=frozenset(files),
            package_json=content_by_name.get("package.json"),
            nvmrc=content_by_name.get(".nvmrc"),
            vite_config_path=vite_config_path,
            vite_config=content_by_name.get(vite_config_path) if vite_config_path else None,
            unreadable_files=unreadable_files,
            warnings=tuple(warnings),
        )

    async def _resolve_commit(self, repository: GitHubRepositoryRef, branch: str) -> str:
        owner, name = self._repository_path(repository)
        payload = await self._get_json(
            f"/repos/{owner}/{name}/commits",
            params={"sha": branch, "per_page": 1},
            max_bytes=MAX_METADATA_BYTES,
        )
        if not isinstance(payload, list) or not payload:
            raise RepositoryUnavailable("No commit was found on the repository's default branch.")
        try:
            commit = GitHubCommit.model_validate(payload[0])
        except (ValueError, TypeError) as exc:
            raise GitHubUpstreamUnavailable("GitHub returned invalid commit metadata.") from exc
        if not _SHA_PATTERN.fullmatch(commit.sha):
            raise GitHubUpstreamUnavailable("GitHub returned an invalid commit identifier.")
        return commit.sha.lower()

    async def _read_root_file(
        self,
        *,
        repository: GitHubRepositoryRef,
        commit_sha: str,
        entry: GitHubRootEntry,
        max_file_bytes: int,
    ) -> str | None:
        if entry.size > max_file_bytes:
            return None
        owner, name = self._repository_path(repository)
        safe_name = quote(entry.name, safe="")
        payload = await self._get_json(
            f"/repos/{owner}/{name}/contents/{safe_name}",
            params={"ref": commit_sha},
            max_bytes=MAX_CONTENT_RESPONSE_BYTES,
            not_found_ok=True,
        )
        if payload is None or not isinstance(payload, dict):
            return None
        content = payload.get("content")
        if payload.get("encoding") != "base64" or not isinstance(content, str):
            return None
        try:
            encoded = "".join(content.split()).encode("ascii")
            decoded = base64.b64decode(encoded, validate=True)
            if len(decoded) > max_file_bytes:
                return None
            return decoded.decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError, binascii.Error):
            return None

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        max_bytes: int,
        not_found_ok: bool = False,
    ) -> Any:
        try:
            async with self._client.stream("GET", path, params=params) as response:
                if response.status_code == 404 and not_found_ok:
                    return None
                self._raise_for_status(response)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > max_bytes:
                        raise GitHubUpstreamUnavailable(
                            "GitHub returned data larger than the inspection limit."
                        )
                    body.extend(chunk)
        except httpx.TimeoutException as exc:
            raise GitHubUpstreamUnavailable("GitHub did not respond before the timeout.") from exc
        except httpx.RequestError as exc:
            raise GitHubUpstreamUnavailable("Could not reach GitHub.") from exc

        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubUpstreamUnavailable("GitHub returned invalid JSON metadata.") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 404:
            raise RepositoryUnavailable("Repository not found or private access is not connected.")
        if response.status_code in {403, 429}:
            if response.status_code == 429 or response.headers.get("x-ratelimit-remaining") == "0":
                raise GitHubRateLimited("GitHub API rate limit reached; try again later.")
            raise RepositoryUnavailable("Repository access is not authorized.")
        if response.status_code >= 500:
            raise GitHubUpstreamUnavailable("GitHub is temporarily unavailable.")
        if response.status_code != 200:
            raise GitHubUpstreamUnavailable("GitHub returned an unexpected metadata response.")

    @staticmethod
    def _repository_path(repository: GitHubRepositoryRef) -> tuple[str, str]:
        return quote(repository.owner, safe=""), quote(repository.name, safe="")


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
