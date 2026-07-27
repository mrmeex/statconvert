from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, TypeAlias

import pandas as pd


ContractSeverity: TypeAlias = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ContractValidationIssue:
    """One backend-neutral schema contract validation finding."""

    severity: ContractSeverity
    code: str
    message: str
    column: str | None = None
    expected: Any = None
    actual: Any = None
    affected_rows: int | None = None
    sample_values: tuple[Any, ...] = ()
    source_rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""

        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "column": self.column,
            "expected": _json_safe(self.expected),
            "actual": _json_safe(self.actual),
            "affected_rows": self.affected_rows,
            "sample_values": _json_safe(list(self.sample_values)),
            "source_rule": self.source_rule,
        }


@dataclass(frozen=True)
class ContractValidationResult:
    """Complete validation outcome for one dataset and contract."""

    contract_version: int
    contract_name: str | None
    issues: tuple[ContractValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        """Return whether validation produced no error findings."""

        return not any(
            issue.severity == "error"
            for issue in self.issues
        )

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def info_count(self) -> int:
        return sum(issue.severity == "info" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-safe result representation."""

        return {
            "contract_version": self.contract_version,
            "contract_name": self.contract_name,
            "valid": self.valid,
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
            },
            "issues": [
                issue.to_dict()
                for issue in self.issues
            ],
        }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    return str(value)
