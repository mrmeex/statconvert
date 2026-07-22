from __future__ import annotations

from copy import deepcopy

from statconvert.error_suggestions import did_you_mean
from statconvert.exceptions import ConfigError

from .models import SUPPORTED_COMMANDS, CommandName, WorkflowConfig
from .validation import validate_config


_TEMPLATES: dict[CommandName, dict[str, object]] = {
    "convert": {
        "command": "convert",
        "input": "./input.csv",
        "output": "./output.parquet",
        "overwrite": False,
        "create_dirs": True,
    },
    "transform": {
        "command": "transform",
        "input": "./input.csv",
        "output": "./output.parquet",
        "select": ["id", "date", "amount"],
        "drop": [],
        "rename": {"amount": "total_amount"},
        "filter": ["amount,gte,0"],
        "overwrite": False,
        "create_dirs": True,
    },
    "batch": {
        "command": "batch",
        "input": "./incoming",
        "output": "./converted",
        "to": "parquet",
        "recursive": True,
        "workers": 1,
        "overwrite": False,
        "create_dirs": True,
    },
    "compare": {
        "command": "compare",
        "left": "./old.csv",
        "right": "./new.csv",
        "key": ["id"],
        "ignore_columns": ["exported_at"],
        "numeric_tolerance": 0.001,
        "max_differences": 50,
    },
    "report": {
        "command": "report",
        "input": "./input.csv",
        "output": "./report.html",
        "preset": "quick",
        "overwrite": False,
        "create_dirs": True,
    },
    "collect": {
        "command": "collect",
        "manifest": "./manifest.csv",
        "output": "./workbook.xlsx",
        "base_dir": ".",
        "dry_run": False,
        "overwrite": False,
        "create_dirs": True,
    },
}


def create_template(command: str) -> WorkflowConfig:
    """Return a validated starter configuration for one command."""

    normalized = command.strip().lower()
    if normalized not in SUPPORTED_COMMANDS:
        supported = ", ".join(SUPPORTED_COMMANDS)
        raise ConfigError(
            f"Config error: unsupported command '{command}'. Use one of: {supported}.",
            suggestion=did_you_mean(normalized, SUPPORTED_COMMANDS),
        )
    return validate_config(deepcopy(_TEMPLATES[normalized]))
