import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def test_batch_dry_run_directory_exits_successfully_without_blockers(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "one.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run: planning only" in result.output
    assert "Batch Plan Summary" in result.output
    assert "Pending" in result.output
    assert not output_dir.exists()


def test_batch_dry_run_outputs_json(tmp_path):

    input_dir = tmp_path / "input"
    _write_csv(
        input_dir / "one.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                tmp_path / "output"
            ),
            "--to",
            "json",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )
    assert data["options"]["target_extension"] == ".json"
    assert data["items"][0]["status"] == "pending"
    assert data["workload"]["workers"] == 1
    assert data["workload"]["planned_items"] == 1
    assert data["workload"]["planned_files"] == 1
    assert data["workload"]["total_input_bytes"] > 0
    assert data["workload"]["largest_input_file_bytes"] > 0
    assert data["workload"]["memory_note"] is None


def test_batch_dry_run_shows_multi_worker_memory_note(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(tmp_path / "output"),
            "--to", "parquet", "--workers", "2", "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Workers" in result.output
    assert "Total input size" in result.output
    assert "Largest input file" in result.output
    assert "Each worker may hold one dataset in memory" in result.output


def test_batch_dry_run_single_worker_omits_memory_note(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(tmp_path / "output"),
            "--to", "parquet", "--workers", "1", "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Workers" in result.output
    assert "Each worker may hold one dataset in memory" not in result.output


def test_batch_dry_run_reports_existing_output_without_writing(tmp_path):

    input_file = _write_csv(
        tmp_path / "input" / "one.csv"
    )
    output_dir = tmp_path / "output"
    _touch(
        output_dir / f"{input_file.stem}.json"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_file.parent
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "pending" in result.output
    assert (output_dir / f"{input_file.stem}.json").read_text() == ""


def test_batch_executes_small_csv_to_json_batch(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "one.csv"
    )
    _write_csv(
        input_dir / "two.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert (
        output_dir / "one.json"
    ).exists()
    assert (
        output_dir / "two.json"
    ).exists()
    assert "Batch Result Summary" in result.output


def test_batch_execution_outputs_json(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "one.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )
    assert data["items"][0]["status"] == "success"
    assert data["items"][0]["rows"] == 2


def test_batch_dry_run_writes_plan_report(tmp_path):
    input_file = _write_csv(tmp_path / "input" / "one.csv")
    report = tmp_path / "reports" / "plan.csv"

    result = runner.invoke(
        app,
        ["batch", "--create-dirs", str(input_file.parent), str(tmp_path / "output"), "--to", "json",
         "--dry-run", "--report", str(report)],
    )

    assert result.exit_code == 0
    assert report.exists()
    assert "pending" in report.read_text(encoding="utf-8")


def test_batch_execution_writes_report_without_progress_in_json_mode(tmp_path):
    input_file = _write_csv(tmp_path / "input" / "one.csv")
    report = tmp_path / "result.csv"

    result = runner.invoke(
        app,
        ["batch", "--create-dirs", str(input_file.parent), str(tmp_path / "output"), "--to", "json",
         "--json", "--report", str(report)],
    )

    assert result.exit_code == 0
    assert "Converting files" not in result.output
    assert "success" in report.read_text(encoding="utf-8")


def test_batch_no_progress_and_unsupported_report_error(tmp_path):
    input_file = _write_csv(tmp_path / "input" / "one.csv")
    no_progress = runner.invoke(
        app,
        ["batch", "--create-dirs", str(input_file.parent), str(tmp_path / "output"), "--to", "json",
         "--no-progress"],
    )
    unsupported = runner.invoke(
        app,
        ["batch", "--create-dirs", str(input_file.parent), str(tmp_path / "other"), "--to", "json",
         "--dry-run", "--report", str(tmp_path / "report.txt")],
    )

    assert no_progress.exit_code == 0
    assert "Batch Workload" in no_progress.output
    assert "Converting files" not in no_progress.output
    assert unsupported.exit_code == 1
    assert "Unsupported batch report format" in unsupported.output


def test_batch_respects_recursive(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "top.csv"
    )
    _write_csv(
        input_dir / "nested" / "deep.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--recursive",
        ],
    )

    assert result.exit_code == 0
    assert (
        output_dir / "top.json"
    ).exists()
    assert (
        output_dir / "nested" / "deep.json"
    ).exists()


def test_batch_respects_pattern_and_exclude_pattern(tmp_path):

    input_dir = tmp_path / "input"
    _write_csv(
        input_dir / "keep.csv"
    )
    _write_csv(
        input_dir / "skip.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                tmp_path / "output"
            ),
            "--to",
            "json",
            "--pattern",
            "*.csv",
            "--exclude-pattern",
            "skip.csv",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )
    assert len(
        data["items"]
    ) == 1
    assert data["items"][0]["input_file"].endswith(
        "keep.csv"
    )


def test_batch_dry_run_flatten_reports_recursive_collisions(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "2024" / "survey.csv")
    _write_csv(input_dir / "2025" / "survey.csv")

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(tmp_path / "output"), "--to", "json",
            "--recursive", "--flatten", "--dry-run", "--json",
        ],
    )

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert [item["status"] for item in data["items"]] == ["blocked", "blocked"]
    assert all(item["reason"].startswith("Output path collision") for item in data["items"])


