from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_webui_preferences(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
):
    """Keep browser-UI tests independent from a developer's saved preferences."""

    if not Path(str(request.path)).name.startswith("test_webui"):
        yield
        return

    from statconvert.webui import settings

    root = tmp_path_factory.mktemp("webui-settings")
    config = root / "config" / "ui-settings.toml"
    logs = root / "logs"
    monkeypatch.setattr(settings, "settings_file_path", lambda: config)
    monkeypatch.setattr(settings, "default_log_directory", lambda: logs)
    monkeypatch.setattr("statconvert.webui.api.routes.settings_file_path", lambda: config)
    yield
