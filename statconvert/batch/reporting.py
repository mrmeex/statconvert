from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from statconvert.batch.exceptions import BatchError
from statconvert.batch.models import BatchItem, BatchPlan, BatchResult


BATCH_REPORT_ITEM_LIMIT = 500
BATCH_REPORT_DIAGNOSTIC_LIMIT = 500
BATCH_REPORT_MESSAGE_LIMIT = 500

REPORT_COLUMNS = (
    "phase",
    "mode",
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
    "subsystem",
    "reason_code",
    "reason",
    "primary_message",
    "manual_retry_hint",
    "input_size_bytes",
    "overwrite_disposition",
    "directory_disposition",
    "sidecar_disposition",
    "potential_sidecar_path",
    "same_path",
    "duplicate_output",
    "existing_output",
    "output_inside_input_excluded",
    "read_state",
    "rows",
    "columns",
    "rows_before",
    "columns_before",
    "rows_after",
    "columns_after",
    "recipe_requested",
    "recipe_name",
    "recipe_path",
    "recipe_syntax_status",
    "recipe_compatibility_status",
    "recipe_execution_status",
    "recipe_step_count",
    "recipe_warning_count",
    "recipe_error_count",
    "recipe_diagnostics_included",
    "recipe_diagnostics_omitted",
    "policy_requested",
    "policy_name",
    "policy_status",
    "policy_decision_count",
    "policy_keep_count",
    "policy_manual_decision_count",
    "policy_issue_count",
    "policy_warning_count",
    "policy_error_count",
    "policy_issue_codes",
    "policy_metadata_native_count",
    "policy_metadata_embedded_count",
    "policy_metadata_sidecar_count",
    "policy_metadata_unsupported_count",
    "policy_diagnostics_included",
    "policy_diagnostics_omitted",
    "optimization_requested",
    "optimization_applied_count",
    "optimization_kept_count",
    "optimization_manual_count",
    "duration_seconds",
    "error",
    "validation_issues",
    "validation_errors",
    "validation_warnings",
    "streaming",
    "chunk_size",
    "chunks_processed",
    "rows_processed",
    "report_total_items",
    "report_pending",
    "report_success",
    "report_failed",
    "report_skipped",
    "report_blocked",
    "report_items_included",
    "report_items_omitted",
    "report_issues_omitted",
)
SUPPORTED_REPORT_FORMATS = {"csv", "html", "json"}


def infer_report_format(report_file: str | Path) -> str:
    """Infer a supported batch report format from a report path."""

    suffix = Path(report_file).suffix.lower().lstrip(".")
    if suffix == "htm":
        return "html"
    if suffix not in SUPPORTED_REPORT_FORMATS:
        raise BatchError(
            "Unsupported batch report format. Use a .csv, .json, .html or .htm report file."
        )
    return suffix


