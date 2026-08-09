from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, fields
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.exceptions import MetadataSidecarError
from statconvert.metadata.sidecar import (
    parse_payload,
    sidecar_path,
)
from statconvert.registry import FORMAT_INFO, get_backend_name, get_extension


@dataclass(frozen=True)
class MetadataIssue:
    severity: str
    code: str
    message: str
    column: str | None = None
    field: str | None = None
    suggestion: str | None = None
    details: Mapping[str, Any] = dataclass_field(default_factory=dict)


@dataclass(frozen=True)
class MetadataSourceInfo:
    input_path: str
    format: str | None
    backend: str | None
    metadata_mode: str | None
    metadata_source: str | None
    sidecar_path: str
    sidecar_present: bool
    sidecar_version: int | None
    embedded_metadata_present: bool
    native_metadata_present: bool
    resolved_precedence: str | None
    object_name: str | None = None
    object_kind: str | None = None


@dataclass(frozen=True)
class MetadataCoverage:
    data_columns: int
    metadata_columns: int
    columns_with_labels: int
    columns_with_value_labels: int
    columns_with_missing_values: int
    columns_with_missing_ranges: int
    columns_with_display_formats: int
    columns_with_measurement_levels: int
    sidecar_columns: int
    uncovered_data_columns: int
    orphan_metadata_columns: int
    notes_count: int
    uncovered_columns: tuple[str, ...]
    orphan_columns: tuple[str, ...]


@dataclass(frozen=True)
class ColumnMetadataDiagnostics:
    column: str
    storage_type: str | None
    logical_type: str | None
    label: str | None
    value_label_count: int
    missing_value_count: int
    missing_range_count: int
    display_format: str | None
    measurement_level: str | None
    metadata_source: str | None
    has_variable_metadata: bool
    has_label: bool
    has_value_labels: bool
    has_missing_values: bool
    has_missing_ranges: bool


@dataclass(frozen=True)
class MetadataDiagnostics:
    valid: bool
    source: MetadataSourceInfo
    coverage: MetadataCoverage
    issues: tuple[MetadataIssue, ...]
    columns: tuple[ColumnMetadataDiagnostics, ...]
    caveats: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = dataclass_field(default_factory=dict)
    truncated: bool = False

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


@dataclass(frozen=True)
class _SidecarInspection:
    path: Path
    present: bool
    version: int | None = None
    columns: tuple[str, ...] = ()
    issues: tuple[MetadataIssue, ...] = ()
    declared_storage_types: Mapping[str, str] = dataclass_field(default_factory=dict)


