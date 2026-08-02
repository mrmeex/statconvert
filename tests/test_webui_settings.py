from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

pytest.importorskip("fastapi")

from statconvert.version import get_statconvert_version
from statconvert.logging import get_logger
from statconvert.webui import launcher, settings
from statconvert.webui.api.models import ConvertRequest
from statconvert.webui.server import create_app
from statconvert.webui.services import convert_command
from statconvert.webui.settings import (
    LoggingSettings,
    PathSettings,
    UiSettings,
    default_log_directory,
    load_ui_settings,
    save_ui_settings,
    settings_file_path,
    ui_logging_context,
)


def _request(application, method: str, path: str, json=None) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            return await client.request(method, path, json=json)
    return asyncio.run(run())


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    config = tmp_path / "config" / "ui-settings.toml"
    logs = tmp_path / "logs"
    monkeypatch.setattr(settings, "settings_file_path", lambda: config)
    monkeypatch.setattr(settings, "default_log_directory", lambda: logs)
    monkeypatch.setattr("statconvert.webui.api.routes.settings_file_path", lambda: config)
    return config, logs


def test_platform_paths_are_platform_appropriate() -> None:
    assert settings_file_path().name == "ui-settings.toml"
    assert default_log_directory().name == "logs"
    if settings.sys.platform == "win32":
        assert "StatConvert" in settings_file_path().parts


def test_missing_malformed_save_and_reset_settings(
    isolated_settings: tuple[Path, Path], tmp_path: Path,
) -> None:
    config, _ = isolated_settings
    assert load_ui_settings().warning is None
    assert load_ui_settings().settings.display.default_table_page_size == 25

    config.parent.mkdir(parents=True)
    config.write_text("[display\ndefault_table_page_size = nope", encoding="utf-8")
    assert "Safe defaults are active" in (load_ui_settings().warning or "")

    working = tmp_path / "working"
    working.mkdir()
    saved = save_ui_settings(UiSettings(paths=PathSettings(default_working_directory=str(working))))
    assert saved == config
    assert "default_working_directory" in config.read_text(encoding="utf-8")


def test_settings_api_validates_saves_and_resets(
    isolated_settings: tuple[Path, Path], tmp_path: Path,
) -> None:
    config, logs = isolated_settings
    application = create_app(open_url="http://statconvert.localhost:8765")
    response = _request(application, "GET", "/api/settings")
    assert response.status_code == 200
    assert response.json()["data"]["settings_file_path"] == str(config)

    payload = response.json()["data"]["settings"]
    payload["logging"] = {"enabled": True, "directory": "", "level": "debug"}
    payload["display"]["default_table_page_size"] = 50
    saved = _request(application, "PUT", "/api/settings", json={"settings": payload})
    assert saved.status_code == 200
    assert config.is_file()
    assert logs.is_dir()

    payload["display"]["default_table_page_size"] = 1
    assert _request(application, "PUT", "/api/settings", json={"settings": payload}).status_code == 400
    payload["display"]["default_table_page_size"] = 25
    payload["logging"]["level"] = "verbose"
    invalid = _request(application, "PUT", "/api/settings", json={"settings": payload})
    assert invalid.status_code == 400
    assert "debug, info, warning, error" in invalid.json()["error"]["message"]

    reset = _request(application, "POST", "/api/settings/reset", json={})
    assert reset.status_code == 200
    assert not config.exists()


def test_disabling_remembered_paths_clears_and_ignores_them(
    isolated_settings: tuple[Path, Path], tmp_path: Path,
) -> None:
    config, _ = isolated_settings
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    save_ui_settings(
        UiSettings(
            paths=PathSettings(
                remember_last_paths=False,
                last_input_directory=str(input_dir),
                last_output_directory=str(output_dir),
            )
        )
    )
    loaded = load_ui_settings().settings.paths
    assert loaded.remember_last_paths is False
    assert loaded.last_input_directory == ""
    assert loaded.last_output_directory == ""

    application = create_app(open_url="http://statconvert.localhost:8765")
    remembered = _request(
        application,
        "POST",
        "/api/settings/remember-path",
        json={"path": str(input_dir), "kind": "input"},
    )
    assert remembered.status_code == 200
    assert remembered.json()["data"]["settings"]["paths"]["last_input_directory"] == ""
    assert "last_input_directory = \"\"" in config.read_text(encoding="utf-8")

    enabled = UiSettings(paths=PathSettings(remember_last_paths=True))
    save_ui_settings(enabled)
    remembered = _request(
        application,
        "POST",
        "/api/settings/remember-path",
        json={"path": str(input_dir), "kind": "input"},
    )
    assert remembered.json()["data"]["settings"]["paths"]["last_input_directory"] == str(input_dir)


