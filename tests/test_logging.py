from __future__ import annotations

import logging as py_logging
from pathlib import Path
import re

import pytest
import typer

from statconvert.logging import (
    CommandLogContext,
    LoggingOptions,
    LoggingSetupError,
    command_logging_context,
    disable_logging,
    get_logger,
    exception_was_logged,
    log_user_error,
    parse_log_level,
    sanitize_parameters,
    setup_logging,
)


@pytest.fixture(autouse=True)
def reset_statconvert_logger():
    disable_logging()
    yield
    disable_logging()


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("debug", py_logging.DEBUG),
        ("info", py_logging.INFO),
        ("warning", py_logging.WARNING),
        ("error", py_logging.ERROR),
        ("DeBuG", py_logging.DEBUG),
        ("WARNING", py_logging.WARNING),
    ],
)
def test_parse_log_level(level: str, expected: int):
    assert parse_log_level(level) == expected


def test_parse_log_level_rejects_unsupported_level():
    with pytest.raises(
        LoggingSetupError,
        match=("Unsupported log level: verbose. " "Use debug, info, warning or error."),
    ):
        parse_log_level("verbose")


def test_setup_logging_disabled_uses_only_null_handler():
    logger = setup_logging(LoggingOptions())

    assert logger.name == "statconvert"
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], py_logging.NullHandler)


def test_setup_logging_requires_file_when_enabled():
    with pytest.raises(LoggingSetupError, match="no log file was provided"):
        setup_logging(LoggingOptions(enabled=True))


def test_setup_failure_replaces_an_existing_file_handler(tmp_path: Path):
    setup_logging(LoggingOptions(enabled=True, log_file=tmp_path / "run.log"))

    with pytest.raises(LoggingSetupError):
        setup_logging(LoggingOptions(level="verbose"))

    logger = get_logger()
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], py_logging.NullHandler)


def test_setup_logging_creates_parent_and_writes_file(tmp_path: Path):
    log_file = tmp_path / "nested" / "run.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))

    logger.info("Logging is ready")

    contents = log_file.read_text(encoding="utf-8")
    assert "| INFO | statconvert | Logging is ready" in contents


def test_setup_logging_overwrites_existing_file_by_default(tmp_path: Path):
    log_file = tmp_path / "run.log"
    log_file.write_text("old contents\n", encoding="utf-8")

    logger = setup_logging(
        LoggingOptions(enabled=True, log_file=log_file, append=False)
    )
    logger.info("new contents")

    contents = log_file.read_text(encoding="utf-8")
    assert "old contents" not in contents
    assert "new contents" in contents


def test_setup_logging_appends_to_existing_file(tmp_path: Path):
    log_file = tmp_path / "run.log"
    log_file.write_text("old contents\n", encoding="utf-8")

    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file, append=True))
    logger.info("new contents")

    contents = log_file.read_text(encoding="utf-8")
    assert "old contents" in contents
    assert "new contents" in contents


def test_repeated_setup_does_not_add_duplicate_handlers(tmp_path: Path):
    options = LoggingOptions(
        enabled=True,
        log_file=tmp_path / "run.log",
        append=True,
    )

    setup_logging(options)
    logger = setup_logging(options)

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], py_logging.FileHandler)


def test_developer_formatter_includes_module_and_line(tmp_path: Path):
    log_file = tmp_path / "developer.log"
    logger = setup_logging(
        LoggingOptions(
            enabled=True,
            log_file=log_file,
            developer=True,
        )
    )

    logger.info("Developer detail")

    contents = log_file.read_text(encoding="utf-8")
    assert re.search(
        r"\| statconvert \| test_logging:\d+ \| Developer detail",
        contents,
    )


def test_get_logger_returns_dedicated_logger():
    assert get_logger().name == "statconvert"


