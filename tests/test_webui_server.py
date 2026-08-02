from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest


pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI

from statconvert.version import get_statconvert_version
from statconvert.webui.server import create_app


def _static_shell(tmp_path: Path) -> Path:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        "<!doctype html><title>StatConvert test shell</title>",
        encoding="utf-8",
    )
    (assets_dir / "shell.css").write_text("body {}", encoding="utf-8")
    return static_dir


def _get(application: FastAPI, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://statconvert.local",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def test_system_api_reports_health_version_and_environment(tmp_path: Path) -> None:
    application = create_app(
        host="localhost",
        port=9100,
        static_dir=_static_shell(tmp_path),
    )

    assert _get(application, "/api/health").json() == {"status": "ok"}
    assert _get(application, "/api/version").json() == {
        "version": get_statconvert_version(),
        "app_name": "StatConvert",
        "license": "AGPL-3.0-or-later",
    }

    environment = _get(application, "/api/environment").json()
    assert environment["ui_mode"] == "local"
    assert environment["server_host"] == "localhost"
    assert environment["server_port"] == 9100
    assert environment["static_assets_present"] is True
    assert set(environment["ui_dependencies"]) == {"fastapi", "uvicorn"}


def test_frontend_shell_and_assets_are_served_with_spa_fallback(
    tmp_path: Path,
) -> None:
    application = create_app(static_dir=_static_shell(tmp_path))

    assert "StatConvert test shell" in _get(application, "/").text
    assert "StatConvert test shell" in _get(application, "/inspect").text
    assert _get(application, "/assets/shell.css").text == "body {}"


def test_missing_frontend_assets_return_clear_error_but_api_stays_available(
    tmp_path: Path,
) -> None:
    application = create_app(static_dir=tmp_path / "missing")

    assert _get(application, "/api/health").status_code == 200
    response = _get(application, "/")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ui_static_assets_missing"
    assert "frontend assets" in response.json()["error"]["message"]
