from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
import re
import tomllib
from typing import Any

from statconvert.error_suggestions import did_you_mean
from statconvert.exceptions import ContractError

from .model import (
    ColumnContract,
    ContractScalar,
    DataQualityRule,
    DatasetContract,
    SchemaContract,
)


CONTRACT_VERSION = 1
_TOP_LEVEL_FIELDS = {
    "contract_version",
    "name",
    "description",
    "dataset",
    "columns",
    "rules",
}
_DATASET_FIELDS = {
    "require_columns",
    "allow_extra_columns",
    "column_order",
}
_COLUMN_FIELDS = {
    "name",
    "required",
    "storage_type",
    "logical_type",
    "nullable",
    "unique",
    "allowed_values",
    "min",
    "max",
    "regex",
}
_COLUMN_ORDERS = {"ignore", "exact", "prefix"}
_RULE_FIELDS = {
    "name",
    "type",
    "severity",
    "description",
    "column",
    "columns",
    "values",
    "min",
    "max",
    "pattern",
}
_RULE_TYPES = {
    "allowed_values",
    "range",
    "regex",
    "unique",
    "row_count",
    "not_null",
    "length",
}
_RULE_SEVERITIES = {"error", "warning", "info"}


def load_contract(path: str | Path) -> SchemaContract:
    """Read and validate one TOML schema contract."""

    contract_path = Path(path)
    if not contract_path.exists():
        raise ContractError(
            f"Schema contract file does not exist: {contract_path}"
        )
    if not contract_path.is_file():
        raise ContractError(
            f"Schema contract path is not a file: {contract_path}"
        )
    try:
        with contract_path.open("rb") as contract_file:
            raw = tomllib.load(contract_file)
    except tomllib.TOMLDecodeError as exc:
        raise ContractError(
            f"Schema contract contains invalid TOML: {contract_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ContractError(
            f"Could not read schema contract {contract_path}: {exc}"
        ) from exc

    try:
        return parse_contract(raw)
    except ContractError as exc:
        detail = exc.message.removeprefix("Schema contract error: ")
        raise ContractError(
            f"Schema contract error in {contract_path}: {detail}",
            suggestion=exc.suggestion,
        ) from exc


def parse_contract(raw: object) -> SchemaContract:
    """Validate a parsed TOML root and return an immutable contract."""

    root = _require_mapping(raw, "the top-level TOML value")
    _reject_unknown_fields(root, _TOP_LEVEL_FIELDS, "top level")

    if "contract_version" not in root:
        raise _error("missing required field 'contract_version'.")
    version = root["contract_version"]
    if not _is_int(version):
        raise _error("'contract_version' must be an integer.")
    if version != CONTRACT_VERSION:
        raise _error(
            f"unsupported contract_version {version}. "
            f"Supported version: {CONTRACT_VERSION}."
        )

    if "dataset" not in root:
        raise _error("missing required section [dataset].")
    dataset = _parse_dataset(root["dataset"])

    columns_value = root.get("columns", [])
    if not isinstance(columns_value, list):
        raise _error("'columns' must be an array of tables.")
    columns = tuple(
        _parse_column(value, index=index)
        for index, value in enumerate(columns_value, start=1)
    )
    duplicates = _duplicates(column.name for column in columns)
    if duplicates:
        raise _error(
            "duplicate column definitions: "
            + ", ".join(duplicates)
            + "."
        )

    rules_value = root.get("rules", [])
    if not isinstance(rules_value, list):
        raise _error("'rules' must be an array of tables.")
    rules = tuple(
        _parse_rule(value, index=index)
        for index, value in enumerate(rules_value, start=1)
    )
    duplicate_rules = _duplicates(rule.name for rule in rules)
    if duplicate_rules:
        raise _error(
            "duplicate rule names: "
            + ", ".join(duplicate_rules)
            + "."
        )

    return SchemaContract(
        contract_version=version,
        name=_optional_string(root, "name", non_blank=True),
        description=_optional_string(root, "description"),
        dataset=dataset,
        columns=columns,
        rules=rules,
    )


def _parse_dataset(value: object) -> DatasetContract:
    raw = _require_mapping(value, "[dataset]")
    _reject_unknown_fields(raw, _DATASET_FIELDS, "[dataset]")
    return DatasetContract(
        require_columns=_optional_bool(raw, "require_columns", default=True),
        allow_extra_columns=_optional_bool(
            raw,
            "allow_extra_columns",
            default=False,
        ),
        column_order=_column_order(raw.get("column_order", "ignore")),
    )