def test_batch_respects_overwrite(tmp_path):

    input_file = _write_csv(
        tmp_path / "input" / "one.csv"
    )
    output_dir = tmp_path / "output"
    output_file = _touch(
        output_dir / "one.json"
    )

    blocked = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_file.parent
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_file.parent
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--overwrite",
        ],
    )

    assert blocked.exit_code == 1
    assert allowed.exit_code == 0
    assert output_file.exists()


def test_batch_skips_unsupported_files_by_default(tmp_path):

    input_dir = tmp_path / "input"
    _write_csv(
        input_dir / "one.csv"
    )
    _touch(
        input_dir / "notes.txt"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                tmp_path / "output"
            ),
            "--to",
            "json",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )
    statuses = {
        item["input_file"].split("\\")[-1]: item["status"]
        for item in data["items"]
    }
    assert statuses["notes.txt"] == "skipped"


def test_batch_supported_only_omits_unsupported_files(tmp_path):

    input_dir = tmp_path / "input"
    _write_csv(
        input_dir / "one.csv"
    )
    _touch(
        input_dir / "notes.txt"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                tmp_path / "output"
            ),
            "--to",
            "json",
            "--supported-only",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )
    assert len(
        data["items"]
    ) == 1
    assert data["items"][0]["input_file"].endswith(
        "one.csv"
    )


def test_batch_rejects_unsupported_target_format(tmp_path):

    input_dir = tmp_path / "input"
    _write_csv(
        input_dir / "one.csv"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                tmp_path / "output"
            ),
            "--to",
            "wizard",
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported target format" in result.output


def test_batch_execution_failure_returns_nonzero(tmp_path):

    input_file = _write_csv(
        tmp_path / "input.csv"
    )
    output_path = _touch(
        tmp_path / "output"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_file
            ),
            str(
                output_path
            ),
            "--to",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert "not a directory" in result.output.lower()


def test_batch_existing_item_fails_without_stopping_other_items(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "blocked.csv"
    )
    _write_csv(
        input_dir / "pending.csv"
    )
    _touch(
        output_dir / "blocked.json"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert (
        output_dir / "pending.json"
    ).exists()
    assert "--overwrite" in result.output


def test_batch_allow_blocked_remains_compatible_with_item_conflicts(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "blocked.csv"
    )
    _write_csv(
        input_dir / "pending.csv"
    )
    _touch(
        output_dir / "blocked.json"
    )

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(
                input_dir
            ),
            str(
                output_dir
            ),
            "--to",
            "json",
            "--allow-blocked",
        ],
    )

    assert result.exit_code == 1
    assert (
        output_dir / "pending.json"
    ).exists()


def test_batch_workers_two_converts_and_writes_ordered_report(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report = tmp_path / "result.csv"
    _write_csv(input_dir / "b.csv")
    _write_csv(input_dir / "a.csv")

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(output_dir), "--to", "json",
            "--workers", "2", "--report", str(report), "--no-progress",
        ],
    )

    assert result.exit_code == 0
    lines = report.read_text(encoding="utf-8").splitlines()
    assert "a.csv" in lines[1]
    assert "b.csv" in lines[2]


