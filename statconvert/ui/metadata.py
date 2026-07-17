from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.dataset import Dataset

from .console import console


def show_formats_table(
    format_info: dict[str, dict[str, Any]]
) -> None:
    """
    Display registered file formats.
    """

    table = Table(
        title="Supported Formats"
    )
    table.add_column(
        "Extension",
        style="cyan",
    )
    table.add_column(
        "Format",
        style="green",
    )
    table.add_column(
        "Backend",
    )
    table.add_column(
        "Read",
    )
    table.add_column(
        "Write",
    )
    table.add_column(
        "Objects",
    )

    for extension, info in format_info.items():
        table.add_row(
            extension,
            info["name"],
            info["backend"],
            _yes_no(info["can_read"]),
            _yes_no(info["can_write"]),
            info["object_kind"] if info["object_selection"] else "-",
        )

    console.print(
        table
    )


def show_backends_table(
    backends: dict[str, Backend]
) -> None:
    """
    Display registered backend engines.
    """

    table = Table(
        title="Backends"
    )
    table.add_column(
        "Backend",
        style="cyan",
    )
    table.add_column(
        "Class",
        style="green",
    )
    table.add_column(
        "Any Read",
    )
    table.add_column(
        "Any Write",
    )
    table.add_column(
        "Metadata",
    )

    for name, backend in backends.items():
        capabilities = backend.capabilities
        table.add_row(
            name,
            backend.__class__.__name__,
            _yes_no(
                capabilities.can_read
            ),
            _yes_no(
                capabilities.can_write
            ),
            _metadata_summary_label(
                capabilities
            ),
        )

    console.print(
        table
    )


def show_capabilities_panel(
    target_info: dict[str, Any]
) -> None:
    """
    Display capabilities for a resolved format or backend.
    """

    capabilities = target_info["capabilities"]

    header = Table.grid(
        padding=(0, 2)
    )
    header.add_column(
        style="cyan",
        justify="right",
    )
    header.add_column()

    if target_info["kind"] == "format":
        header.add_row(
            "Format",
            target_info["format_name"],
        )
        header.add_row(
            "Extension",
            target_info["extension"],
        )

    else:
        header.add_row(
            "Target",
            target_info["backend_name"],
        )

    header.add_row(
        "Backend",
        target_info["backend_name"],
    )
    header.add_row(
        "Class",
        target_info["backend"].__class__.__name__,
    )

    console.print(
        Panel(
            header,
            title="Capabilities Target",
            expand=False,
        )
    )

    table = Table(
        title="Capabilities"
    )
    table.add_column(
        "Capability",
        style="cyan",
    )
    table.add_column(
        "Supported",
    )

    capability_rows = {
        "Read": capabilities.can_read,
        "Write": capabilities.can_write,
        "Variable labels": capabilities.supports_variable_labels,
        "Value labels": capabilities.supports_value_labels,
        "Missing values": capabilities.supports_missing_values,
        "Display formats": capabilities.supports_display_formats,
        "Measurement levels": capabilities.supports_measurement_levels,
        "Custom metadata": capabilities.supports_custom_metadata,
        "Container": capabilities.is_container,
        "Object selection": capabilities.object_selection,
        "Multi-object write": capabilities.multi_object_write,
        "Multiple sheets": capabilities.supports_multiple_sheets,
        "Multiple tables": capabilities.supports_multiple_tables,
        "Compression": capabilities.supports_compression,
        "Streaming": capabilities.supports_streaming,
        "Preserves index": capabilities.preserves_index,
    }

    for label, supported in capability_rows.items():
        table.add_row(
            label,
            _yes_no(
                supported
            ),
        )

    table.add_row(
        "Object kind",
        capabilities.object_kind or "-",
    )
    table.add_row(
        "Output object kind",
        capabilities.output_object_kind or "-",
    )

    console.print(
        table
    )


