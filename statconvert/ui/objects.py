from __future__ import annotations

from collections.abc import Sequence

from rich.table import Table

from statconvert.backends.objects import DatasetObjectInfo
from statconvert.object_discovery import ObjectDiscoveryReport

from .console import console


def show_dataset_objects(objects: Sequence[DatasetObjectInfo]) -> None:
    """Display dataset-like objects reported by a backend."""

    table = Table(title="Dataset Objects")
    table.add_column("Index", justify="right")
    table.add_column("Name", style="cyan")
    table.add_column("Kind", style="green")
    table.add_column("Rows", justify="right")
    table.add_column("Columns", justify="right")
    table.add_column("Supported")
    table.add_column("Message")

    for info in objects:
        table.add_row(
            "" if info.index is None else str(info.index),
            info.name,
            info.kind,
            "" if info.rows is None else str(info.rows),
            "" if info.columns is None else str(info.columns),
            "yes" if info.supported else "no",
            info.message or "",
        )

    console.print(table)


def show_objects_not_supported() -> None:
    """Explain that a single-dataset format has no object listing."""

    console.print("This format does not expose multiple dataset objects.")


def show_object_discovery_report(report: ObjectDiscoveryReport) -> None:
    """Display manifest-ready discovery rows for one folder or report request."""

    table = Table(title="Object Discovery")
    table.add_column("Include")
    table.add_column("Input file", style="cyan")
    table.add_column("Object")
    table.add_column("Kind", style="green")
    table.add_column("Rows", justify="right")
    table.add_column("Columns", justify="right")
    table.add_column("Output name")
    table.add_column("Message")

    for row in report.rows:
        table.add_row(
            "yes" if row.include else "no",
            row.input_file,
            row.object_name or "",
            row.object_kind or "",
            "" if row.rows is None else str(row.rows),
            "" if row.columns is None else str(row.columns),
            row.output_name or "",
            row.message or "",
        )

    console.print(table)
