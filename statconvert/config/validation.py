from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

from statconvert.error_suggestions import did_you_mean
from statconvert.exceptions import ConfigError
from statconvert.registry import (
    can_write_format,
    resolve_format_info,
    supported_extensions,
)

from .models import SUPPORTED_COMMANDS, CommandName, WorkflowConfig


Validator = Callable[[object], bool]


def _is_string(value: object) -> bool:
    return isinstance(value, str)


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _is_string_map(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str)
        and bool(key.strip())
        and isinstance(item, str)
        and bool(item.strip())
        for key, item in value.items()
    )


@dataclass(frozen=True)
class Field:
    validator: Validator
    type_name: str
    required: bool = False
    non_blank: bool = False


STRING = Field(_is_string, "a string")
PATH = Field(_is_string, "a string", non_blank=True)
NAME = Field(_is_string, "a string", non_blank=True)
BOOL = Field(_is_bool, "a boolean")
INT = Field(_is_int, "an integer")
NUMBER = Field(_is_number, "a number")
STRING_LIST = Field(_is_string_list, "a list of strings")
STRING_MAP = Field(_is_string_map, "a table of string values")


def _required(field: Field) -> Field:
    return Field(
        field.validator,
        field.type_name,
        required=True,
        non_blank=field.non_blank,
    )


COMMON_IO_FIELDS: dict[str, Field] = {
    "object": NAME,
    "overwrite": BOOL,
    "create_dirs": BOOL,
    "validate": BOOL,
    "strict_validation": BOOL,
    "input_encoding": STRING,
    "output_encoding": STRING,
    "csv_delimiter": STRING,
    "csv_decimal": STRING,
}
COMMON_LOG_FIELDS: dict[str, Field] = {
    "log": PATH,
    "log_level": NAME,
    "log_append": BOOL,
    "developer_log": BOOL,
}

COMMAND_FIELDS: dict[CommandName, dict[str, Field]] = {
    "convert": {
        "input": _required(PATH),
        "output": _required(PATH),
        "all_objects": BOOL,
        **COMMON_IO_FIELDS,
        **COMMON_LOG_FIELDS,
    },
    "transform": {
        "input": _required(PATH),
        "output": _required(PATH),
        "select": STRING_LIST,
        "drop": STRING_LIST,
        "rename": STRING_MAP,
        "filter": STRING_LIST,
        "recode": STRING_LIST,
        "type": STRING_LIST,
        "type_errors": NAME,
        "datetime_format": NAME,
        "filter_mode": NAME,
        "recode_default": STRING,
        "update_value_labels": BOOL,
        "ignore_missing_columns": BOOL,
        "reset_index": BOOL,
        "dry_run": BOOL,
        **COMMON_IO_FIELDS,
        **COMMON_LOG_FIELDS,
    },
    "batch": {
        "input": _required(PATH),
        "output": _required(PATH),
        "to": _required(PATH),
        "recursive": BOOL,
        "workers": INT,
        "preserve_structure": BOOL,
        "flatten": BOOL,
        "dry_run": BOOL,
        "object_manifest": PATH,
        "all_objects": BOOL,
        "report": PATH,
        "report_format": STRING,
        "transform": BOOL,
        "select": STRING_LIST,
        "drop": STRING_LIST,
        "rename": STRING_MAP,
        "type": STRING_LIST,
        "type_errors": NAME,
        "datetime_format": NAME,
        "filter": STRING_LIST,
        "filter_mode": NAME,
        "recode": STRING_LIST,
        "recode_default": STRING,
        "update_value_labels": BOOL,
        "ignore_missing_columns": BOOL,
        "reset_index": BOOL,
        "include_unsupported": BOOL,
        "patterns": STRING_LIST,
        "exclude_patterns": STRING_LIST,
        "fail_fast": BOOL,
        "allow_blocked": BOOL,
        "json": BOOL,
        "no_progress": BOOL,
        **COMMON_IO_FIELDS,
        **COMMON_LOG_FIELDS,
    },
    "compare": {
        "left": _required(PATH),
        "right": _required(PATH),
        "key": STRING_LIST,
        "ignore_columns": STRING_LIST,
        "numeric_tolerance": NUMBER,
        "max_differences": INT,
        "left_object": NAME,
        "right_object": NAME,
        "object": NAME,
        "values": BOOL,
        "sample_size": INT,
        "columns": STRING_LIST,
        "json": BOOL,
        "strict": BOOL,
        "report": PATH,
        "report_format": STRING,
        **COMMON_LOG_FIELDS,
    },
    "report": {
        "input": _required(PATH),
        "output": _required(PATH),
        "preset": STRING,
        "report_format": STRING,
        "sections": STRING_LIST,
        "no_summary": BOOL,
        "no_schema": BOOL,
        "no_metadata": BOOL,
        "no_labels": BOOL,
        "no_missing": BOOL,
        "no_describe": BOOL,
        "frequencies": BOOL,
        "no_validation": BOOL,
        "columns": STRING_LIST,
        "frequency_top": INT,
        "frequency_include_missing": BOOL,
        "frequency_max_unique": INT,
        "max_table_rows": INT,
        "max_preview_values": INT,
        "target_format": NAME,
        "json": BOOL,
        "quiet": BOOL,
        "object": NAME,
        "overwrite": BOOL,
        "create_dirs": BOOL,
        "strict_validation": BOOL,
        **COMMON_LOG_FIELDS,
    },
    "collect": {
        "manifest": _required(PATH),
        "output": _required(PATH),
        "base_dir": PATH,
        "dry_run": BOOL,
        "overwrite": BOOL,
        "create_dirs": BOOL,
        "validate": BOOL,
        "strict_validation": BOOL,
        "input_encoding": STRING,
        "output_encoding": STRING,
        "csv_delimiter": STRING,
        "csv_decimal": STRING,
        **COMMON_LOG_FIELDS,
    },
}

