"""CLI-facing helpers for optional per-command file logging."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging as py_logging
from pathlib import Path
from typing import Any

from statconvert.logging.context import command_logging_context
from statconvert.logging.models import CommandLogContext, LoggingOptions
from statconvert.logging.setup import disable_logging, setup_logging


def build_logging_options(
    log_file: str | Path | None = None,
    log_level: str = "info",
    log_append: bool = False,
    developer_log: bool = False,
) -> LoggingOptions:
    """Build internal logging options from CLI values."""

    resolved_log_file = Path(log_file) if log_file is not None else None
    return LoggingOptions(
        enabled=resolved_log_file is not None,
        log_file=resolved_log_file,
        level=log_level,
        developer=developer_log,
        append=log_append,
    )


@contextmanager
def command_log_wrapper(
    command: str,
    parameters: dict[str, Any],
    log_file: str | Path | None = None,
    log_level: str = "info",
    log_append: bool = False,
    developer_log: bool = False,
) -> Iterator[py_logging.Logger]:
    """Configure logging and record one CLI command lifecycle."""

    options = build_logging_options(
        log_file=log_file,
        log_level=log_level,
        log_append=log_append,
        developer_log=developer_log,
    )
    logger = setup_logging(options)
    context = CommandLogContext(command=command, parameters=parameters)

    try:
        with command_logging_context(logger, context):
            yield logger
    finally:
        disable_logging()
