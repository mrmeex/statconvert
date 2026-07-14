from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from statconvert.dataset import Dataset
from statconvert.transformations import TransformationPipeline

from .console import console


def show_transformation_summary(
    input_file: str,
    output_file: str,
    pipeline: TransformationPipeline,
    transformed_dataset: Dataset,
    dry_run: bool = False,
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
    table.add_row(
        "Transformations",
        str(
            len(
                pipeline
            )
        ),
    )
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
