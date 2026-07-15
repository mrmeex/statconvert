from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date, datetime
from html import escape
import json
from pathlib import Path
from typing import Any

from statconvert.output_paths import validate_output_file_path
from statconvert.reporting.exceptions import ReportError
from statconvert.reporting.models import DatasetReport, ReportIssue, ReportSection
from statconvert.serialization import make_json_safe


REPORT_COLUMNS = (
    "section",
    "section_title",
    "item_type",
    "table",
    "severity",
    "code",
    "column",
    "metric",
    "value",
    "description",
    "message",
)
SUPPORTED_REPORT_OUTPUT_FORMATS = {"csv", "html", "json"}


def infer_report_output_format(output_file: str | Path) -> str:
    """Infer a supported dataset report format from a path suffix."""

    suffix = Path(output_file).suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".json", ".csv"}:
        return suffix.lstrip(".")
    raise ReportError(
        "Unsupported dataset report format. Use a .json, .csv, .html or .htm file."
    )


def write_dataset_report(
    report: DatasetReport,
    output_file: str | Path,
    output_format: str | None = None,
    max_table_rows: int | None = None,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> None:
    """Write a dataset report as JSON, CSV or static HTML."""

    path = Path(output_file)
    resolved_format = _normalize_output_format(output_format, path)
    _validate_max_table_rows(max_table_rows)
    validate_output_file_path(
        path,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )
    try:
        if resolved_format == "json":
            write_dataset_report_json(report, path)
        elif resolved_format == "csv":
            write_dataset_report_csv(report, path, max_table_rows=max_table_rows)
        else:
            write_dataset_report_html(report, path, max_table_rows=max_table_rows)
    except ReportError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ReportError(f"Unable to write dataset report '{path}': {exc}") from exc


def dataset_report_summary_dict(
    report: DatasetReport,
    output_file: str | Path,
    output_format: str | None = None,
    preset: str = "default",
    max_table_rows: int = 1000,
    max_preview_values: int = 5,
) -> dict[str, Any]:
    """Return a concise, JSON-ready summary for a written dataset report."""

    path = Path(output_file)
    return {
        "output_file": str(path),
        "format": _normalize_output_format(output_format, path),
        "preset": preset,
        "sections": report.section_count,
        "section_keys": [section.key for section in report.sections],
        "issues": report.issue_count,
        "has_errors": report.has_errors,
        "has_warnings": report.has_warnings,
        "max_table_rows": max_table_rows,
        "max_preview_values": max_preview_values,
    }


def write_dataset_report_json(
    report: DatasetReport,
    output_file: str | Path,
) -> None:
    """Write the complete report hierarchy as UTF-8 JSON."""

    path = Path(output_file)
    try:
        _create_parent(path)
        payload = {
            "type": "dataset_report",
            "title": report.title,
            "source_file": report.source_file,
            "source_format": report.source_format,
            "generated_at": report.generated_at,
            "summary": {
                "sections": report.section_count,
                "issues": report.issue_count,
                "has_errors": report.has_errors,
                "has_warnings": report.has_warnings,
            },
            "report": asdict(report),
        }
        with path.open("w", encoding="utf-8") as output:
            json.dump(
                make_json_safe(payload),
                output,
                indent=2,
                default=str,
                ensure_ascii=False,
                allow_nan=False,
            )
            output.write("\n")
    except (OSError, TypeError, ValueError) as exc:
        raise ReportError(f"Unable to write dataset report '{path}': {exc}") from exc


def write_dataset_report_csv(
    report: DatasetReport,
    output_file: str | Path,
    max_table_rows: int | None = None,
) -> None:
    """Write a deterministic, flattened report as UTF-8 CSV."""

    path = Path(output_file)
    _validate_max_table_rows(max_table_rows)
    try:
        _create_parent(path)
        rows = _report_to_csv_rows(report, max_table_rows=max_table_rows)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, TypeError, ValueError) as exc:
        raise ReportError(f"Unable to write dataset report '{path}': {exc}") from exc


def write_dataset_report_html(
    report: DatasetReport,
    output_file: str | Path,
    max_table_rows: int | None = None,
) -> None:
    """Write a readable, dependency-free static HTML report."""

    path = Path(output_file)
    _validate_max_table_rows(max_table_rows)
    try:
        _create_parent(path)
        _write_text(path, _html_document(report, max_table_rows=max_table_rows))
    except (OSError, TypeError, ValueError) as exc:
        raise ReportError(f"Unable to write dataset report '{path}': {exc}") from exc


