from __future__ import annotations

from typing import Callable

from rich.console import Group
from rich.live import Live
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from statconvert.batch import BatchItem, BatchPlan, BatchResult, execute_batch_plan
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.transformations.pipeline import TransformationPipeline

from .console import console


def run_batch_with_progress(
    plan: BatchPlan,
    fail_fast: bool = False,
    workers: int = 1,
    validate: bool = False,
    strict_validation: bool = False,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
    transform_pipeline: TransformationPipeline | None = None,
) -> BatchResult:
    """Execute a batch plan with file-level Rich progress."""

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=30,
        ),
        TextColumn("{task.completed:.0f}/{task.total:.0f}"),
        TimeElapsedColumn(),
        console=console,
        expand=False,
    )
    counts = {"success": 0, "failed": 0, "skipped": 0, "blocked": 0}
    current_file = "-"
    task_id = progress.add_task(
        f"Converting items ({workers} worker{'s' if workers != 1 else ''})",
        total=plan.total_count,
    )

    def render_progress():
        return Group(
            progress,
            _batch_progress_details(
                current_file,
                counts,
            ),
        )

    with Live(
        render_progress(),
        console=console,
        refresh_per_second=10,
    ) as live:

        def on_item_start(item: BatchItem) -> None:
            nonlocal current_file
            current_file = item.input_file.name
            live.update(
                render_progress()
            )

        def on_item_finish(item: BatchItem) -> None:
            nonlocal current_file
            if item.status in counts:
                counts[item.status] += 1
            current_file = item.input_file.name
            progress.update(
                task_id,
                advance=1,
            )
            live.update(
                render_progress()
            )

        return execute_batch_plan(
            plan,
            fail_fast=fail_fast,
            workers=workers,
            validate=validate,
            strict_validation=strict_validation,
            object_selector=object_selector,
            read_options=read_options,
            write_options=write_options,
            on_option_warning=on_option_warning,
            transform_pipeline=transform_pipeline,
            on_item_start=on_item_start,
            on_item_finish=on_item_finish,
        )


def show_batch_plan(
    plan: BatchPlan
) -> None:
    """
    Display a batch conversion plan.
    """

    summary = Table(
        title="Batch Plan Summary"
    )
    summary.add_column(
        "Metric",
        style="cyan",
    )
    summary.add_column(
        "Value",
        justify="right",
    )
    summary.add_row(
        "Total items",
        _format_count(
            plan.total_count
        ),
    )
    summary.add_row(
        "Pending",
        _format_count(
            plan.pending_count
        ),
    )
    summary.add_row(
        "Skipped",
        _format_count(
            plan.skipped_count
        ),
    )
    summary.add_row(
        "Blocked",
        _format_count(
            plan.blocked_count
        ),
    )
    _add_workload_rows(summary, plan.workload)
    summary.add_row(
        "Target extension",
        plan.options.target_extension,
    )
    summary.add_row(
        "Recursive",
        _format_bool(
            plan.options.recursive
        ),
    )
    summary.add_row(
        "Preserve structure",
        _format_bool(
            plan.options.preserve_structure
        ),
    )
    summary.add_row(
        "Overwrite",
        _format_bool(
            plan.options.overwrite
        ),
    )
    summary.add_row(
        "Include patterns",
        _format_patterns(plan.options.patterns),
    )
    summary.add_row(
        "Exclude patterns",
        _format_patterns(plan.options.exclude_patterns),
    )
    summary.add_row(
        "Object manifest",
        "none" if plan.options.object_manifest is None else str(
            plan.options.object_manifest
        ),
    )
    summary.add_row(
        "All objects",
        _format_bool(plan.options.all_objects),
    )

    console.print(
        summary
    )
    _show_memory_note(plan.workload.memory_note)

    table = Table(
        title="Batch Plan Items"
    )
    table.add_column(
        "Status",
        no_wrap=True,
    )
    table.add_column(
        "Input file",
        style="cyan",
        max_width=28,
    )
    table.add_column(
        "Output file",
        max_width=28,
    )
    table.add_column(
        "Reason",
    )

    for item in plan.items:
        table.add_row(
            item.status,
            _format_input_file(
                item
            ),
            "" if item.output_file is None else str(
                item.output_file
            ),
            item.reason or "",
        )

    console.print(
        table
    )


