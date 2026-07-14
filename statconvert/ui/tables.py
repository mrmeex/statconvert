from rich.table import Table

from .console import console


def show_dataset_info(dataset):
    """
    Display the variables contained in the dataset.
    """

    labels = dataset.variable_labels()
    storage_types = dataset.storage_types()

    table = Table(title="Variables")

    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Label")

    for column in dataset.columns:

        dtype = storage_types.get(
            str(column),
            str(dataset.dataframe[column].dtype),
        )

        label = labels.get(column, "")

        table.add_row(
            column,
            dtype,
            label,
        )

    console.print(table)


def show_preview(dataset, rows: int = 5):
    """
    Display the first rows of a dataset.
    """

    preview = dataset.preview(rows)

    table = Table(
        title=f"Preview ({len(preview)} of {dataset.rows:,} rows)"
    )

    for column in preview.columns:
        table.add_column(str(column))

    for _, row in preview.iterrows():
        table.add_row(
            *[str(value) for value in row]
        )

    console.print(table)
