from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


IssueSeverity = Literal["info", "warning", "error"]
PlanStatus = Literal["ready", "warnings", "blocked"]
DecisionAction = Literal["keep", "widen", "narrow", "semantic_convert", "manual"]
EvidenceLevel = Literal["exact_full_scan", "declared_only", "insufficient"]
MetadataDispositionKind = Literal[
    "native", "embedded", "sidecar", "derived", "unsupported", "not_applicable"
]


@dataclass(frozen=True)
class TransferIssue:
    """One stable backend-neutral transfer planning finding."""

    code: str
    severity: IssueSeverity
    message: str
    suggestion: str | None = None
    column: str | None = None
    field: str | None = None
    policy: str = "safe"
    target: str = ""
    category: str = "transfer"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ColumnScanSummary:
    """Aggregate full-column evidence without row-level values."""

    rows_scanned: int
    non_missing_count: int
    missing_count: int
    minimum: int | float | None = None
    maximum: int | float | None = None
    max_string_length: int | None = None
    string_length_unit: str | None = None
    integer_exactness: bool | None = None
    float32_exactness: bool | None = None
    date_only_compatible: bool | None = None
    timezone_summary: str | None = None
    value_family_counts: dict[str, int] = field(default_factory=dict)
    value_family_count_truncated: int = 0
    category_count: int | None = None
    category_ordered: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ColumnTypeDecision:
    """One ordered target-aware column type decision."""

    column: str
    ordinal: int
    current_storage_type: str
    declared_logical_type: str
    proposed_storage_type: str
    proposed_logical_type: str
    action: DecisionAction
    reason_code: str
    reason: str
    policy: str
    evidence_level: EvidenceLevel
    lossy: bool
    issues: tuple[TransferIssue, ...]
    scan: ColumnScanSummary
    metadata_impact: dict[str, Any]
    target_compatibility: str
    target_compatibility_reason: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["issues"] = [issue.to_dict() for issue in self.issues]
        return result


@dataclass(frozen=True)
class MetadataDisposition:
    """Disposition of one normalized metadata field for the selected target."""

    scope: Literal["dataset", "column"]
    field: str
    disposition: MetadataDispositionKind
    severity: IssueSeverity
    message: str
    column: str | None = None
    issue_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransferPlan:
    """Complete immutable non-writing transfer plan."""

    schema_version: int
    source: dict[str, Any]
    target: dict[str, Any]
    policy: str
    status: PlanStatus
    scan: dict[str, Any]
    summary: dict[str, Any]
    decisions: tuple[ColumnTypeDecision, ...]
    metadata: tuple[MetadataDisposition, ...]
    issues: tuple[TransferIssue, ...]
    output: None = None

    def to_dict(
        self,
        *,
        max_decisions: int = 200,
        max_metadata: int = 500,
        max_issues: int = 200,
    ) -> dict[str, Any]:
        """Return deterministic bounded JSON-ready primitives."""

        decisions = self.decisions[:max_decisions]
        metadata = self.metadata[:max_metadata]
        issues = self.issues[:max_issues]
        omitted_decisions = len(self.decisions) - len(decisions)
        omitted_metadata = len(self.metadata) - len(metadata)
        omitted_issues = len(self.issues) - len(issues)
        return {
            "schema_version": self.schema_version,
            "source": dict(self.source),
            "target": dict(self.target),
            "policy": self.policy,
            "status": self.status,
            "scan": dict(self.scan),
            "summary": dict(self.summary),
            "decisions": [decision.to_dict() for decision in decisions],
            "metadata": [item.to_dict() for item in metadata],
            "issues": [issue.to_dict() for issue in issues],
            "output": self.output,
            "truncated": {
                "decisions": omitted_decisions > 0,
                "decisions_omitted": omitted_decisions,
                "metadata": omitted_metadata > 0,
                "metadata_omitted": omitted_metadata,
                "issues": omitted_issues > 0,
                "issues_omitted": omitted_issues,
            },
        }