LIST_FIELDS_WITH_UNIQUE_VALUES = {
    "key",
    "ignore_columns",
    "select",
    "drop",
}

REPORT_FORMATS: dict[CommandName, set[str]] = {
    "compare": {"csv", "json", "html"},
    "report": {"csv", "json", "html"},
    "batch": {"csv", "json"},
}
REPORT_PRESETS = {"default", "quick", "full", "validation", "metadata"}


def validate_config(raw: object) -> WorkflowConfig:
    """Validate a parsed TOML root and return a normalized config model."""

    if not isinstance(raw, dict):
        raise ConfigError("Config error: the top-level TOML value must be a table.")

    command_value = raw.get("command")
    if command_value is None:
        raise ConfigError("Config error: missing required field 'command'.")
    if not isinstance(command_value, str):
        raise ConfigError("Config error: 'command' must be a string.")
    if command_value not in SUPPORTED_COMMANDS:
        supported = ", ".join(SUPPORTED_COMMANDS)
        raise ConfigError(
            f"Config error: unsupported command '{command_value}'. "
            f"Use one of: {supported}.",
            suggestion=did_you_mean(command_value, SUPPORTED_COMMANDS),
        )

    command: CommandName = command_value
    fields = COMMAND_FIELDS[command]
    options = {key: value for key, value in raw.items() if key != "command"}
    _validate_unknown_fields(options, fields)
    _validate_fields(command, options, fields)
    _validate_command_rules(command, options)
    return WorkflowConfig(command=command, options=options)


def _validate_unknown_fields(
    options: dict[str, Any],
    fields: dict[str, Field],
) -> None:
    for name in options:
        if name in fields:
            continue
        raise ConfigError(
            f"Config error: unknown field '{name}'.",
            suggestion=did_you_mean(name, fields, cutoff=0.65),
        )


def _validate_fields(
    command: CommandName,
    options: dict[str, Any],
    fields: dict[str, Field],
) -> None:
    for name, field in fields.items():
        if field.required and name not in options:
            raise ConfigError(
                f"Config error: missing required field '{name}' "
                f"for command '{command}'.",
                suggestion=(
                    f"Run `statconvert config init {command} --output {command}.toml` "
                    "to create a starter config."
                ),
            )
        if name not in options:
            continue
        value = options[name]
        if not field.validator(value):
            raise ConfigError(
                f"Config error: '{name}' must be {field.type_name}."
            )
        if field.non_blank and isinstance(value, str) and not value.strip():
            raise ConfigError(f"Config error: '{name}' must not be blank.")


