import asyncio

from fastapi import APIRouter, HTTPException, Request, status

from testatlas.api.schemas import RepositoryInspectRequest, RepositoryInspectResponse
from testatlas.domain.repository import parse_github_repository_url
from testatlas.services.github_metadata import (
    GitHubMetadataClient,
    GitHubRateLimited,
    GitHubUpstreamUnavailable,
    RepositoryUnavailable,
)
from testatlas.services.setup_inference import infer_repository_setup

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


@router.post("/inspect", response_model=RepositoryInspectResponse)
async def inspect_repository(
    payload: RepositoryInspectRequest,
    request: Request,
) -> RepositoryInspectResponse:
    try:
        repository = parse_github_repository_url(payload.repository_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    client: GitHubMetadataClient = request.app.state.github_metadata_client
    try:
        async with asyncio.timeout(request.app.state.github_total_timeout_seconds):
            metadata = await client.inspect(repository)
            snapshot = await client.inspect_setup(repository, metadata.default_branch)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Repository inspection exceeded the time limit; try again later.",
        ) from exc
    except RepositoryUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GitHubUpstreamUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    setup_plan = infer_repository_setup(snapshot)
    license_spdx_id = metadata.license.spdx_id if metadata.license else None
    if setup_plan.status == "ready":
        next_step = (
            "A commit-pinned setup plan is ready for preflight; no repository code was executed."
        )
    else:
        next_step = (
            "Review the setup-plan blockers before preflight; no repository code was executed."
        )

    return RepositoryInspectResponse(
        full_name=metadata.full_name,
        canonical_url=repository.canonical_url,
        html_url=metadata.html_url,
        description=metadata.description,
        default_branch=metadata.default_branch,
        commit_sha=snapshot.commit_sha,
        primary_language=metadata.language,
        is_private=metadata.private,
        is_archived=metadata.archived,
        size_kb=metadata.size_kb,
        pushed_at=metadata.pushed_at,
        license_spdx_id=license_spdx_id,
        setup_plan=setup_plan,
        next_step=next_step,
    )
