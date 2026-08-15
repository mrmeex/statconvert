from __future__ import annotations

from dataclasses import replace

from statconvert.exceptions import StatConvertError

from .models import TransferIssue


SUPPORTED_POLICIES = (
    "safe",
    "strict",
    "analysis-ready",
    "preserve-metadata",
    "smallest-types",
)


class TransferPlanningError(StatConvertError):
    """A transfer plan cannot be produced for the requested inputs."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "TRANSFER_POLICY_BLOCKED",
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion)
        self.code = code


def resolve_policy(value: str | None) -> str:
    """Resolve one explicit planning policy; only type-plan defaults to safe."""

    policy = (value or "safe").strip().lower()
    if policy == "legacy-compatible":
        raise TransferPlanningError(
            "Transfer policy is not implemented: legacy-compatible.",
            code="TRANSFER_POLICY_UNSUPPORTED",
            suggestion="Choose safe, strict, analysis-ready, preserve-metadata, or smallest-types.",
        )
    if policy not in SUPPORTED_POLICIES:
        choices = ", ".join(SUPPORTED_POLICIES)
        raise TransferPlanningError(
            f"Unknown transfer policy: {value}.",
            code="TRANSFER_POLICY_UNKNOWN",
            suggestion=f"Choose one of: {choices}.",
        )
    return policy


def apply_policy_severity(issue: TransferIssue, policy: str) -> TransferIssue:
    """Promote relevant findings without ever demoting or hiding them."""

    promote = False
    if policy == "strict":
        promote = issue.code in {
            "TRANSFER_TARGET_UNVERIFIED",
            "TRANSFER_LOSSY_VALUE",
            "TYPE_MIXED_OBJECT_UNSAFE",
            "TYPE_TARGET_UNSUPPORTED",
            "METADATA_TARGET_UNSUPPORTED",
        }
    elif policy == "preserve-metadata":
        promote = issue.code == "METADATA_TARGET_UNSUPPORTED"
    if promote and issue.severity == "warning":
        return replace(issue, severity="error")
    return issue
