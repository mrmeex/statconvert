from __future__ import annotations

from rich.table import Table

from statconvert.compare import DatasetComparison

from .console import console


def show_dataset_comparison(comparison: DatasetComparison) -> None:
    """Display a compact, complete dataset comparison."""

    _show_summary(comparison)
    _show_inputs(comparison)
    _show_options(comparison)
    _show_shape(comparison)
    _show_columns(comparison)
    _show_schema(comparison)
    _show_metadata(comparison)
    _show_values(comparison)
    _show_first_differences(comparison)
    _show_issues(comparison)


def _show_inputs(comparison: DatasetComparison) -> None:
    if comparison.left_source is None and comparison.right_source is None:
        return
    table = Table(title="Inputs")
    table.add_column("Side", style="cyan")
    table.add_column("Source")
    table.add_row("Left", comparison.left_source or "-")
    table.add_row("Right", comparison.right_source or "-")
    console.print(table)


def _show_options(comparison: DatasetComparison) -> None:
    options = comparison.options
    if (
        not options.ignore_columns
        and options.numeric_tolerance == 0
        and not options.key_columns
        and options.max_differences == 50
    ):
        return

    table = Table(title="Comparison Options")
    table.add_column("Option", style="cyan")
    table.add_column("Value")
    table.add_row("Row matching", comparison.row_matching_mode)
    if options.key_columns:
        table.add_row(
            "Key columns",
            _format_column_list(list(options.key_columns)),
        )
        table.add_row("Matched rows", f"{comparison.matched_rows:,}")
        table.add_row("Rows only in left", f"{comparison.rows_only_left:,}")
        table.add_row("Rows only in right", f"{comparison.rows_only_right:,}")
    table.add_row(
        "Ignored columns",
        _format_column_list(list(options.ignore_columns)),
    )
    table.add_row("Columns compared", str(len(comparison.columns_compared)))
    table.add_row("Numeric tolerance", f"{options.numeric_tolerance:g}")
    table.add_row("Max differences", f"{options.max_differences:,}")
    console.print(table)


def _show_summary(comparison: DatasetComparison) -> None:
    error_count = sum(issue.severity == "error" for issue in comparison.issues)
    warning_count = sum(issue.severity == "warning" for issue in comparison.issues)
    if comparison.has_errors:
        status = "Errors found"
    elif comparison.is_identical:
        status = "Identical"
    elif comparison.issues:
        status = "Differences found"
    else:
        status = "No checked differences"

    table = Table(title="Comparison Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Status", status)
    table.add_row("Identical", _yes_no(comparison.is_identical))
    table.add_row("Compatible", _yes_no(comparison.is_compatible))
    table.add_row("Errors", str(error_count))
    table.add_row("Warnings", str(warning_count))
    table.add_row("Row matching", comparison.row_matching_mode)
    table.add_row(
        "Rows left / right",
        f"{comparison.shape.left_rows:,} / {comparison.shape.right_rows:,}",
    )
    table.add_row("Matched rows", f"{comparison.matched_rows:,}")
    table.add_row(
        "Rows only left / right",
        f"{comparison.rows_only_left:,} / {comparison.rows_only_right:,}",
    )
    table.add_row("Columns compared", f"{len(comparison.columns_compared):,}")
    if comparison.values is not None:
        table.add_row("Cells compared", f"{comparison.values.cells_compared:,}")
        table.add_row("Cells different", f"{comparison.values.differing_cells:,}")
    table.add_row("Max differences shown", f"{comparison.options.max_differences:,}")
    console.print(table)


def _show_shape(comparison: DatasetComparison) -> None:
    shape = comparison.shape
    table = Table(title="Shape")
    table.add_column("Metric", style="cyan")
    table.add_column("Left", justify="right")
    table.add_column("Right", justify="right")
    table.add_column("Match")
    table.add_row(
        "Rows", f"{shape.left_rows:,}", f"{shape.right_rows:,}", _yes_no(shape.rows_match)
    )
    table.add_row(
        "Columns",
        f"{shape.left_columns:,}",
        f"{shape.right_columns:,}",
        _yes_no(shape.columns_match),
    )
    console.print(table)


def _show_columns(comparison: DatasetComparison) -> None:
    columns = comparison.columns
    table = Table(title="Columns")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Same columns", _yes_no(columns.same_columns))
    table.add_row("Same order", _yes_no(columns.same_order))
    table.add_row("Left only", _format_column_list(columns.left_only_columns))
    table.add_row("Right only", _format_column_list(columns.right_only_columns))
    console.print(table)


