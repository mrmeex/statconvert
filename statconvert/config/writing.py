from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from statconvert.exceptions import ConfigError
from statconvert.output_paths import validate_output_file_path

from .models import WorkflowConfig
from .validation import COMMAND_FIELDS, validate_config


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

_OPTION_ALIASES = {
    "input_file": "input",
    "input_path": "input",
    "output_file": "output",
    "output_path": "output",
    "left_file": "left",
    "right_file": "right",
    "to_format": "to",
    "object_selector": "object",
    "left_object_selector": "left_object",
    "right_object_selector": "right_object",
    "validate_inputs": "validate",
    "transform_items": "transform",
    "type_items": "type",
    "filter_items": "filter",
    "json_output": "json",
    "log_file": "log",
    "output_format": "report_format",
}


def config_from_options(command: str, **options: Any) -> WorkflowConfig:
    """Build a validated config from command option values.

    ``None`` values are omitted so CLI defaults can be represented without writing
    TOML null values, which TOML does not support.
    """

    raw: dict[str, Any] = {"command": command}
    for option_name, value in options.items():
        if value is None:
            continue
        name = _OPTION_ALIASES.get(option_name, option_name)
        if name in raw:
            raise ConfigError(
                f"Config error: multiple option values map to field '{name}'."
            )
        raw[name] = _normalize_option_value(name, value)
    return validate_config(raw)


def config_to_dict(config: WorkflowConfig) -> dict[str, Any]:
    """Serialize a workflow model in deterministic schema order."""

    result: dict[str, Any] = {"command": config.command}
    for name in COMMAND_FIELDS[config.command]:
        if name in config.options and config.options[name] is not None:
            result[name] = config.options[name]
    return result


def to_toml(config: WorkflowConfig | Mapping[str, Any]) -> str:
    """Write the controlled subset of TOML used by StatConvert configs."""

    raw = config.to_dict() if isinstance(config, WorkflowConfig) else dict(config)
    model = validate_config(raw)
    lines = [
        f"{_format_key(name)} = {_format_value(value)}"
        for name, value in config_to_dict(model).items()
    ]
    return "\n".join(lines) + "\n"


def write_config(
    config: WorkflowConfig | Mapping[str, Any],
    path: str | Path,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
    overwrite_option: str = "--overwrite",
) -> Path:
    """Validate and safely write a StatConvert TOML config file."""

    text = to_toml(config)
    output_path = validate_output_file_path(
        path,
        overwrite=overwrite,
        create_dirs=create_dirs,
        overwrite_option=overwrite_option,
        output_label="Config file",
    )
    try:
        output_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not write config file {output_path}: {exc}") from exc
    return output_path


def _format_key(value: str) -> str:
    if _BARE_KEY.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = (
            f"{_format_key(key)} = {_format_value(value[key])}"
            for key in sorted(value)
        )
        return "{ " + ", ".join(entries) + " }"
    raise ConfigError(
        f"Config error: cannot write TOML value of type {type(value).__name__}."
    )


def _normalize_option_value(name: str, value: Any) -> Any:
    if name == "key" and isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if name == "ignore_columns" and isinstance(value, list):
        if not all(isinstance(group, str) for group in value):
            return value
        return [
            item.strip()
            for group in value
            for item in group.split(",")
            if item.strip()
        ]
    if name == "rename" and isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            if not isinstance(item, str) or "=" not in item:
                return value
            old, new = item.split("=", 1)
            old = old.strip()
            if old in result:
                raise ConfigError(
                    f"Config error: 'rename' contains duplicate key '{old}'."
                )
            result[old] = new.strip()
        return result
    return value
