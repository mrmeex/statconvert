"""Configuration helpers for StatConvert's dedicated logger."""

from __future__ import annotations

import logging as py_logging

from statconvert.logging.exceptions import LoggingSetupError
from statconvert.logging.models import LoggingOptions

LOGGER_NAME = "statconvert"
NORMAL_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEVELOPER_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | " "%(module)s:%(lineno)d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVELS = {
    "debug": py_logging.DEBUG,
    "info": py_logging.INFO,
    "warning": py_logging.WARNING,
    "error": py_logging.ERROR,
}


def parse_log_level(level: str) -> int:
    """Return the standard-library logging value for a supported level."""

    normalized = level.strip().lower()
    try:
        return _LEVELS[normalized]
    except KeyError as exc:
        supported_levels = "debug, info, warning or error"
        raise LoggingSetupError(
            f"Unsupported log level: {level}. Use {supported_levels}."
        ) from exc


def get_logger() -> py_logging.Logger:
    """Return the dedicated StatConvert logger without configuring it."""

    return py_logging.getLogger(LOGGER_NAME)


def setup_logging(options: LoggingOptions) -> py_logging.Logger:
    """Configure and return StatConvert's dedicated logger."""

    logger = get_logger()
    logger.propagate = False
    _reset_handlers(logger)
    _set_traceback_preference(logger, options.include_tracebacks)

    try:
        logger.setLevel(parse_log_level(options.level))
    except LoggingSetupError:
        logger.addHandler(py_logging.NullHandler())
        raise

    if not options.enabled:
        logger.addHandler(py_logging.NullHandler())
        return logger

    if options.log_file is None:
        logger.addHandler(py_logging.NullHandler())
        raise LoggingSetupError("File logging is enabled but no log file was provided.")

    try:
        options.log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = py_logging.FileHandler(
            options.log_file,
            mode="a" if options.append else "w",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        logger.addHandler(py_logging.NullHandler())
        raise LoggingSetupError(
            f"Unable to configure log file '{options.log_file}': {exc}"
        ) from exc

    formatter = py_logging.Formatter(
        DEVELOPER_FORMAT if options.developer else NORMAL_FORMAT,
        datefmt=DATE_FORMAT,
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def disable_logging() -> py_logging.Logger:
    """Reset StatConvert logging to a silent NullHandler configuration."""

    logger = get_logger()
    _reset_handlers(logger)
    logger.setLevel(py_logging.INFO)
    logger.propagate = False
    _set_traceback_preference(logger, True)
    logger.addHandler(py_logging.NullHandler())
    return logger


def _reset_handlers(logger: py_logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _set_traceback_preference(
    logger: py_logging.Logger,
    include_tracebacks: bool,
) -> None:
    setattr(logger, "_statconvert_include_tracebacks", include_tracebacks)