def test_batch_workers_zero_exits_with_friendly_error(tmp_path):
    input_file = _write_csv(tmp_path / "input" / "one.csv")

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_file.parent), str(tmp_path / "output"),
            "--to", "json", "--workers", "0",
        ],
    )

    assert result.exit_code == 1
    assert "Workers must be 1 or greater" in result.output


def test_batch_parallel_json_is_valid_and_dry_run_does_not_execute(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    output_dir = tmp_path / "output"

    dry_run = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(output_dir), "--to", "json",
            "--workers", "4", "--dry-run", "--json",
        ],
    )
    assert dry_run.exit_code == 0
    assert not output_dir.exists()

    execution = runner.invoke(
        app,
        [
            "batch", "--create-dirs", str(input_dir), str(output_dir), "--to", "json",
            "--workers", "2", "--json",
        ],
    )

    assert execution.exit_code == 0
    payload = json.loads(execution.output)
    assert payload["items"][0]["status"] == "success"
    assert payload["workload"]["workers"] == 2
    assert "reduce --workers" in payload["workload"]["memory_note"]


def test_batch_selects_same_sheet_from_each_workbook(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_workbook(input_dir / "one.xlsx", selected_value=1)
    _write_workbook(input_dir / "two.xlsx", selected_value=2)

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--object",
            "Data",
            "--workers",
            "2",
            "--json",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert [item["status"] for item in payload["items"]] == ["success", "success"]
    assert pd.read_csv(output_dir / "one.csv")["selected"].tolist() == [1]
    assert pd.read_csv(output_dir / "two.csv")["selected"].tolist() == [2]
    assert [item["input_file"] for item in payload["items"]] == sorted(
        item["input_file"] for item in payload["items"]
    )


def test_batch_multi_sheet_workbooks_without_object_fail_per_file(tmp_path):
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "one.xlsx", selected_value=1)

    result = runner.invoke(
        app,
        ["batch", "--create-dirs", str(input_dir), str(tmp_path / "output"), "--to", "csv", "--json"],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["items"][0]["status"] == "failed"
    assert "multiple sheets" in payload["items"][0]["error"]


def test_batch_unknown_object_is_reported_per_file(tmp_path):
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "one.xlsx", selected_value=1)

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "csv",
            "--object",
            "Missing",
            "--json",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert "Sheet 'Missing' was not found" in payload["items"][0]["error"]
    assert "Data" in payload["items"][0]["error"]


def test_batch_object_selector_is_not_ignored_for_single_dataset_files(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    _write_workbook(input_dir / "two.xlsx", selected_value=2)

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "json",
            "--object",
            "Data",
            "--json",
        ],
    )

    payload = json.loads(result.output)
    by_name = {
        item["input_file"].replace("\\", "/").split("/")[-1]: item
        for item in payload["items"]
    }
    assert result.exit_code == 1
    assert by_name["two.xlsx"]["status"] == "success"
    assert by_name["one.csv"]["status"] == "failed"
    assert "Object selection is not supported" in by_name["one.csv"]["error"]


def test_batch_dry_run_with_object_remains_read_free(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_workbook(input_dir / "one.xlsx", selected_value=1)

    result = runner.invoke(
        app,
        [
            "batch", "--create-dirs",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--object",
            "Missing",
            "--dry-run",
            "--json",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["items"][0]["status"] == "pending"
    assert not output_dir.exists()


def _write_csv(
    path
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    pd.DataFrame(
        {
            "id": [
                1,
                2,
            ],
            "name": [
                "Ada",
                "Grace",
            ],
        }
    ).to_csv(
        path,
        index=False,
    )

    return path


def _write_workbook(path, *, selected_value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"ignored": [0]}).to_excel(
            writer,
            sheet_name="Other",
            index=False,
        )
        pd.DataFrame({"selected": [selected_value]}).to_excel(
            writer,
            sheet_name="Data",
            index=False,
        )
    return path


def _touch(
    path
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.touch()

    return path