def _parse_column(value: object, *, index: int) -> ColumnContract:
    context = f"columns entry {index}"
    raw = _require_mapping(value, context)
    _reject_unknown_fields(raw, _COLUMN_FIELDS, context)
    name = _required_string(raw, "name", context=context)
    min_value = _optional_number(raw, "min", context=context)
    max_value = _optional_number(raw, "max", context=context)
    if (
        min_value is not None
        and max_value is not None
        and min_value > max_value
    ):
        raise _error(
            f"{context} ('{name}') has min greater than max."
        )

    regex = _optional_string(raw, "regex")
    if regex is not None:
        try:
            re.compile(regex)
        except re.error as exc:
            raise _error(
                f"{context} ('{name}') has invalid regex: {exc}."
            ) from exc

    return ColumnContract(
        name=name,
        required=_optional_bool(raw, "required", default=True, context=context),
        storage_type=_optional_string(raw, "storage_type", non_blank=True),
        logical_type=_optional_string(raw, "logical_type", non_blank=True),
        nullable=_optional_bool(raw, "nullable", default=True, context=context),
        unique=_optional_bool(raw, "unique", default=False, context=context),
        allowed_values=_optional_scalar_list(
            raw,
            "allowed_values",
            context=context,
        ),
        min_value=min_value,
        max_value=max_value,
        regex=regex,
    )


def _parse_rule(value: object, *, index: int) -> DataQualityRule:
    context = f"rules entry {index}"
    raw = _require_mapping(value, context)
    _reject_unknown_fields(raw, _RULE_FIELDS, context)
    name = _required_string(raw, "name", context=context)
    rule_type = _required_string(raw, "type", context=context).lower()
    if rule_type not in _RULE_TYPES:
        supported = ", ".join(sorted(_RULE_TYPES))
        raise _error(
            f"{context} ('{name}') has unsupported type '{rule_type}'. "
            f"Use one of: {supported}."
        )

    allowed_fields = {
        "name",
        "type",
        "severity",
        "description",
    } | {
        "allowed_values": {"column", "values"},
        "range": {"column", "min", "max"},
        "regex": {"column", "pattern"},
        "unique": {"columns"},
        "row_count": {"min", "max"},
        "not_null": {"column"},
        "length": {"column", "min", "max"},
    }[rule_type]
    _reject_unknown_fields(raw, allowed_fields, context)

    severity = _rule_severity(raw.get("severity", "error"), context=context)
    description = _optional_string(raw, "description")
    column = None
    columns: tuple[str, ...] = ()
    values: tuple[ContractScalar, ...] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    pattern = None

    if rule_type in {
        "allowed_values",
        "range",
        "regex",
        "not_null",
        "length",
    }:
        column = _required_string(raw, "column", context=context)
    if rule_type == "allowed_values":
        values = _required_scalar_list(raw, "values", context=context)
    elif rule_type == "unique":
        columns = _required_string_list(raw, "columns", context=context)
    elif rule_type in {"range", "row_count", "length"}:
        min_value, max_value = _rule_bounds(
            raw,
            context=context,
            integer_only=rule_type in {"row_count", "length"},
        )
    elif rule_type == "regex":
        pattern = _required_string(raw, "pattern", context=context)
        try:
            re.compile(pattern)
        except re.error as exc:
            raise _error(
                f"{context} ('{name}') has invalid pattern: {exc}."
            ) from exc

    return DataQualityRule(
        name=name,
        rule_type=rule_type,
        severity=severity,
        description=description,
        column=column,
        columns=columns,
        values=values,
        min_value=min_value,
        max_value=max_value,
        pattern=pattern,
    )


