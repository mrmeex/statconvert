"""FastAPI application factory and packaged frontend serving."""

from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api.errors import install_error_handlers, missing_static_assets_response
from .api.routes import create_api_router
from .jobs import JobManager
from .launcher import WebUiLaunchError, resolve_open_url


APP_TITLE = "StatConvert UI"
DEFAULT_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_url: str | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create the local API and bundled single-page application."""

    resolved_static_dir = Path(static_dir) if static_dir is not None else DEFAULT_STATIC_DIR
    index_file = resolved_static_dir / "index.html"
    assets_dir = resolved_static_dir / "assets"
    static_assets_present = index_file.is_file() and assets_dir.is_dir()
    job_manager = JobManager()
    if open_url is not None:
        resolved_open_url = open_url
    else:
        try:
            resolved_open_url = resolve_open_url(host, port)
        except WebUiLaunchError:
            # The launcher rejects this before binding. Keeping the app factory
            # constructible lets route tests verify their own loopback guard.
            resolved_open_url = f"http://{host}:{port}"

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        del application
        yield
        job_manager.shutdown()

    application = FastAPI(
        title=APP_TITLE,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(application)
    application.include_router(
        create_api_router(
            host=host,
            port=port,
            open_url=resolved_open_url,
            static_assets_present=static_assets_present,
            job_manager=job_manager,
        )
    )

    if assets_dir.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="webui-assets",
        )

    @application.get("/", include_in_schema=False)
    async def frontend_index() -> Response:
        if not static_assets_present:
            return missing_static_assets_response()
        return FileResponse(index_file)

    @application.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_fallback(frontend_path: str) -> Response:
        del frontend_path
        if not static_assets_present:
            return missing_static_assets_response()
        return FileResponse(index_file)

    return application