def build_metadata_diagnostics(
    dataset: Dataset,
    input_path: str | Path,
    *,
    sidecar_input: str | Path | None = None,
    require_sidecar: bool = False,
    object_name: str | None = None,
    object_kind: str | None = None,
    max_columns: int = 100,
    max_issues: int = 200,
) -> MetadataDiagnostics:
    """Inspect resolved metadata and an optional sidecar without changing either."""

    path = Path(input_path)
    selected_sidecar = Path(sidecar_input) if sidecar_input else sidecar_path(path)
    sidecar = _inspect_sidecar(selected_sidecar, required=require_sidecar)
    issues = list(sidecar.issues)
    dataframe_columns = tuple(str(column) for column in dataset.dataframe.columns)
    metadata = dataset.get_normalized_metadata()
    metadata_columns = set(metadata.variables)
    physical_columns = set(dataframe_columns)

    for name in sorted(metadata_columns - physical_columns):
        issues.append(MetadataIssue(
            "warning", "metadata_orphan_normalized_variable",
            f"Metadata exists for a column not present in the data: {name}.",
            column=name,
        ))
    for name in sorted(set(sidecar.columns) - physical_columns):
        issues.append(MetadataIssue(
            "error", "sidecar_missing_data_column",
            f"Sidecar references a column not present in the data: {name}.",
            column=name,
            suggestion="Use a matching data file or correct the sidecar column name.",
        ))

    provenance = dataset.metadata_provenance or {}
    column_sources = provenance.get("columns", {})
    if not isinstance(column_sources, Mapping):
        column_sources = {}

    column_rows: list[ColumnMetadataDiagnostics] = []
    for index, name in enumerate(dataframe_columns):
        variable = metadata.get_variable(name)
        legacy = dataset.column_metadata.get(name)
        if variable is None:
            issues.append(MetadataIssue(
                "warning", "metadata_missing_normalized_variable",
                f"No normalized metadata record exists for column {name}.", column=name,
            ))
            continue
        if variable.label is not None and not variable.label.strip():
            issues.append(MetadataIssue(
                "warning", "metadata_empty_variable_label",
                f"Column {name} has an empty variable label.", column=name, field="label",
                suggestion="Remove the empty label or replace it with meaningful text.",
            ))
        declared_type = sidecar.declared_storage_types.get(name)
        actual_type = variable.storage_type or str(dataset.dataframe.iloc[:, index].dtype)
        if declared_type and declared_type != actual_type:
            issues.append(MetadataIssue(
                "warning", "sidecar_type_drift",
                f"Sidecar storage type {declared_type!r} differs from {actual_type!r}.",
                column=name, field="storage_type",
            ))
        _check_value_labels(dataset.dataframe.iloc[:, index], name, variable.value_labels, issues)
        if variable.missing_ranges:
            issues.append(MetadataIssue(
                "info", "metadata_missing_range_present",
                f"Column {name} defines {len(variable.missing_ranges)} missing range(s).",
                column=name, field="missing_ranges",
            ))
        if len(column_rows) < max_columns:
            column_rows.append(ColumnMetadataDiagnostics(
                column=name,
                storage_type=actual_type,
                logical_type=legacy.logical_type if legacy else None,
                label=variable.label,
                value_label_count=len(variable.value_labels),
                missing_value_count=len(variable.missing_values),
                missing_range_count=len(variable.missing_ranges),
                display_format=variable.display_format,
                measurement_level=variable.measure,
                metadata_source=str(column_sources.get(name) or "") or None,
                has_variable_metadata=True,
                has_label=bool(variable.label),
                has_value_labels=bool(variable.value_labels),
                has_missing_values=bool(variable.missing_values),
                has_missing_ranges=bool(variable.missing_ranges),
            ))

    if object_name and sidecar.present:
        issues.append(MetadataIssue(
            "warning", "sidecar_object_ambiguous",
            "The current flat sidecar schema does not record container object identity.",
            suggestion="Keep the explicit object selector with the validation record.",
        ))

    extension = get_extension(str(path))
    format_info = FORMAT_INFO[extension]
    caveat = format_info.get("caveat")
    caveats = tuple(str(value) for value in (caveat,) if value)
    source_name = str(provenance.get("dataset") or "") or None
    embedded_present = bool(dataset.metadata.get("embedded_metadata_present"))
    native_present = bool(dataset.metadata.get("pyreadstat")) or source_name == "native_file"
    if sidecar.present and require_sidecar:
        issues.append(MetadataIssue(
            "info", "sidecar_validation_only",
            "The selected sidecar was parsed for diagnostics and was not activated.",
        ))
    elif sidecar.present:
        issues.append(MetadataIssue(
            "info", "metadata_sidecar_precedence",
            "A sibling or explicitly selected sidecar participates in metadata resolution.",
        ))
    if embedded_present:
        code = (
            "metadata_embedded_payload_overridden"
            if source_name == "automatic_sidecar"
            else "metadata_embedded_payload_present"
        )
        issues.append(MetadataIssue(
            "info", code,
            "An embedded StatConvert metadata payload is present."
            if code.endswith("present")
            else "Embedded metadata is present but the sibling sidecar has precedence.",
        ))
    uncovered = tuple(name for name in dataframe_columns if name not in set(sidecar.columns))
    if sidecar.present and uncovered:
        issues.append(MetadataIssue(
            "warning", "sidecar_uncovered_data_column",
            f"Sidecar does not provide metadata for {len(uncovered)} data column(s).",
            details={"columns": uncovered[:20], "truncated": len(uncovered) > 20},
        ))
    if format_info.get("metadata_mode") in {"limited", "read-only"}:
        issues.append(MetadataIssue(
            "warning", "metadata_native_roundtrip_limited",
            "The source format has limited native metadata round-trip support.",
        ))
    source = MetadataSourceInfo(
        input_path=str(path),
        format=format_info.get("name"),
        backend=get_backend_name(str(path)),
        metadata_mode=format_info.get("metadata_mode"),
        metadata_source=source_name,
        sidecar_path=str(selected_sidecar),
        sidecar_present=sidecar.present,
        sidecar_version=sidecar.version,
        embedded_metadata_present=embedded_present,
        native_metadata_present=native_present,
        resolved_precedence=_resolved_precedence(
            source_name, sidecar_present=sidecar.present and not require_sidecar,
            embedded_present=embedded_present,
        ),
        object_name=object_name,
        object_kind=object_kind or format_info.get("object_kind"),
    )
    summary = dataset.metadata_summary()
    sidecar_names = set(sidecar.columns)
    coverage = MetadataCoverage(
        data_columns=len(dataframe_columns),
        metadata_columns=len(metadata_columns),
        columns_with_labels=int(summary.get("variable_labels", 0)),
        columns_with_value_labels=int(summary.get("value_label_sets", 0)),
        columns_with_missing_values=int(summary.get("missing_value_sets", 0)),
        columns_with_missing_ranges=int(summary.get("missing_range_sets", 0)),
        columns_with_display_formats=int(summary.get("display_formats", 0)),
        columns_with_measurement_levels=int(summary.get("measurement_levels", 0)),
        sidecar_columns=len(sidecar_names),
        uncovered_data_columns=len(physical_columns - sidecar_names) if sidecar.present else 0,
        orphan_metadata_columns=len(metadata_columns - physical_columns),
        notes_count=len(metadata.notes),
        uncovered_columns=uncovered[:max_columns] if sidecar.present else (),
        orphan_columns=tuple(sorted(metadata_columns - physical_columns))[:max_columns],
    )
    has_errors = any(issue.severity == "error" for issue in issues)
    issues_truncated = len(issues) > max_issues
    returned_issues = issues[:max_issues]
    if issues_truncated and max_issues:
        returned_issues[-1] = MetadataIssue(
            "info", "metadata_diagnostics_truncated",
            f"Diagnostic issue details were bounded to {max_issues} entries.",
        )
    return MetadataDiagnostics(
        valid=not has_errors,
        source=source,
        coverage=coverage,
        issues=tuple(returned_issues),
        columns=tuple(column_rows),
        caveats=caveats,
        provenance={
            "dataset": source_name,
            "column_sources": {
                str(source): sum(1 for value in column_sources.values() if str(value) == source)
                for source in sorted({str(value) for value in column_sources.values()})
            },
        },
        truncated=len(dataframe_columns) > max_columns or issues_truncated,
    )