def test_disable_logging_removes_file_handlers(tmp_path: Path):
    log_file = tmp_path / "run.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))
    logger.info("before disable")

    logger = disable_logging()
    logger.info("after disable")

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], py_logging.NullHandler)
    contents = log_file.read_text(encoding="utf-8")
    assert "before disable" in contents
    assert "after disable" not in contents


def test_repeated_disable_logging_uses_one_null_handler():
    disable_logging()
    logger = disable_logging()

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], py_logging.NullHandler)


def test_sanitize_parameters_preserves_normal_values():
    parameters = {"input": "survey.sav", "rows": 10}

    sanitized = sanitize_parameters(parameters)

    assert sanitized == parameters
    assert sanitized is not parameters


@pytest.mark.parametrize(
    "key",
    ["password", "api_token", "client_secret", "api_key", "credential_id"],
)
def test_sanitize_parameters_masks_sensitive_keys(key: str):
    assert sanitize_parameters({key: "sensitive"}) == {key: "***"}


def test_sanitize_parameters_masks_nested_mappings():
    parameters = {
        "connection": {
            "user": "alice",
            "credentials": {"access_token": "sensitive"},
        }
    }

    assert sanitize_parameters(parameters) == {
        "connection": {
            "user": "alice",
            "credentials": "***",
        }
    }


def test_sanitize_parameters_preserves_supported_structured_values(tmp_path: Path):
    parameters = {
        "input_file": tmp_path / "input.csv",
        "columns": ["age", "name"],
        "shape": (2, 2),
        "options": {"strict": False, "limit": 10},
    }

    sanitized = sanitize_parameters(parameters)

    assert sanitized == parameters
    assert sanitized["input_file"] == tmp_path / "input.csv"


def test_sanitize_parameters_masks_secrets_inside_sequences():
    parameters = {
        "connections": [
            {"user": "alice", "password": "hidden"},
            ({"api_token": "hidden"},),
        ]
    }

    assert sanitize_parameters(parameters) == {
        "connections": [
            {"user": "alice", "password": "***"},
            ({"api_token": "***"},),
        ]
    }


def test_command_logging_context_records_success(tmp_path: Path):
    log_file = tmp_path / "success.log"
    logger = setup_logging(
        LoggingOptions(enabled=True, log_file=log_file, level="debug")
    )
    context = CommandLogContext(
        command="convert",
        parameters={"input": "input.sav", "api_token": "sensitive"},
    )

    with command_logging_context(logger, context):
        logger.debug("Inside command")

    contents = log_file.read_text(encoding="utf-8")
    assert "Command started: convert" in contents
    assert "Command parameters:" in contents
    assert "'api_token': '***'" in contents
    assert "sensitive" not in contents
    assert "Command completed: convert" in contents
    assert context.started_at is not None
    assert context.ended_at is not None
    assert context.duration_seconds is not None
    assert context.duration_seconds >= 0
    assert context.success is True


def test_command_logging_context_records_failure_and_reraises(tmp_path: Path):
    log_file = tmp_path / "failure.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))
    context = CommandLogContext(command="validate")

    captured_exception = None
    with pytest.raises(ValueError, match="invalid dataset") as raised:
        with command_logging_context(logger, context):
            raise ValueError("invalid dataset")
    captured_exception = raised.value

    contents = log_file.read_text(encoding="utf-8")
    assert "Command started: validate" in contents
    assert "Command failed: validate" in contents
    assert "ValueError: invalid dataset" in contents
    assert "Traceback (most recent call last)" in contents
    assert context.started_at is not None
    assert context.ended_at is not None
    assert context.duration_seconds is not None
    assert context.duration_seconds >= 0
    assert context.success is False
    assert exception_was_logged(captured_exception)


def test_command_logging_context_records_intentional_nonzero_exit(tmp_path: Path):
    log_file = tmp_path / "intentional-exit.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))
    context = CommandLogContext(command="validate")

    with pytest.raises(typer.Exit) as raised:
        with command_logging_context(logger, context):
            raise typer.Exit(1)

    contents = log_file.read_text(encoding="utf-8")
    assert raised.value.exit_code == 1
    assert contents.count("Command completed with non-zero outcome: validate") == 1
    assert "exit_code=1 | reason=intentional_exit" in contents
    assert "Command failed: validate" not in contents
    assert "Traceback (most recent call last)" not in contents
    assert context.success is False
    assert exception_was_logged(raised.value)