def _rule_severity(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise _error(f"'severity' in {context} must be a string.")
    normalized = value.strip().lower()
    if normalized not in _RULE_SEVERITIES:
        supported = ", ".join(sorted(_RULE_SEVERITIES))
        raise _error(
            f"unsupported severity '{value}' in {context}. "
            f"Use one of: {supported}."
        )
    return normalized


def _rule_bounds(
    values: Mapping[str, Any],
    *,
    context: str,
    integer_only: bool,
) -> tuple[int | float | None, int | float | None]:
    min_value = _optional_number(values, "min", context=context)
    max_value = _optional_number(values, "max", context=context)
    if min_value is None and max_value is None:
        raise _error(f"{context} requires 'min' and/or 'max'.")
    if integer_only:
        for name, value in (("min", min_value), ("max", max_value)):
            if value is not None and (not _is_int(value) or value < 0):
                raise _error(
                    f"'{name}' in {context} must be a non-negative integer."
                )
    if (
        min_value is not None
        and max_value is not None
        and min_value > max_value
    ):
        raise _error(f"{context} has min greater than max.")
    return min_value, max_value


def _required_scalar_list(
    values: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> tuple[ContractScalar, ...]:
    if name not in values:
        raise _error(f"{context} is missing required field '{name}'.")
    parsed = _optional_scalar_list(values, name, context=context)
    return parsed or ()


def _required_string_list(
    values: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> tuple[str, ...]:
    if name not in values:
        raise _error(f"{context} is missing required field '{name}'.")
    value = values[name]
    if not isinstance(value, list):
        raise _error(f"'{name}' in {context} must be an array.")
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _error(
                f"'{name}' in {context} must contain non-blank strings."
            )
        parsed.append(item.strip())
    if not parsed:
        raise _error(f"'{name}' in {context} must not be empty.")
    duplicates = _duplicates(parsed)
    if duplicates:
        raise _error(
            f"'{name}' in {context} contains duplicates: "
            + ", ".join(duplicates)
            + "."
        )
    return tuple(parsed)


def _reject_unknown_fields(
    values: Mapping[str, Any],
    supported: set[str],
    context: str,
) -> None:
    for name in values:
        if name in supported:
            continue
        raise _error(
            f"unknown field '{name}' in {context}.",
            suggestion=did_you_mean(name, supported, cutoff=0.65),
        )


def _require_mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"{context} must be a table.")
    if not all(isinstance(key, str) for key in value):
        raise _error(f"{context} must use string field names.")
    return value


def _required_string(
    values: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> str:
    if name not in values:
        raise _error(f"{context} is missing required field '{name}'.")
    value = values[name]
    if not isinstance(value, str):
        raise _error(f"'{name}' in {context} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise _error(f"'{name}' in {context} must not be blank.")
    return normalized


def _optional_string(
    values: Mapping[str, Any],
    name: str,
    *,
    non_blank: bool = False,
) -> str | None:
    if name not in values:
        return None
    value = values[name]
    if not isinstance(value, str):
        raise _error(f"'{name}' must be a string.")
    normalized = value.strip()
    if non_blank and not normalized:
        raise _error(f"'{name}' must not be blank.")
    return normalized


def _optional_bool(
    values: Mapping[str, Any],
    name: str,
    *,
    default: bool,
    context: str = "[dataset]",
) -> bool:
    if name not in values:
        return default
    value = values[name]
    if not isinstance(value, bool):
        raise _error(f"'{name}' in {context} must be a boolean.")
    return value


def _optional_number(
    values: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> int | float | None:
    if name not in values:
        return None
    value = values[name]
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise _error(f"'{name}' in {context} must be a finite number.")
    return value


def _optional_scalar_list(
    values: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> tuple[ContractScalar, ...] | None:
    if name not in values:
        return None
    value = values[name]
    if not isinstance(value, list):
        raise _error(f"'{name}' in {context} must be an array.")
    if not all(_is_contract_scalar(item) for item in value):
        raise _error(
            f"'{name}' in {context} must contain only strings, "
            "finite numbers, or booleans."
        )
    return tuple(value)


def _column_order(value: object) -> str:
    if not isinstance(value, str):
        raise _error("'column_order' in [dataset] must be a string.")
    normalized = value.strip().lower()
    if normalized not in _COLUMN_ORDERS:
        supported = ", ".join(sorted(_COLUMN_ORDERS))
        raise _error(
            f"unsupported column_order '{value}'. Use one of: {supported}."
        )
    return normalized


def _is_contract_scalar(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return True
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _duplicates(values: Any) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _error(
    message: str,
    *,
    suggestion: str | None = None,
) -> ContractError:
    return ContractError(
        f"Schema contract error: {message}",
        suggestion=suggestion,
    )
