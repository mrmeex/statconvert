import csv
import json
from pathlib import Path

import pytest

from statconvert.batch import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SKIPPED,
    BATCH_STATUS_SUCCESS,
    BatchError,
    BatchItem,
    BatchPlan,
    BatchPlanningOptions,
    BatchResult,
    infer_report_format,
    write_batch_plan_report,
    write_batch_result_report,
)


def test_infer_report_format_supports_csv_and_json(tmp_path):
    assert infer_report_format(tmp_path / "report.CSV") == "csv"
    assert infer_report_format(tmp_path / "report.json") == "json"


def test_infer_report_format_rejects_unsupported_suffix(tmp_path):
    with pytest.raises(BatchError, match="Unsupported batch report format"):
        infer_report_format(tmp_path / "report.txt")


def test_write_csv_plan_report_has_stable_rows_and_empty_values(tmp_path):
    plan = _plan(
        tmp_path,
        [
            _item(tmp_path, "pending.csv", BATCH_STATUS_PENDING),
            _item(tmp_path, "skipped.txt", BATCH_STATUS_SKIPPED, output=False),
            _item(tmp_path, "blocked.csv", BATCH_STATUS_BLOCKED),
        ],
    )
    report = tmp_path / "reports" / "plan.csv"

    write_batch_plan_report(plan, report)

    with report.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["status"] for row in rows] == ["pending", "skipped", "blocked"]
    assert rows[0]["input_file"] == str(plan.items[0].input_file)
    assert rows[0]["rows"] == ""
    assert rows[1]["output_file"] == ""


def test_write_csv_result_report_includes_execution_details(tmp_path):
    items = [
        _item(tmp_path, "success.csv", BATCH_STATUS_SUCCESS, rows=2, columns=3),
        _item(tmp_path, "failed.csv", BATCH_STATUS_FAILED, error="broken"),
        _item(tmp_path, "skipped.txt", BATCH_STATUS_SKIPPED, output=False),
        _item(tmp_path, "blocked.csv", BATCH_STATUS_BLOCKED),
    ]
    result = BatchResult(plan=_plan(tmp_path, []), items=items)
    report = tmp_path / "result.csv"

    write_batch_result_report(result, report)

    with report.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["status"] for row in rows] == ["success", "failed", "skipped", "blocked"]
    assert rows[0]["rows"] == "2"
    assert rows[0]["columns"] == "3"
    assert rows[0]["duration_seconds"] == "0.25"
    assert rows[1]["error"] == "broken"


@pytest.mark.parametrize("kind", ["plan", "result"])
def test_write_json_reports_include_type_summary_and_items(tmp_path, kind):
    item = _item(tmp_path, "one.csv", BATCH_STATUS_PENDING)
    report = tmp_path / f"nested/{kind}.json"
    if kind == "plan":
        write_batch_plan_report(_plan(tmp_path, [item]), report)
    else:
        item.status = BATCH_STATUS_SUCCESS
        write_batch_result_report(
            BatchResult(plan=_plan(tmp_path, []), items=[item]), report
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["type"] == kind
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["workload"]["workers"] == 1
    assert payload["summary"]["workload"]["planned_items"] == (
        1 if kind == "plan" else 0
    )
    assert len(payload["items"]) == 1


def _item(
    tmp_path: Path,
    name: str,
    status: str,
    *,
    output: bool = True,
    rows: int | None = None,
    columns: int | None = None,
    error: str | None = None,
) -> BatchItem:
    return BatchItem(
        input_file=tmp_path / "input" / name,
        output_file=tmp_path / "output" / f"{Path(name).stem}.json" if output else None,
        relative_path=Path(name),
        input_extension=Path(name).suffix,
        output_extension=".json" if output else None,
        status=status,
        reason="reason" if status != BATCH_STATUS_SUCCESS else None,
        rows=rows,
        columns=columns,
        duration_seconds=0.25 if rows is not None else None,
        error=error,
    )


def _plan(tmp_path: Path, items: list[BatchItem]) -> BatchPlan:
    return BatchPlan(
        options=BatchPlanningOptions(
            input_path=tmp_path / "input",
            output_path=tmp_path / "output",
            target_extension=".json",
        ),
        items=items,
    )
