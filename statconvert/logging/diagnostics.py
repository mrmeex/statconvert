"""Safe developer-diagnostic helpers for StatConvert."""

from __future__ import annotations

import logging as py_logging

from statconvert.logging.setup import get_logger

_LOGGED_EXCEPTION_ATTRIBUTE = "_statconvert_diagnostic_logged"


def log_exception(
    exc: BaseException,
    message: str | None = None,
) -> None:
    """Log an exception once through the dedicated StatConvert logger."""

    if exception_was_logged(exc):
        return

    logger = get_logger()
    if not _has_diagnostic_handler(logger):
        return

    include_traceback = bool(getattr(logger, "_statconvert_include_tracebacks", True))
    diagnostic_message = message or "Unhandled exception"
    logger.error(
        "%s: %s: %s",
        diagnostic_message,
        type(exc).__name__,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__) if include_traceback else None,
    )
    mark_exception_logged(exc)


def log_user_error(
    message: str,
    exc: BaseException | None = None,
) -> None:
    """Record a user-facing error without printing or duplicating a traceback."""

    if exc is not None:
        log_exception(exc, message=f"User-facing error: {message}")
        return

    logger = get_logger()
    if _has_diagnostic_handler(logger):
        logger.error("User-facing error: %s", message)


def log_warning(message: str) -> None:
    """Record a diagnostic warning without printing it."""

    logger = get_logger()
    if _has_diagnostic_handler(logger):
        logger.warning("%s", message)


def log_command_outcome(command: str, exit_code: int, reason: str) -> None:
    """Record a deliberate command exit without treating it as a crash."""

    logger = get_logger()
    if not _has_diagnostic_handler(logger):
        return

    logger.warning(
        "Command outcome: %s | exit_code=%s | reason=%s",
        command,
        exit_code,
        reason,
    )


def mark_exception_logged(exc: BaseException) -> None:
    """Mark an exception so later presentation layers do not log it again."""

    try:
        setattr(exc, _LOGGED_EXCEPTION_ATTRIBUTE, True)
    except (AttributeError, TypeError):
        pass


def exception_was_logged(exc: BaseException) -> bool:
    """Return whether the exception already produced diagnostic output."""

    return bool(getattr(exc, _LOGGED_EXCEPTION_ATTRIBUTE, False))


def _has_diagnostic_handler(logger: py_logging.Logger) -> bool:
    return any(
        not isinstance(handler, py_logging.NullHandler) for handler in logger.handlers
    )
