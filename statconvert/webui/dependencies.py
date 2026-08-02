"""Optional dependency checks for the local browser UI."""

from __future__ import annotations

from importlib.util import find_spec

from statconvert.exceptions import StatConvertError


UI_DEPENDENCY_MESSAGE = (
    "The StatConvert UI dependencies are not installed.\n"
    "Install them with:\n"
    '    python -m pip install "statconvert[ui]"'
)
UI_DEPENDENCY_MODULES = ("fastapi", "uvicorn")


class UiDependencyError(StatConvertError):
    """The optional local UI dependencies are unavailable."""


def ui_dependency_status() -> dict[str, bool]:
    """Return availability without importing optional modules."""

    return {
        module_name: _module_is_available(module_name)
        for module_name in UI_DEPENDENCY_MODULES
    }


def missing_ui_dependencies() -> tuple[str, ...]:
    """Return missing optional module names in deterministic order."""

    status = ui_dependency_status()
    return tuple(name for name in UI_DEPENDENCY_MODULES if not status[name])


def ensure_ui_dependencies() -> None:
    """Raise the documented install guidance when the UI extra is incomplete."""

    if missing_ui_dependencies():
        raise UiDependencyError(UI_DEPENDENCY_MESSAGE)


def _module_is_available(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False
