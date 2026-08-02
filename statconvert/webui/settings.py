"""Platform-appropriate preferences for the local browser UI."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
import os
from pathlib import Path
import sys
from threading import Lock
from typing import Any, Iterator
import tomllib

from statconvert.logging import LogLevel, command_log_wrapper


MIN_TABLE_PAGE_SIZE = 5
MAX_TABLE_PAGE_SIZE = 500
ALLOWED_LOG_LEVELS = tuple(level.value for level in LogLevel)
_UI_LOGGING_LOCK = Lock()


class UiSettingsError(ValueError):
    """A local UI preference is invalid."""


@dataclass
class PathSettings:
    default_working_directory: str = ""
    path_browser_start_directory: str = ""
    remember_last_paths: bool = True
    last_input_directory: str = ""
    last_output_directory: str = ""


@dataclass
class DisplaySettings:
    default_table_page_size: int = 25
    show_command_preview: bool = True


@dataclass
class LoggingSettings:
    enabled: bool = False
    directory: str = ""
    level: str = "info"


@dataclass
class UiSettings:
    paths: PathSettings = field(default_factory=PathSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


@dataclass
class LoadedUiSettings:
    settings: UiSettings
    warning: str | None = None


def settings_file_path() -> Path:
    """Return the platform-native UI settings file without creating it."""

    home = Path.home()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return root / "StatConvert" / "config" / "ui-settings.toml"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "StatConvert" / "config" / "ui-settings.toml"
    root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return root / "statconvert" / "ui-settings.toml"


def default_log_directory() -> Path:
    """Return the platform-native default log directory without creating it."""

    home = Path.home()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return root / "StatConvert" / "logs"
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "StatConvert"
    root = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
    return root / "statconvert" / "logs"


def load_ui_settings(path: Path | None = None) -> LoadedUiSettings:
    """Load known preferences, returning defaults and a warning on malformed TOML."""

    target = path or settings_file_path()
    if not target.exists():
        return LoadedUiSettings(UiSettings())
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
        return LoadedUiSettings(_settings_from_dict(raw))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, UiSettingsError) as exc:
        return LoadedUiSettings(
            UiSettings(),
            f"Could not load UI settings from {target}: {exc}. Safe defaults are active.",
        )


def save_ui_settings(settings: UiSettings, path: Path | None = None) -> Path:
    """Validate and persist only the known UI preference keys."""

    target = path or settings_file_path()
    validated = validate_ui_settings(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    log_directory = validated.logging.directory.strip()
    if log_directory:
        Path(log_directory).expanduser().mkdir(parents=True, exist_ok=True)
    elif validated.logging.enabled:
        default_log_directory().mkdir(parents=True, exist_ok=True)
    target.write_text(_settings_toml(validated), encoding="utf-8")
    return target


def reset_ui_settings(path: Path | None = None) -> UiSettings:
    """Remove the managed settings file and return safe defaults."""

    target = path or settings_file_path()
    if target.exists():
        target.unlink()
    return UiSettings()


def validate_ui_settings(settings: UiSettings) -> UiSettings:
    """Validate supported values and explicit local directory fields."""

    page_size = settings.display.default_table_page_size
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not MIN_TABLE_PAGE_SIZE <= page_size <= MAX_TABLE_PAGE_SIZE
    ):
        raise UiSettingsError(
            f"Default table page size must be from {MIN_TABLE_PAGE_SIZE} through {MAX_TABLE_PAGE_SIZE}."
        )
    if not isinstance(settings.display.show_command_preview, bool):
        raise UiSettingsError("Show command preview must be true or false.")
    if not isinstance(settings.paths.remember_last_paths, bool):
        raise UiSettingsError("Remember last paths must be true or false.")
    if not settings.paths.remember_last_paths:
        settings.paths.last_input_directory = ""
        settings.paths.last_output_directory = ""
    if not isinstance(settings.logging.enabled, bool):
        raise UiSettingsError("Logging enabled must be true or false.")
    if settings.logging.level not in ALLOWED_LOG_LEVELS:
        raise UiSettingsError(
            "Log level must be one of: " + ", ".join(ALLOWED_LOG_LEVELS) + "."
        )
    for name, value in asdict(settings.paths).items():
        if name == "remember_last_paths" or not value:
            continue
        if not isinstance(value, str):
            raise UiSettingsError(f"{name.replace('_', ' ').title()} must be a path string.")
        candidate = Path(str(value)).expanduser()
        if not candidate.is_dir():
            raise UiSettingsError(f"{name.replace('_', ' ').title()} must be an existing directory: {candidate}")
    if not isinstance(settings.logging.directory, str):
        raise UiSettingsError("Logging directory must be a path string.")
    configured_log_directory = settings.logging.directory.strip()
    if configured_log_directory:
        candidate = Path(configured_log_directory).expanduser()
        if candidate.exists() and not candidate.is_dir():
            raise UiSettingsError(f"Logging directory is not a directory: {candidate}")
    return settings


def settings_payload(*, path: Path | None = None) -> dict[str, Any]:
    """Return preferences and diagnostics as JSON-safe primitives."""

    target = path or settings_file_path()
    loaded = load_ui_settings(target)
    return {
        "settings": asdict(loaded.settings),
        "settings_file_path": str(target),
        "config_directory": str(target.parent),
        "default_log_directory": str(default_log_directory()),
        "effective_log_directory": str(_effective_log_directory(loaded.settings)),
        "platform": sys.platform,
        "allowed_log_levels": list(ALLOWED_LOG_LEVELS),
        "logging_cli_options": ["--log", "--log-level"],
        "warning": loaded.warning,
    }


def settings_from_payload(raw: dict[str, Any]) -> UiSettings:
    """Build validated settings from an API payload."""

    return validate_ui_settings(_settings_from_dict(raw))


def remember_path(path_text: str, *, output: bool) -> None:
    """Remember one deliberate valid path selection when enabled."""

    selected = Path(path_text).expanduser()
    directory = selected if selected.is_dir() else selected.parent
    if not directory.is_dir():
        return
    loaded = load_ui_settings()
    if loaded.warning or not loaded.settings.paths.remember_last_paths:
        return
    if output:
        loaded.settings.paths.last_output_directory = str(directory)
    else:
        loaded.settings.paths.last_input_directory = str(directory)
    save_ui_settings(loaded.settings)


def logging_cli_arguments(workflow: str) -> list[str]:
    """Return existing CLI logging options for a UI workflow preview."""

    loaded = load_ui_settings()
    if loaded.warning or not loaded.settings.logging.enabled:
        return []
    directory = _effective_log_directory(loaded.settings)
    preview_file = directory / f"YYYY-MM-DD_HHMMSS_{workflow}_jobid.log"
    return ["--log", str(preview_file), "--log-level", loaded.settings.logging.level]


@contextmanager
def ui_logging_context(workflow: str, job_id: str) -> Iterator[Path | None]:
    """Map UI defaults onto the existing per-command logging lifecycle."""

    loaded = load_ui_settings()
    if loaded.warning or not loaded.settings.logging.enabled:
        yield None
        return
    directory = _effective_log_directory(loaded.settings)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = directory / f"{stamp}_{workflow}_{job_id[:8]}.log"
    with _UI_LOGGING_LOCK:
        with command_log_wrapper(
            command=workflow,
            parameters={"ui_mode": "local", "job_id": job_id},
            log_file=log_file,
            log_level=loaded.settings.logging.level,
        ):
            yield log_file


def _effective_log_directory(settings: UiSettings) -> Path:
    configured = settings.logging.directory.strip()
    return Path(configured).expanduser() if configured else default_log_directory()


def _settings_from_dict(raw: dict[str, Any]) -> UiSettings:
    try:
        paths = raw.get("paths", {})
        display = raw.get("display", {})
        logging = raw.get("logging", {})
        if not all(isinstance(section, dict) for section in (paths, display, logging)):
            raise UiSettingsError("Settings sections must be TOML tables")
        settings = UiSettings(
            paths=PathSettings(**_known(paths, PathSettings)),
            display=DisplaySettings(**_known(display, DisplaySettings)),
            logging=LoggingSettings(**_known(logging, LoggingSettings)),
        )
    except (TypeError, ValueError) as exc:
        raise UiSettingsError(str(exc)) from exc
    return validate_ui_settings(settings)


def _known(raw: dict[str, Any], model: type[Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key in model.__dataclass_fields__}


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _settings_toml(settings: UiSettings) -> str:
    paths = settings.paths
    display = settings.display
    logging = settings.logging
    return "\n".join(
        [
            "[paths]",
            f"default_working_directory = {_toml_string(paths.default_working_directory)}",
            f"path_browser_start_directory = {_toml_string(paths.path_browser_start_directory)}",
            f"remember_last_paths = {str(paths.remember_last_paths).lower()}",
            f"last_input_directory = {_toml_string(paths.last_input_directory)}",
            f"last_output_directory = {_toml_string(paths.last_output_directory)}",
            "",
            "[display]",
            f"default_table_page_size = {display.default_table_page_size}",
            f"show_command_preview = {str(display.show_command_preview).lower()}",
            "",
            "[logging]",
            f"enabled = {str(logging.enabled).lower()}",
            f"directory = {_toml_string(logging.directory)}",
            f"level = {_toml_string(logging.level)}",
            "",
        ]
    )
