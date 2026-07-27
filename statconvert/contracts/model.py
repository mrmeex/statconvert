from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias


ColumnOrder: TypeAlias = Literal["ignore", "exact", "prefix"]
ContractScalar: TypeAlias = str | int | float | bool
RuleSeverity: TypeAlias = Literal["error", "warning", "info"]
RuleType: TypeAlias = Literal[
    "allowed_values",
    "range",
    "regex",
    "unique",
    "row_count",
    "not_null",
    "length",
]


@dataclass(frozen=True)
class DatasetContract:
    """Dataset-level schema policies."""

    require_columns: bool = True
    allow_extra_columns: bool = False
    column_order: ColumnOrder = "ignore"

    def to_dict(self) -> dict[str, Any]:
        """Return the TOML-shaped dataset policy."""

        return {
            "require_columns": self.require_columns,
            "allow_extra_columns": self.allow_extra_columns,
            "column_order": self.column_order,
        }


@dataclass(frozen=True)
class ColumnContract:
    """Validation rules for one named dataset column."""

    name: str
    required: bool = True
    storage_type: str | None = None
    logical_type: str | None = None
    nullable: bool = True
    unique: bool = False
    allowed_values: tuple[ContractScalar, ...] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    regex: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the TOML-shaped column rule."""

        values: dict[str, Any] = {
            "name": self.name,
            "required": self.required,
            "nullable": self.nullable,
            "unique": self.unique,
        }
        optional = {
            "storage_type": self.storage_type,
            "logical_type": self.logical_type,
            "allowed_values": (
                list(self.allowed_values)
                if self.allowed_values is not None
                else None
            ),
            "min": self.min_value,
            "max": self.max_value,
            "regex": self.regex,
        }
        values.update(
            {
                name: value
                for name, value in optional.items()
                if value is not None
            }
        )
        return values


@dataclass(frozen=True)
class DataQualityRule:
    """One explicit named data-quality rule."""

    name: str
    rule_type: RuleType
    severity: RuleSeverity = "error"
    description: str | None = None
    column: str | None = None
    columns: tuple[str, ...] = ()
    values: tuple[ContractScalar, ...] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the TOML-shaped named rule."""

        values: dict[str, Any] = {
            "name": self.name,
            "type": self.rule_type,
        }
        if self.description is not None:
            values["description"] = self.description
        values["severity"] = self.severity
        optional = {
            "column": self.column,
            "columns": list(self.columns) if self.columns else None,
            "values": (
                list(self.values)
                if self.values is not None
                else None
            ),
            "min": self.min_value,
            "max": self.max_value,
            "pattern": self.pattern,
        }
        values.update(
            {
                name: value
                for name, value in optional.items()
                if value is not None
            }
        )
        return values


@dataclass(frozen=True)
class SchemaContract:
    """One versioned, backend-neutral schema contract."""

    contract_version: int
    dataset: DatasetContract
    columns: tuple[ColumnContract, ...] = ()
    name: str | None = None
    description: str | None = None
    rules: tuple[DataQualityRule, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic TOML-shaped representation."""

        values: dict[str, Any] = {
            "contract_version": self.contract_version,
        }
        if self.name is not None:
            values["name"] = self.name
        if self.description is not None:
            values["description"] = self.description
        values["dataset"] = self.dataset.to_dict()
        values["columns"] = [
            column.to_dict()
            for column in self.columns
        ]
        if self.rules:
            values["rules"] = [
                rule.to_dict()
                for rule in self.rules
            ]
        return values
