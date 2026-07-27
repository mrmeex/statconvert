from __future__ import annotations

from typing import Any

from .validation import SchemaContractValidation


def contract_validation_summary(
    validation: SchemaContractValidation,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Return backend-neutral summary fields for reports and UI."""

    return {
        "contract_path": str(validation.path),
        "status": validation.status(strict=strict),
        "issue_count": len(validation.issues),
        "error_count": validation.error_count,
        "warning_count": validation.warning_count,
        "info_count": validation.info_count,
        "checked_rule_count": validation.checked_rule_count,
        "checked_column_count": validation.checked_column_count,
    }


def contract_issue_rows(
    validation: SchemaContractValidation,
) -> list[dict[str, Any]]:
    """Flatten bounded contract findings without evaluating rules again."""

    rows: list[dict[str, Any]] = []
    for issue in validation.issues:
        serialized = issue.to_dict()
        rows.append(
            {
            "severity": issue.severity,
            "code": issue.code,
            "column": issue.column,
            "source_rule": issue.source_rule,
            "message": issue.message,
            "expected": serialized["expected"],
            "actual": serialized["actual"],
            "affected_rows": issue.affected_rows,
            "samples": serialized["sample_values"],
            }
        )
    return rows
