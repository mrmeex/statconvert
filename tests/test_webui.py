from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.webui import dependencies
from statconvert.webui.dependencies import UI_DEPENDENCY_MESSAGE, UiDependencyError
from statconvert.webui.launcher import (
    WebUiLaunchError,
    build_local_url,
    validate_host,
    validate_port,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_ui_command_help_documents_local_options() -> None:
    result = runner.invoke(app, ["ui", "--help"])

    assert result.exit_code == 0
    assert "--host" in result.stdout
    assert "127.0.0.1" in result.stdout
    assert "--port" in result.stdout
    assert "8765" in result.stdout
    assert "--no-browser" in result.stdout


def test_ui_command_delegates_validated_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_launch_ui(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("statconvert.webui.launcher.launch_ui", fake_launch_ui)

    result = runner.invoke(
        app,
        ["ui", "--host", "localhost", "--port", "9100", "--no-browser"],
    )

    assert result.exit_code == 0
    assert captured["host"] == "localhost"
    assert captured["port"] == 9100
    assert captured["open_browser"] is False
    assert callable(captured["on_start"])


def test_ui_command_prints_open_url_and_bound_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_launch_ui(**kwargs: object) -> None:
        callback = kwargs["on_start"]
        assert callable(callback)
        callback("http://statconvert.localhost:8765", "127.0.0.1:8765")

    monkeypatch.setattr("statconvert.webui.launcher.launch_ui", fake_launch_ui)
    result = runner.invoke(app, ["ui", "--no-browser"])

    assert result.exit_code == 0
    assert "Open URL: http://statconvert.localhost:8765" in result.stdout
    assert "Bound address: 127.0.0.1:8765" in result.stdout


def test_ui_command_reports_optional_dependency_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_launch_ui(**kwargs: object) -> None:
        del kwargs
        raise UiDependencyError(UI_DEPENDENCY_MESSAGE)

    monkeypatch.setattr("statconvert.webui.launcher.launch_ui", fake_launch_ui)

    result = runner.invoke(app, ["ui", "--no-browser"])

    assert result.exit_code == 1
    assert "UI dependencies are not installed" in result.stdout
    assert 'python -m pip install "statconvert[ui]"' in result.stdout


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "LOCALHOST"])
def test_validate_host_accepts_only_loopback_names(host: str) -> None:
    assert validate_host(host) == host.casefold()


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.2", "example.com"])
def test_validate_host_rejects_non_loopback_bindings(host: str) -> None:
    with pytest.raises(WebUiLaunchError, match="local-only"):
        validate_host(host)


@pytest.mark.parametrize("port", [1, 8765, 65535])
def test_validate_port_accepts_tcp_port_range(port: int) -> None:
    assert validate_port(port) == port


@pytest.mark.parametrize("port", [0, 65536, True])
def test_validate_port_rejects_invalid_values(port: int) -> None:
    with pytest.raises(WebUiLaunchError, match="1 through 65535"):
        validate_port(port)


def test_build_local_url_brackets_ipv6_loopback() -> None:
    assert build_local_url("::1", 8765) == "http://[::1]:8765"


def test_dependency_status_does_not_import_optional_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_find_spec(module_name: str) -> object | None:
        seen.append(module_name)
        return object() if module_name == "fastapi" else None

    monkeypatch.setattr(dependencies, "find_spec", fake_find_spec)

    assert dependencies.ui_dependency_status() == {
        "fastapi": True,
        "uvicorn": False,
    }
    assert seen == ["fastapi", "uvicorn"]


def test_importing_cli_does_not_import_ui_server_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import statconvert.cli; "
                "print('fastapi' in sys.modules, 'uvicorn' in sys.modules)"
            ),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"
