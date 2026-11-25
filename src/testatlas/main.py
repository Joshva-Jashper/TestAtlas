from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from testatlas.api.repositories import router as repositories_router
from testatlas.config import Settings, get_settings
from testatlas.services.github_metadata import GitHubMetadataClient, build_github_http_client


def create_app(
    *,
    settings: Settings | None = None,
    github_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        http_client = build_github_http_client(
            timeout_seconds=app_settings.github_timeout_seconds,
            user_agent=app_settings.github_user_agent,
            transport=github_transport,
        )
        app.state.github_http_client = http_client
        app.state.github_metadata_client = GitHubMetadataClient(http_client)
        app.state.github_total_timeout_seconds = app_settings.github_total_timeout_seconds
        try:
            yield
        finally:
            await http_client.aclose()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Repository intake and evidence-first automated testing.",
        lifespan=lifespan,
    )
    app.include_router(repositories_router)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
