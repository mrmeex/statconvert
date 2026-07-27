"""Incremental schema-contract validation for approved streaming inputs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from statconvert.contracts.model import SchemaContract
from statconvert.contracts.parser import load_contract
from statconvert.contracts.results import (
    ContractValidationIssue,
    ContractValidationResult,
)
from statconvert.contracts.validation import SchemaContractValidation
from statconvert.contracts.validator import validate_contract
from statconvert.exceptions import ConversionError
from statconvert.registry import get_reader_for_file
from statconvert.streaming.options import ChunkedReadOptions
from statconvert.streaming.schema import StreamingSchemaGuard


_SUPPORTED_INPUTS = {".csv", ".jsonl", ".ndjson"}
_SAMPLE_LIMIT = 5
STREAMING_RULE_CLASSIFICATIONS = {
    "not_null": "chunk_local_bounded",
    "allowed_values": "chunk_local_bounded",
    "range": "chunk_local_bounded",
    "regex": "chunk_local_bounded",
    "length": "chunk_local_bounded",
    "row_count": "dataset_aggregate_bounded",
    "unique": "retained_key_state",
}
_STRUCTURAL_CODES = {
    "missing_column",
    "unexpected_column",
    "column_order_mismatch",
    "storage_type_mismatch",
    "logical_type_mismatch",
    "rule_missing_column",
}
_DEFERRED_CODES = {
    "uniqueness_violation",
    "rule_uniqueness_violation",
    "rule_row_count_violation",
}


@dataclass(frozen=True)
class StreamingValidationResult:
    """One complete, read-only streaming contract-validation result."""

    source_path: Path
    chunk_size: int
    chunks_processed: int
    rows_processed: int
    rules_checked: int
    columns_checked: int
    contract_validation: SchemaContractValidation

    def streaming_dict(self) -> dict[str, int | bool]:
        """Return the additive machine-output streaming section."""

        return {
            "enabled": True,
            "chunk_size": self.chunk_size,
            "chunks_processed": self.chunks_processed,
            "rows_processed": self.rows_processed,
            "rules_checked": self.rules_checked,
            "columns_checked": self.columns_checked,
        }


@dataclass
class _AccumulatedIssue:
    issue: ContractValidationIssue
    affected_rows: int | None
    actual: Any
    samples: list[Any]

    def add(self, issue: ContractValidationIssue) -> None:
        if self.affected_rows is not None and issue.affected_rows is not None:
            self.affected_rows += issue.affected_rows
        elif self.affected_rows is None:
            self.affected_rows = issue.affected_rows
        if isinstance(self.actual, int) and isinstance(issue.actual, int):
            self.actual += issue.actual
        for value in issue.sample_values:
            if not any(_values_match(value, existing) for existing in self.samples):
                self.samples.append(value)
            if len(self.samples) >= _SAMPLE_LIMIT:
                break

    def finish(self) -> ContractValidationIssue:
        return replace(
            self.issue,
            message=_aggregate_message(
                self.issue,
                self.affected_rows,
            ),
            affected_rows=self.affected_rows,
            actual=self.actual,
            sample_values=tuple(self.samples),
        )


@dataclass
class _UniqueState:
    columns: tuple[str, ...]
    severity: str
    code: str
    source_rule: str
    named_rule: str | None
    counts: dict[Any, int]
    samples: dict[Any, Any]

    def observe(self, dataframe: pd.DataFrame) -> None:
        positions = {
            str(column): index
            for index, column in enumerate(dataframe.columns)
        }
        if any(column not in positions for column in self.columns):
            return
        for row in dataframe.itertuples(index=False, name=None):
            values = tuple(row[positions[column]] for column in self.columns)
            if any(_is_missing(value) for value in values):
                continue
            display: Any = values[0] if len(values) == 1 else values
            key = _freeze(display)
            self.counts[key] = self.counts.get(key, 0) + 1
            self.samples.setdefault(key, display)

    def issue(self) -> ContractValidationIssue | None:
        duplicate_keys = [
            key
            for key, count in self.counts.items()
            if count > 1
        ]
        duplicate_count = sum(self.counts[key] for key in duplicate_keys)
        if not duplicate_count:
            return None
        sample_values = tuple(
            self.samples[key]
            for key in duplicate_keys[:_SAMPLE_LIMIT]
        )
        column = ", ".join(self.columns)
        if self.named_rule is None:
            message = (
                f"Column '{column}' contains {duplicate_count:,} row(s) "
                "with duplicate values."
            )
            expected = "unique non-missing values"
        else:
            message = (
                f"Rule '{self.named_rule}' found {duplicate_count:,} row(s) "
                "with duplicate key values."
            )
            expected = "unique complete key values"
        return ContractValidationIssue(
            severity=self.severity,
            code=self.code,
            message=message,
            column=column,
            expected=expected,
            actual=duplicate_count,
            affected_rows=duplicate_count,
            sample_values=sample_values,
            source_rule=self.source_rule,
        )


def validate_streaming_contract(
    source_path: str | Path,
    contract_path: str | Path,
    *,
    chunk_size: int,
) -> StreamingValidationResult:
    """Validate one CSV/JSONL/NDJSON input without materializing all rows."""

    source = Path(source_path)
    if not source.exists():
        raise ConversionError(f"Input file does not exist: {source}")
    require_streaming_validation_input(source)

    contract_file = Path(contract_path)
    contract = load_contract(contract_file)
    reader = get_reader_for_file(str(source))
    guard = StreamingSchemaGuard()
    accumulator: dict[tuple[str, str | None, str | None, str], _AccumulatedIssue] = {}
    unique_states = _unique_states(contract)
    chunks_processed = 0
    rows_processed = 0

    for chunk in reader.iter_chunks(
        str(source),
        ChunkedReadOptions(chunk_size),
    ):
        guard.validate(chunk.dataset)
        chunk_result = validate_contract(chunk.dataset, contract)
        for issue in chunk_result.issues:
            if issue.code in _DEFERRED_CODES:
                continue
            if chunks_processed > 0 and issue.code in _STRUCTURAL_CODES:
                continue
            _accumulate(accumulator, issue)
        for state in unique_states:
            state.observe(chunk.dataset.dataframe)
        chunks_processed += 1
        rows_processed += chunk.rows

    issues = [item.finish() for item in accumulator.values()]
    issues.extend(
        issue
        for state in unique_states
        if (issue := state.issue()) is not None
    )
    issues.extend(_row_count_issues(contract, rows_processed))
    issues.sort(key=lambda issue: _issue_rank(issue, contract))

    checked_columns = _checked_columns(contract)
    validation = SchemaContractValidation(
        path=contract_file,
        result=ContractValidationResult(
            contract_version=contract.contract_version,
            contract_name=contract.name,
            issues=tuple(issues),
        ),
        checked_rule_count=len(contract.rules),
        checked_column_count=len(checked_columns),
    )
    return StreamingValidationResult(
        source_path=source,
        chunk_size=chunk_size,
        chunks_processed=chunks_processed,
        rows_processed=rows_processed,
        rules_checked=len(contract.rules),
        columns_checked=len(checked_columns),
        contract_validation=validation,
    )


def require_streaming_validation_input(source: str | Path) -> None:
    """Reject formats outside the 0.9.0 streaming-validation scope."""

    extension = Path(source).suffix.lower()
    if extension in _SUPPORTED_INPUTS:
        return
    if extension == ".json":
        raise ConversionError(
            "Streaming validation is not supported for JSON array files.",
            suggestion=(
                "Use JSONL or NDJSON for streaming validation, or run without --stream."
            ),
        )
    raise ConversionError(
        "Streaming validation is not supported for "
        f"{extension or '<no extension>'} files.",
        suggestion=(
            "Streaming validation in 0.9.0 supports only CSV, JSONL, and NDJSON. "
            "Run without --stream for normal in-memory validation."
        ),
    )


def _accumulate(
    accumulator: dict[
        tuple[str, str | None, str | None, str],
        _AccumulatedIssue,
    ],
    issue: ContractValidationIssue,
) -> None:
    key = (
        issue.code,
        issue.column,
        issue.source_rule,
        issue.severity,
    )
    current = accumulator.get(key)
    if current is None:
        accumulator[key] = _AccumulatedIssue(
            issue=issue,
            affected_rows=issue.affected_rows,
            actual=issue.actual,
            samples=list(issue.sample_values),
        )
        return
    current.add(issue)


def _unique_states(contract: SchemaContract) -> list[_UniqueState]:
    states = [
        _UniqueState(
            columns=(column.name,),
            severity="error",
            code="uniqueness_violation",
            source_rule="column.unique",
            named_rule=None,
            counts={},
            samples={},
        )
        for column in contract.columns
        if column.unique
    ]
    states.extend(
        _UniqueState(
            columns=rule.columns,
            severity=rule.severity,
            code="rule_uniqueness_violation",
            source_rule=rule.name,
            named_rule=rule.name,
            counts={},
            samples={},
        )
        for rule in contract.rules
        if rule.rule_type == "unique"
    )
    return states


def _row_count_issues(
    contract: SchemaContract,
    rows: int,
) -> list[ContractValidationIssue]:
    issues: list[ContractValidationIssue] = []
    for rule in contract.rules:
        if rule.rule_type != "row_count":
            continue
        below = rule.min_value is not None and rows < rule.min_value
        above = rule.max_value is not None and rows > rule.max_value
        if not below and not above:
            continue
        affected = (
            int(rule.min_value - rows)
            if below and rule.min_value is not None
            else int(rows - rule.max_value)
            if rule.max_value is not None
            else None
        )
        issues.append(
            ContractValidationIssue(
                severity=rule.severity,
                code="rule_row_count_violation",
                message=f"Rule '{rule.name}' does not allow {rows:,} rows.",
                expected={
                    "min": rule.min_value,
                    "max": rule.max_value,
                },
                actual=rows,
                affected_rows=affected,
                source_rule=rule.name,
            )
        )
    return issues


def _checked_columns(contract: SchemaContract) -> set[str]:
    columns = {column.name for column in contract.columns}
    for rule in contract.rules:
        if rule.column is not None:
            columns.add(rule.column)
        columns.update(rule.columns)
    return columns


def _issue_rank(
    issue: ContractValidationIssue,
    contract: SchemaContract,
) -> tuple[int, int]:
    column_positions = {
        column.name: index
        for index, column in enumerate(contract.columns)
    }
    rule_positions = {
        rule.name: index
        for index, rule in enumerate(contract.rules)
    }
    if issue.source_rule in rule_positions:
        return (3, rule_positions[issue.source_rule])
    if issue.code in {
        "missing_column",
        "unexpected_column",
        "column_order_mismatch",
    }:
        return (0, 0)
    return (1, column_positions.get(issue.column or "", len(column_positions)))


def _aggregate_message(
    issue: ContractValidationIssue,
    affected_rows: int | None,
) -> str:
    if affected_rows is None:
        return issue.message
    count = affected_rows or 0
    column = issue.column or ""
    messages = {
        "nullable_violation": (
            f"Column '{column}' contains {count:,} missing value(s)."
        ),
        "allowed_values_violation": (
            f"Column '{column}' contains {count:,} value(s) outside allowed_values."
        ),
        "range_violation": (
            f"Column '{column}' contains {count:,} value(s) outside the configured range."
        ),
        "regex_violation": (
            f"Column '{column}' contains {count:,} value(s) that do not match the regex."
        ),
    }
    if issue.code == "rule_not_null_violation":
        return (
            f"Rule '{issue.source_rule}' found {count:,} missing value(s)."
        )
    return messages.get(issue.code, issue.message)


def _is_missing(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _freeze(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _freeze(item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return tuple(
            sorted((str(key), _freeze(item)) for key, item in value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _values_match(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False
