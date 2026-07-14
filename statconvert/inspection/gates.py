from __future__ import annotations

from statconvert.dataset import Dataset
from statconvert.inspection.models import ValidationIssue
from statconvert.inspection.validation import validate_dataset


class ValidationFailedError(Exception):
    """Raised when validation policy prevents an output write."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        super().__init__(
            f"Validation failed: {errors} error(s), {warnings} warning(s)."
        )


def validation_has_errors(issues: list[ValidationIssue]) -> bool:
    """Return whether any validation issue is an error."""

    return any(issue.severity == "error" for issue in issues)


def validation_has_warnings(issues: list[ValidationIssue]) -> bool:
    """Return whether any validation issue is a warning."""

    return any(issue.severity == "warning" for issue in issues)


def validation_should_fail(
    issues: list[ValidationIssue],
    strict: bool = False,
) -> bool:
    """Apply the shared write-gate policy to validation issues."""

    return validation_has_errors(issues) or (
        strict and validation_has_warnings(issues)
    )


def validate_for_write(
    dataset: Dataset,
    target_format: str | None,
    strict: bool = False,
) -> list[ValidationIssue]:
    """Validate a dataset for writing without displaying or writing anything."""

    return validate_dataset(
        dataset,
        target_format=target_format,
        strict=strict,
    )