def validate_batch_report_path(
    plan: BatchPlan,
    report_file: str | Path,
    *,
    items: list[BatchItem] | None = None,
    report_format: str | None = None,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> Path:
    """Preflight one explicit report path without modifying the filesystem."""

    path = Path(report_file)
    _normalize_report_format(report_format, path)
    checked_items = plan.items if items is None else items
    key = _path_key(path)
    if key in {_path_key(item.input_file) for item in checked_items}:
        raise BatchError(
            f"Batch report path conflicts with a selected source: {path}",
            suggestion="Choose a report path outside the selected source files.",
        )
    if key in {
        _path_key(item.output_file)
        for item in checked_items
        if item.output_file is not None
    }:
        raise BatchError(
            f"Batch report path conflicts with a planned primary output: {path}",
            suggestion="Choose a separate report path.",
        )
    if key in {
        _path_key(item.potential_sidecar_path)
        for item in checked_items
        if item.potential_sidecar_path is not None
    }:
        raise BatchError(
            f"Batch report path conflicts with a planned metadata sidecar: {path}",
            suggestion="Choose a separate report path.",
        )
    if path.exists():
        if path.is_dir():
            raise BatchError(
                f"Batch report path is a directory: {path}",
                suggestion="Choose a report file path.",
            )
        if not overwrite:
            raise BatchError(
                f"Batch report already exists: {path}",
                suggestion="Use --overwrite to replace it, or choose a different path.",
            )
    parent = path.parent
    if parent != Path("."):
        if parent.exists() and not parent.is_dir():
            raise BatchError(
                f"Batch report parent is not a directory: {parent}",
                suggestion="Choose a report path whose parent is a directory.",
            )
        if not parent.exists() and not create_dirs:
            raise BatchError(
                f"Batch report directory does not exist: {parent}",
                suggestion="Use --create-dirs to create missing report directories.",
            )
    return path


def batch_item_to_report_row(
    item: BatchItem,
    *,
    phase: str = "",
    mode: str = "",
    report_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Flatten one item into the stable CSV report contract."""

    recipe = item.recipe
    policy = item.policy
    summary = report_summary or {}
    values: dict[str, Any] = {
        "phase": phase,
        "mode": mode,
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
        "subsystem": item.subsystem,
        "reason_code": item.reason_code,
        "reason": _bounded_message(item.reason),
        "primary_message": _bounded_message(item.error or item.reason),
        "manual_retry_hint": _manual_retry_hint(item),
        "input_size_bytes": item.input_size_bytes,
        "overwrite_disposition": item.overwrite_disposition,
        "directory_disposition": item.directory_disposition,
        "sidecar_disposition": item.sidecar_disposition,
        "potential_sidecar_path": item.potential_sidecar_path,
        "same_path": item.same_path,
        "duplicate_output": item.duplicate_output,
        "existing_output": item.existing_output,
        "output_inside_input_excluded": item.output_inside_input_excluded,
        "read_state": item.read_state,
        "rows": item.rows,
        "columns": item.columns,
        "rows_before": item.rows_before,
        "columns_before": item.columns_before,
        "rows_after": item.rows_after,
        "columns_after": item.columns_after,
        "recipe_requested": recipe.requested,
        "recipe_name": recipe.recipe_name,
        "recipe_path": recipe.recipe_path,
        "recipe_syntax_status": recipe.syntax_status,
        "recipe_compatibility_status": recipe.compatibility_status,
        "recipe_execution_status": recipe.execution_status,
        "recipe_step_count": recipe.step_count,
        "recipe_warning_count": recipe.warning_count,
        "recipe_error_count": recipe.error_count,
        "recipe_diagnostics_included": len(recipe.diagnostics),
        "recipe_diagnostics_omitted": recipe.diagnostics_omitted,
        "policy_requested": policy.requested,
        "policy_name": policy.policy_name,
        "policy_status": policy.status,
        "policy_decision_count": sum(policy.decision_counts.values()),
        "policy_keep_count": policy.decision_counts.get("keep", 0),
        "policy_manual_decision_count": policy.decision_counts.get("manual", 0),
        "policy_issue_count": sum(policy.issue_counts.values()),
        "policy_warning_count": policy.issue_counts.get("warning", 0),
        "policy_error_count": policy.issue_counts.get("error", 0),
        "policy_issue_codes": ";".join(sorted(policy.issue_code_counts)),
        "policy_metadata_native_count": policy.metadata_disposition_counts.get(
            "native", 0
        ),
        "policy_metadata_embedded_count": policy.metadata_disposition_counts.get(
            "embedded", 0
        ),
        "policy_metadata_sidecar_count": policy.metadata_disposition_counts.get(
            "sidecar", 0
        ),
        "policy_metadata_unsupported_count": policy.metadata_disposition_counts.get(
            "unsupported", 0
        ),
        "policy_diagnostics_included": len(policy.diagnostics),
        "policy_diagnostics_omitted": policy.diagnostics_omitted,
        "optimization_requested": policy.optimization_requested,
        "optimization_applied_count": policy.applied_count,
        "optimization_kept_count": policy.kept_count,
        "optimization_manual_count": policy.manual_count,
        "duration_seconds": item.duration_seconds,
        "error": _bounded_message(item.error),
        "validation_issues": item.validation_issues,
        "validation_errors": item.validation_errors,
        "validation_warnings": item.validation_warnings,
        "streaming": item.streaming,
        "chunk_size": item.chunk_size,
        "chunks_processed": item.chunks_processed,
        "rows_processed": item.rows_processed,
        "report_total_items": summary.get("total", ""),
        "report_pending": summary.get("pending", ""),
        "report_success": summary.get("success", ""),
        "report_failed": summary.get("failed", ""),
        "report_skipped": summary.get("skipped", ""),
        "report_blocked": summary.get("blocked", ""),
        "report_items_included": summary.get("items_included", ""),
        "report_items_omitted": summary.get("items_omitted", ""),
        "report_issues_omitted": summary.get("issues_omitted", ""),
    }
    return {column: _report_value(values[column]) for column in REPORT_COLUMNS}


def batch_plan_to_rows(plan: BatchPlan) -> list[dict[str, Any]]:
    """Convert a plan to uncapped report rows for in-process consumers."""

    return [
        batch_item_to_report_row(item, phase=plan.phase, mode=plan.mode)
        for item in plan.items
    ]


def batch_result_to_rows(result: BatchResult) -> list[dict[str, Any]]:
    """Convert an execution result to uncapped rows for in-process consumers."""

    return [
        batch_item_to_report_row(item, phase=result.phase, mode=result.mode)
        for item in result.items
    ]


def batch_plan_to_dict(
    plan: BatchPlan, *, item_limit: int | None = None
) -> dict[str, Any]:
    """Serialize a plan with complete summaries and explicit detail truncation."""

    included, truncation = _bounded_items(plan.items, item_limit)
    summary = {**plan.summary_dict(), **_advanced_summary(plan.items)}
    return {
        "phase": plan.phase,
        "mode": plan.mode,
        "options": asdict(plan.options),
        "workload": asdict(plan.workload),
        "summary": summary,
        "checks_not_performed": list(plan.checks_not_performed),
        "items": [asdict(item) for item in included],
        "truncation": truncation,
    }


def batch_result_to_dict(
    result: BatchResult, *, item_limit: int | None = None
) -> dict[str, Any]:
    """Serialize an execution result using the nested bounded report contract."""

    included, truncation = _bounded_items(result.items, item_limit)
    summary: dict[str, Any] = {
        "total": result.total_count,
        "pending": 0,
        "success": result.success_count,
        "failed": result.failed_count,
        "skipped": result.skipped_count,
        "blocked": result.blocked_count,
        "reason_counts": _counts(
            item.reason_code for item in result.items if item.reason_code
        ),
        "streaming": result.plan.options.streaming_enabled,
        "chunk_size": result.plan.options.chunk_size,
        "total_streamed_chunks": result.total_streamed_chunks,
        "total_streamed_rows": result.total_streamed_rows,
        **_advanced_summary(result.items),
    }
    return {
        "phase": result.phase,
        "mode": result.mode,
        "options": asdict(result.plan.options),
        "workload": asdict(result.workload),
        "summary": summary,
        "checks_not_performed": [],
        "items": [asdict(item) for item in included],
        "truncation": truncation,
    }


def write_batch_plan_report(
    plan: BatchPlan,
    report_file: str | Path,
    report_format: str | None = None,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> None:
    """Write a safely preflighted, bounded planning report."""

    payload = batch_plan_to_dict(plan, item_limit=BATCH_REPORT_ITEM_LIMIT)
    payload["type"] = "plan"
    payload["summary"].update(
        streaming=plan.options.streaming_enabled,
        chunk_size=plan.options.chunk_size,
        workload=asdict(plan.workload),
    )
    _write_report(
        payload, plan, plan.items, report_file, report_format, overwrite, create_dirs
    )


def write_batch_result_report(
    result: BatchResult,
    report_file: str | Path,
    report_format: str | None = None,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> None:
    """Write a safely preflighted, bounded execution report."""

    payload = batch_result_to_dict(result, item_limit=BATCH_REPORT_ITEM_LIMIT)
    payload["type"] = "result"
    payload["summary"]["workload"] = asdict(result.workload)
    _write_report(
        payload,
        result.plan,
        result.items,
        report_file,
        report_format,
        overwrite,
        create_dirs,
    )


def _write_report(
    payload: dict[str, Any],
    plan: BatchPlan,
    all_items: list[BatchItem],
    report_file: str | Path,
    report_format: str | None,
    overwrite: bool,
    create_dirs: bool,
) -> None:
    path = Path(report_file)
    resolved_format = _normalize_report_format(report_format, path)
    validate_batch_report_path(
        plan,
        path,
        items=all_items,
        report_format=resolved_format,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )
    try:
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, payload, all_items, resolved_format, overwrite)
    except BatchError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise BatchError(f"Unable to write batch report '{path}': {exc}") from exc


def _atomic_write(
    path: Path,
    payload: dict[str, Any],
    all_items: list[BatchItem],
    report_format: str,
    overwrite: bool,
) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        if report_format == "csv":
            _write_csv(temporary, payload, all_items[:BATCH_REPORT_ITEM_LIMIT])
        elif report_format == "html":
            temporary.write_text(_html_document(payload), encoding="utf-8")
        else:
            _write_json(temporary, payload)
        if path.exists() and not overwrite:
            raise BatchError(
                f"Batch report already exists: {path}",
                suggestion="Use --overwrite to replace it, or choose a different path.",
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_report_format(report_format: str | None, path: Path) -> str:
    if report_format is None:
        return infer_report_format(path)
    normalized = report_format.lower().lstrip(".")
    if normalized == "htm":
        normalized = "html"
    if normalized not in SUPPORTED_REPORT_FORMATS:
        raise BatchError("Unsupported batch report format. Use csv, json or html.")
    return normalized


def _write_csv(path: Path, payload: dict[str, Any], items: list[BatchItem]) -> None:
    summary = payload["summary"]
    truncation = payload["truncation"]
    csv_summary = {
        **{
            key: summary.get(key, 0)
            for key in ("total", "pending", "success", "failed", "skipped", "blocked")
        },
        "items_included": len(items),
        "items_omitted": truncation["items_omitted"],
        "issues_omitted": truncation["issues_omitted"],
    }
    rows = [
        batch_item_to_report_row(
            item,
            phase=payload["phase"],
            mode=payload["mode"],
            report_summary=csv_summary,
        )
        for item in items
    ]
    with path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as report:
        json.dump(payload, report, indent=2, default=str, ensure_ascii=False)
        report.write("\n")


def _html_document(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    workload = payload["workload"]
    options = payload["options"]
    truncation = payload["truncation"]
    items = payload["items"]
    summary_rows = [
        ("Phase", payload["phase"]),
        ("Mode", payload["mode"]),
        ("Target", workload.get("target_format")),
        ("Workers", workload.get("workers")),
        ("Preserve structure", workload.get("preserve_structure")),
        ("Overwrite", options.get("overwrite")),
        ("Create directories", options.get("create_dirs")),
        ("Total items", summary.get("total", 0)),
        ("Pending", summary.get("pending", 0)),
        ("Success", summary.get("success", 0)),
        ("Failed", summary.get("failed", 0)),
        ("Skipped", summary.get("skipped", 0)),
        ("Blocked", summary.get("blocked", 0)),
        ("Would replace", summary.get("would_replace", 0)),
        ("Would create directories", summary.get("would_create_directories", 0)),
        ("Path conflicts", summary.get("path_conflicts", 0)),
        ("Total input bytes", workload.get("total_input_bytes", 0)),
        ("Items omitted", truncation["items_omitted"]),
        ("Issues omitted", truncation["issues_omitted"]),
    ]
    item_rows = [
        (
            item.get("status"),
            item.get("subsystem"),
            item.get("reason_code"),
            item.get("error") or item.get("reason"),
            item.get("input_file"),
            item.get("input_object"),
            item.get("output_file"),
            f"{item.get('input_extension') or ''} → {item.get('output_extension') or ''}",
            item.get("read_state"),
            item.get("rows_after")
            if item.get("rows_after") is not None
            else item.get("rows"),
            item.get("columns_after")
            if item.get("columns_after") is not None
            else item.get("columns"),
            _recipe_cell(item["recipe"]),
            _policy_cell(item["policy"]),
            _optimization_cell(item["policy"]),
            item.get("sidecar_disposition"),
            item.get("duration_seconds"),
            _manual_retry_hint_dict(item),
        )
        for item in items
    ]
    diagnostics, html_diagnostics_omitted = _html_diagnostics(items)
    notes = _html_notes(
        payload["phase"], payload.get("checks_not_performed", []), options
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>StatConvert batch report</title><style>
body{{font-family:Arial,sans-serif;max-width:1500px;margin:2rem auto;padding:0 1rem;color:#1f2937;line-height:1.45}}
h1,h2{{color:#244b66}}.note{{background:#f7f9fb;border-left:4px solid #3b82f6;padding:.7rem 1rem}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.6rem}}.summary div{{background:#f3f4f6;padding:.7rem}}
.table-wrap{{overflow-x:auto;margin:1rem 0 2rem}}table{{border-collapse:collapse;width:100%;font-size:.86rem}}
th,td{{border:1px solid #d1d5db;padding:.42rem;text-align:left;vertical-align:top}}th{{background:#eaf0f4;white-space:nowrap}}
.truncation{{background:#fff7ed;border-left:4px solid #f59e0b;padding:.7rem 1rem}}
</style></head><body><h1>StatConvert batch report</h1>
<p>This bounded operational report contains no row-level source data or sample values.</p>{notes}
<h2>Command and aggregate summary</h2>{_html_summary(summary_rows)}
{_html_advanced_summaries(summary)}
<h2>Reason-code counts</h2>{_html_table(("Reason code", "Count"), list(sorted(summary.get("reason_counts", {}).items())))}
<h2>Items</h2><p class="truncation">Included {len(items)} of {summary.get("total", 0)} items; {truncation["items_omitted"]} omitted. {truncation["issues_omitted"]} issue details were omitted by model/report limits.</p>
{_html_table(("Status", "Subsystem", "Reason code", "Message", "Input", "Object", "Output", "Format", "Read", "Rows", "Columns", "Recipe", "Policy", "Optimization", "Sidecar", "Duration", "Retry hint"), item_rows)}
<h2>Bounded diagnostics</h2><p class="truncation">Included {len(diagnostics)} diagnostics; {html_diagnostics_omitted} additional included-item diagnostics omitted by the HTML limit.</p>
{_html_table(("Input", "Subsystem", "Severity", "Code", "Column/field", "Message", "Suggestion"), diagnostics)}
</body></html>"""


def _html_advanced_summaries(summary: dict[str, Any]) -> str:
    sections: list[str] = []
    recipe = summary["recipe"]
    if recipe["requested_items"]:
        sections.append(
            "<h2>Recipe summary</h2>"
            + _html_summary(
                [
                    ("Requested items", recipe["requested_items"]),
                    ("Warnings", recipe["warnings"]),
                    ("Errors", recipe["errors"]),
                ]
            )
        )
    policy = summary["policy"]
    if policy["requested_items"]:
        sections.append(
            "<h2>Policy summary</h2>"
            + _html_summary(
                [
                    ("Requested items", policy["requested_items"]),
                    ("Decisions", policy["decisions"]),
                    ("Issues", policy["issues"]),
                ]
            )
        )
    optimization = summary["optimization"]
    if optimization["requested_items"]:
        sections.append(
            "<h2>Optimization summary</h2>"
            + _html_summary(
                [
                    ("Requested items", optimization["requested_items"]),
                    ("Applied", optimization["applied"]),
                    ("Kept", optimization["kept"]),
                    ("Manual", optimization["manual"]),
                ]
            )
        )
    sections.append(
        "<h2>Validation and sidecar summary</h2>"
        + _html_summary(
            [
                ("Validation issues", summary["validation"]["issues"]),
                ("Validation errors", summary["validation"]["errors"]),
                ("Validation warnings", summary["validation"]["warnings"]),
                ("Sidecar dispositions", summary["sidecars"]),
                ("Streaming rows", summary.get("total_streamed_rows", 0)),
                ("Streaming chunks", summary.get("total_streamed_chunks", 0)),
            ]
        )
    )
    return "".join(sections)


def _html_notes(phase: str, checks: list[str], options: dict[str, Any]) -> str:
    notes: list[str] = []
    if phase == "filesystem_plan":
        notes.append(
            "Filesystem dry-run did not read datasets or check schemas, recipe compatibility, transfer-policy decisions, or required metadata sidecars."
        )
    elif phase == "full_plan":
        requested = []
        if options.get("recipe_path"):
            requested.append("recipe compatibility")
        if options.get("policy"):
            requested.append("transfer-policy decisions")
        notes.append(
            "Full-plan read pending datasets and checked "
            + (" and ".join(requested) if requested else "only requested assessments")
            + "; it did not write dataset outputs."
        )
    if checks:
        notes.append("Not checked: " + ", ".join(checks) + ".")
    return "".join(f'<p class="note">{escape(note)}</p>' for note in notes)


def _html_summary(rows: list[tuple[str, Any]]) -> str:
    return (
        '<div class="summary">'
        + "".join(
            f"<div><strong>{escape(label)}:</strong><br>{_html_value(value)}</div>"
            for label, value in rows
        )
        + "</div>"
    )


def _html_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    header = "".join(f"<th>{escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html_value(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


def _html_diagnostics(items: list[dict[str, Any]]) -> tuple[list[tuple[Any, ...]], int]:
    rows: list[tuple[Any, ...]] = []
    total = 0
    for item in items:
        for subsystem in ("recipe", "policy"):
            for diagnostic in item[subsystem].get("diagnostics", []):
                total += 1
                if len(rows) < BATCH_REPORT_DIAGNOSTIC_LIMIT:
                    rows.append(
                        (
                            item.get("input_file"),
                            subsystem,
                            diagnostic.get("severity"),
                            diagnostic.get("code"),
                            diagnostic.get("column") or diagnostic.get("field"),
                            _bounded_message(diagnostic.get("message")),
                            _bounded_message(diagnostic.get("suggestion")),
                        )
                    )
    return rows, total - len(rows)


def _recipe_cell(recipe: dict[str, Any]) -> str:
    if not recipe.get("requested"):
        return "not requested"
    state = recipe.get("execution_status")
    if state in {None, "not_checked"}:
        state = recipe.get("compatibility_status")
    return f"{state}; steps={recipe.get('step_count', 0)}; warnings={recipe.get('warning_count', 0)}; errors={recipe.get('error_count', 0)}"


def _policy_cell(policy: dict[str, Any]) -> str:
    if not policy.get("requested"):
        return "not requested"
    return f"{policy.get('policy_name')}: {policy.get('status')}; decisions={sum(policy.get('decision_counts', {}).values())}; issues={sum(policy.get('issue_counts', {}).values())}"


def _optimization_cell(policy: dict[str, Any]) -> str:
    if not policy.get("optimization_requested"):
        return "not requested"
    return f"applied={policy.get('applied_count', 0)}; kept={policy.get('kept_count', 0)}; manual={policy.get('manual_count', 0)}"


def _bounded_items(
    items: list[BatchItem], limit: int | None
) -> tuple[list[BatchItem], dict[str, int | None]]:
    if limit is not None and limit < 0:
        raise ValueError("Batch report item limit must be zero or greater.")
    included = items if limit is None else items[:limit]
    omitted = items[len(included) :]
    issues_omitted = sum(
        item.recipe.diagnostics_omitted + item.policy.diagnostics_omitted
        for item in included
    )
    issues_omitted += sum(
        len(item.recipe.diagnostics)
        + item.recipe.diagnostics_omitted
        + len(item.policy.diagnostics)
        + item.policy.diagnostics_omitted
        for item in omitted
    )
    return included, {
        "item_limit": limit,
        "items_omitted": len(omitted),
        "issues_omitted": issues_omitted,
    }


def _advanced_summary(items: list[BatchItem]) -> dict[str, Any]:
    return {
        "recipe": {
            "requested_items": sum(item.recipe.requested for item in items),
            "warnings": sum(item.recipe.warning_count for item in items),
            "errors": sum(item.recipe.error_count for item in items),
        },
        "policy": {
            "requested_items": sum(item.policy.requested for item in items),
            "decisions": sum(
                sum(item.policy.decision_counts.values()) for item in items
            ),
            "issues": sum(sum(item.policy.issue_counts.values()) for item in items),
        },
        "optimization": {
            "requested_items": sum(
                item.policy.optimization_requested for item in items
            ),
            "applied": sum(item.policy.applied_count for item in items),
            "kept": sum(item.policy.kept_count for item in items),
            "manual": sum(item.policy.manual_count for item in items),
        },
        "sidecars": _counts(item.sidecar_disposition for item in items),
        "validation": {
            "issues": sum(item.validation_issues or 0 for item in items),
            "errors": sum(item.validation_errors or 0 for item in items),
            "warnings": sum(item.validation_warnings or 0 for item in items),
        },
    }


def _counts(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _manual_retry_hint(item: BatchItem) -> str:
    if item.status not in {"blocked", "failed"}:
        return ""
    object_hint = f" --object {item.input_object}" if item.input_object else ""
    code = f" after resolving {item.reason_code}" if item.reason_code else ""
    return _bounded_message(f"Retry {item.input_file}{object_hint}{code}.") or ""


def _manual_retry_hint_dict(item: dict[str, Any]) -> str:
    if item.get("status") not in {"blocked", "failed"}:
        return ""
    object_hint = (
        f" --object {item['input_object']}" if item.get("input_object") else ""
    )
    code = f" after resolving {item['reason_code']}" if item.get("reason_code") else ""
    return _bounded_message(f"Retry {item.get('input_file')}{object_hint}{code}.") or ""


def _bounded_message(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ")
    return (
        text
        if len(text) <= BATCH_REPORT_MESSAGE_LIMIT
        else text[: BATCH_REPORT_MESSAGE_LIMIT - 1] + "…"
    )


def _html_value(value: Any) -> str:
    return "" if value is None else escape(str(value))


def _report_value(value: Any) -> Any:
    if value is None:
        return ""
    return str(value) if isinstance(value, Path) else value


def _path_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix().casefold()
