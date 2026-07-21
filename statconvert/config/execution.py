from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from statconvert.exceptions import ConfigError

from .models import WorkflowConfig


ConfigRunner = Callable[..., None]
RUNNABLE_COMMANDS = (
    "convert",
    "transform",
    "batch",
    "compare",
    "report",
    "collect",
)


@dataclass(frozen=True)
class ConfigExecution:
    """One validated command invocation prepared from a workflow config."""

    command: str
    arguments: dict[str, Any]


def prepare_execution(config: WorkflowConfig) -> ConfigExecution:
    """Map public config fields to an existing command callback signature."""

    if config.command == "convert":
        arguments = _convert_arguments(config.options)
    elif config.command == "transform":
        arguments = _transform_arguments(config.options)
    elif config.command == "batch":
        arguments = _batch_arguments(config.options)
    elif config.command == "compare":
        arguments = _compare_arguments(config.options)
    elif config.command == "report":
        arguments = _report_arguments(config.options)
    elif config.command == "collect":
        arguments = _collect_arguments(config.options)
    else:
        raise ConfigError(f"Config run is not supported for '{config.command}'.")
    return ConfigExecution(command=config.command, arguments=arguments)


def execute_config(
    config: WorkflowConfig,
    runners: Mapping[str, ConfigRunner],
) -> None:
    """Execute a config through an existing application command runner."""

    execution = prepare_execution(config)
    runner = runners.get(execution.command)
    if runner is None:
        raise ConfigError(
            f"No config execution runner is registered for '{execution.command}'."
        )
    runner(**execution.arguments)


def _convert_arguments(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_file": options["input"],
        "output_file": options["output"],
        "object_selector": options.get("object"),
        "all_objects": options.get("all_objects", False),
        "overwrite": options.get("overwrite", False),
        "create_dirs": options.get("create_dirs", False),
        "validate_inputs": options.get("validate", False),
        "strict_validation": options.get("strict_validation", False),
        "input_encoding": options.get("input_encoding"),
        "output_encoding": options.get("output_encoding"),
        "csv_delimiter": options.get("csv_delimiter"),
        "csv_decimal": options.get("csv_decimal"),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
    }


def _transform_arguments(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_file": options["input"],
        "output_file": options["output"],
        "object_selector": options.get("object"),
        "extra_columns": None,
        "select": options.get("select"),
        "drop": options.get("drop"),
        "rename": _rename_items(options.get("rename")),
        "type_items": options.get("type"),
        "type_errors": options.get("type_errors", "raise"),
        "datetime_format": options.get("datetime_format"),
        "filter_items": options.get("filter"),
        "filter_mode": options.get("filter_mode", "and"),
        "recode": options.get("recode"),
        "recode_default": options.get("recode_default"),
        "update_value_labels": options.get("update_value_labels", True),
        "ignore_missing_columns": options.get("ignore_missing_columns", False),
        "reset_index": options.get("reset_index", True),
        "overwrite": options.get("overwrite", False),
        "create_dirs": options.get("create_dirs", False),
        "dry_run": options.get("dry_run", False),
        "validate_inputs": options.get("validate", False),
        "strict_validation": options.get("strict_validation", False),
        "input_encoding": options.get("input_encoding"),
        "output_encoding": options.get("output_encoding"),
        "csv_delimiter": options.get("csv_delimiter"),
        "csv_decimal": options.get("csv_decimal"),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
    }