def _normalize_output_format(output_format: str | None, path: Path) -> str:
    if output_format is None:
        return infer_report_output_format(path)
    normalized = output_format.lower().lstrip(".")
    if normalized == "htm":
        normalized = "html"
    if normalized not in SUPPORTED_REPORT_OUTPUT_FORMATS:
        raise ReportError("Unsupported dataset report format. Use json, csv or html.")
    return normalized


def _report_to_csv_rows(
    report: DatasetReport,
    max_table_rows: int | None = None,
) -> list[dict[str, str]]:
    rows = [
        _csv_row("report", report.title, "metric", metric="title", value=report.title),
        _csv_row("report", report.title, "metric", metric="source_file", value=report.source_file),
        _csv_row("report", report.title, "metric", metric="source_format", value=report.source_format),
        _csv_row("report", report.title, "metric", metric="generated_at", value=report.generated_at),
        _csv_row("report", report.title, "metric", metric="sections", value=report.section_count),
        _csv_row("report", report.title, "metric", metric="issues", value=report.issue_count),
        _csv_row("report", report.title, "metric", metric="has_errors", value=report.has_errors),
        _csv_row("report", report.title, "metric", metric="has_warnings", value=report.has_warnings),
    ]
    for section in report.sections:
        rows.extend(
            _csv_row(
                section.key,
                section.title,
                "metric",
                metric=metric.name,
                value=metric.value,
                description=metric.description,
            )
            for metric in section.metrics
        )
        for table in section.tables:
            displayed_rows = _limited_rows(table.rows, max_table_rows)
            for row_number, table_row in enumerate(displayed_rows, start=1):
                rows.append(
                    _csv_row(
                        section.key,
                        section.title,
                        "table",
                        table=table.name,
                        column=table_row.get("column"),
                        metric=str(row_number),
                        value=table_row,
                        description=table.description,
                    )
                )
            if len(displayed_rows) < len(table.rows):
                rows.append(
                    _csv_row(
                        section.key,
                        section.title,
                        "note",
                        table=table.name,
                        message=_truncation_message(
                            table.name,
                            len(displayed_rows),
                            len(table.rows),
                        ),
                    )
                )
        rows.extend(_issue_csv_row(section, issue) for issue in section.issues)
    rows.extend(
        _csv_row(
            "report",
            report.title,
            "issue",
            severity=issue.severity,
            code=issue.code,
            column=issue.column,
            message=issue.message,
        )
        for issue in report.issues
    )
    return rows


def _issue_csv_row(section: ReportSection, issue: ReportIssue) -> dict[str, str]:
    return _csv_row(
        section.key,
        section.title,
        "issue",
        severity=issue.severity,
        code=issue.code,
        column=issue.column,
        message=issue.message,
    )


def _csv_row(
    section: str,
    section_title: str,
    item_type: str,
    **values: Any,
) -> dict[str, str]:
    row: dict[str, Any] = {column: "" for column in REPORT_COLUMNS}
    row.update(
        section=section,
        section_title=section_title,
        item_type=item_type,
    )
    row.update(values)
    return {column: _format_cell(row[column]) for column in REPORT_COLUMNS}


def _html_document(
    report: DatasetReport,
    max_table_rows: int | None = None,
) -> str:
    toc = "".join(
        f'<li><a href="#section-{index}">{escape(section.title)}</a></li>'
        for index, section in enumerate(report.sections, start=1)
    )
    sections = "".join(
        _html_section(section, index, max_table_rows=max_table_rows)
        for index, section in enumerate(report.sections, start=1)
    )
    report_issues = '<h2>Report Issues</h2><p class="empty">No issues.</p>'
    if report.issues:
        issue_rows = [
            (issue.severity, issue.code, issue.column, issue.message)
            for issue in report.issues
        ]
        report_issues = "<h2>Report Issues</h2>" + _html_table(
            ("Severity", "Code", "Column", "Message"),
            issue_rows,
        )
    status, status_class = _report_status(report)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_value(report.title)}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.45}}