def show_batch_result(
    result: BatchResult
) -> None:
    """
    Display a batch execution result.
    """

    summary = Table(
        title="Batch Result Summary"
    )
    summary.add_column(
        "Metric",
        style="cyan",
    )
    summary.add_column(
        "Value",
        justify="right",
    )
    summary.add_row(
        "Total items",
        _format_count(
            result.total_count
        ),
    )
    summary.add_row(
        "Succeeded",
        _format_count(
            result.success_count
        ),
    )
    summary.add_row(
        "Failed",
        _format_count(
            result.failed_count
        ),
    )
    summary.add_row(
        "Skipped",
        _format_count(
            result.skipped_count
        ),
    )
    summary.add_row(
        "Blocked",
        _format_count(
            result.blocked_count
        ),
    )
    _add_workload_rows(summary, result.workload)

    console.print(
        summary
    )
    _show_memory_note(result.workload.memory_note)

    table = Table(
        title="Batch Result Items"
    )
    table.add_column(
        "Status",
        no_wrap=True,
    )
    table.add_column(
        "Input file",
        style="cyan",
        max_width=24,
    )
    table.add_column(
        "Shape",
        justify="right",
    )
    table.add_column(
        "Duration",
        justify="right",
    )
    table.add_column(
        "Error / reason",
        min_width=20,
    )

    for item in result.items:
        table.add_row(
            item.status,
            _format_input_file(item),
            _format_shape(item),
            "" if item.duration_seconds is None else f"{item.duration_seconds:.2f}s",
            _format_item_message(item),
        )

    console.print(
        table
    )


def _format_count(
    value: int
) -> str:
    """
    Format an integer count.
    """

    return f"{value:,}"


def _add_workload_rows(summary: Table, workload) -> None:
    """Add lightweight workload and concurrency metadata to a summary table."""

    summary.add_row("Planned files", _format_count(workload.planned_files))
    summary.add_row("Supported files", _format_count(workload.supported_files))
    summary.add_row("Skipped files", _format_count(workload.skipped_files))
    summary.add_row("Workers", _format_count(workload.workers))
    summary.add_row("Total input size", _format_bytes(workload.total_input_bytes))
    summary.add_row(
        "Largest input file",
        _format_bytes(workload.largest_input_file_bytes),
    )
    summary.add_row("Object mode", workload.object_mode)
    summary.add_row("Transform", _format_bool(workload.transform_enabled))
    summary.add_row("Validation", _format_bool(workload.validation_enabled))


def _show_memory_note(message: str | None) -> None:
    if message:
        console.print(f"[cyan]Note:[/cyan] {message}")


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _format_bool(
    value: bool
) -> str:
    """
    Format a boolean option for display.
    """

    return "yes" if value else "no"


def _format_patterns(patterns: list[str] | None) -> str:
    """Format optional batch patterns compactly."""

    return ", ".join(patterns) if patterns else "none"


def _format_item_message(item: BatchItem) -> str:
    """Combine optional validation counts with an item's error or reason."""

    message = item.error or item.reason or ""
    if item.validation_issues is None:
        return message
    counts = f"[{item.validation_errors or 0}E/{item.validation_warnings or 0}W]"
    return f"{counts} {message}" if message else counts


def _format_shape(item: BatchItem) -> str:
    """Format rows and columns compactly when both are available."""

    if item.rows is None or item.columns is None:
        return ""
    return f"{item.rows:,}×{item.columns:,}"


def _batch_progress_details(
    current_file: str,
    counts: dict[str, int],
) -> Text:
    """Render file and status details below the progress bar."""

    return Text(
        "\n"
        f"Current: {_format_current_file(current_file)}\n"
        f"Succeeded: {counts['success']:,}   "
        f"Failed: {counts['failed']:,}   "
        f"Skipped: {counts['skipped']:,}   "
        f"Blocked: {counts['blocked']:,}"
    )


def _format_current_file(
    file_name: str,
    max_length: int = 48,
) -> str:
    """Keep long file names from stretching the progress display."""

    if len(
        file_name
    ) <= max_length:
        return file_name

    return f"{file_name[: max_length - 3]}..."


def _format_input_file(
    item
) -> str:
    """
    Format an input file compactly for result tables.
    """

    display = (
        str(item.relative_path)
        if item.relative_path is not None
        else item.input_file.name
    )
    if item.input_object is not None:
        return f"{display} [{item.input_object}]"
    return display
