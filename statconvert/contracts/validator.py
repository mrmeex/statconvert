from __future__ import annotations

from collections.abc import Iterable
from typing import Any
import re

import pandas as pd

from statconvert.dataset import Dataset

from .model import ColumnContract, DataQualityRule, SchemaContract
from .results import ContractValidationIssue, ContractValidationResult
from .schema import resolved_logical_type


_SAMPLE_LIMIT = 5


def validate_contract(
    dataset: Dataset,
    contract: SchemaContract,
) -> ContractValidationResult:
    """Validate a Dataset without modifying its data or metadata."""

    issues: list[ContractValidationIssue] = []
    actual_columns = [
        str(column)
        for column in dataset.dataframe.columns
    ]
    actual_names = set(actual_columns)
    contract_names = {
        column.name
        for column in contract.columns
    }

    if contract.dataset.require_columns:
        for column in contract.columns:
            if column.required and column.name not in actual_names:
                issues.append(
                    ContractValidationIssue(
                        severity="error",
                        code="missing_column",
                        column=column.name,
                        message=f"Required column is missing: {column.name}.",
                        expected="present",
                        actual="missing",
                        source_rule="column.required",
                    )
                )

    if not contract.dataset.allow_extra_columns:
        for name in actual_columns:
            if name not in contract_names:
                issues.append(
                    ContractValidationIssue(
                        severity="error",
                        code="unexpected_column",
                        column=name,
                        message=f"Unexpected column is not allowed: {name}.",
                        expected="declared in contract",
                        actual="not declared",
                        source_rule="dataset.allow_extra_columns",
                    )
                )

    order_issue = _validate_column_order(
        actual_columns,
        contract,
    )
    if order_issue is not None:
        issues.append(order_issue)

    storage_types = dataset.storage_types()
    for column in contract.columns:
        if column.name not in actual_names:
            continue
        series = _series_by_name(dataset.dataframe, column.name)
        issues.extend(
            _validate_column(
                dataset,
                column,
                series,
                storage_type=storage_types.get(column.name),
            )
        )

    for rule in contract.rules:
        issues.extend(_validate_rule(dataset, rule))

    return ContractValidationResult(
        contract_version=contract.contract_version,
        contract_name=contract.name,
        issues=tuple(issues),
    )


def _validate_rule(
    dataset: Dataset,
    rule: DataQualityRule,
) -> list[ContractValidationIssue]:
    referenced = (
        rule.columns
        if rule.rule_type == "unique"
        else ((rule.column,) if rule.column is not None else ())
    )
    actual_names = {
        str(column)
        for column in dataset.dataframe.columns
    }
    missing = [
        name
        for name in referenced
        if name not in actual_names
    ]
    if missing:
        return [
            _rule_issue(
                rule,
                code="rule_missing_column",
                column=", ".join(missing),
                message=(
                    f"Rule '{rule.name}' references missing column(s): "
                    + ", ".join(missing)
                    + "."
                ),
                expected="present",
                actual=missing,
            )
        ]

    if rule.rule_type == "row_count":
        return _validate_row_count_rule(dataset, rule)
    if rule.rule_type == "unique":
        return _validate_unique_rule(dataset, rule)

    column = rule.column or ""
    series = _series_by_name(dataset.dataframe, column)
    non_missing = series.dropna()
    if rule.rule_type == "allowed_values":
        invalid_mask = non_missing.map(
            lambda value: not _value_in_allowed(
                value,
                rule.values or (),
            )
        )
        return _masked_rule_result(
            rule,
            column,
            non_missing,
            invalid_mask,
            code="rule_allowed_values_violation",
            message=(
                f"Rule '{rule.name}' found value(s) outside its allowed set."
            ),
            expected=list(rule.values or ()),
        )
    if rule.rule_type == "range":
        return _validate_named_range_rule(rule, column, non_missing)
    if rule.rule_type == "regex":
        pattern = re.compile(rule.pattern or "")
        invalid_mask = non_missing.map(
            lambda value: (
                not isinstance(value, str)
                or pattern.search(value) is None
            )
        )
        return _masked_rule_result(
            rule,
            column,
            non_missing,
            invalid_mask,
            code="rule_regex_violation",
            message=f"Rule '{rule.name}' found value(s) outside its pattern.",
            expected=rule.pattern,
        )
    if rule.rule_type == "not_null":
        missing_count = int(series.isna().sum())
        if not missing_count:
            return []
        return [
            _rule_issue(
                rule,
                code="rule_not_null_violation",
                column=column,
                message=(
                    f"Rule '{rule.name}' found {missing_count:,} missing "
                    "value(s)."
                ),
                expected="no missing values",
                actual=missing_count,
                affected_rows=missing_count,
            )
        ]
    if rule.rule_type == "length":
        invalid_mask = non_missing.map(
            lambda value: not _length_in_bounds(value, rule)
        )
        return _masked_rule_result(
            rule,
            column,
            non_missing,
            invalid_mask,
            code="rule_length_violation",
            message=f"Rule '{rule.name}' found value(s) outside its length.",
            expected={
                "min": rule.min_value,
                "max": rule.max_value,
            },
        )
    return []


