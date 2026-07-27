from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from statconvert.dataset import Dataset

from .parser import load_contract
from .results import ContractValidationResult
from .validator import validate_contract


@dataclass(frozen=True)
class SchemaContractValidation:
    """One file-backed schema contract validation outcome."""

    path: Path
    result: ContractValidationResult
    checked_rule_count: int = 0
    checked_column_count: int = 0

    @property
    def valid(self) -> bool:
        return self.result.valid

    @property
    def issues(self):
        return self.result.issues

    @property
    def error_count(self) -> int:
        return self.result.error_count

    @property
    def warning_count(self) -> int:
        return self.result.warning_count

    @property
    def info_count(self) -> int:
        return self.result.info_count

    def status(self, *, strict: bool = False) -> str:
        """Return the operator status under the existing validation policy."""

        if not self.valid or (strict and self.warning_count):
            return "failed"
        if self.warning_count:
            return "passed_with_warnings"
        return "passed"

    def to_dict(self, *, strict: bool = False) -> dict[str, Any]:
        """Return a stable JSON-safe result including contract provenance."""

        return {
            "path": str(self.path),
            "contract_version": self.result.contract_version,
            "contract_name": self.result.contract_name,
            "valid": self.valid,
            "status": self.status(strict=strict),
            "issue_count": len(self.issues),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "checked_rule_count": self.checked_rule_count,
            "checked_column_count": self.checked_column_count,
            "issues": [
                issue.to_dict()
                for issue in self.issues
            ],
        }


def validate_schema_contract_file(
    dataset: Dataset,
    path: str | Path,
) -> SchemaContractValidation:
    """Load and apply one TOML schema contract to a resolved Dataset."""

    contract_path = Path(path)
    contract = load_contract(contract_path)
    checked_columns = {
        column.name
        for column in contract.columns
    }
    for rule in contract.rules:
        if rule.column is not None:
            checked_columns.add(rule.column)
        checked_columns.update(rule.columns)
    return SchemaContractValidation(
        path=contract_path,
        result=validate_contract(dataset, contract),
        checked_rule_count=len(contract.rules),
        checked_column_count=len(checked_columns),
    )
