from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.inspection import ValidationIssue

runner = CliRunner()

PUBLIC_COMMANDS = [
    "convert",
    "transform",
    "formats",
    "backends",
    "capabilities",
    "info",
    "peek",
    "schema",
    "labels",
    "metadata",
    "summary",
    "describe",
    "frequencies",
    "missing",
    "validate",
    "batch",
    "compare",
    "report",
]


@pytest.mark.parametrize("command", PUBLIC_COMMANDS)
def test_public_command_help_has_consistent_logging_options(command: str):
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0, result.output
    assert "--log" in result.output
    assert "--log-level" in result.output
    assert "--log-append" in result.output
    assert "--developer-log" in result.output


def test_convert_log_writes_lifecycle_and_parameters(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    log_file = tmp_path / "logs" / "convert.log"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--log",
            str(log_file),
            "--log-level",
            "debug",
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert output_file.exists()
    assert "Command started: convert" in contents
    assert "Command parameters:" in contents
    assert input_file.name in contents
    assert output_file.name in contents
    assert "Command completed: convert" in contents
    assert "Conversion result:" in contents
    assert re.search(r"Command completed: convert \(\d+\.\d{3} seconds\)", contents)


def test_convert_without_log_creates_no_log_file(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")

    result = runner.invoke(
        app,
        ["convert", str(input_file), str(tmp_path / "output.json")],
    )

    assert result.exit_code == 0
    assert list(tmp_path.glob("*.log")) == []


def test_invalid_log_level_is_friendly_and_stops_command(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--log",
            str(tmp_path / "run.log"),
            "--log-level",
            "verbose",
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported log level: verbose" in result.output
    assert not output_file.exists()


def test_convert_failure_writes_exception_and_traceback(tmp_path: Path):
    missing_input = tmp_path / "missing.csv"
    log_file = tmp_path / "failure.log"

    result = runner.invoke(
        app,
        [
            "convert",
            str(missing_input),
            str(tmp_path / "output.json"),
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Command failed: convert" in contents
    assert "Input file does not exist" in contents
    assert contents.count("Traceback (most recent call last)") == 1
    assert "Traceback (most recent call last)" not in result.output


def test_log_file_does_not_change_normal_terminal_output(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    second_file = _write_csv(tmp_path / "second.csv")

    normal = runner.invoke(app, ["compare", str(input_file), str(second_file)])
    logged = runner.invoke(
        app,
        [
            "compare",
            str(input_file),
            str(second_file),
            "--log",
            str(tmp_path / "compare.log"),
        ],
    )

    assert normal.exit_code == logged.exit_code == 0
    assert logged.output == normal.output
    assert "Command started" not in logged.output
    assert "Logging enabled" not in logged.output


def test_unlogged_ui_error_does_not_emit_developer_diagnostics(tmp_path: Path):
    result = runner.invoke(app, ["info", str(tmp_path / "missing.csv")])

    assert result.exit_code == 1
    assert "User-facing error:" not in result.output
    assert "Traceback (most recent call last)" not in result.output


def test_log_append_and_overwrite_modes(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    log_file = tmp_path / "convert.log"
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"
    third_output = tmp_path / "third.json"

    _run_convert(input_file, first_output, log_file)
    _run_convert(input_file, second_output, log_file)
    overwritten = log_file.read_text(encoding="utf-8")
    _run_convert(input_file, third_output, log_file, append=True)
    appended = log_file.read_text(encoding="utf-8")

    assert first_output.name not in overwritten
    assert second_output.name in overwritten
    assert second_output.name in appended
    assert third_output.name in appended
    assert appended.count("Command started: convert") == 2


def test_developer_log_changes_file_only(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    second_file = _write_csv(tmp_path / "second.csv")

    normal = runner.invoke(
        app,
        ["compare", str(input_file), str(second_file)],
    )
    developer = runner.invoke(
        app,
        [
            "compare",
            str(input_file),
            str(second_file),
            "--log",
            str(tmp_path / "developer.log"),
            "--developer-log",
        ],
    )

    contents = (tmp_path / "developer.log").read_text(encoding="utf-8")
    assert developer.exit_code == 0
    assert developer.output == normal.output
    assert re.search(r"\| context:\d+ \| Command started: compare", contents)


def test_developer_failure_keeps_details_in_log_only(tmp_path: Path):
    log_file = tmp_path / "developer-failure.log"

    result = runner.invoke(
        app,
        [
            "convert",
            str(tmp_path / "missing.csv"),
            str(tmp_path / "output.json"),
            "--log",
            str(log_file),
            "--developer-log",
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Traceback (most recent call last)" not in result.output
    assert re.search(r"\| context:\d+ \| Command failed: convert", contents)
    assert contents.count("Traceback (most recent call last)") == 1


def test_existing_debug_option_still_controls_terminal_tracebacks(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "--debug",
            "convert",
            str(tmp_path / "missing.csv"),
            str(tmp_path / "output.json"),
        ],
    )

    assert result.exit_code == 1
    assert "Traceback (most recent call last)" in result.output


def test_operational_commands_create_log_files(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    second_file = _write_csv(tmp_path / "second.csv")
    commands = [
        (
            "transform",
            [
                "transform",
                str(input_file),
                str(tmp_path / "transformed.json"),
            ],
        ),
        (
            "batch",
            [
                "batch",
                str(input_file),
                str(tmp_path / "batch-output"),
                "--to",
                "json",
                    "--dry-run",
                    "--create-dirs",
            ],
        ),
        (
            "compare",
            ["compare", str(input_file), str(second_file)],
        ),
        (
            "report",
            [
                "report",
                str(input_file),
                "--output",
                str(tmp_path / "report.html"),
                "--quiet",
            ],
        ),
        (
            "validate",
            ["validate", str(input_file)],
        ),
    ]

    for command, arguments in commands:
        log_file = tmp_path / f"{command}.log"
        result = runner.invoke(app, [*arguments, "--log", str(log_file)])
        contents = log_file.read_text(encoding="utf-8")
        assert result.exit_code == 0, result.output
        assert f"Command started: {command}" in contents
        assert f"Command completed: {command}" in contents
        expected_result = {
            "transform": "Transformation result:",
            "batch": "Batch plan result:",
            "compare": "Comparison result:",
            "report": "Report result:",
            "validate": "Validation result:",
        }[command]
        assert expected_result in contents


def test_discovery_and_inspection_commands_create_logs(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    commands = [
        ("formats", ["formats"]),
        ("backends", ["backends"]),
        ("capabilities", ["capabilities", "csv"]),
        ("info", ["info", str(input_file)]),
        ("peek", ["peek", str(input_file), "--rows", "1"]),
        ("schema", ["schema", str(input_file)]),
        ("labels", ["labels", str(input_file)]),
        ("metadata", ["metadata", str(input_file)]),
        ("summary", ["summary", str(input_file)]),
        ("describe", ["describe", str(input_file)]),
        ("frequencies", ["frequencies", str(input_file)]),
        ("missing", ["missing", str(input_file)]),
    ]

    for command, arguments in commands:
        log_file = tmp_path / f"{command}.log"
        result = runner.invoke(app, [*arguments, "--log", str(log_file)])

        assert result.exit_code == 0, result.output
        contents = log_file.read_text(encoding="utf-8")
        assert f"Command started: {command}" in contents
        assert f"Command completed: {command}" in contents


def test_info_log_contains_dataset_boundary_summary(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    log_file = tmp_path / "info.log"

    result = runner.invoke(
        app,
        ["info", str(input_file), "--log", str(log_file)],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "input_file" in contents
    assert input_file.name in contents
    assert "Dataset read:" in contents
    assert "rows=2 columns=2" in contents


def test_summary_json_remains_valid_with_logging(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    log_file = tmp_path / "summary.log"

    result = runner.invoke(
        app,
        ["summary", str(input_file), "--json", "--log", str(log_file)],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["row_count"] == 2
    assert "Command started" not in result.output
    assert "Summary result:" in log_file.read_text(encoding="utf-8")


def test_inspection_failure_is_logged_once_and_terminal_stays_friendly(
    tmp_path: Path,
):
    log_file = tmp_path / "info-failure.log"

    result = runner.invoke(
        app,
        ["info", str(tmp_path / "missing.csv"), "--log", str(log_file)],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert contents.count("Command failed: info") == 1
    assert "User-facing error:" not in contents
    assert "Traceback (most recent call last)" in contents
    assert "Traceback (most recent call last)" not in result.output


def test_json_commands_remain_valid_with_logging(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    second_file = _write_csv(tmp_path / "second.csv")

    compare_result = runner.invoke(
        app,
        [
            "compare",
            str(input_file),
            str(second_file),
            "--json",
            "--log",
            str(tmp_path / "compare.log"),
        ],
    )
    report_result = runner.invoke(
        app,
        [
            "report",
            str(input_file),
            "--output",
            str(tmp_path / "report.html"),
            "--json",
            "--log",
            str(tmp_path / "report.log"),
        ],
    )
    validate_result = runner.invoke(
        app,
        [
            "validate",
            str(input_file),
            "--json",
            "--log",
            str(tmp_path / "validate.log"),
        ],
    )

    assert json.loads(compare_result.output)["shape"]["rows_match"] is True
    assert json.loads(report_result.output)["format"] == "html"
    assert isinstance(json.loads(validate_result.output), list)


@pytest.mark.parametrize(
    "command",
    ["summary", "describe", "frequencies", "missing"],
)
def test_inspection_json_stdout_contains_no_log_records(
    tmp_path: Path,
    command: str,
):
    input_file = _write_csv(tmp_path / "input.csv")
    log_file = tmp_path / f"{command}.log"

    result = runner.invoke(
        app,
        [command, str(input_file), "--json", "--log", str(log_file)],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert isinstance(payload, dict if command == "summary" else list)
    assert "Command started" not in result.output
    assert "| INFO | statconvert |" not in result.output
    assert f"Command started: {command}" in log_file.read_text(encoding="utf-8")


def test_intentional_nonzero_result_logs_completion_not_failure(tmp_path: Path):
    left_file = _write_csv(tmp_path / "left.csv")
    right_file = tmp_path / "right.csv"
    right_file.write_text("id,name\n1,Ada\n2,Linus\n", encoding="utf-8")
    log_file = tmp_path / "compare.log"

    result = runner.invoke(
        app,
        [
            "compare",
            str(left_file),
            str(right_file),
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Command outcome: compare | exit_code=1" in contents
    assert "Command completed: compare" in contents
    assert "Command failed: compare" not in contents
    assert "Traceback (most recent call last)" not in contents


def test_validate_and_batch_intentional_exits_have_no_tracebacks(tmp_path: Path):
    duplicate_file = tmp_path / "duplicates.csv"
    duplicate_file.write_text("id,name\n1,Ada\n1,Ada\n", encoding="utf-8")
    validate_log = tmp_path / "validate.log"

    validate_result = runner.invoke(
        app,
        [
            "validate",
            str(duplicate_file),
            "--strict",
            "--log",
            str(validate_log),
        ],
    )

    input_file = _write_csv(tmp_path / "batch" / "input.csv")
    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    (output_dir / "input.json").write_text("existing", encoding="utf-8")
    batch_log = tmp_path / "batch.log"
    batch_result = runner.invoke(
        app,
        [
            "batch",
            str(input_file.parent),
            str(output_dir),
            "--to",
            "json",
            "--dry-run",
            "--log",
            str(batch_log),
        ],
    )

    validate_contents = validate_log.read_text(encoding="utf-8")
    batch_contents = batch_log.read_text(encoding="utf-8")
    assert validate_result.exit_code == 1
    assert "Command outcome: validate | exit_code=1" in validate_contents
    assert "Traceback (most recent call last)" not in validate_contents
    assert batch_result.exit_code == 0
    assert "Command completed: batch" in batch_contents
    assert "Traceback (most recent call last)" not in batch_contents


def test_commands_in_same_process_do_not_duplicate_or_cross_write(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    first_log = tmp_path / "first.log"
    second_log = tmp_path / "second.log"

    _run_convert(input_file, tmp_path / "first.json", first_log)
    _run_convert(input_file, tmp_path / "second.json", second_log)

    assert first_log.read_text(encoding="utf-8").count("Command started: convert") == 1
    assert second_log.read_text(encoding="utf-8").count("Command started: convert") == 1
    assert "second.json" not in first_log.read_text(encoding="utf-8")


def test_convert_existing_output_logs_one_failure(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    output_file.write_text("existing", encoding="utf-8")
    log_file = tmp_path / "convert-existing.log"

    result = runner.invoke(
        app,
        ["convert", str(input_file), str(output_file), "--log", str(log_file)],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Use --overwrite to replace it" in result.output
    assert "Traceback (most recent call last)" not in result.output
    assert contents.count("Command failed: convert") == 1
    assert "OutputPathError" in contents


@pytest.mark.parametrize("command", ["convert", "transform"])
def test_validation_block_is_logged_as_intentional_outcome(
    monkeypatch,
    tmp_path: Path,
    command: str,
):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / f"{command}.json"
    log_file = tmp_path / f"{command}-validation.log"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [
            ValidationIssue("error", "blocked", "Controlled validation error")
        ],
    )

    result = runner.invoke(
        app,
        [
            command,
            str(input_file),
            str(output_file),
            "--validate",
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Validation failed. Output was not written." in result.output
    assert not output_file.exists()
    assert f"Command outcome: {command} | exit_code=1 | reason=validation_failed" in contents
    assert "Output was not written." in contents
    assert f"Command completed: {command}" in contents
    assert f"Command failed: {command}" not in contents
    assert "Traceback (most recent call last)" not in contents
    assert "ValidationFailedError" not in contents


@pytest.mark.parametrize("command", ["convert", "transform"])
def test_strict_validation_warning_is_logged_as_intentional_outcome(
    monkeypatch,
    tmp_path: Path,
    command: str,
):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / f"{command}.json"
    log_file = tmp_path / f"{command}-strict-validation.log"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [
            ValidationIssue("warning", "warning", "Controlled validation warning")
        ],
    )

    result = runner.invoke(
        app,
        [
            command,
            str(input_file),
            str(output_file),
            "--strict-validation",
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert not output_file.exists()
    assert (
        f"Command outcome: {command} | exit_code=1 "
        "| reason=strict_validation_failed"
    ) in contents
    assert f"Command failed: {command}" not in contents
    assert "Traceback (most recent call last)" not in contents


@pytest.mark.parametrize("command", ["convert", "transform"])
def test_non_strict_validation_warning_still_completes(
    monkeypatch,
    tmp_path: Path,
    command: str,
):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / f"{command}.json"
    log_file = tmp_path / f"{command}-warning.log"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [
            ValidationIssue("warning", "warning", "Controlled validation warning")
        ],
    )

    result = runner.invoke(
        app,
        [
            command,
            str(input_file),
            str(output_file),
            "--validate",
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 0, result.output
    assert output_file.exists()
    assert f"Command completed: {command}" in contents
    assert f"Command outcome: {command} | exit_code=1" not in contents
    assert f"Command failed: {command}" not in contents
    assert "Traceback (most recent call last)" not in contents


@pytest.mark.parametrize(
    ("command", "arguments", "expected_message"),
    [
        (
            "validate",
            ["validate", "unsupported.unknown"],
            "Unsupported file format",
        ),
        (
            "compare",
            ["compare", "missing.csv", "also-missing.csv"],
            "Failed reading CSV file",
        ),
    ],
)
def test_dataset_command_failures_are_logged_once(
    tmp_path: Path,
    command: str,
    arguments: list[str],
    expected_message: str,
):
    log_file = tmp_path / f"{command}-failure.log"
    resolved_arguments = [
        str(tmp_path / argument) if "." in argument else argument
        for argument in arguments
    ]

    result = runner.invoke(
        app,
        [*resolved_arguments, "--log", str(log_file)],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert expected_message in result.output
    assert "Traceback (most recent call last)" not in result.output
    assert contents.count(f"Command failed: {command}") == 1
    assert expected_message in contents


def test_report_unsupported_format_is_friendly_and_logged(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    log_file = tmp_path / "report-failure.log"

    result = runner.invoke(
        app,
        [
            "report",
            str(input_file),
            "--output",
            str(tmp_path / "report.pdf"),
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Unsupported dataset report format" in result.output
    assert "Traceback (most recent call last)" not in result.output
    assert contents.count("Command failed: report") == 1
    assert "Unsupported dataset report format" in contents


def test_unlogged_commands_do_not_leave_or_reuse_file_handlers(tmp_path: Path):
    input_file = _write_csv(tmp_path / "input.csv")
    old_log = tmp_path / "old.log"
    logged = runner.invoke(
        app,
        ["summary", str(input_file), "--log", str(old_log)],
    )
    old_contents = old_log.read_text(encoding="utf-8")

    unlogged = runner.invoke(app, ["summary", str(input_file)])

    assert logged.exit_code == unlogged.exit_code == 0
    assert old_log.read_text(encoding="utf-8") == old_contents
    assert list(tmp_path.glob("*.log")) == [old_log]


def _run_convert(
    input_file: Path,
    output_file: Path,
    log_file: Path,
    *,
    append: bool = False,
) -> None:
    arguments = [
        "convert",
        str(input_file),
        str(output_file),
        "--log",
        str(log_file),
    ]
    if append:
        arguments.append("--log-append")

    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("id,name\n1,Ada\n2,Grace\n", encoding="utf-8")
    return path
