from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ReportIssue:
    severity: str
    code: str
    message: str
    column: str | None = None


@dataclass
class ReportMetric:
    name: str
    value: Any
    label: str | None = None
    description: str | None = None


@dataclass
class ReportTable:
    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    description: str | None = None


@dataclass
class ReportSection:
    key: str
    title: str
    metrics: list[ReportMetric] = field(default_factory=list)
    tables: list[ReportTable] = field(default_factory=list)
    issues: list[ReportIssue] = field(default_factory=list)
    text: str | None = None


@dataclass
class DatasetReport:
    title: str
    source_file: str | None = None
    source_format: str | None = None
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    sections: list[ReportSection] = field(default_factory=list)
    issues: list[ReportIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self._all_issues())

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self._all_issues())

    @property
    def section_count(self) -> int:
        return len(self.sections)

    @property
    def issue_count(self) -> int:
        return len(self._all_issues())

    def get_section(self, key: str) -> ReportSection | None:
        return next((section for section in self.sections if section.key == key), None)

    def _all_issues(self) -> list[ReportIssue]:
        """Return unique top-level and section issues without double counting."""

        issues = list(self.issues)
        known_ids = {id(issue) for issue in issues}
        for section in self.sections:
            for issue in section.issues:
                if id(issue) not in known_ids:
                    issues.append(issue)
                    known_ids.add(id(issue))
        return issues

