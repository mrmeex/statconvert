from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from statconvert.batch.exceptions import BatchError
from statconvert.batch.models import BatchItem, BatchPlan, BatchResult


REPORT_COLUMNS = (
    "input_file",
    "output_file",
    "relative_path",
    "input_object",
    "output_name",
    "object_index",
    "object_name",
    "input_extension",
    "output_extension",
    "status",
    "reason",
    "rows",
    "columns",
    "duration_seconds",
    "error",
    "validation_issues",
    "validation_errors",
    "validation_warnings",
)
SUPPORTED_REPORT_FORMATS = {"csv", "json"}


def infer_report_format(report_file: str | Path) -> str:
    """Infer a supported report format from a report path."""

    suffix = Path(report_file).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_REPORT_FORMATS:
        raise BatchError(
            "Unsupported batch report format. Use a .csv or .json report file."
        )
    return suffix


def batch_item_to_report_row(item: BatchItem) -> dict[str, Any]:
    """Convert one batch item to a stable, serializable report row."""

    values: dict[str, Any] = {
        "input_file": item.input_file,
        "output_file": item.output_file,
        "relative_path": item.relative_path,
        "input_object": item.input_object,
        "output_name": item.output_name,
        "object_index": item.object_index,
        "object_name": item.object_name,
        "input_extension": item.input_extension,
        "output_extension": item.output_extension,
        "status": item.status,
        "reason": item.reason,
        "rows": item.rows,
        "columns": item.columns,
        "duration_seconds": item.duration_seconds,
        "error": item.error,
        "validation_issues": item.validation_issues,
        "validation_errors": item.validation_errors,
        "validation_warnings": item.validation_warnings,
    }
    return {
        column: _report_value(values[column])
        for column in REPORT_COLUMNS
    }


def batch_plan_to_rows(plan: BatchPlan) -> list[dict[str, Any]]:
    """Convert a plan to report rows."""

    return [batch_item_to_report_row(item) for item in plan.items]


def batch_result_to_rows(result: BatchResult) -> list[dict[str, Any]]:
    """Convert an execution result to report rows."""

    return [batch_item_to_report_row(item) for item in result.items]


def write_batch_plan_report(
    plan: BatchPlan,
    report_file: str | Path,
    report_format: str | None = None,
) -> None:
    """Write a planning report in CSV or JSON format."""

    payload = {
        "type": "plan",
        "summary": {
            "total": plan.total_count,
            "pending": plan.pending_count,
            "skipped": plan.skipped_count,
            "blocked": plan.blocked_count,
        },
        "items": batch_plan_to_rows(plan),
    }
    _write_report(payload, report_file, report_format)


def write_batch_result_report(
    result: BatchResult,
    report_file: str | Path,
    report_format: str | None = None,
) -> None:
    """Write an execution report in CSV or JSON format."""

    payload = {
        "type": "result",
        "summary": {
            "total": result.total_count,
            "success": result.success_count,
            "failed": result.failed_count,
            "skipped": result.skipped_count,
            "blocked": result.blocked_count,
        },
        "items": batch_result_to_rows(result),
    }
    _write_report(payload, report_file, report_format)


def _write_report(
    payload: dict[str, Any],
    report_file: str | Path,
    report_format: str | None,
) -> None:
    path = Path(report_file)
    resolved_format = _normalize_report_format(report_format, path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if resolved_format == "csv":
            _write_csv(path, payload["items"])
        else:
            _write_json(path, payload)
    except BatchError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise BatchError(f"Unable to write batch report '{path}': {exc}") from exc


def _normalize_report_format(
    report_format: str | None,
    report_file: Path,
) -> str:
    if report_format is None:
        return infer_report_format(report_file)

    normalized = report_format.lower().lstrip(".")
    if normalized not in SUPPORTED_REPORT_FORMATS:
        raise BatchError(
            "Unsupported batch report format. Use csv or json."
        )
    return normalized


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as report:
        json.dump(payload, report, indent=2, default=str)
        report.write("\n")


def _report_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    return value