def _validate_named_range_rule(
    rule: DataQualityRule,
    column: str,
    series: pd.Series,
) -> list[ContractValidationIssue]:
    if not _is_numeric_series(series):
        return [
            _rule_issue(
                rule,
                code="rule_range_violation",
                column=column,
                message=(
                    f"Rule '{rule.name}' requires a numeric column."
                ),
                expected={
                    "min": rule.min_value,
                    "max": rule.max_value,
                },
                actual=str(series.dtype),
            )
        ]
    invalid_mask = pd.Series(False, index=series.index)
    if rule.min_value is not None:
        invalid_mask = invalid_mask | (series < rule.min_value)
    if rule.max_value is not None:
        invalid_mask = invalid_mask | (series > rule.max_value)
    return _masked_rule_result(
        rule,
        column,
        series,
        invalid_mask.fillna(False),
        code="rule_range_violation",
        message=f"Rule '{rule.name}' found value(s) outside its range.",
        expected={
            "min": rule.min_value,
            "max": rule.max_value,
        },
    )


def _validate_unique_rule(
    dataset: Dataset,
    rule: DataQualityRule,
) -> list[ContractValidationIssue]:
    key_frame = pd.concat(
        [
            _series_by_name(dataset.dataframe, name)
            for name in rule.columns
        ],
        axis=1,
    )
    key_frame.columns = list(rule.columns)
    complete_keys = key_frame.dropna(how="any")
    duplicate_mask = complete_keys.duplicated(keep=False)
    duplicate_count = int(duplicate_mask.sum())
    if not duplicate_count:
        return []
    duplicate_keys = complete_keys[duplicate_mask]
    samples = _key_samples(duplicate_keys)
    return [
        _rule_issue(
            rule,
            code="rule_uniqueness_violation",
            column=", ".join(rule.columns),
            message=(
                f"Rule '{rule.name}' found {duplicate_count:,} row(s) "
                "with duplicate key values."
            ),
            expected="unique complete key values",
            actual=duplicate_count,
            affected_rows=duplicate_count,
            sample_values=samples,
        )
    ]


def _validate_row_count_rule(
    dataset: Dataset,
    rule: DataQualityRule,
) -> list[ContractValidationIssue]:
    row_count = len(dataset.dataframe)
    below = (
        rule.min_value is not None
        and row_count < rule.min_value
    )
    above = (
        rule.max_value is not None
        and row_count > rule.max_value
    )
    if not below and not above:
        return []
    affected = (
        int(rule.min_value - row_count)
        if below and rule.min_value is not None
        else int(row_count - rule.max_value)
        if rule.max_value is not None
        else None
    )
    return [
        _rule_issue(
            rule,
            code="rule_row_count_violation",
            message=f"Rule '{rule.name}' does not allow {row_count:,} rows.",
            expected={
                "min": rule.min_value,
                "max": rule.max_value,
            },
            actual=row_count,
            affected_rows=affected,
        )
    ]


def _masked_rule_result(
    rule: DataQualityRule,
    column: str,
    series: pd.Series,
    invalid_mask: pd.Series,
    *,
    code: str,
    message: str,
    expected: Any,
) -> list[ContractValidationIssue]:
    invalid_count = int(invalid_mask.sum())
    if not invalid_count:
        return []
    return [
        _rule_issue(
            rule,
            code=code,
            column=column,
            message=message,
            expected=expected,
            actual=invalid_count,
            affected_rows=invalid_count,
            sample_values=_samples(series[invalid_mask]),
        )
    ]


def _length_in_bounds(value: Any, rule: DataQualityRule) -> bool:
    if not isinstance(value, str):
        return False
    length = len(value)
    return (
        (rule.min_value is None or length >= rule.min_value)
        and (rule.max_value is None or length <= rule.max_value)
    )