h1,h2,h3{{color:#244b66}}section{{margin:2.5rem 0;padding-top:.5rem;border-top:2px solid #e5e7eb}}
nav{{background:#f7f9fb;border:1px solid #dbe3e8;padding:.5rem 1rem;margin:1.5rem 0}}nav ul{{columns:2}}
.table-wrap{{overflow-x:auto;margin:.75rem 0 1.5rem}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}}th{{background:#f2f2f2;white-space:nowrap}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;margin:1rem 0}}
.summary div{{background:#f7f7f7;padding:.65rem;border-radius:4px}}.badge{{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:bold}}
.status-ok{{background:#dcfce7;color:#166534}}.status-warning{{background:#fef3c7;color:#92400e}}.status-error{{background:#fee2e2;color:#991b1b}}
.empty{{color:#667085;font-style:italic}}.truncation{{background:#fff7ed;border-left:4px solid #f59e0b;padding:.5rem .75rem}}
</style>
</head>
<body>
<h1>{_html_value(report.title)}</h1>
<p><strong>Generated:</strong> {_html_value(report.generated_at)}</p>
<p><strong>Source file:</strong> {_html_value(report.source_file)}</p>
<p><strong>Source format:</strong> {_html_value(report.source_format)}</p>
<p><strong>Status:</strong> <span class="badge {status_class}">{escape(status)}</span></p>
<div class="summary">
<div><strong>Errors:</strong> {"yes" if report.has_errors else "no"}</div>
<div><strong>Warnings:</strong> {"yes" if report.has_warnings else "no"}</div>
<div><strong>Sections:</strong> {report.section_count}</div>
<div><strong>Issues:</strong> {report.issue_count}</div>
</div>
{report_issues}
<nav aria-label="Table of contents"><h2>Table of Contents</h2><ul>{toc}</ul></nav>
{sections}
</body>
</html>
"""


def _html_section(
    section: ReportSection,
    index: int,
    max_table_rows: int | None = None,
) -> str:
    parts = [f'<section id="section-{index}"><h2>{escape(section.title)}</h2>']
    if section.text:
        parts.append(f"<p>{escape(section.text)}</p>")
    if section.metrics:
        metric_rows = [
            (
                metric.label or metric.name,
                metric.value,
                metric.description,
            )
            for metric in section.metrics
        ]
        parts.append(_html_table(("Metric", "Value", "Description"), metric_rows))
    if section.issues:
        issue_rows = [
            (issue.severity, issue.code, issue.column, issue.message)
            for issue in section.issues
        ]
        parts.append("<h3>Issues</h3>")
        parts.append(_html_table(("Severity", "Code", "Column", "Message"), issue_rows))
    else:
        parts.append('<h3>Issues</h3><p class="empty">No issues.</p>')
    for table in section.tables:
        parts.append(f"<h3>{escape(table.name)}</h3>")
        if table.description:
            parts.append(f"<p>{escape(table.description)}</p>")
        displayed_rows = _limited_rows(table.rows, max_table_rows)
        table_rows = [
            tuple(row.get(column) for column in table.columns)
            for row in displayed_rows
        ]
        parts.append(_html_table(tuple(table.columns), table_rows))
        if len(displayed_rows) < len(table.rows):
            parts.append(
                f'<p class="truncation">{escape(_truncation_message(table.name, len(displayed_rows), len(table.rows)))}</p>'
            )
    parts.append("</section>")
    return "".join(parts)


def _html_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    header_html = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    if not rows:
        return f'<p class="empty">No rows.</p><div class="table-wrap"><table><thead><tr>{header_html}</tr></thead><tbody></tbody></table></div>'
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_html_value(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def _format_cell(value: Any) -> str:
    if _is_missing_scalar(value):
        return ""
    if isinstance(value, (dict, list, tuple)):
        return _compact_json(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _format_cell(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _compact_json(value: Any) -> str:
    return json.dumps(
        _to_csv_jsonable(value),
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _to_csv_jsonable(value: Any) -> Any:
    if _is_missing_scalar(value):
        return ""
    if isinstance(value, dict):
        return {str(key): _to_csv_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_csv_jsonable(item) for item in value]
    return make_json_safe(value)


def _html_value(value: Any) -> str:
    return escape(_format_cell(value))


def _limited_rows(
    rows: list[dict[str, Any]],
    max_table_rows: int | None,
) -> list[dict[str, Any]]:
    if max_table_rows is None:
        return rows
    return rows[:max_table_rows]


def _truncation_message(table_name: str, displayed: int, total: int) -> str:
    return f"Table '{table_name}' truncated to {displayed} rows from {total} rows."


def _report_status(report: DatasetReport) -> tuple[str, str]:
    if report.has_errors:
        return "Errors", "status-error"
    if report.has_warnings:
        return "Warnings", "status-warning"
    return "OK", "status-ok"


def _validate_max_table_rows(max_table_rows: int | None) -> None:
    if max_table_rows is not None and max_table_rows < 1:
        raise ReportError("max_table_rows must be at least 1.")


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (dict, list, tuple, str, bytes)):
        return False
    value_type = type(value)
    if (
        value_type.__name__ == "NAType"
        and value_type.__module__.startswith("pandas")
    ):
        return True
    try:
        unequal = value != value
        return bool(unequal)
    except (TypeError, ValueError):
        return False


def _create_parent(path: Path) -> None:
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