def _show_schema(comparison: DatasetComparison) -> None:
    schema = comparison.schema
    change_groups = (
        ("Storage type", "Changed Storage Types", schema.storage_type_changes),
        ("Display format", "Display Format Changes", schema.display_format_changes),
        (
            "Measurement level",
            "Measurement Level Changes",
            schema.measurement_level_changes,
        ),
    )
    if not any(changes for _, _, changes in change_groups):
        console.print("[green]Schema: no changes.[/green]")
        return

    summary = Table(title="Schema")
    summary.add_column("Change type", style="cyan")
    summary.add_column("Columns", justify="right")
    for label, _, changes in change_groups:
        summary.add_row(label, str(len(changes)))
    console.print(summary)

    for _, title, changes in change_groups:
        if changes:
            _show_schema_changes(title, changes)


def _show_schema_changes(
    title: str,
    changes: dict[str, tuple[str | None, str | None]],
) -> None:
    table = Table(title=title)
    table.add_column("Column", style="cyan")
    table.add_column("Left")
    table.add_column("Right")
    for column, (left_value, right_value) in changes.items():
        table.add_row(column, left_value or "-", right_value or "-")
    console.print(table)


def _show_metadata(comparison: DatasetComparison) -> None:
    metadata = comparison.metadata
    table = Table(title="Metadata")
    table.add_column("Change type", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_row("Variable labels", str(len(metadata.variable_label_changes)))
    table.add_row("Value labels", str(len(metadata.value_label_changes)))
    table.add_row("Missing values", str(len(metadata.missing_value_changes)))
    console.print(table)


def _show_values(comparison: DatasetComparison) -> None:
    values = comparison.values
    if values is None:
        console.print("[yellow]Values: comparison skipped.[/yellow]")
        return

    table = Table(title="Values")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Compared rows", f"{values.compared_rows:,}")
    table.add_row("Compared columns", f"{values.compared_columns:,}")
    table.add_row("Cells compared", f"{values.cells_compared:,}")
    table.add_row("Differing cells", f"{values.differing_cells:,}")
    table.add_row("Same values", _yes_no(values.same_values))
    if values.sampled:
        displayed_sample_size = values.sample_size or values.compared_rows
        sample_text = f"yes (first {displayed_sample_size:,} rows)"
    else:
        sample_text = "no"
    table.add_row("Sampled", sample_text)
    console.print(table)

    differences = {
        column: count
        for column, count in values.differences_by_column.items()
        if count
    }
    if differences:
        detail = Table(title="Value Differences By Column")
        detail.add_column("Column", style="cyan")
        detail.add_column("Differing cells", justify="right")
        for column, count in differences.items():
            detail.add_row(column, f"{count:,}")
        console.print(detail)


def _show_first_differences(comparison: DatasetComparison) -> None:
    if not comparison.differences:
        return

    table = Table(title="First Differences")
    table.add_column("Kind", style="cyan")
    table.add_column("Row / key")
    table.add_column("Column")
    table.add_column("Left")
    table.add_column("Right")
    for detail in comparison.differences:
        table.add_row(
            detail.kind,
            _format_difference_location(detail.row, detail.key),
            detail.column or "-",
            _format_detail_value(detail.left),
            _format_detail_value(detail.right),
        )
    console.print(table)
    if comparison.detailed_differences_truncated:
        console.print(
            "[yellow]Showing first "
            f"{comparison.detailed_differences_shown:,} of "
            f"{comparison.detailed_differences_total:,} detailed differences.[/yellow]"
        )


def _show_issues(comparison: DatasetComparison) -> None:
    if not comparison.issues:
        console.print("[green]No comparison issues found.[/green]")
        return

    table = Table(title="Comparison Issues")
    table.add_column("Severity")
    table.add_column("Code", style="cyan")
    table.add_column("Column")
    table.add_column("Message")
    for issue in comparison.issues:
        table.add_row(
            _format_severity(issue.severity),
            issue.code,
            issue.column or "-",
            issue.message,
        )
    console.print(table)


def _format_column_list(columns: list[str], limit: int = 8) -> str:
    if not columns:
        return "-"
    displayed = ", ".join(columns[:limit])
    remaining = len(columns) - limit
    return f"{displayed} ... (+{remaining} more)" if remaining > 0 else displayed


def _format_difference_location(
    row: int | None,
    key: dict[str, object] | None,
) -> str:
    if key is not None:
        return ", ".join(f"{column}={value!r}" for column, value in key.items())
    return str(row) if row is not None else "-"


def _format_detail_value(value: object) -> str:
    return "-" if value is None else repr(value)


def _format_severity(severity: str) -> str:
    style = {"info": "blue", "warning": "yellow", "error": "red"}.get(
        severity, "white"
    )
    return f"[{style}]{severity}[/{style}]"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
