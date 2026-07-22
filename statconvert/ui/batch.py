from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Callable

from rich.console import Group
from rich.live import Live
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from statconvert.batch import (
    BATCH_PROGRESS_ITEM_FINISHED,
    BATCH_PROGRESS_ITEM_STARTED,
    BATCH_STATUS_SUCCESS,
    BatchItem,
    BatchPlan,
    BatchProgressEvent,
    BatchResult,
    execute_batch_plan,
)
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
    report_path: str | Path | None = None,
) -> BatchResult:
    """Execute a batch plan with concise live item and worker status."""

    show_batch_workload(plan, report_path=report_path)
    console.print("[bold]Running batch...[/bold]")

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
    active_items: dict[int, str] = {}
    worker_slots: dict[int, int] = {}
    state_lock = Lock()
    task_id = progress.add_task(
        f"Converting items ({workers} worker{'s' if workers != 1 else ''})",
        total=plan.total_count,
    )

    live_details = _LiveBatchDetails(
        active_items,
        worker_slots,
        counts,
        workers,
        state_lock,
    )

    with Live(
        Group(progress, live_details),
        console=console,
        refresh_per_second=10,
    ):

        def on_progress(event: BatchProgressEvent) -> None:
            if event.kind == BATCH_PROGRESS_ITEM_STARTED:
                with state_lock:
                    worker_id = event.worker_id or 0
                    if worker_id not in worker_slots:
                        worker_slots[worker_id] = len(worker_slots) + 1
                    active_items[worker_id] = _format_event_input(event)
                return

            if event.kind == BATCH_PROGRESS_ITEM_FINISHED:
                with state_lock:
                    if event.status in counts:
                        counts[event.status] += 1
                    if event.worker_id is not None:
                        active_items.pop(event.worker_id, None)
                progress.update(task_id, advance=1)

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
            on_progress=on_progress,
        )


def show_batch_workload(
    plan: BatchPlan,
    report_path: str | Path | None = None,
) -> None:
    """Show the execution settings that matter to a batch operator."""

    table = Table(title="Batch Workload")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Planned items", _format_count(plan.total_count))
    table.add_row("Workers", _format_count(plan.workload.workers))
    table.add_row("Target format", plan.workload.target_format)
    table.add_row(
        "Structure",
        "preserve" if plan.workload.preserve_structure else "flatten",
    )
    table.add_row("Object mode", plan.workload.object_mode)
    table.add_row("Transform", _format_bool(plan.workload.transform_enabled))
    table.add_row("Validation", _format_bool(plan.workload.validation_enabled))
    table.add_row("Report", "none" if report_path is None else str(report_path))
    console.print(table)
    _show_memory_note(plan.workload.memory_note)


def show_batch_plan(
    plan: BatchPlan,
    report_path: str | Path | None = None,
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
    summary.add_row(
        "Report",
        "none" if report_path is None else str(report_path),
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
    result: BatchResult,
    report_path: str | Path | None = None,
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
        "Output file",
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
            _format_output_file(item),
            _format_shape(item),
            "" if item.duration_seconds is None else f"{item.duration_seconds:.2f}s",
            _format_item_message(item),
        )

    console.print(
        table
    )
    _show_batch_issues(result)
    if report_path is not None:
        console.print(f"[green]Report:[/green] {report_path}")
    if result.has_failures or result.has_blockers:
        if report_path is not None:
            next_step = (
                f"Review the report at {report_path}, correct the failed inputs or "
                "options, then rerun the batch."
            )
        else:
            next_step = (
                "Review the failed items above, correct the inputs or options, then "
                "rerun the batch."
            )
        console.print(f"[yellow]Next step:[/yellow] {next_step}")
    elif result.success_count == 0 and result.skipped_count > 0:
        console.print(
            "[yellow]Next step:[/yellow] No items were converted. Review the skipped "
            "reasons above, check supported formats with `statconvert formats`, and "
            "rerun the batch."
        )


def _show_batch_issues(result: BatchResult) -> None:
    """Show non-success items without truncating their actionable reason."""

    issues = [
        item
        for item in result.items
        if item.status != BATCH_STATUS_SUCCESS and _format_item_message(item)
    ]
    if not issues:
        return
    console.print("[bold]Batch issues[/bold]")
    for item in issues:
        output = _format_output_file(item) or "no output planned"
        console.print(
            f"- {_format_input_file(item)} -> {output}: {_format_item_message(item)}"
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
    active_items: dict[int, str],
    worker_slots: dict[int, int],
    counts: dict[str, int],
    workers: int,
) -> Text:
    """Render active items and terminal counts below the progress bar."""

    if workers == 1:
        current = next(iter(active_items.values()), "waiting")
        active_text = f"Current: {_format_current_file(current)}"
    else:
        by_slot = {
            worker_slots[worker_id]: file_name
            for worker_id, file_name in active_items.items()
            if worker_id in worker_slots
        }
        worker_lines = [
            f"Worker {slot}: {_format_current_file(by_slot.get(slot, 'waiting'))}"
            for slot in range(1, workers + 1)
        ]
        active_text = "Active:\n  " + "\n  ".join(worker_lines)

    return Text(
        f"\n{active_text}\n"
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


def _format_output_file(item: BatchItem) -> str:
    """Format a planned output path compactly while retaining structure."""

    if item.output_file is None:
        return ""
    if item.relative_path is not None and item.relative_path.parent != Path("."):
        return str(item.relative_path.parent / item.output_file.name)
    return item.output_file.name


class _LiveBatchDetails:
    """Render a thread-safe snapshot during automatic Live refreshes."""

    def __init__(
        self,
        active_items: dict[int, str],
        worker_slots: dict[int, int],
        counts: dict[str, int],
        workers: int,
        lock: Lock,
    ) -> None:
        self.active_items = active_items
        self.worker_slots = worker_slots
        self.counts = counts
        self.workers = workers
        self.lock = lock

    def __rich_console__(self, console, options):
        del console, options
        with self.lock:
            active_items = dict(self.active_items)
            worker_slots = dict(self.worker_slots)
            counts = dict(self.counts)
        yield _batch_progress_details(
            active_items,
            worker_slots,
            counts,
            self.workers,
        )


def _format_event_input(event: BatchProgressEvent) -> str:
    if event.input_path is None:
        return "waiting"
    return event.input_path.name
