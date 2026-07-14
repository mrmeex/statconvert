from __future__ import annotations

from pathlib import Path

from rich.table import Table

from statconvert.reporting import DatasetReport, dataset_report_summary_dict

from .console import console


def show_dataset_report_written(
    report: DatasetReport,
    output_file: str | Path,
    output_format: str | None = None,
    preset: str = "default",
    max_table_rows: int = 1000,
    max_preview_values: int = 5,
) -> None:
    """Display a compact summary for a successfully written dataset report."""

    summary = dataset_report_summary_dict(
        report,
        output_file,
        output_format,
        preset=preset,
        max_table_rows=max_table_rows,
        max_preview_values=max_preview_values,
    )
    table = Table(title="Dataset report written")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Output", summary["output_file"])
    table.add_row("Format", summary["format"])
    table.add_row("Preset", summary["preset"])
    table.add_row("Sections", str(summary["sections"]))
    table.add_row("Issues", str(summary["issues"]))
    table.add_row("Warnings", _yes_no(summary["has_warnings"]))
    table.add_row("Errors", _yes_no(summary["has_errors"]))
    console.print(table)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