def show_schema(
    dataset: Dataset
) -> None:
    """
    Display normalized dataset schema.
    """

    storage_types = dataset.storage_types()
    labels = dataset.variable_labels()
    value_labels = dataset.value_labels()
    missing_values = dataset.missing_values()
    display_formats = dataset.display_formats()
    measurement_levels = dataset.measurement_levels()

    table = Table(
        title="Schema"
    )
    table.add_column(
        "Name",
        style="cyan",
    )
    table.add_column(
        "Storage Type",
        style="green",
    )
    table.add_column(
        "Label",
    )
    table.add_column(
        "Value Labels",
        justify="right",
    )
    table.add_column(
        "Missing Values",
        justify="right",
    )
    table.add_column(
        "Display Format",
    )
    table.add_column(
        "Measure",
    )

    for column in dataset.columns:
        name = str(
            column
        )
        table.add_row(
            name,
            storage_types.get(
                name,
                "",
            ),
            labels.get(
                name,
                "",
            ),
            str(
                len(
                    value_labels.get(
                        name,
                        {},
                    )
                )
            ),
            str(
                len(
                    missing_values.get(
                        name,
                        [],
                    )
                )
            ),
            display_formats.get(
                name,
                "",
            ),
            measurement_levels.get(
                name,
                "",
            ),
        )

    console.print(
        table
    )


def show_labels(
    dataset: Dataset,
    limit: int = 100
) -> None:
    """
    Display variable labels and value labels.
    """

    variable_labels = dataset.variable_labels()
    value_labels = dataset.value_labels()

    if not variable_labels and not value_labels:
        console.print(
            "[yellow]No labels found.[/yellow]"
        )
        return

    if variable_labels:
        table = Table(
            title="Variable Labels"
        )
        table.add_column(
            "Variable",
            style="cyan",
        )
        table.add_column(
            "Label",
        )

        for variable, label in variable_labels.items():
            table.add_row(
                variable,
                label,
            )

        console.print(
            table
        )

    if value_labels:
        table = Table(
            title=f"Value Labels (showing up to {limit})"
        )
        table.add_column(
            "Variable",
            style="cyan",
        )
        table.add_column(
            "Value",
            style="green",
        )
        table.add_column(
            "Label",
        )

        shown = 0

        for variable, labels in value_labels.items():
            for value, label in labels.items():
                if shown >= limit:
                    break

                table.add_row(
                    variable,
                    str(
                        value
                    ),
                    label,
                )
                shown += 1

            if shown >= limit:
                break

        console.print(
            table
        )


def show_metadata_summary(
    dataset: Dataset
) -> None:
    """
    Display normalized metadata summary.
    """

    metadata = dataset.get_normalized_metadata()
    summary = dataset.metadata_summary()

    table = Table.grid(
        padding=(0, 2)
    )
    table.add_column(
        style="cyan",
        justify="right",
    )
    table.add_column()

    table.add_row(
        "Source format",
        metadata.source_format or "",
    )
    table.add_row(
        "Source backend",
        metadata.source_backend or "",
    )
    table.add_row(
        "Dataset label",
        metadata.dataset_label or "",
    )
    table.add_row(
        "Notes",
        str(
            len(
                metadata.notes
            )
        ),
    )

    for name, value in summary.items():
        table.add_row(
            name.replace(
                "_",
                " ",
            ).title(),
            str(
                value
            ),
        )

    console.print(
        Panel(
            table,
            title="Metadata Summary",
            expand=False,
        )
    )


def _metadata_summary_label(
    capabilities: BackendCapabilities
) -> str:
    """
    Return a short metadata support label.
    """

    if not capabilities.supports_any_metadata():
        return "no"

    if capabilities.supports_custom_metadata:
        return "custom"

    return "yes"


def _yes_no(
    value: bool
) -> str:
    """
    Return a display string for a boolean.
    """

    if value:
        return "yes"

    return "no"