def _inspect_sidecar(path: Path, *, required: bool) -> _SidecarInspection:
    if not path.exists():
        issues = ()
        if required:
            issues = (MetadataIssue(
                "error", "sidecar_not_found", f"Metadata sidecar does not exist: {path}.",
                suggestion="Provide an existing sidecar with --sidecar-input.",
            ),)
        return _SidecarInspection(path=path, present=False, issues=issues)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _SidecarInspection(path, True, issues=(MetadataIssue(
            "error", "sidecar_parse_error", f"Could not decode sidecar JSON: {exc}.",
        ),))
    if not isinstance(raw, Mapping):
        return _SidecarInspection(path, True, issues=(MetadataIssue(
            "error", "sidecar_invalid_schema", "Sidecar top-level value must be an object.",
        ),))

    issues: list[MetadataIssue] = []
    allowed_top = {
        "sidecar_version", "created_by", "source_format", "source_file",
        "dataset_metadata", "columns", "provenance",
    }
    for key in sorted(set(raw) - allowed_top):
        issues.append(MetadataIssue(
            "warning", "sidecar_unknown_top_level_field", f"Unknown sidecar field: {key}.", field=str(key),
        ))
    allowed_column = {item.name for item in fields(ColumnMetadata)} | {"value_label_items"}
    declared_types: dict[str, str] = {}
    columns_value = raw.get("columns", [])
    if isinstance(columns_value, list):
        for index, item in enumerate(columns_value):
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if isinstance(name, str) and isinstance(item.get("physical_type"), str):
                declared_types[name] = item["physical_type"]
            for key in sorted(set(item) - allowed_column):
                issues.append(MetadataIssue(
                    "warning", "sidecar_unknown_column_field",
                    f"Unknown sidecar column field: {key}.",
                    column=name if isinstance(name, str) else None, field=str(key),
                ))
            read_only_fields = sorted(
                key for key in (
                    "alignment", "readstat_variable_type", "role", "width",
                    "decimals", "display_width",
                )
                if item.get(key) is not None
            )
            if read_only_fields:
                issues.append(MetadataIssue(
                    "warning", "sidecar_read_only_field",
                    "Sidecar contains fields that are transport-only in the planned editor: "
                    + ", ".join(read_only_fields) + ".",
                    column=name if isinstance(name, str) else None,
                    details={"fields": read_only_fields},
                ))
            _check_typed_label_items(item, index, issues)
    try:
        payload = parse_payload(raw, source=str(path))
    except MetadataSidecarError as exc:
        message = str(exc)
        if "Unsupported metadata payload version" in message:
            code = "sidecar_unsupported_version"
        elif "duplicate column metadata name" in message:
            code = "sidecar_duplicate_column"
        else:
            code = "sidecar_invalid_schema"
        issues.append(MetadataIssue("error", code, message))
        return _SidecarInspection(path, True, _integer(raw.get("sidecar_version")), issues=tuple(issues))
    return _SidecarInspection(
        path, True, payload.version, tuple(payload.columns), tuple(issues), declared_types,
    )