def _key_samples(dataframe: pd.DataFrame) -> tuple[Any, ...]:
    values: list[Any] = []
    for row in dataframe.itertuples(index=False, name=None):
        value: Any = row[0] if len(row) == 1 else tuple(row)
        if any(_values_match(value, existing) for existing in values):
            continue
        values.append(value)
        if len(values) >= _SAMPLE_LIMIT:
            break
    return tuple(values)


def _rule_issue(
    rule: DataQualityRule,
    *,
    code: str,
    message: str,
    column: str | None = None,
    expected: Any = None,
    actual: Any = None,
    affected_rows: int | None = None,
    sample_values: tuple[Any, ...] = (),
) -> ContractValidationIssue:
    return ContractValidationIssue(
        severity=rule.severity,
        code=code,
        message=message,
        column=column,
        expected=expected,
        actual=actual,
        affected_rows=affected_rows,
        sample_values=sample_values,
        source_rule=rule.name,
    )


def _validate_column_order(
    actual_columns: list[str],
    contract: SchemaContract,
) -> ContractValidationIssue | None:
    policy = contract.dataset.column_order
    if policy == "ignore":
        return None

    contract_order = [
        column.name
        for column in contract.columns
    ]
    present_expected = [
        name
        for name in contract_order
        if name in actual_columns
    ]
    actual_contract_columns = [
        name
        for name in actual_columns
        if name in set(contract_order)
    ]
    matches = (
        actual_contract_columns == present_expected
        if policy == "exact"
        else actual_columns[: len(present_expected)] == present_expected
    )
    if matches:
        return None
    return ContractValidationIssue(
        severity="error",
        code="column_order_mismatch",
        message=f"Dataset columns do not satisfy the '{policy}' order policy.",
        expected=present_expected,
        actual=(
            actual_contract_columns
            if policy == "exact"
            else actual_columns[: len(present_expected)]
        ),
        source_rule="dataset.column_order",
    )


def _validate_column(
    dataset: Dataset,
    contract: ColumnContract,
    series: pd.Series,
    *,
    storage_type: str | None,
) -> list[ContractValidationIssue]:
    issues: list[ContractValidationIssue] = []
    logical_type = resolved_logical_type(dataset, contract.name, series) or "unknown"

    if (
        contract.storage_type is not None
        and _normalize_type(storage_type) != _normalize_type(contract.storage_type)
    ):
        issues.append(
            _column_issue(
                contract,
                code="storage_type_mismatch",
                message=(
                    f"Column '{contract.name}' has storage type "
                    f"'{storage_type}', expected '{contract.storage_type}'."
                ),
                expected=contract.storage_type,
                actual=storage_type,
                source_rule="column.storage_type",
            )
        )

    if (
        contract.logical_type is not None
        and not _logical_types_match(logical_type, contract.logical_type)
    ):
        issues.append(
            _column_issue(
                contract,
                code="logical_type_mismatch",
                message=(
                    f"Column '{contract.name}' has logical type "
                    f"'{logical_type}', expected '{contract.logical_type}'."
                ),
                expected=contract.logical_type,
                actual=logical_type,
                source_rule="column.logical_type",
            )
        )

    if not contract.nullable:
        missing_count = int(series.isna().sum())
        if missing_count:
            issues.append(
                _column_issue(
                    contract,
                    code="nullable_violation",
                    message=(
                        f"Column '{contract.name}' contains "
                        f"{missing_count:,} missing value(s)."
                    ),
                    expected="no missing values",
                    actual=missing_count,
                    affected_rows=missing_count,
                    source_rule="column.nullable",
                )
            )

    non_missing = series.dropna()
    if contract.unique:
        duplicate_mask = _duplicate_mask(non_missing)
        duplicate_count = int(duplicate_mask.sum())
        if duplicate_count:
            issues.append(
                _column_issue(
                    contract,
                    code="uniqueness_violation",
                    message=(
                        f"Column '{contract.name}' contains "
                        f"{duplicate_count:,} row(s) with duplicate values."
                    ),
                    expected="unique non-missing values",
                    actual=duplicate_count,
                    affected_rows=duplicate_count,
                    sample_values=_samples(non_missing[duplicate_mask]),
                    source_rule="column.unique",
                )
            )

    if contract.allowed_values is not None:
        invalid_mask = non_missing.map(
            lambda value: not _value_in_allowed(
                value,
                contract.allowed_values or (),
            )
        )
        invalid_count = int(invalid_mask.sum())
        if invalid_count:
            issues.append(
                _column_issue(
                    contract,
                    code="allowed_values_violation",
                    message=(
                        f"Column '{contract.name}' contains "
                        f"{invalid_count:,} value(s) outside allowed_values."
                    ),
                    expected=list(contract.allowed_values),
                    actual=invalid_count,
                    affected_rows=invalid_count,
                    sample_values=_samples(non_missing[invalid_mask]),
                    source_rule="column.allowed_values",
                )
            )

    if contract.min_value is not None or contract.max_value is not None:
        issues.extend(
            _validate_range(
                contract,
                non_missing,
                logical_type=logical_type,
            )
        )

    if contract.regex is not None:
        pattern = re.compile(contract.regex)
        invalid_mask = non_missing.map(
            lambda value: (
                not isinstance(value, str)
                or pattern.search(value) is None
            )
        )
        invalid_count = int(invalid_mask.sum())
        if invalid_count:
            issues.append(
                _column_issue(
                    contract,
                    code="regex_violation",
                    message=(
                        f"Column '{contract.name}' contains "
                        f"{invalid_count:,} value(s) that do not match the regex."
                    ),
                    expected=contract.regex,
                    actual=invalid_count,
                    affected_rows=invalid_count,
                    sample_values=_samples(non_missing[invalid_mask]),
                    source_rule="column.regex",
                )
            )

    return issues


