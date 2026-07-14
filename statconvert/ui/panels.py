from rich.panel import Panel
from rich.table import Table

from .console import console


def show_dataset_header(
    filename: str,
    file_format: str,
    backend: str,
    rows: int,
    columns: int,
):
    """
    Display dataset summary.
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
        "File",
        filename,
    )

    table.add_row(
        "Format",
        file_format,
    )

    table.add_row(
        "Backend",
        backend,
    )

    table.add_row(
        "Rows",
        f"{rows:,}",
    )

    table.add_row(
        "Columns",
        f"{columns:,}",
    )


    console.print(
        Panel(
            table,
            title="Dataset",
            expand=False,
        )
    )