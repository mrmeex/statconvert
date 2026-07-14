from dataclasses import dataclass, field
from typing import Any


@dataclass
class VariableMetadata:
    """
    Backend-independent metadata for one dataset variable.
    """

    name: str
    label: str | None = None
    value_labels: dict[Any, str] = field(default_factory=dict)
    missing_values: list[Any] = field(default_factory=list)
    missing_ranges: list[dict[str, Any]] = field(default_factory=list)
    storage_type: str | None = None
    display_format: str | None = None
    display_width: int | None = None
    measure: str | None = None
    role: str | None = None
    width: int | None = None
    decimals: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


    def has_label(self) -> bool:
        """
        Return whether this variable has a label.
        """

        return bool(self.label)


    def has_value_labels(self) -> bool:
        """
        Return whether this variable has value labels.
        """

        return bool(self.value_labels)


    def has_missing_values(self) -> bool:
        """
        Return whether this variable has missing value metadata.
        """

        return bool(self.missing_values or self.missing_ranges)


@dataclass
class DatasetMetadata:
    """
    Backend-independent metadata for a dataset.
    """

    source_format: str | None = None
    source_backend: str | None = None
    variables: dict[str, VariableMetadata] = field(default_factory=dict)
    dataset_label: str | None = None
    notes: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


    def add_variable(
        self,
        variable: VariableMetadata
    ) -> None:
        """
        Add or replace variable metadata by name.
        """

        self.variables[variable.name] = variable


    def get_variable(
        self,
        name: str
    ) -> VariableMetadata | None:
        """
        Return metadata for a variable by name.
        """

        return self.variables.get(
            name
        )


    def variable_labels(self) -> dict[str, str]:
        """
        Return all variable labels.
        """

        return {
            name: variable.label
            for name, variable in self.variables.items()
            if variable.label
        }


    def value_labels(self) -> dict[str, dict[Any, str]]:
        """
        Return all variable value labels.
        """

        return {
            name: variable.value_labels
            for name, variable in self.variables.items()
            if variable.value_labels
        }


    def missing_values(self) -> dict[str, list[Any]]:
        """
        Return all variable missing value metadata.
        """

        return {
            name: variable.missing_values
            for name, variable in self.variables.items()
            if variable.missing_values
        }


    def missing_ranges(self) -> dict[str, list[dict[str, Any]]]:
        """Return explicit missing ranges without flattening them to values."""

        return {
            name: variable.missing_ranges
            for name, variable in self.variables.items()
            if variable.missing_ranges
        }