def test_logging_preferences_map_to_existing_cli_options(
    isolated_settings: tuple[Path, Path],
) -> None:
    request = ConvertRequest(input_path="input.csv", output_path="output.sav")
    assert "--log" not in convert_command(request, chunk_size=None)
    save_ui_settings(UiSettings(logging=LoggingSettings(enabled=True, level="warning")))
    command = convert_command(request, chunk_size=None)
    assert "--log" in command
    assert "--log-level warning" in command

    with ui_logging_context("convert", "abcdef123456") as log_file:
        get_logger().info("UI logging smoke without dataset content")
    assert log_file is not None and log_file.is_file()
    assert log_file.name.endswith("_convert_abcdef12.log")


def test_about_reports_version_dependencies_and_local_runtime(
    isolated_settings: tuple[Path, Path],
) -> None:
    config, logs = isolated_settings
    application = create_app(
        host="127.0.0.1", port=9123, open_url="http://statconvert.localhost:9123"
    )
    response = _request(application, "GET", "/api/about")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == get_statconvert_version()
    assert data["license"] == "AGPL-3.0-or-later"
    assert data["open_url"] == "http://statconvert.localhost:9123"
    assert data["bound_address"] == "127.0.0.1:9123"
    assert data["settings_file_path"] == str(config)
    assert data["log_directory"] == str(logs)
    assert set(data["dependencies"]) >= {"pandas", "fastapi", "uvicorn"}
    assert data["privacy"]["telemetry"] is False


def test_friendly_open_url_and_loopback_fallback() -> None:
    assert launcher.resolve_open_url("127.0.0.1", 8765) == "http://statconvert.localhost:8765"
    assert launcher.resolve_open_url(
        "127.0.0.1", 8765, friendly_available=False
    ) == "http://127.0.0.1:8765"
    assert launcher.resolve_open_url("localhost", 8765) == "http://localhost:8765"
    with pytest.raises(launcher.WebUiLaunchError):
        launcher.resolve_open_url("0.0.0.0", 8765)


def test_browser_open_falls_back_when_friendly_open_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            del args

    opened: list[str] = []
    monkeypatch.setattr(launcher, "urlopen", lambda *args, **kwargs: ReadyResponse())
    monkeypatch.setattr(
        launcher.webbrowser,
        "open",
        lambda url: opened.append(url) or len(opened) > 1,
    )
    launcher._open_browser_when_ready(
        "http://127.0.0.1:8765",
        "http://statconvert.localhost:8765",
    )
    assert opened == [
        "http://statconvert.localhost:8765",
        "http://127.0.0.1:8765",
    ]


def test_global_frontend_regressions_are_fixed_in_shared_components() -> None:
    root = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    command_preview = (root / "components" / "CommandPreview.tsx").read_text(encoding="utf-8")
    status = (root / "components" / "ApiStatus.tsx").read_text(encoding="utf-8")
    picker = (root / "components" / "PathPickerField.tsx").read_text(encoding="utf-8")
    home = (root / "pages" / "HomePage.tsx").read_text(encoding="utf-8")

    assert "if (visible !== true) return null" in command_preview
    assert "window.setInterval" in status
    assert "HEALTH_POLL_INTERVAL_MS = 30_000" in status
    assert "void check()" in status
    assert "StatConvert backend" in status
    assert "Disconnected" in status
    assert "paths.remember_last_paths" in picker
    assert "Local browser workspace" not in home
    assert "Workflow workspace" not in home
    assert "One workspace, existing StatConvert behavior" not in home