def _validate_command_rules(command: CommandName, options: dict[str, Any]) -> None:
    for name in LIST_FIELDS_WITH_UNIQUE_VALUES:
        values = options.get(name)
        if isinstance(values, list):
            duplicates = _duplicates(values)
            if duplicates:
                joined = ", ".join(duplicates)
                raise ConfigError(
                    f"Config error: '{name}' contains duplicate values: {joined}."
                )

    if command == "compare":
        _validate_compare(options)
    elif command == "convert":
        if options.get("object") is not None and options.get("all_objects"):
            raise ConfigError(
                "Config error: 'object' and 'all_objects' cannot be used together."
            )
    elif command == "batch":
        _validate_batch(options)
    elif command == "report":
        preset = options.get("preset")
        if isinstance(preset, str) and preset.lower() not in REPORT_PRESETS:
            supported = ", ".join(sorted(REPORT_PRESETS))
            raise ConfigError(
                f"Config error: unsupported preset '{preset}'. Use one of: {supported}."
            )

        for name in (
            "frequency_top",
            "frequency_max_unique",
            "max_table_rows",
            "max_preview_values",
        ):
            value = options.get(name)
            if isinstance(value, int) and value <= 0:
                raise ConfigError(
                    f"Config error: '{name}' must be greater than 0."
                )

    report_format = options.get("report_format")
    allowed_formats = REPORT_FORMATS.get(command)
    if isinstance(report_format, str) and allowed_formats is not None:
        if report_format.lower() not in allowed_formats:
            supported = ", ".join(sorted(allowed_formats))
            raise ConfigError(
                f"Config error: unsupported report_format '{report_format}'. "
                f"Use one of: {supported}."
            )

    log_level = options.get("log_level")
    if isinstance(log_level, str) and log_level.lower() not in {
        "debug",
        "info",
        "warning",
        "error",
    }:
        raise ConfigError(
            "Config error: unsupported log_level. "
            "Use one of: debug, info, warning, error."
        )

    type_errors = options.get("type_errors")
    if isinstance(type_errors, str) and type_errors.lower() not in {
        "raise",
        "coerce",
        "ignore",
    }:
        raise ConfigError(
            "Config error: unsupported type_errors. "
            "Use one of: raise, coerce, ignore."
        )
    filter_mode = options.get("filter_mode")
    if isinstance(filter_mode, str) and filter_mode.lower() not in {"and", "or"}:
        raise ConfigError(
            "Config error: unsupported filter_mode. Use one of: and, or."
        )

    delimiter = options.get("csv_delimiter")
    decimal = options.get("csv_decimal")
    if isinstance(delimiter, str) and len(delimiter) != 1:
        raise ConfigError(
            "Config error: 'csv_delimiter' must be exactly one character."
        )
    if isinstance(decimal, str) and len(decimal) != 1:
        raise ConfigError(
            "Config error: 'csv_decimal' must be exactly one character."
        )
    if delimiter is not None and delimiter == decimal:
        raise ConfigError(
            "Config error: 'csv_delimiter' and 'csv_decimal' cannot be the same."
        )


def _validate_compare(options: dict[str, Any]) -> None:
    if options.get("object") is not None and (
        options.get("left_object") is not None
        or options.get("right_object") is not None
    ):
        raise ConfigError(
            "Config error: 'object' cannot be combined with "
            "'left_object' or 'right_object'."
        )
    tolerance = options.get("numeric_tolerance")
    if isinstance(tolerance, (int, float)) and tolerance < 0:
        raise ConfigError("Config error: 'numeric_tolerance' must be at least 0.")
    maximum = options.get("max_differences")
    if isinstance(maximum, int) and maximum <= 0:
        raise ConfigError("Config error: 'max_differences' must be greater than 0.")

    keys = set(options.get("key", []))
    ignored = set(options.get("ignore_columns", []))
    overlap = sorted(keys & ignored)
    if overlap:
        raise ConfigError(
            "Config error: key columns cannot also be ignored: "
            f"{', '.join(overlap)}"
        )
    sample_size = options.get("sample_size")
    if isinstance(sample_size, int) and sample_size <= 0:
        raise ConfigError("Config error: 'sample_size' must be greater than 0.")


def _validate_batch(options: dict[str, Any]) -> None:
    workers = options.get("workers")
    if isinstance(workers, int) and workers <= 0:
        raise ConfigError("Config error: 'workers' must be greater than 0.")

    selectors = [
        name
        for name in ("object", "object_manifest", "all_objects")
        if options.get(name) not in (None, False)
    ]
    if len(selectors) > 1:
        joined = ", ".join(f"'{name}'" for name in selectors)
        raise ConfigError(
            f"Config error: {joined} are mutually exclusive batch fields."
        )
    if options.get("preserve_structure") and options.get("flatten"):
        raise ConfigError(
            "Config error: 'preserve_structure' and 'flatten' cannot both be true."
        )

    output_format = options.get("to")
    if isinstance(output_format, str):
        resolved = resolve_format_info(output_format)
        if resolved is None or not can_write_format(output_format):
            writable = [
                extension.lstrip(".")
                for extension in supported_extensions()
                if can_write_format(extension)
            ]
            raise ConfigError(
                f"Config error: unsupported output format '{output_format}'.",
                suggestion=did_you_mean(output_format.lstrip("."), writable),
            )


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
