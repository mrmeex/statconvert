"""Command lifecycle helpers for StatConvert logging."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import logging as py_logging
from time import perf_counter
from typing import Any

import typer

from statconvert.logging.diagnostics import mark_exception_logged
from statconvert.logging.models import CommandLogContext

_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
)


def sanitize_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of command parameters with likely secrets masked."""

    return {key: _sanitize_value(key, value) for key, value in parameters.items()}


def log_command_start(
    logger: py_logging.Logger,
    context: CommandLogContext,
) -> None:
    """Log the start and sanitized parameters of a command."""

    logger.info("Command started: %s", context.command)
    if context.parameters:
        logger.info("Command parameters: %s", sanitize_parameters(context.parameters))


def log_command_success(
    logger: py_logging.Logger,
    context: CommandLogContext,
) -> None:
    """Log successful command completion."""

    logger.info(
        "Command completed: %s (%.3f seconds)",
        context.command,
        context.duration_seconds or 0.0,
    )


def log_command_failure(
    logger: py_logging.Logger,
    context: CommandLogContext,
    exc: BaseException,
) -> None:
    """Log failed command completion and optional traceback details."""

    include_traceback = bool(getattr(logger, "_statconvert_include_tracebacks", True))
    logger.error(
        "Command failed: %s (%.3f seconds): %s: %s",
        context.command,
        context.duration_seconds or 0.0,
        type(exc).__name__,
        exc,
        exc_info=include_traceback,
    )
    mark_exception_logged(exc)


def log_command_exit(
    logger: py_logging.Logger,
    context: CommandLogContext,
    exit_code: int,
) -> None:
    """Log a deliberate non-zero CLI exit without a traceback."""

    logger.warning(
        "Command completed with non-zero outcome: %s (%.3f seconds) | "
        "exit_code=%s | reason=intentional_exit",
        context.command,
        context.duration_seconds or 0.0,
        exit_code,
    )


@contextmanager
def command_logging_context(
    logger: py_logging.Logger,
    context: CommandLogContext,
) -> Iterator[CommandLogContext]:
    """Record and log the lifecycle of a command invocation."""

    context.started_at = datetime.now(timezone.utc)
    started_counter = perf_counter()
    log_command_start(logger, context)

    try:
        yield context
    except typer.Exit as exc:
        exit_code = int(exc.exit_code)
        _finish_context(context, started_counter, success=exit_code == 0)
        if exit_code == 0:
            log_command_success(logger, context)
        else:
            log_command_exit(logger, context, exit_code)
        mark_exception_logged(exc)
        raise
    except BaseException as exc:
        _finish_context(context, started_counter, success=False)
        log_command_failure(logger, context, exc)
        raise
    else:
        _finish_context(context, started_counter, success=True)
        log_command_success(logger, context)


def _finish_context(
    context: CommandLogContext,
    started_counter: float,
    *,
    success: bool,
) -> None:
    context.ended_at = datetime.now(timezone.utc)
    context.duration_seconds = perf_counter() - started_counter
    context.success = success


def _sanitize_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return "***"
    if isinstance(value, Mapping):
        return {
            nested_key: _sanitize_value(str(nested_key), nested_value)
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_nested_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_nested_value(item) for item in value)
    return value


def _sanitize_nested_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            nested_key: _sanitize_value(str(nested_key), nested_value)
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_nested_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_nested_value(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
