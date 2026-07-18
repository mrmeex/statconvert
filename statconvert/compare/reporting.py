from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import json
from pathlib import Path
from typing import Any

from statconvert.compare.exceptions import CompareError
from statconvert.compare.models import DatasetComparison
from statconvert.serialization import make_json_safe


REPORT_COLUMNS = (
    "section",
    "severity",
    "code",
    "column",
    "metric",
    "left",
    "right",
    "message",
)
SUPPORTED_REPORT_FORMATS = {"csv", "json", "html"}


def infer_compare_report_format(report_file: str | Path) -> str:
    """Infer a supported comparison report format from its suffix."""

    report_format = Path(report_file).suffix.lower().lstrip(".")
    if report_format not in SUPPORTED_REPORT_FORMATS:
        raise CompareError(
            "Unsupported compare report format. Use a .csv, .json or .html report file."
        )
    return report_format


def write_compare_report(
    comparison: DatasetComparison,
    report_file: str | Path,
    report_format: str | None = None,
) -> None:
    """Write a durable CSV, JSON or HTML comparison report."""

    path = Path(report_file)
    resolved_format = _normalize_report_format(report_format, path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if resolved_format == "csv":
            _write_csv(path, comparison_to_rows(comparison))
        elif resolved_format == "json":
            _write_json(path, comparison)
        else:
            _write_html(path, comparison)
    except CompareError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise CompareError(f"Unable to write compare report '{path}': {exc}") from exc


def comparison_to_summary_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return stable high-level summary rows."""

    return [
        _row("summary", metric=metric, left=value)
        for metric, value in _comparison_summary(comparison).items()
    ]


def comparison_to_issue_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return one stable row per comparison issue."""

    return [
        _row(
            "issue",
            severity=issue.severity,
            code=issue.code,
            column=issue.column,
            message=issue.message,
        )
        for issue in comparison.issues
    ]


def comparison_to_schema_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return schema change rows in comparison order."""

    rows = [
        _row(
            "schema",
            column=column,
            metric="storage_type",
            left=left_value,
            right=right_value,
            message="Storage type changed.",
        )
        for column, (left_value, right_value) in comparison.schema.storage_type_changes.items()
    ]
    rows.extend(
        _row(
            "schema",
            column=column,
            metric="display_format",
            left=left_value,
            right=right_value,
            message="Display format changed.",
        )
        for column, (left_value, right_value) in comparison.schema.display_format_changes.items()
    )
    rows.extend(
        _row(
            "schema",
            column=column,
            metric="measurement_level",
            left=left_value,
            right=right_value,
            message="Measurement level changed.",
        )
        for column, (left_value, right_value) in comparison.schema.measurement_level_changes.items()
    )
    return rows


def comparison_to_metadata_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return metadata summaries and detailed change rows."""

    metadata = comparison.metadata
    rows = [
        _row("metadata", metric="variable_label_changes", left=len(metadata.variable_label_changes)),
        _row("metadata", metric="value_label_changes", left=len(metadata.value_label_changes)),
        _row("metadata", metric="missing_value_changes", left=len(metadata.missing_value_changes)),
    ]
    rows.extend(
        _row(
            "metadata",
            column=column,
            metric="variable_label",
            left=left_value,
            right=right_value,
            message="Variable label changed.",
        )
        for column, (left_value, right_value) in metadata.variable_label_changes.items()
    )
    rows.extend(
        _row(
            "metadata",
            column=column,
            metric="value_labels",
            left=left_value,
            right=right_value,
            message="Value labels changed.",
        )
        for column, (left_value, right_value) in metadata.value_label_changes.items()
    )
    rows.extend(
        _row(
            "metadata",
            column=column,
            metric="missing_values",
            left=left_value,
            right=right_value,
            message="Missing values changed.",
        )
        for column, (left_value, right_value) in metadata.missing_value_changes.items()
    )
    return rows


def comparison_to_value_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return value comparison summaries and per-column counts."""

    values = comparison.values
    if values is None:
        return [_row("values", metric="comparison", message="Value comparison skipped.")]

    summary_values = (
        ("compared_rows", values.compared_rows),
        ("compared_columns", values.compared_columns),
        ("cells_compared", values.cells_compared),
        ("differing_cells", values.differing_cells),
        ("same_values", values.same_values),
        ("sampled", values.sampled),
        ("sample_size", values.sample_size),
    )
    rows = [_row("values", metric=metric, left=value) for metric, value in summary_values]
    rows.extend(
        _row(
            "values",
            column=column,
            metric="differing_cells",
            left=count,
            message="Cell values differ.",
        )
        for column, count in values.differences_by_column.items()
        if count
    )
    return rows


def comparison_to_difference_rows(
    comparison: DatasetComparison,
) -> list[dict[str, Any]]:
    """Return the bounded first-difference examples."""

    return [
        _row(
            "difference",
            code=detail.kind,
            column=detail.column,
            metric={"row": detail.row, "key": detail.key},
            left=detail.left,
            right=detail.right,
            message=detail.message,
        )
        for detail in comparison.differences
    ]


def comparison_to_rows(comparison: DatasetComparison) -> list[dict[str, Any]]:
    """Flatten a comparison into deterministic CSV rows."""

    columns = comparison.columns
    rows = comparison_to_summary_rows(comparison)
    rows.extend(
        (
            _row(
                "shape",
                metric="rows",
                left=comparison.shape.left_rows,
                right=comparison.shape.right_rows,
            ),
            _row(
                "shape",
                metric="columns",
                left=comparison.shape.left_columns,
                right=comparison.shape.right_columns,
            ),
            _row("columns", metric="same_columns", left=columns.same_columns),
            _row("columns", metric="same_order", left=columns.same_order),
            _row("columns", metric="left_only", left=columns.left_only_columns),
            _row("columns", metric="right_only", right=columns.right_only_columns),
        )
    )
    rows.extend(comparison_to_schema_rows(comparison))
    rows.extend(comparison_to_metadata_rows(comparison))
    rows.extend(comparison_to_value_rows(comparison))
    rows.extend(comparison_to_difference_rows(comparison))
    rows.extend(comparison_to_issue_rows(comparison))
    return rows


def _normalize_report_format(report_format: str | None, path: Path) -> str:
    if report_format is None:
        return infer_compare_report_format(path)
    normalized = report_format.lower().lstrip(".")
    if normalized not in SUPPORTED_REPORT_FORMATS:
        raise CompareError("Unsupported compare report format. Use csv, json or html.")
    return normalized


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, comparison: DatasetComparison) -> None:
    payload = {
        "type": "comparison",
        "summary": _comparison_summary(comparison),
        "comparison": asdict(comparison),
        "differences": asdict(comparison)["differences"],
    }
    with path.open("w", encoding="utf-8") as report:
        json.dump(
            make_json_safe(payload),
            report,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        report.write("\n")


def _write_html(path: Path, comparison: DatasetComparison) -> None:
    html = _html_document(comparison)
    path.write_text(html, encoding="utf-8")


def _comparison_summary(comparison: DatasetComparison) -> dict[str, Any]:
    values = comparison.values
    return {
        "equal": comparison.is_identical,
        "status": _comparison_status(comparison),
        "identical": comparison.is_identical,
        "compatible": comparison.is_compatible,
        "errors": sum(issue.severity == "error" for issue in comparison.issues),
        "warnings": sum(issue.severity == "warning" for issue in comparison.issues),
        "left_source": comparison.left_source,
        "right_source": comparison.right_source,
        "ignored_columns": comparison.options.ignore_columns,
        "columns_compared": comparison.columns_compared,
        "numeric_tolerance": comparison.options.numeric_tolerance,
        "max_differences": comparison.options.max_differences,
        "row_matching_mode": comparison.row_matching_mode,
        "key_columns": comparison.key_columns,
        "rows_left": comparison.shape.left_rows,
        "rows_right": comparison.shape.right_rows,
        "columns_left": comparison.shape.left_columns,
        "columns_right": comparison.shape.right_columns,
        "matched_rows": comparison.matched_rows,
        "rows_only_left": comparison.rows_only_left,
        "rows_only_right": comparison.rows_only_right,
        "columns_compared_count": len(comparison.columns_compared),
        "cells_compared": values.cells_compared if values is not None else 0,
        "cells_different": values.differing_cells if values is not None else 0,
        "schema_differences": _schema_difference_count(comparison),
        "detailed_differences_total": comparison.detailed_differences_total,
        "detailed_differences_shown": comparison.detailed_differences_shown,
        "detailed_differences_truncated": comparison.detailed_differences_truncated,
    }


def comparison_to_json_payload(comparison: DatasetComparison) -> dict[str, Any]:
    """Extend the backward-compatible CLI JSON model with a concise summary."""

    payload = asdict(comparison)
    payload["equal"] = comparison.is_identical
    payload["summary"] = _comparison_summary(comparison)
    return payload


def _html_document(comparison: DatasetComparison) -> str:
    summary = _comparison_summary(comparison)
    status = _comparison_status(comparison)
    schema_rows = [
        ("Storage type", column, left, right)
        for column, (left, right) in comparison.schema.storage_type_changes.items()
    ]
    schema_rows.extend(
        ("Display format", column, left, right)
        for column, (left, right) in comparison.schema.display_format_changes.items()
    )
    schema_rows.extend(
        ("Measurement level", column, left, right)
        for column, (left, right) in comparison.schema.measurement_level_changes.items()
    )
    issue_rows = [
        (issue.severity, issue.code, issue.column or "", issue.message)
        for issue in comparison.issues
    ]
    values = comparison.values
    value_rows = (
        [("Status", "Value comparison skipped")]
        if values is None
        else [
            ("Compared rows", values.compared_rows),
            ("Compared columns", values.compared_columns),
            ("Cells compared", values.cells_compared),
            ("Differing cells", values.differing_cells),
            ("Sampled", values.sampled),
        ]
    )
    difference_rows = [
        (
            detail.kind,
            _difference_location(detail.row, detail.key),
            detail.column or "",
            detail.left,
            detail.right,
            detail.message or "",
        )
        for detail in comparison.differences
    ]
    difference_note = _difference_note(comparison)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>StatConvert Comparison Report</title>
<style>body{{font-family:Arial,sans-serif;max-width:1100px;margin:2rem auto;color:#222}}
table{{border-collapse:collapse;width:100%;margin-bottom:1.5rem}}th,td{{border:1px solid #ccc;padding:.45rem;text-align:left}}
th{{background:#f2f2f2}}h1,h2{{color:#244b66}}.status{{font-weight:bold}}</style></head>
<body><h1>StatConvert Comparison Report</h1>
<p><strong>Left source:</strong> {_html_value(comparison.left_source)}</p>
<p><strong>Right source:</strong> {_html_value(comparison.right_source)}</p>
<p class="status">Status: {escape(status)}</p>
{_html_table("Summary", ("Metric", "Value"), list(summary.items()))}
{_html_table("Comparison Options", ("Option", "Value"), [("Row matching", comparison.row_matching_mode), ("Key columns", comparison.key_columns), ("Matched rows", comparison.matched_rows), ("Rows only in left", comparison.rows_only_left), ("Rows only in right", comparison.rows_only_right), ("Ignored columns", comparison.options.ignore_columns), ("Columns compared", comparison.columns_compared), ("Numeric tolerance", comparison.options.numeric_tolerance), ("Max differences", comparison.options.max_differences)])}
{_html_table("Shape", ("Metric", "Left", "Right"), [("Rows", comparison.shape.left_rows, comparison.shape.right_rows), ("Columns", comparison.shape.left_columns, comparison.shape.right_columns)])}
{_html_table("Columns", ("Metric", "Value"), [("Same columns", comparison.columns.same_columns), ("Same order", comparison.columns.same_order), ("Left only", comparison.columns.left_only_columns), ("Right only", comparison.columns.right_only_columns)])}
{_html_table("Schema Changes", ("Change type", "Column", "Left", "Right"), schema_rows, "No schema changes.")}
{_html_table("Metadata Summary", ("Change type", "Columns"), [("Variable labels", len(comparison.metadata.variable_label_changes)), ("Value labels", len(comparison.metadata.value_label_changes)), ("Missing values", len(comparison.metadata.missing_value_changes))])}
{_html_table("Values", ("Metric", "Value"), value_rows)}
{_html_table("First Differences", ("Kind", "Row / key", "Column", "Left", "Right", "Message"), difference_rows, "No detailed differences.")}
{difference_note}
{_html_table("Issues", ("Severity", "Code", "Column", "Message"), issue_rows, "No comparison issues found.")}
</body></html>\n"""


def _html_table(
    title: str,
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
    empty_message: str = "No changes.",
) -> str:
    if not rows:
        return f"<h2>{escape(title)}</h2><p>{escape(empty_message)}</p>"
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_html_value(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<h2>{escape(title)}</h2><table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _comparison_status(comparison: DatasetComparison) -> str:
    if comparison.has_errors:
        return "Errors found"
    if comparison.is_identical:
        return "Identical"
    return "Differences found"


def _schema_difference_count(comparison: DatasetComparison) -> int:
    return sum(
        len(changes)
        for changes in (
            comparison.schema.storage_type_changes,
            comparison.schema.display_format_changes,
            comparison.schema.measurement_level_changes,
        )
    )


def _difference_location(row: int | None, key: dict[str, Any] | None) -> Any:
    if key is not None:
        return key
    return row if row is not None else ""


def _difference_note(comparison: DatasetComparison) -> str:
    if not comparison.detailed_differences_truncated:
        return ""
    return (
        "<p><strong>Showing first "
        f"{comparison.detailed_differences_shown} of "
        f"{comparison.detailed_differences_total} detailed differences.</strong></p>"
    )


def _html_value(value: Any) -> str:
    return escape(str(_report_value(value)))


def _row(section: str, **values: Any) -> dict[str, Any]:
    row = {column: "" for column in REPORT_COLUMNS}
    row["section"] = section
    row.update(values)
    return {column: _report_value(row[column]) for column in REPORT_COLUMNS}


def _report_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            make_json_safe(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    return value
