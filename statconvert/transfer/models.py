from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from types import MappingProxyType
from typing import Any, Literal


IssueSeverity = Literal["info", "warning", "error"]
PlanStatus = Literal["ready", "warnings", "blocked"]
DecisionAction = Literal["keep", "widen", "narrow", "semantic_convert", "manual"]
EvidenceLevel = Literal["exact_full_scan", "declared_only", "insufficient"]
MetadataDispositionKind = Literal[
    "native", "embedded", "sidecar", "derived", "unsupported", "not_applicable"
]


def _freeze(value: Any) -> Any:
    """Recursively freeze plan-owned containers without changing scalar values."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Return independent JSON-ready containers from frozen plan state."""

    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


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
    value_family_counts: Mapping[str, int] = field(default_factory=dict)
    value_family_count_truncated: int = 0
    category_count: int | None = None
    category_ordered: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value_family_counts", _freeze(self.value_family_counts))

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _thaw(getattr(self, item.name))
            for item in fields(self)
        }


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
    metadata_impact: Mapping[str, Any]
    target_compatibility: str
    target_compatibility_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "metadata_impact", _freeze(self.metadata_impact))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in fields(self):
            if item.name == "issues":
                result[item.name] = [issue.to_dict() for issue in self.issues]
            elif item.name == "scan":
                result[item.name] = self.scan.to_dict()
            else:
                result[item.name] = _thaw(getattr(self, item.name))
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
    source: Mapping[str, Any]
    target: Mapping[str, Any]
    policy: str
    status: PlanStatus
    scan: Mapping[str, Any]
    summary: Mapping[str, Any]
    decisions: tuple[ColumnTypeDecision, ...]
    metadata: tuple[MetadataDisposition, ...]
    issues: tuple[TransferIssue, ...]
    output: None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _freeze(self.source))
        object.__setattr__(self, "target", _freeze(self.target))
        object.__setattr__(self, "scan", _freeze(self.scan))
        object.__setattr__(self, "summary", _freeze(self.summary))
        object.__setattr__(self, "decisions", tuple(self.decisions))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        object.__setattr__(self, "issues", tuple(self.issues))

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
            "source": _thaw(self.source),
            "target": _thaw(self.target),
            "policy": self.policy,
            "status": self.status,
            "scan": _thaw(self.scan),
            "summary": _thaw(self.summary),
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
