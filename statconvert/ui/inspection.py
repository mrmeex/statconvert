from __future__ import annotations

import pandas as pd

from rich.table import Table

from statconvert.inspection import (
    ColumnProfile,
    DatasetSummary,
    FrequencyTable,
    MissingProfile,
    ValidationIssue,
)

from .console import console


def show_dataset_summary(
    summary: DatasetSummary
) -> None:
    """
    Display a dataset summary.
    """

    table = Table(
        title="Dataset Summary"
    )
    table.add_column(
        "Metric",
        style="cyan",
    )
    table.add_column(
        "Value",
        justify="right",
    )

    for metric, value in _summary_rows(
        summary
    ):
        table.add_row(
            metric,
            value,
        )

    console.print(
        table
    )


def show_column_profiles(
    profiles: list[ColumnProfile]
) -> None:
    """
    Display column profiles.
    """

    if not profiles:
        console.print(
            "[yellow]No column profiles to display.[/yellow]"
        )
        return

    table = Table(
        title="Column Profiles"
    )
    table.add_column(
        "Column",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Type",
        no_wrap=True,
    )
    table.add_column(
        "Label",
    )
    table.add_column(
        "Profile",
        no_wrap=True,
    )
    table.add_column(
        "Non-missing",
        justify="right",
    )
    table.add_column(
        "Missing",
        justify="right",
    )
    table.add_column(
        "Missing %",
        justify="right",
    )
    table.add_column(
        "Unique",
        justify="right",
    )

    for profile in profiles:
        table.add_row(
            profile.name,
            profile.storage_type,
            profile.label or "",
            profile.profile_type,
            _format_count(
                profile.non_missing_count
            ),
            _format_count(
                profile.missing_count
            ),
            _format_percent(
                profile.missing_percent
            ),
            "" if profile.unique_count is None else _format_count(
                profile.unique_count
            ),
        )

    console.print(
        table
    )
    _show_numeric_profiles(
        profiles
    )
    _show_categorical_profiles(
        profiles
    )


def show_missing_profiles(
    profiles: list[MissingProfile]
) -> None:
    """
    Display missing-value profiles.
    """

    if not profiles:
        console.print(
            "[yellow]No missing values found.[/yellow]"
        )
        return

    table = Table(
        title="Missing Values"
    )
    table.add_column(
        "Column",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Label",
    )
    table.add_column(
        "Missing",
        justify="right",
    )
    table.add_column(
        "Missing %",
        justify="right",
    )
    table.add_column(
        "Metadata missing values",
    )

    for profile in profiles:
        table.add_row(
            profile.column,
            profile.label or "",
            _format_count(
                profile.missing_count
            ),
            _format_percent(
                profile.missing_percent
            ),
            _format_metadata_missing_values(
                profile.metadata_missing_values
            ),
        )

    console.print(
        table
    )


def show_frequency_tables(
    tables: list[FrequencyTable]
) -> None:
    """
    Display frequency tables.
    """

    if not tables:
        console.print(
            "[yellow]No frequency tables available.[/yellow]"
        )
        return

    for frequency in tables:
        title = f"Frequencies: {frequency.column}"

        if frequency.label:
            title = f"{title} - {frequency.label}"

        table = Table(
            title=title
        )
        table.add_column(
            "Value",
            style="cyan",
            no_wrap=True,
        )
        table.add_column(
            "Label",
        )
        table.add_column(
            "Count",
            justify="right",
        )
        table.add_column(
            "Percent",
            justify="right",
        )

        for item in frequency.items:
            table.add_row(
                _format_frequency_value(
                    item.value
                ),
                item.label or "",
                _format_count(
                    item.count
                ),
                _format_percent(
                    item.percent
                ),
            )

        console.print(
            table
        )


def show_validation_issues(
    issues: list[ValidationIssue],
    strict: bool = False,
    target_format: str | None = None,
) -> None:
    """
    Display validation issues.
    """

    if not issues:
        console.print(
            "[green]No validation issues found.[/green]"
        )
        return

    title = "Validation Issues"

    if target_format:
        title = f"{title} for {target_format}"

    if strict:
        title = f"{title} (strict)"

    table = Table(
        title=title
    )
    table.add_column(
        "Severity",
        no_wrap=True,
    )
    table.add_column(
        "Code",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Column",
        no_wrap=True,
    )
    table.add_column(
        "Message",
    )

    for issue in issues:
        table.add_row(
            _format_severity(
                issue.severity
            ),
            issue.code,
            issue.column or "",
            issue.message,
        )

    console.print(
        table
    )

    if not any(
        issue.severity in {
            "warning",
            "error",
        }
        for issue in issues
    ):
        console.print(
            "[green]No validation warnings or errors found.[/green]"
        )