def _validate_range(
    contract: ColumnContract,
    series: pd.Series,
    *,
    logical_type: str,
) -> list[ContractValidationIssue]:
    if not _is_numeric_series(series):
        return [
            _column_issue(
                contract,
                code="range_violation",
                message=(
                    f"Column '{contract.name}' is not numeric, so its range "
                    "rule cannot be satisfied."
                ),
                expected={
                    "min": contract.min_value,
                    "max": contract.max_value,
                },
                actual=logical_type,
                source_rule="column.range",
            )
        ]

    invalid_mask = pd.Series(False, index=series.index)
    if contract.min_value is not None:
        invalid_mask = invalid_mask | (series < contract.min_value)
    if contract.max_value is not None:
        invalid_mask = invalid_mask | (series > contract.max_value)
    invalid_mask = invalid_mask.fillna(False)
    invalid_count = int(invalid_mask.sum())
    if not invalid_count:
        return []
    return [
        _column_issue(
            contract,
            code="range_violation",
            message=(
                f"Column '{contract.name}' contains "
                f"{invalid_count:,} value(s) outside the configured range."
            ),
            expected={
                "min": contract.min_value,
                "max": contract.max_value,
            },
            actual=invalid_count,
            affected_rows=invalid_count,
            sample_values=_samples(series[invalid_mask]),
            source_rule="column.range",
        )
    ]


def _logical_types_match(actual: str, expected: str) -> bool:
    normalized_actual = _normalize_type(actual)
    normalized_expected = _normalize_type(expected)
    if normalized_expected in {"number", "numeric"}:
        return normalized_actual in {"integer", "float", "number", "numeric"}
    return normalized_actual == normalized_expected


def _normalize_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().casefold()


def _is_numeric_series(series: pd.Series) -> bool:
    return bool(
        pd.api.types.is_numeric_dtype(series.dtype)
        and not pd.api.types.is_bool_dtype(series.dtype)
    )


def _duplicate_mask(series: pd.Series) -> pd.Series:
    try:
        return series.duplicated(keep=False)
    except TypeError:
        values = series.tolist()
        return pd.Series(
            [
                sum(_values_match(value, other) for other in values) > 1
                for value in values
            ],
            index=series.index,
        )


def _value_in_allowed(
    value: Any,
    allowed_values: Iterable[Any],
) -> bool:
    return any(
        _values_match(value, allowed)
        for allowed in allowed_values
    )


def _values_match(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


def _samples(series: pd.Series) -> tuple[Any, ...]:
    samples: list[Any] = []
    for value in series.tolist():
        if any(_values_match(value, existing) for existing in samples):
            continue
        samples.append(value)
        if len(samples) >= _SAMPLE_LIMIT:
            break
    return tuple(samples)


def _series_by_name(dataframe: pd.DataFrame, name: str) -> pd.Series:
    for index, column in enumerate(dataframe.columns):
        if str(column) == name:
            return dataframe.iloc[:, index]
    return pd.Series(dtype="object")


def _column_issue(
    contract: ColumnContract,
    *,
    code: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    affected_rows: int | None = None,
    sample_values: tuple[Any, ...] = (),
    source_rule: str,
) -> ContractValidationIssue:
    return ContractValidationIssue(
        severity="error",
        code=code,
        message=message,
        column=contract.name,
        expected=expected,
        actual=actual,
        affected_rows=affected_rows,
        sample_values=sample_values,
        source_rule=source_rule,
    )