def _check_typed_label_items(
    item: Mapping[str, Any], index: int, issues: list[MetadataIssue]
) -> None:
    entries = item.get("value_label_items")
    if not isinstance(entries, list):
        return
    seen: set[tuple[str, str]] = set()
    seen_values: list[tuple[Any, tuple[str, str]]] = []
    name = item.get("name")
    for entry in entries:
        if not isinstance(entry, Mapping) or "value" not in entry:
            continue
        value = entry.get("value")
        marker = (type(value).__name__, json.dumps(value, sort_keys=True, default=str))
        if marker in seen:
            issues.append(MetadataIssue(
                "error", "sidecar_duplicate_typed_value_label",
                f"Duplicate typed value-label key in columns[{index}].",
                column=name if isinstance(name, str) else None, field="value_label_items",
            ))
        elif any(
            previous_marker != marker and _safe_equal(previous_value, value)
            for previous_value, previous_marker in seen_values
        ):
            issues.append(MetadataIssue(
                "error", "sidecar_value_label_type_conflict",
                f"Typed value-label keys collide after mapping conversion in columns[{index}].",
                column=name if isinstance(name, str) else None, field="value_label_items",
            ))
        seen.add(marker)
        seen_values.append((value, marker))


def _check_value_labels(
    series: pd.Series,
    name: str,
    labels: Mapping[Any, Any],
    issues: list[MetadataIssue],
) -> None:
    try:
        unique_count = int(series.nunique(dropna=True))
        if unique_count > 100:
            return
        observed = list(series.dropna().unique())
    except (TypeError, ValueError):
        return
    if not labels:
        if 1 < unique_count <= 20:
            issues.append(MetadataIssue(
                "info", "metadata_unlabelled_observed_value",
                f"Low-cardinality column {name} has observed values but no value labels.",
                column=name, field="value_labels",
                details={"observed_value_count": unique_count},
            ))
        return
    unused = [value for value in labels if not any(_safe_equal(value, item) for item in observed)]
    if unused:
        issues.append(MetadataIssue(
            "warning", "metadata_unused_value_label",
            f"{len(unused)} value-label key(s) are not observed in column {name}.",
            column=name, field="value_labels",
        ))


def _safe_equal(left: Any, right: Any) -> bool:
    try:
        value = left == right
        return bool(value) if not isinstance(value, (pd.Series, pd.DataFrame)) else False
    except (TypeError, ValueError):
        return False


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _resolved_precedence(
    resolved_source: str | None,
    *,
    sidecar_present: bool,
    embedded_present: bool,
) -> str | None:
    sources = []
    if sidecar_present:
        sources.append("automatic_sidecar")
    if embedded_present:
        sources.append("embedded_arrow")
    if resolved_source and resolved_source not in sources:
        sources.append(resolved_source)
    return " > ".join(sources) or None
