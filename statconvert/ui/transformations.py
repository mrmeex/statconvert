from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from statconvert.dataset import Dataset
from statconvert.transformations import (
    DeriveColumnTransformation,
    ExpressionFilterTransformation,
    RecodeValuesTransformation,
    TransformationPipeline,
)

from .console import console


def show_transformation_summary(
    input_file: str,
    output_file: str,
    pipeline: TransformationPipeline | None,
    transformed_dataset: Dataset,
    dry_run: bool = False,
    *,
    ordered_recipe: bool = False,
    recipe_step_count: int | None = None,
    derived_count: int | None = None,
    expression_filter_count: int | None = None,
    recode_count: int | None = None,
) -> None:
    """
    Display a concise transformation result summary.
    """

    table = Table.grid(
        padding=(0, 2)
    )
    table.add_column(
        style="cyan",
        justify="right",
    )
    table.add_column()

    table.add_row(
        "Input",
        input_file,
    )
    table.add_row(
        "Output",
        output_file,
    )
    table.add_row(
        "Mode",
        "Dry run" if dry_run else "Written",
    )
    transformation_count = (
        recipe_step_count
        if recipe_step_count is not None
        else len(pipeline or TransformationPipeline())
    )
    table.add_row("Transformations", str(transformation_count))
    if ordered_recipe:
        table.add_row("Ordered recipe", "Yes")
    transformations = (
        pipeline.transformations if pipeline is not None else []
    )
    if derived_count is None:
        derived_count = sum(
            isinstance(transformation, DeriveColumnTransformation)
            for transformation in transformations
        )
    if expression_filter_count is None:
        expression_filter_count = sum(
            isinstance(transformation, ExpressionFilterTransformation)
            for transformation in transformations
        )
    if recode_count is None:
        recode_count = sum(
            len(transformation.recode_map)
            for transformation in transformations
            if isinstance(transformation, RecodeValuesTransformation)
        )
    if derived_count:
        table.add_row("Derived columns", str(derived_count))
    if expression_filter_count:
        table.add_row("Expression filters", str(expression_filter_count))
    if recode_count:
        table.add_row("Recoded columns", str(recode_count))
    table.add_row(
        "Rows",
        f"{transformed_dataset.rows:,}",
    )
    table.add_row(
        "Columns",
        f"{len(transformed_dataset.columns):,}",
    )

    console.print(
        Panel(
            table,
            title="Transformation Summary",
            expand=False,
        )
    )


def show_full_transform_preview(payload: dict[str, object]) -> None:
    """Display the compact human view of an exact non-writing preview."""

    summary = payload["summary"]
    output = payload["output"]
    assert isinstance(summary, dict)
    assert isinstance(output, dict)
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", justify="right")
    table.add_column()
    table.add_row("Mode", "Full preview (writes nothing)")
    table.add_row("Output", str(output["path"]))
    table.add_row(
        "Rows",
        f"{summary['rows_before']:,} -> {summary['rows_after']:,} "
        f"({summary['rows_removed']:,} removed)",
    )
    table.add_row(
        "Columns",
        f"{len(summary['columns_before']):,} -> {len(summary['columns_after']):,}",
    )
    table.add_row("Metadata", str(output["metadata_mode"]))
    table.add_row("Steps", str(len(payload["steps"])))
    console.print(Panel(table, title="Transform Preview", expand=False))


def show_transform_recipe_validation(payload: dict[str, object]) -> None:
    """Display a compact portable-recipe validation result."""

    valid = bool(payload["valid"])
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", justify="right")
    table.add_column()
    table.add_row("Status", "Valid" if valid else "Invalid")
    table.add_row("Mode", str(payload["mode"]))
    table.add_row("Schema", str(payload.get("schema_version", "-")))
    issues = payload.get("issues", [])
    table.add_row("Issues", str(len(issues) if isinstance(issues, list) else 0))
    console.print(Panel(table, title="Transform Recipe", expand=False))
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict):
                console.print(f"[red]{issue.get('message', 'Unknown issue')}[/red]")
