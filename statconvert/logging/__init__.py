"""Internal structured logging foundation for StatConvert."""

from statconvert.logging.context import (
    command_logging_context,
    log_command_failure,
    log_command_exit,
    log_command_start,
    log_command_success,
    sanitize_parameters,
)
from statconvert.logging.cli import build_logging_options, command_log_wrapper
from statconvert.logging.exceptions import LoggingSetupError
from statconvert.logging.diagnostics import (
    exception_was_logged,
    log_command_outcome,
    log_exception,
    log_user_error,
    log_warning,
)
from statconvert.logging.models import CommandLogContext, LogLevel, LoggingOptions
from statconvert.logging.setup import (
    disable_logging,
    get_logger,
    parse_log_level,
    setup_logging,
)

__all__ = [
    "CommandLogContext",
    "LogLevel",
    "LoggingOptions",
    "LoggingSetupError",
    "command_logging_context",
    "build_logging_options",
    "command_log_wrapper",
    "disable_logging",
    "get_logger",
    "exception_was_logged",
    "log_command_outcome",
    "log_command_failure",
    "log_command_exit",
    "log_command_start",
    "log_command_success",
    "log_exception",
    "log_user_error",
    "log_warning",
    "parse_log_level",
    "sanitize_parameters",
    "setup_logging",
]