def test_command_logging_context_records_clean_zero_exit(tmp_path: Path):
    log_file = tmp_path / "clean-exit.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))
    context = CommandLogContext(command="formats")

    with pytest.raises(typer.Exit) as raised:
        with command_logging_context(logger, context):
            raise typer.Exit(0)

    contents = log_file.read_text(encoding="utf-8")
    assert raised.value.exit_code == 0
    assert contents.count("Command completed: formats") == 1
    assert "Command failed: formats" not in contents
    assert "Traceback (most recent call last)" not in contents
    assert context.success is True


def test_user_error_diagnostic_does_not_duplicate_logged_exception(tmp_path: Path):
    log_file = tmp_path / "failure.log"
    logger = setup_logging(LoggingOptions(enabled=True, log_file=log_file))

    with pytest.raises(ValueError) as raised:
        with command_logging_context(
            logger,
            CommandLogContext(command="convert"),
        ):
            raise ValueError("bad input")

    log_user_error("Bad input.", raised.value)

    contents = log_file.read_text(encoding="utf-8")
    assert contents.count("Traceback (most recent call last)") == 1
    assert contents.count("Command failed: convert") == 1
    assert "User-facing error:" not in contents


def test_user_error_diagnostic_logs_unhandled_exception_once(tmp_path: Path):
    log_file = tmp_path / "failure.log"
    setup_logging(LoggingOptions(enabled=True, log_file=log_file))

    try:
        raise RuntimeError("diagnostic failure")
    except RuntimeError as exc:
        log_user_error("Operation failed.", exc)
        log_user_error("Operation failed.", exc)

    contents = log_file.read_text(encoding="utf-8")
    assert contents.count("Traceback (most recent call last)") == 1
    assert contents.count("User-facing error: Operation failed.") == 1


def test_user_error_diagnostic_is_silent_without_configured_handler(capsys):
    logger = get_logger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = True

    log_user_error("Quiet failure.", RuntimeError("not configured"))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_command_failure_can_omit_traceback(tmp_path: Path):
    log_file = tmp_path / "failure.log"
    logger = setup_logging(
        LoggingOptions(
            enabled=True,
            log_file=log_file,
            include_tracebacks=False,
        )
    )

    with pytest.raises(RuntimeError):
        with command_logging_context(
            logger,
            CommandLogContext(command="report"),
        ):
            raise RuntimeError("report failed")

    contents = log_file.read_text(encoding="utf-8")
    assert "RuntimeError: report failed" in contents
    assert "Traceback (most recent call last)" not in contents


def test_command_context_is_safe_when_logging_is_disabled():
    logger = disable_logging()
    context = CommandLogContext(command="formats", parameters={"api_key": "hidden"})

    with command_logging_context(logger, context):
        logger.info("silent")

    assert context.success is True
    assert context.started_at is not None
    assert context.ended_at is not None
    assert context.duration_seconds is not None


def test_reconfigured_log_files_are_isolated(tmp_path: Path):
    first_log = tmp_path / "first.log"
    second_log = tmp_path / "second.log"

    first_logger = setup_logging(
        LoggingOptions(enabled=True, log_file=first_log, append=True)
    )
    first_logger.info("first only")
    second_logger = setup_logging(
        LoggingOptions(enabled=True, log_file=second_log, append=True)
    )
    second_logger.info("second only")

    assert "first only" in first_log.read_text(encoding="utf-8")
    assert "second only" not in first_log.read_text(encoding="utf-8")
    assert "second only" in second_log.read_text(encoding="utf-8")
    assert "first only" not in second_log.read_text(encoding="utf-8")