def _batch_arguments(options: dict[str, Any]) -> dict[str, Any]:
    preserve_structure = options.get("preserve_structure", True)
    if options.get("flatten"):
        preserve_structure = False
    return {
        "input_path": options["input"],
        "output_path": options["output"],
        "to_format": options["to"],
        "object_selector": options.get("object"),
        "object_manifest": options.get("object_manifest"),
        "all_objects": options.get("all_objects", False),
        "transform_items": options.get("transform", False),
        "select": options.get("select"),
        "drop": options.get("drop"),
        "rename": _rename_items(options.get("rename")),
        "type_items": options.get("type"),
        "type_errors": options.get("type_errors", "raise"),
        "datetime_format": options.get("datetime_format"),
        "filter_items": options.get("filter"),
        "filter_mode": options.get("filter_mode", "and"),
        "recode": options.get("recode"),
        "recode_default": options.get("recode_default"),
        "update_value_labels": options.get("update_value_labels", True),
        "ignore_missing_columns": options.get("ignore_missing_columns", False),
        "reset_index": options.get("reset_index", True),
        "recursive": options.get("recursive", False),
        "overwrite": options.get("overwrite", False),
        "create_dirs": options.get("create_dirs", False),
        "preserve_structure": preserve_structure,
        "include_unsupported": options.get("include_unsupported", True),
        "patterns": options.get("patterns"),
        "exclude_patterns": options.get("exclude_patterns"),
        "dry_run": options.get("dry_run", False),
        "fail_fast": options.get("fail_fast", False),
        "allow_blocked": options.get("allow_blocked", False),
        "json_output": options.get("json", False),
        "report": options.get("report"),
        "report_format": options.get("report_format"),
        "no_progress": options.get("no_progress", False),
        "workers": options.get("workers", 1),
        "validate_inputs": options.get("validate", False),
        "strict_validation": options.get("strict_validation", False),
        "input_encoding": options.get("input_encoding"),
        "output_encoding": options.get("output_encoding"),
        "csv_delimiter": options.get("csv_delimiter"),
        "csv_decimal": options.get("csv_decimal"),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
        "_config_option_names": frozenset(options),
    }


def _compare_arguments(options: dict[str, Any]) -> dict[str, Any]:
    key = options.get("key")
    return {
        "left_file": options["left"],
        "right_file": options["right"],
        "object_selector": options.get("object"),
        "left_object_selector": options.get("left_object"),
        "right_object_selector": options.get("right_object"),
        "values": options.get("values", True),
        "sample_size": options.get("sample_size"),
        "columns": options.get("columns"),
        "ignore_columns": options.get("ignore_columns"),
        "numeric_tolerance": options.get("numeric_tolerance", 0.0),
        "key": ",".join(key) if isinstance(key, list) else key,
        "max_differences": options.get("max_differences", 50),
        "json_output": options.get("json", False),
        "strict": options.get("strict", False),
        "report": options.get("report"),
        "report_format": options.get("report_format"),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
    }


def _report_arguments(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_file": options["input"],
        "object_selector": options.get("object"),
        "output_file": options["output"],
        "output_format": options.get("report_format"),
        "overwrite": options.get("overwrite", False),
        "create_dirs": options.get("create_dirs", False),
        "preset": options.get("preset"),
        "sections": options.get("sections"),
        "no_summary": options.get("no_summary", False),
        "no_schema": options.get("no_schema", False),
        "no_metadata": options.get("no_metadata", False),
        "no_labels": options.get("no_labels", False),
        "no_missing": options.get("no_missing", False),
        "no_describe": options.get("no_describe", False),
        "frequencies": options.get("frequencies", False),
        "no_validation": options.get("no_validation", False),
        "columns": options.get("columns"),
        "frequency_top": options.get("frequency_top", 20),
        "frequency_include_missing": options.get(
            "frequency_include_missing", False
        ),
        "frequency_max_unique": options.get("frequency_max_unique"),
        "max_table_rows": options.get("max_table_rows", 1000),
        "max_preview_values": options.get("max_preview_values", 5),
        "target_format": options.get("target_format"),
        "strict_validation": options.get("strict_validation", False),
        "json_output": options.get("json", False),
        "quiet": options.get("quiet", False),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
    }


def _collect_arguments(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest": options["manifest"],
        "output_file": options["output"],
        "base_dir": options.get("base_dir"),
        "overwrite": options.get("overwrite", False),
        "create_dirs": options.get("create_dirs", False),
        "dry_run": options.get("dry_run", False),
        "validate_inputs": options.get("validate", False),
        "strict_validation": options.get("strict_validation", False),
        "input_encoding": options.get("input_encoding"),
        "output_encoding": options.get("output_encoding"),
        "csv_delimiter": options.get("csv_delimiter"),
        "csv_decimal": options.get("csv_decimal"),
        "log_file": options.get("log"),
        "log_level": options.get("log_level", "info"),
        "log_append": options.get("log_append", False),
        "developer_log": options.get("developer_log", False),
        "write_config_file": None,
        "overwrite_config": False,
    }


def _rename_items(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError("Config error: 'rename' must be a table of string values.")
    return [f"{old}={new}" for old, new in value.items()]
