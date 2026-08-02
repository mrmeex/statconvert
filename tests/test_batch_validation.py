import csv
import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.batch import (
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SKIPPED,
    BATCH_STATUS_SUCCESS,
    BatchResult,
    build_batch_plan,
    execute_batch_plan,
    write_batch_result_report,
)
from statconvert.cli import app
from statconvert.inspection import ValidationIssue
from statconvert.ui.batch import console, show_batch_result


runner = CliRunner()


def test_validation_allows_valid_file_and_records_counts(tmp_path):
    input_file = _write_csv(tmp_path / "input" / "valid.csv")
    plan = build_batch_plan(input_file, tmp_path / "output", "json")

    result = execute_batch_plan(plan, validate=True)
    item = result.items[0]

    assert item.status == BATCH_STATUS_SUCCESS
    assert item.validation_issues is not None
    assert item.validation_errors == 0
    assert item.validation_warnings is not None
    assert item.output_file.exists()


def test_validation_error_fails_item_and_continues(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "bad.csv")
    _write_csv(input_dir / "good.csv")
    plan = build_batch_plan(input_dir, tmp_path / "output", "json")

    def controlled_validation(dataset, target_format=None):
        if dataset.source_file.endswith("bad.csv"):
            return [ValidationIssue("error", "bad", "Controlled validation error.")]
        return []

    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        controlled_validation,
    )
    result = execute_batch_plan(plan, validate=True, fail_fast=False)

    assert [item.status for item in result.items] == [
        BATCH_STATUS_FAILED,
        BATCH_STATUS_SUCCESS,
    ]
    failed = result.items[0]
    assert failed.reason == "Validation failed"
    assert "1 error(s), 0 warning(s)" in failed.error
    assert "Controlled validation error" in failed.error
    assert failed.rows == 2
    assert failed.columns == 2
    assert failed.duration_seconds is not None
    assert not failed.output_file.exists()


def test_strict_validation_fails_warning(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "warning.csv")
    plan = build_batch_plan(input_file, tmp_path / "output", "json")
    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        lambda dataset, target_format=None: [
            ValidationIssue("warning", "warning", "Controlled warning.")
        ],
    )

    result = execute_batch_plan(
        plan,
        validate=True,
        strict_validation=True,
    )

    assert result.items[0].status == BATCH_STATUS_FAILED
    assert result.items[0].validation_warnings == 1
    assert "0 error(s), 1 warning(s)" in result.items[0].error


def test_validation_fail_fast_skips_remaining_sequential_items(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "a.csv")
    _write_csv(input_dir / "b.csv")
    plan = build_batch_plan(input_dir, tmp_path / "output", "json")
    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        lambda dataset, target_format=None: [
            ValidationIssue("error", "bad", "Invalid dataset.")
        ],
    )

    result = execute_batch_plan(plan, validate=True, fail_fast=True)

    assert [item.status for item in result.items] == [
        BATCH_STATUS_FAILED,
        BATCH_STATUS_SKIPPED,
    ]
    assert result.items[1].reason == "Not processed due to fail-fast"


def test_validation_statuses_match_with_one_and_two_workers(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "a.csv")
    _write_csv(input_dir / "b.csv")

    def controlled_validation(dataset, target_format=None):
        if dataset.source_file.endswith("a.csv"):
            return [ValidationIssue("error", "bad", "Invalid dataset.")]
        return []

    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        controlled_validation,
    )
    sequential = execute_batch_plan(
        build_batch_plan(input_dir, tmp_path / "sequential", "json"),
        validate=True,
        workers=1,
    )
    parallel = execute_batch_plan(
        build_batch_plan(input_dir, tmp_path / "parallel", "json"),
        validate=True,
        workers=2,
    )

    assert [item.status for item in sequential.items] == [
        item.status for item in parallel.items
    ]


def test_validation_failure_is_clear_in_csv_and_json_reports(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "bad.csv")
    plan = build_batch_plan(input_file, tmp_path / "output", "json")
    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        lambda dataset, target_format=None: [
            ValidationIssue("error", "bad", "Report validation error.")
        ],
    )
    result = execute_batch_plan(plan, validate=True)
    csv_report = tmp_path / "report.csv"
    json_report = tmp_path / "report.json"

    write_batch_result_report(result, csv_report)
    write_batch_result_report(result, json_report)

    with csv_report.open(encoding="utf-8", newline="") as file:
        row = next(csv.DictReader(file))
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert row["reason"] == "Validation failed"
    assert row["validation_errors"] == "1"
    assert row["duration_seconds"]
    assert payload["items"][0]["reason"] == "Validation failed"
    assert payload["items"][0]["validation_errors"] == 1


def test_batch_cli_validate_and_strict_validation_exit_codes(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input" / "warning.csv")
    monkeypatch.setattr(
        "statconvert.batch.execution.validate_dataset",
        lambda dataset, target_format=None: [
            ValidationIssue("warning", "warning", "Controlled warning.")
        ],
    )

    normal = runner.invoke(
        app,
        [
            "batch", str(input_file.parent), str(tmp_path / "normal"),
            "--to", "json", "--validate", "--no-progress", "--create-dirs",
        ],
    )
    strict = runner.invoke(
        app,
        [
            "batch", str(input_file.parent), str(tmp_path / "strict"),
            "--to", "json", "--validate", "--strict-validation", "--json",
            "--create-dirs",
        ],
    )

    assert normal.exit_code == 0
    assert strict.exit_code == 1
    assert json.loads(strict.output)["items"][0]["reason"] == "Validation failed"


def test_batch_result_ui_handles_validation_failure_and_long_error(tmp_path):
    plan = build_batch_plan(
        _write_csv(tmp_path / "input.csv"),
        tmp_path / "output",
        "json",
    )
    item = plan.items[0]
    item.status = BATCH_STATUS_FAILED
    item.reason = "Validation failed"
    item.error = "Validation failed: 2 error(s), 3 warning(s). " + "detail " * 30
    item.validation_issues = 5
    item.validation_errors = 2
    item.validation_warnings = 3

    with console.capture() as capture:
        show_batch_result(BatchResult(plan=plan, items=[item]))

    output = capture.get()
    assert "Validation" in output
    assert "failed" in output
    assert "2E/3W" in output


def _write_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": [1, 2], "name": ["Ada", "Grace"]}).to_csv(
        path,
        index=False,
    )
    return path
