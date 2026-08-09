from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataDiagnosticsError
from statconvert.serialization import make_json_safe


@dataclass(frozen=True)
class MetadataChange:
    field: str
    left: Any
    right: Any
    column: str | None = None


@dataclass(frozen=True)
class MetadataDiffIssue:
    severity: str
    code: str
    message: str
    column: str | None = None


@dataclass(frozen=True)
class MetadataDiffResult:
    same_metadata: bool
    compared_columns: int
    total_changes: int
    shown_changes: int
    changes: tuple[MetadataChange, ...]
    left_source: str | None
    right_source: str | None
    truncated: bool
    summary: Mapping[str, int]
    left_provenance: Mapping[str, Any]
    right_provenance: Mapping[str, Any]
    issues: tuple[MetadataDiffIssue, ...] = ()


def compare_metadata(
    left: Dataset,
    right: Dataset,
    *,
    columns: list[str] | None = None,
    max_changes: int = 100,
) -> MetadataDiffResult:
    """Compare normalized metadata only; data values are never compared."""

    if max_changes < 1:
        raise MetadataDiagnosticsError("max_changes must be at least 1.")
    left_names = {str(column) for column in left.dataframe.columns}
    right_names = {str(column) for column in right.dataframe.columns}
    if columns:
        requested = list(dict.fromkeys(columns))
        unknown = [name for name in requested if name not in left_names | right_names]
        if unknown:
            raise MetadataDiagnosticsError(
                f"Unknown metadata comparison column(s): {', '.join(unknown)}."
            )
        names = requested
    else:
        names = sorted(left_names | right_names)

    all_changes: list[MetadataChange] = []
    issues: list[MetadataDiffIssue] = []
    left_metadata = left.get_normalized_metadata()
    right_metadata = right.get_normalized_metadata()
    _append_change(all_changes, "dataset_label", left_metadata.dataset_label, right_metadata.dataset_label)
    _append_change(all_changes, "notes", list(left_metadata.notes), list(right_metadata.notes))
    _append_change(
        all_changes, "metadata_source",
        (left.metadata_provenance or {}).get("dataset"),
        (right.metadata_provenance or {}).get("dataset"),
    )

    left_sources = (left.metadata_provenance or {}).get("columns", {})
    right_sources = (right.metadata_provenance or {}).get("columns", {})
    for name in names:
        left_variable = left_metadata.get_variable(name)
        right_variable = right_metadata.get_variable(name)
        if left_variable is None or right_variable is None:
            _append_change(
                all_changes, "column_presence",
                left_variable is not None, right_variable is not None, column=name,
            )
            issues.append(MetadataDiffIssue(
                "warning", "metadata_diff_column_presence",
                f"Column {name} is present on only one side of the metadata comparison.",
                column=name,
            ))
            continue
        left_legacy = left.column_metadata.get(name)
        right_legacy = right.column_metadata.get(name)
        values = (
            ("variable_label", left_variable.label, right_variable.label),
            ("missing_values", left_variable.missing_values, right_variable.missing_values),
            ("missing_ranges", left_variable.missing_ranges, right_variable.missing_ranges),
            ("storage_type", left_variable.storage_type, right_variable.storage_type),
            ("display_format", left_variable.display_format, right_variable.display_format),
            ("measurement_level", left_variable.measure, right_variable.measure),
            ("logical_type", getattr(left_legacy, "logical_type", None), getattr(right_legacy, "logical_type", None)),
            ("metadata_source", _mapping_get(left_sources, name), _mapping_get(right_sources, name)),
        )
        for field_name, left_value, right_value in values:
            _append_change(all_changes, field_name, left_value, right_value, column=name)
        if _typed_labels(left_variable.value_labels) != _typed_labels(right_variable.value_labels):
            all_changes.append(MetadataChange(
                "value_labels", left_variable.value_labels, right_variable.value_labels, name,
            ))

    shown = tuple(all_changes[:max_changes])
    summary_fields = (
        "dataset_label", "notes", "variable_label", "value_labels",
        "missing_values", "missing_ranges", "storage_type", "display_format",
        "measurement_level", "logical_type", "metadata_source", "column_presence",
    )
    summary = {
        field_name: sum(change.field == field_name for change in all_changes)
        for field_name in summary_fields
    }
    return MetadataDiffResult(
        same_metadata=not all_changes,
        compared_columns=len(names),
        total_changes=len(all_changes),
        shown_changes=len(shown),
        changes=shown,
        left_source=left.source_file,
        right_source=right.source_file,
        truncated=len(all_changes) > max_changes,
        summary=summary,
        left_provenance=_provenance_summary(left),
        right_provenance=_provenance_summary(right),
        issues=tuple(issues[:max_changes]),
    )


def _append_change(
    target: list[MetadataChange], field_name: str, left: Any, right: Any,
    *, column: str | None = None,
) -> None:
    if make_json_safe(left) != make_json_safe(right):
        target.append(MetadataChange(field_name, left, right, column))


def _mapping_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _typed_labels(value: Mapping[Any, Any]) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted(
        (type(key).__name__, repr(key), repr(label))
        for key, label in value.items()
    ))


def _provenance_summary(dataset: Dataset) -> dict[str, Any]:
    provenance = dataset.metadata_provenance or {}
    columns = provenance.get("columns", {})
    counts: dict[str, int] = {}
    if isinstance(columns, Mapping):
        for value in columns.values():
            name = str(value)
            counts[name] = counts.get(name, 0) + 1
    return {"dataset": provenance.get("dataset"), "column_sources": counts}
