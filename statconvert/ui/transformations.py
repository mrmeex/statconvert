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
