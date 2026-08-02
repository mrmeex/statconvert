from __future__ import annotations

import pytest

from statconvert.config import SUPPORTED_COMMANDS, create_template, validate_config
from statconvert.exceptions import ConfigError


def test_all_supported_commands_have_valid_templates() -> None:
    for command in SUPPORTED_COMMANDS:
        config = create_template(command)
        assert config.command == command


@pytest.mark.parametrize("command", SUPPORTED_COMMANDS)
def test_command_requires_its_input_fields(command: str) -> None:
    with pytest.raises(ConfigError, match="missing required field"):
        validate_config({"command": command})


def test_missing_command_is_friendly() -> None:
    with pytest.raises(ConfigError, match="missing required field 'command'"):
        validate_config({})


def test_unknown_command_lists_supported_commands() -> None:
    with pytest.raises(ConfigError, match="unsupported command 'export'"):
        validate_config({"command": "export"})


def test_unknown_field_suggests_close_match() -> None:
    with pytest.raises(ConfigError, match="Did you mean 'workers'"):
        validate_config(
            {
                "command": "batch",
                "input": "in",
                "output": "out",
                "to": "csv",
                "workerz": 2,
            }
        )


def test_wrong_basic_type_is_rejected() -> None:
    with pytest.raises(ConfigError, match="'overwrite' must be a boolean"):
        validate_config(
            {
                "command": "convert",
                "input": "in.csv",
                "output": "out.csv",
                "overwrite": "yes",
            }
        )


def test_blank_required_path_is_rejected() -> None:
    with pytest.raises(ConfigError, match="'input' must not be blank"):
        validate_config(
            {"command": "convert", "input": "  ", "output": "out.csv"}
        )


@pytest.mark.parametrize("workers", [0, -1])
def test_batch_workers_must_be_positive(workers: int) -> None:
    with pytest.raises(ConfigError, match="'workers' must be greater than 0"):
        validate_config(
            {
                "command": "batch",
                "input": "in",
                "output": "out",
                "to": "csv",
                "workers": workers,
            }
        )


def test_compare_numeric_tolerance_cannot_be_negative() -> None:
    with pytest.raises(ConfigError, match="numeric_tolerance.*at least 0"):
        validate_config(
            {
                "command": "compare",
                "left": "left.csv",
                "right": "right.csv",
                "numeric_tolerance": -0.1,
            }
        )


def test_compare_max_differences_must_be_positive() -> None:
    with pytest.raises(ConfigError, match="max_differences.*greater than 0"):
        validate_config(
            {
                "command": "compare",
                "left": "left.csv",
                "right": "right.csv",
                "max_differences": 0,
            }
        )


def test_compare_key_cannot_be_ignored() -> None:
    with pytest.raises(ConfigError, match="cannot also be ignored: id"):
        validate_config(
            {
                "command": "compare",
                "left": "left.csv",
                "right": "right.csv",
                "key": ["id"],
                "ignore_columns": ["id"],
            }
        )


def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(ConfigError, match="duplicate values: id"):
        validate_config(
            {
                "command": "compare",
                "left": "left.csv",
                "right": "right.csv",
                "key": ["id", "id"],
            }
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("object", "all_objects"),
        ("object", "object_manifest"),
        ("object_manifest", "all_objects"),
    ],
)
def test_batch_object_modes_are_mutually_exclusive(first: str, second: str) -> None:
    values: dict[str, object] = {
        "command": "batch",
        "input": "in",
        "output": "out",
        "to": "csv",
        first: True if first == "all_objects" else "value",
        second: True if second == "all_objects" else "value",
    }
    with pytest.raises(ConfigError, match="mutually exclusive"):
        validate_config(values)


def test_batch_structure_modes_cannot_both_be_true() -> None:
    with pytest.raises(ConfigError, match="cannot both be true"):
        validate_config(
            {
                "command": "batch",
                "input": "in",
                "output": "out",
                "to": "csv",
                "preserve_structure": True,
                "flatten": True,
            }
        )


def test_batch_output_format_uses_registry() -> None:
    with pytest.raises(ConfigError, match="unsupported output format"):
        validate_config(
            {
                "command": "batch",
                "input": "in",
                "output": "out",
                "to": "made-up",
            }
        )


def test_convert_object_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ConfigError, match="cannot be used together"):
        validate_config(
            {
                "command": "convert",
                "input": "in.xlsx",
                "output": "out.csv",
                "object": "Sheet1",
                "all_objects": True,
            }
        )
