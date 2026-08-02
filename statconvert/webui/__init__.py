"""Optional local browser UI for StatConvert.

This package intentionally imports no optional server dependency at package import time.
Use :mod:`statconvert.webui.launcher` to validate and start the local application.
"""

from .dependencies import UI_DEPENDENCY_MESSAGE, UiDependencyError
from .launcher import (
    DEFAULT_UI_HOST,
    DEFAULT_UI_PORT,
    WebUiLaunchError,
    build_local_url,
    launch_ui,
    validate_host,
    validate_port,
)

__all__ = [
    "DEFAULT_UI_HOST",
    "DEFAULT_UI_PORT",
    "UI_DEPENDENCY_MESSAGE",
    "UiDependencyError",
    "WebUiLaunchError",
    "build_local_url",
    "launch_ui",
    "validate_host",
    "validate_port",
]