def _summary_rows(
    summary: DatasetSummary
) -> list[tuple[str, str]]:
    """
    Return display rows for a dataset summary.
    """

    return [
        (
            "Rows",
            _format_count(
                summary.row_count
            ),
        ),
        (
            "Columns",
            _format_count(
                summary.column_count
            ),
        ),
        (
            "Numeric columns",
            _format_count(
                summary.numeric_columns
            ),
        ),
        (
            "Text columns",
            _format_count(
                summary.text_columns
            ),
        ),
        (
            "Boolean columns",
            _format_count(
                summary.boolean_columns
            ),
        ),
        (
            "Datetime columns",
            _format_count(
                summary.datetime_columns
            ),
        ),
        (
            "Categorical columns",
            _format_count(
                summary.categorical_columns
            ),
        ),
        (
            "Other columns",
            _format_count(
                summary.other_columns
            ),
        ),
        (
            "Columns with variable labels",
            _format_count(
                summary.columns_with_variable_labels
            ),
        ),
        (
            "Columns with value labels",
            _format_count(
                summary.columns_with_value_labels
            ),
        ),
        (
            "Total missing cells",
            _format_count(
                summary.total_missing_cells
            ),
        ),
        (
            "Duplicate rows",
            _format_count(
                summary.duplicate_rows
            ),
        ),
        (
            "Memory usage",
            _format_memory(
                summary.memory_usage_bytes
            ),
        ),
    ]


def _format_count(
    value: int
) -> str:
    """
    Format an integer count.
    """

    return f"{value:,}"


def _format_memory(
    value: int | None
) -> str:
    """
    Format a byte count as a compact human-readable value.
    """

    if value is None:
        return "unknown"

    size = float(
        value
    )

    for unit in [
        "B",
        "KB",
        "MB",
        "GB",
    ]:
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size):,} {unit}"

            return f"{size:.1f} {unit}"

        size = size / 1024

    return f"{size:.1f} GB"


def _show_numeric_profiles(
    profiles: list[ColumnProfile]
) -> None:
    """
    Display numeric statistics for profiles that have them.
    """

    numeric_profiles = [
        profile
        for profile in profiles
        if profile.numeric
    ]

    if not numeric_profiles:
        return

    table = Table(
        title="Numeric Statistics"
    )
    table.add_column(
        "Column",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Mean",
        justify="right",
    )
    table.add_column(
        "Std Dev",
        justify="right",
    )
    table.add_column(
        "Min",
        justify="right",
    )
    table.add_column(
        "Q1",
        justify="right",
    )
    table.add_column(
        "Median",
        justify="right",
    )
    table.add_column(
        "Q3",
        justify="right",
    )
    table.add_column(
        "Max",
        justify="right",
    )

    for profile in numeric_profiles:
        numeric = profile.numeric
        table.add_row(
            profile.name,
            _format_number(
                numeric.mean
            ),
            _format_number(
                numeric.std
            ),
            _format_number(
                numeric.min
            ),
            _format_number(
                numeric.q1
            ),
            _format_number(
                numeric.median
            ),
            _format_number(
                numeric.q3
            ),
            _format_number(
                numeric.max
            ),
        )

    console.print(
        table
    )


def _show_categorical_profiles(
    profiles: list[ColumnProfile]
) -> None:
    """
    Display categorical statistics for profiles that have them.
    """

    categorical_profiles = [
        profile
        for profile in profiles
        if profile.categorical
    ]

    if not categorical_profiles:
        return

    table = Table(
        title="Categorical Statistics"
    )
    table.add_column(
        "Column",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Top Value",
    )
    table.add_column(
        "Top Label",
    )
    table.add_column(
        "Top Count",
        justify="right",
    )
    table.add_column(
        "Top %",
        justify="right",
    )

    for profile in categorical_profiles:
        categorical = profile.categorical
        table.add_row(
            profile.name,
            "" if categorical.top_value is None else str(
                categorical.top_value
            ),
            categorical.top_label or "",
            "" if categorical.top_count is None else _format_count(
                categorical.top_count
            ),
            "" if categorical.top_percent is None else _format_percent(
                categorical.top_percent
            ),
        )

    console.print(
        table
    )


def _format_percent(
    value: float
) -> str:
    """
    Format a percentage value.
    """

    return f"{value:.1f}%"


def _format_number(
    value: float | None
) -> str:
    """
    Format a numeric profile value.
    """

    if value is None:
        return ""

    return f"{value:,.2f}"


def _format_frequency_value(
    value
) -> str:
    """
    Format a frequency value for display.
    """

    try:
        if pd.isna(
            value
        ):
            return "<missing>"

    except Exception:
        pass

    return str(
        value
    )


def _format_metadata_missing_values(
    values: list
) -> str:
    """
    Format metadata-defined missing values compactly for display.
    """

    if not values:
        return "-"

    display_limit = 5
    displayed_values = [
        str(
            value
        )
        for value in values[:display_limit]
    ]

    if len(
        values
    ) > display_limit:
        remaining = len(
            values
        ) - display_limit
        displayed_values.append(
            f"... (+{remaining} more)"
        )

    return ", ".join(
        displayed_values
    )


def _format_severity(
    severity: str
) -> str:
    """
    Format validation severity with a stable visual style.
    """

    styles = {
        "info": "blue",
        "warning": "yellow",
        "error": "red",
    }
    style = styles.get(
        severity,
        "white",
    )

    return f"[{style}]{severity}[/{style}]"
