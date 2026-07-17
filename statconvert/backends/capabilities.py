from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCapabilities:
    """
    Declarative capabilities exposed by a backend.
    """

    can_read: bool = True
    can_write: bool = True

    supports_variable_labels: bool = False
    supports_value_labels: bool = False
    supports_missing_values: bool = False
    supports_display_formats: bool = False
    supports_measurement_levels: bool = False
    supports_custom_metadata: bool = False

    supports_multiple_tables: bool = False
    supports_multiple_sheets: bool = False
    is_container: bool = False
    object_selection: bool = False
    object_kind: str | None = None
    multi_object_write: bool = False
    output_object_kind: str | None = None
    supports_compression: bool = False
    supports_streaming: bool = False

    preserves_index: bool = False


    def supports_any_metadata(self) -> bool:
        """
        Return whether any metadata capability is supported.
        """

        return any(
            self.metadata_summary().values()
        )


    def metadata_summary(self) -> dict[str, bool]:
        """
        Return metadata-related capabilities.
        """

        return {
            "variable_labels": self.supports_variable_labels,
            "value_labels": self.supports_value_labels,
            "missing_values": self.supports_missing_values,
            "display_formats": self.supports_display_formats,
            "measurement_levels": self.supports_measurement_levels,
            "custom_metadata": self.supports_custom_metadata,
        }


    def storage_summary(self) -> dict[str, bool]:
        """
        Return storage-related capabilities.
        """

        return {
            "compression": self.supports_compression,
            "streaming": self.supports_streaming,
            "preserves_index": self.preserves_index,
        }


    def table_summary(self) -> dict[str, bool]:
        """
        Return table/sheet-related capabilities.
        """

        return {
            "multiple_tables": self.supports_multiple_tables,
            "multiple_sheets": self.supports_multiple_sheets,
        }


    def object_summary(self) -> dict[str, bool | str | None]:
        """Return container and dataset-object capabilities."""

        return {
            "is_container": self.is_container,
            "object_selection": self.object_selection,
            "object_kind": self.object_kind,
            "multi_object_write": self.multi_object_write,
            "output_object_kind": self.output_object_kind,
        }
