from __future__ import annotations

from pathlib import Path
import tomllib

from statconvert.exceptions import ConfigError

from .models import WorkflowConfig
from .validation import validate_config


def load_config(path: str | Path) -> WorkflowConfig:
    """Read and validate one TOML workflow configuration."""

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"Config file does not exist: {config_path}",
            suggestion=(
                "Check the path, or run `statconvert config init COMMAND --output "
                "PATH` to create a starter config."
            ),
        )
    if not config_path.is_file():
        raise ConfigError(
            f"Config path is not a file: {config_path}",
            suggestion="Choose a TOML config file instead of a directory.",
        )
    try:
        with config_path.open("rb") as config_file:
            raw = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config error: invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {config_path}: {exc}") from exc
    try:
        return validate_config(raw)
    except ConfigError as exc:
        detail = exc.message.removeprefix("Config error: ")
        raise ConfigError(
            f"Config error in {config_path}: {detail}",
            suggestion=exc.suggestion,
        ) from exc
