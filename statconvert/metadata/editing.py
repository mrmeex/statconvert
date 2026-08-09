from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import date, datetime
import json
import os
from pathlib import Path
import tempfile
import tomllib
from typing import Any, Mapping

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataDiagnosticsError, MetadataSidecarError, OutputPathError
from statconvert.metadata.diagnostics import MetadataCoverage, MetadataIssue, build_metadata_diagnostics
from statconvert.metadata.sidecar import (
    METADATA_SOURCE_EXPLICIT_SIDECAR,
    apply_payload,
    dataset_to_payload,
    read_sidecar_path,
    serialize_payload,
    sidecar_path,
)
from statconvert.registry import FORMAT_INFO, get_extension


MEASUREMENT_LEVELS = frozenset({"nominal", "ordinal", "scale"})
MAX_PATCH_OPERATIONS = 1_000
MAX_PREVIEW_CHANGES = 500


@dataclass(frozen=True)
class ScalarPatchOperation:
    action: str
    value: str | None = None


@dataclass(frozen=True)
class NotesPatchOperation:
    action: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class VariableLabelPatchOperation:
    column: str
    action: str
    value: str | None = None


@dataclass(frozen=True)
class ValueLabelPatchOperation:
    column: str
    action: str
    value: Any
    label: str | None = None


@dataclass(frozen=True)
class MeasurementPatchOperation:
    column: str
    action: str
    value: str | None = None


@dataclass(frozen=True)
class MetadataPatch:
    dataset_label: ScalarPatchOperation | None = None
    notes: NotesPatchOperation | None = None
    variable_labels: tuple[VariableLabelPatchOperation, ...] = ()
    value_labels: tuple[ValueLabelPatchOperation, ...] = ()
    measurement_levels: tuple[MeasurementPatchOperation, ...] = ()


@dataclass(frozen=True)
class MetadataPatchChange:
    field: str
    action: str
    before: Any
    after: Any
    column: str | None = None
    key: Any = None


@dataclass(frozen=True)
class MetadataPatchPreview:
    valid: bool
    writes: bool
    target: str
    source_data_modified: bool
    sidecar_target_modified: bool
    overwrite_required: bool
    changes: tuple[MetadataPatchChange, ...]
    conflicts: tuple[MetadataIssue, ...]
    issues: tuple[MetadataIssue, ...]
    coverage: MetadataCoverage
    object_kind: str | None
    object_name: str | None
    dry_run: bool
    total_changes: int
    shown_changes: int
    truncated: bool


def parse_metadata_patch(path: str | Path) -> MetadataPatch:
    """Parse the closed, data-only TOML metadata patch schema."""

    patch_path = Path(path)
    try:
        raw = tomllib.loads(patch_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise MetadataDiagnosticsError(
            f"Metadata patch is not valid UTF-8: {patch_path}."
        ) from exc
    except OSError as exc:
        raise MetadataDiagnosticsError(f"Could not read metadata patch: {patch_path}. {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MetadataDiagnosticsError(f"Metadata patch is not valid TOML: {patch_path}. {exc}") from exc
    return parse_metadata_patch_data(raw)


def parse_metadata_patch_data(raw: Any) -> MetadataPatch:
    """Validate an already decoded JSON/TOML-compatible patch object."""

    if not isinstance(raw, dict):
        raise MetadataDiagnosticsError("Metadata patch must be a TOML table.")
    allowed = {
        "dataset_label", "notes", "variable_labels", "value_labels",
        "measurement_levels",
    }
    _reject_unknown(raw, allowed, "patch")
    patch = MetadataPatch(
        dataset_label=_parse_scalar_operation(raw.get("dataset_label"), "dataset_label"),
        notes=_parse_notes(raw.get("notes")),
        variable_labels=tuple(
            _parse_variable_label(item, index)
            for index, item in enumerate(_operation_list(raw, "variable_labels"))
        ),
        value_labels=tuple(
            _parse_value_label(item, index)
            for index, item in enumerate(_operation_list(raw, "value_labels"))
        ),
        measurement_levels=tuple(
            _parse_measurement(item, index)
            for index, item in enumerate(_operation_list(raw, "measurement_levels"))
        ),
    )
    if not any((
        patch.dataset_label,
        patch.notes,
        patch.variable_labels,
        patch.value_labels,
        patch.measurement_levels,
    )):
        raise MetadataDiagnosticsError("Metadata patch contains no operations.")
    operation_count = (
        int(patch.dataset_label is not None)
        + int(patch.notes is not None)
        + len(patch.variable_labels)
        + len(patch.value_labels)
        + len(patch.measurement_levels)
    )
    if operation_count > MAX_PATCH_OPERATIONS:
        raise MetadataDiagnosticsError(
            f"Metadata patch exceeds the {MAX_PATCH_OPERATIONS}-operation limit."
        )
    return patch


def preview_metadata_patch(
    dataset: Dataset,
    input_path: str | Path,
    patch: MetadataPatch,
    target_path: str | Path,
    *,
    overwrite: bool = False,
    object_name: str | None = None,
    dry_run: bool = True,
) -> tuple[MetadataPatchPreview, Dataset]:
    """Apply a patch to a copy and return a deterministic, write-free preview."""

    _require_editable_target(input_path, target_path, object_name=object_name)
    target = Path(target_path)
    conflicts = _target_conflicts(dataset, patch)
    edited = dataset.copy()
    changes = _apply_patch(edited, patch, conflicts)
    edited.sync_metadata()
    diagnostics = build_metadata_diagnostics(edited, input_path, object_name=object_name)
    overwrite_required = target.exists() and not overwrite
    if overwrite_required:
        conflicts.append(MetadataIssue(
            "error", "metadata_sidecar_overwrite_required",
            f"Metadata sidecar already exists: {target}.",
            suggestion="Use --overwrite-sidecar to replace it.",
        ))
    shown_changes = tuple(changes[:MAX_PREVIEW_CHANGES])
    preview = MetadataPatchPreview(
        valid=not any(issue.severity == "error" for issue in (*conflicts, *diagnostics.issues)),
        writes=False,
        target=str(target),
        source_data_modified=False,
        sidecar_target_modified=False,
        overwrite_required=overwrite_required,
        changes=shown_changes,
        conflicts=tuple(conflicts),
        issues=diagnostics.issues,
        coverage=diagnostics.coverage,
        object_kind=diagnostics.source.object_kind,
        object_name=object_name,
        dry_run=dry_run,
        total_changes=len(changes),
        shown_changes=len(shown_changes),
        truncated=len(changes) > len(shown_changes),
    )
    return preview, edited


def preview_sidecar_apply(
    dataset: Dataset,
    input_path: str | Path,
    source_sidecar: str | Path,
    target_path: str | Path,
    *,
    overwrite: bool = False,
    object_name: str | None = None,
    dry_run: bool = True,
) -> tuple[MetadataPatchPreview, Dataset]:
    """Preview applying a sidecar as a new sidecar without activating either path."""

    _require_editable_target(input_path, target_path, object_name=object_name)
    candidate_diagnostics = build_metadata_diagnostics(
        dataset,
        input_path,
        sidecar_input=source_sidecar,
        require_sidecar=True,
        object_name=object_name,
    )
    conflicts = [
        replace(issue, severity="error")
        if issue.code in {
            "sidecar_unknown_top_level_field", "sidecar_unknown_column_field",
            "sidecar_read_only_field",
        }
        else issue
        for issue in candidate_diagnostics.issues
        if issue.severity == "error" or issue.code in {
            "sidecar_unknown_top_level_field", "sidecar_unknown_column_field",
            "sidecar_read_only_field",
        }
    ]
    payload = read_sidecar_path(source_sidecar)
    edited = dataset.copy()
    metadata, columns, provenance = apply_payload(
        dataframe=edited.dataframe,
        base_metadata=edited.get_normalized_metadata(),
        payload=payload,
        source=METADATA_SOURCE_EXPLICIT_SIDECAR,
        provenance=edited.metadata_provenance,
    )
    edited.normalized_metadata = metadata
    edited.column_metadata.update(columns)
    edited.metadata_provenance = provenance
    edited.sync_metadata()
    changes = _metadata_changes(dataset, edited)
    target = Path(target_path)
    overwrite_required = target.exists() and not overwrite
    if overwrite_required:
        conflicts.append(MetadataIssue(
            "error", "metadata_sidecar_overwrite_required",
            f"Metadata sidecar already exists: {target}.",
            suggestion="Use --overwrite-sidecar to replace it.",
        ))
    shown_changes = tuple(changes[:MAX_PREVIEW_CHANGES])
    preview = MetadataPatchPreview(
        valid=not any(issue.severity == "error" for issue in conflicts),
        writes=False,
        target=str(target),
        source_data_modified=False,
        sidecar_target_modified=False,
        overwrite_required=overwrite_required,
        changes=shown_changes,
        conflicts=tuple(conflicts),
        issues=candidate_diagnostics.issues,
        coverage=candidate_diagnostics.coverage,
        object_kind=candidate_diagnostics.source.object_kind,
        object_name=object_name,
        dry_run=dry_run,
        total_changes=len(changes),
        shown_changes=len(shown_changes),
        truncated=len(changes) > len(shown_changes),
    )
    return preview, edited


def save_metadata_sidecar(
    preview: MetadataPatchPreview,
    edited: Dataset,
    *,
    overwrite: bool = False,
) -> MetadataPatchPreview:
    """Atomically save a validated preview to its sidecar target."""

    if not preview.valid:
        raise MetadataDiagnosticsError("Metadata preview contains conflicts and cannot be saved.")
    target = Path(preview.target)
    if target.exists() and not overwrite:
        raise OutputPathError(
            f"Metadata sidecar already exists: {target}",
            suggestion="Use --overwrite-sidecar to replace it.",
        )
    if not target.parent.exists():
        raise OutputPathError(
            f"Parent folder does not exist: {target.parent}",
            suggestion="Create the folder first or choose a different sidecar output path.",
        )
    text = serialize_payload(dataset_to_payload(edited))
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists() and not overwrite:
            raise OutputPathError(
                f"Metadata sidecar already exists: {target}",
                suggestion="Use --overwrite-sidecar to replace it.",
            )
        os.replace(temporary, target)
        temporary = None
    except OutputPathError:
        raise
    except OSError as exc:
        raise MetadataSidecarError(
            f"Could not atomically write metadata sidecar: {target}. {exc}"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return replace(
        preview,
        writes=True,
        sidecar_target_modified=True,
        overwrite_required=False,
        dry_run=False,
    )


def default_sidecar_target(input_path: str | Path) -> Path:
    return sidecar_path(input_path)


def _parse_scalar_operation(value: Any, field_name: str) -> ScalarPatchOperation | None:
    if value is None:
        return None
    item = _table(value, field_name)
    _reject_unknown(item, {"action", "value"}, field_name)
    action = _action(item, field_name, {"set", "delete"})
    raw_value = item.get("value")
    if action == "set":
        label = _label(raw_value, f"{field_name}.value")
        return ScalarPatchOperation(action, label)
    if "value" in item:
        raise MetadataDiagnosticsError(f"{field_name}.value is not allowed for delete.")
    return ScalarPatchOperation(action)


def _parse_notes(value: Any) -> NotesPatchOperation | None:
    if value is None:
        return None
    item = _table(value, "notes")
    _reject_unknown(item, {"action", "values"}, "notes")
    action = _action(item, "notes", {"replace", "append", "delete"})
    values = item.get("values", [])
    if action == "delete":
        if "values" in item:
            raise MetadataDiagnosticsError("notes.values is not allowed for delete.")
        return NotesPatchOperation(action)
    if not isinstance(values, list) or not all(isinstance(note, str) for note in values):
        raise MetadataDiagnosticsError("notes.values must be a list of strings.")
    return NotesPatchOperation(action, tuple(values))


def _parse_variable_label(value: Any, index: int) -> VariableLabelPatchOperation:
    name = f"variable_labels[{index}]"
    item = _table(value, name)
    _reject_unknown(item, {"column", "action", "value"}, name)
    column = _column(item, name)
    action = _action(item, name, {"set", "delete"})
    if action == "set":
        return VariableLabelPatchOperation(column, action, _label(item.get("value"), f"{name}.value"))
    if "value" in item:
        raise MetadataDiagnosticsError(f"{name}.value is not allowed for delete.")
    return VariableLabelPatchOperation(column, action)


def _parse_value_label(value: Any, index: int) -> ValueLabelPatchOperation:
    name = f"value_labels[{index}]"
    item = _table(value, name)
    _reject_unknown(item, {"column", "action", "value", "label"}, name)
    column = _column(item, name)
    action = _action(item, name, {"set", "delete"})
    if "value" not in item or not _is_scalar(item["value"]):
        raise MetadataDiagnosticsError(f"{name}.value must be a string, integer, float, or boolean.")
    if action == "set":
        return ValueLabelPatchOperation(
            column, action, copy.deepcopy(item["value"]), _label(item.get("label"), f"{name}.label"),
        )
    if "label" in item:
        raise MetadataDiagnosticsError(f"{name}.label is not allowed for delete.")
    return ValueLabelPatchOperation(column, action, copy.deepcopy(item["value"]))


def _parse_measurement(value: Any, index: int) -> MeasurementPatchOperation:
    name = f"measurement_levels[{index}]"
    item = _table(value, name)
    _reject_unknown(item, {"column", "action", "value"}, name)
    column = _column(item, name)
    action = _action(item, name, {"set", "delete"})
    if action == "set":
        level = item.get("value")
        if level not in MEASUREMENT_LEVELS:
            raise MetadataDiagnosticsError(
                f"{name}.value must be nominal, ordinal, or scale."
            )
        return MeasurementPatchOperation(column, action, level)
    if "value" in item:
        raise MetadataDiagnosticsError(f"{name}.value is not allowed for delete.")
    return MeasurementPatchOperation(column, action)


def _target_conflicts(dataset: Dataset, patch: MetadataPatch) -> list[MetadataIssue]:
    conflicts: list[MetadataIssue] = []
    columns = [str(column) for column in dataset.dataframe.columns]
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        conflicts.append(MetadataIssue(
            "error", "metadata_edit_duplicate_data_column",
            "Metadata editing requires unique data column names: " + ", ".join(duplicates) + ".",
        ))
    operations = (*patch.variable_labels, *patch.value_labels, *patch.measurement_levels)
    for operation in operations:
        if operation.column not in columns:
            conflicts.append(MetadataIssue(
                "error", "metadata_patch_unknown_column",
                f"Patch references a column not present in the data: {operation.column}.",
                column=operation.column,
            ))
    for field_name, field_operations in (
        ("variable_label", patch.variable_labels),
        ("measurement_level", patch.measurement_levels),
    ):
        seen_columns: set[str] = set()
        for operation in field_operations:
            if operation.column in seen_columns:
                conflicts.append(MetadataIssue(
                    "error", "metadata_patch_duplicate_column_operation",
                    f"Patch contains more than one {field_name} operation for {operation.column}.",
                    column=operation.column, field=field_name,
                ))
            seen_columns.add(operation.column)
    seen: set[tuple[str, str, str]] = set()
    equal_keys: list[tuple[str, Any, tuple[str, str, str]]] = []
    for operation in patch.value_labels:
        marker = _typed_marker(operation.column, operation.value)
        if marker in seen:
            conflicts.append(MetadataIssue(
                "error", "metadata_patch_duplicate_value_label_key",
                "Patch contains duplicate typed value-label operations.",
                column=operation.column, field="value_labels",
            ))
        if any(
            column == operation.column and previous_marker != marker
            and _safe_equal(previous, operation.value)
            for column, previous, previous_marker in equal_keys
        ):
            conflicts.append(MetadataIssue(
                "error", "metadata_patch_value_label_type_conflict",
                "Typed value-label keys collide after mapping conversion.",
                column=operation.column, field="value_labels",
            ))
        seen.add(marker)
        equal_keys.append((operation.column, operation.value, marker))
        if operation.column in columns and not _value_compatible(dataset.dataframe[operation.column], operation.value):
            conflicts.append(MetadataIssue(
                "error", "metadata_patch_value_label_type_incompatible",
                f"Value-label key type is incompatible with column {operation.column}.",
                column=operation.column, field="value_labels",
            ))
    return conflicts


def _apply_patch(
    dataset: Dataset,
    patch: MetadataPatch,
    conflicts: list[MetadataIssue],
) -> list[MetadataPatchChange]:
    metadata = dataset.get_normalized_metadata()
    changes: list[MetadataPatchChange] = []
    if patch.dataset_label:
        before = metadata.dataset_label
        after = patch.dataset_label.value if patch.dataset_label.action == "set" else None
        _change(changes, "dataset_label", patch.dataset_label.action, before, after)
        metadata.dataset_label = after
    if patch.notes:
        before_notes = list(metadata.notes)
        if patch.notes.action == "delete":
            after_notes: list[str] = []
        elif patch.notes.action == "append":
            after_notes = [*before_notes, *patch.notes.values]
        else:
            after_notes = list(patch.notes.values)
        _change(changes, "notes", patch.notes.action, before_notes, after_notes)
        metadata.notes = after_notes
    for operation in patch.variable_labels:
        variable = metadata.get_variable(operation.column)
        if variable is None:
            continue
        before = variable.label
        after = operation.value if operation.action == "set" else None
        _change(changes, "variable_label", operation.action, before, after, column=operation.column)
        variable.label = after
    for operation in patch.value_labels:
        variable = metadata.get_variable(operation.column)
        if variable is None:
            continue
        before = _typed_mapping_get(variable.value_labels, operation.value)
        after = operation.label if operation.action == "set" else None
        _change(
            changes, "value_label", operation.action, before, after,
            column=operation.column, key=operation.value,
        )
        if operation.action == "set":
            variable.value_labels[operation.value] = operation.label
        else:
            _typed_mapping_delete(variable.value_labels, operation.value)
    for operation in patch.measurement_levels:
        variable = metadata.get_variable(operation.column)
        if variable is None:
            continue
        before = variable.measure
        after = operation.value if operation.action == "set" else None
        _change(
            changes, "measurement_level", operation.action, before, after,
            column=operation.column,
        )
        variable.measure = after
    return changes


def _metadata_changes(before: Dataset, after: Dataset) -> list[MetadataPatchChange]:
    changes: list[MetadataPatchChange] = []
    left = before.get_normalized_metadata()
    right = after.get_normalized_metadata()
    _change(changes, "dataset_label", "replace", left.dataset_label, right.dataset_label)
    _change(changes, "notes", "replace", list(left.notes), list(right.notes))
    for name in (str(column) for column in before.dataframe.columns):
        left_variable = left.get_variable(name)
        right_variable = right.get_variable(name)
        if left_variable is None or right_variable is None:
            continue
        _change(changes, "variable_label", "replace", left_variable.label, right_variable.label, column=name)
        _change(changes, "measurement_level", "replace", left_variable.measure, right_variable.measure, column=name)
        typed_keys = {
            _typed_marker(name, key): key
            for key in (*left_variable.value_labels.keys(), *right_variable.value_labels.keys())
        }
        for key in typed_keys.values():
            _change(
                changes, "value_label", "replace",
                _typed_mapping_get(left_variable.value_labels, key),
                _typed_mapping_get(right_variable.value_labels, key),
                column=name, key=key,
            )
    return changes


def _require_editable_target(
    input_path: str | Path,
    target_path: str | Path,
    *,
    object_name: str | None,
) -> None:
    input_value = Path(input_path)
    target = Path(target_path)
    if input_value.resolve(strict=False) == target.resolve(strict=False):
        raise OutputPathError(
            f"Metadata sidecar target would replace the source data file: {target}",
            suggestion="Choose a separate sidecar output path.",
        )
    info = FORMAT_INFO[get_extension(str(input_value))]
    if info.get("is_container"):
        detail = " even with an object selector" if object_name else ""
        raise MetadataDiagnosticsError(
            "Sidecar editing for container formats is deferred because legacy flat "
            f"sidecars cannot record deterministic object identity{detail}."
        )


def _operation_list(raw: Mapping[str, Any], field_name: str) -> list[Any]:
    value = raw.get(field_name, [])
    if not isinstance(value, list):
        raise MetadataDiagnosticsError(f"{field_name} must be an array of TOML tables.")
    return value


def _table(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MetadataDiagnosticsError(f"{field_name} must be a TOML table.")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], field_name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MetadataDiagnosticsError(
            f"Unknown or unsupported metadata patch field in {field_name}: {', '.join(unknown)}."
        )


def _action(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> str:
    action = value.get("action")
    if action not in allowed:
        raise MetadataDiagnosticsError(
            f"{field_name}.action must be one of: {', '.join(sorted(allowed))}."
        )
    return str(action)


def _column(value: Mapping[str, Any], field_name: str) -> str:
    column = value.get("column")
    if not isinstance(column, str) or not column:
        raise MetadataDiagnosticsError(f"{field_name}.column must be a non-empty string.")
    return column


def _label(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise MetadataDiagnosticsError(f"{field_name} must be a string.")
    if not value or not value.strip():
        raise MetadataDiagnosticsError(
            f"{field_name} cannot be empty or whitespace-only; use action = 'delete'."
        )
    return value


def _is_scalar(value: Any) -> bool:
    return value is not None and isinstance(value, (str, int, float, bool)) and not isinstance(value, (date, datetime))


def _typed_marker(column: str, value: Any) -> tuple[str, str, str]:
    return column, type(value).__name__, json.dumps(value, ensure_ascii=False, sort_keys=True)


def _typed_mapping_get(mapping: Mapping[Any, Any], key: Any) -> Any:
    marker = _typed_marker("", key)[1:]
    for candidate, value in mapping.items():
        if _typed_marker("", candidate)[1:] == marker:
            return value
    return None


def _typed_mapping_delete(mapping: dict[Any, Any], key: Any) -> None:
    marker = _typed_marker("", key)[1:]
    for candidate in list(mapping):
        if _typed_marker("", candidate)[1:] == marker:
            del mapping[candidate]
            return


def _value_compatible(series: pd.Series, value: Any) -> bool:
    dtype = series.dtype
    if pd.api.types.is_object_dtype(dtype):
        return True
    if pd.api.types.is_bool_dtype(dtype):
        return isinstance(value, bool)
    if pd.api.types.is_numeric_dtype(dtype):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if pd.api.types.is_string_dtype(dtype):
        return isinstance(value, str)
    return True


def _safe_equal(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


def _change(
    changes: list[MetadataPatchChange],
    field_name: str,
    action: str,
    before: Any,
    after: Any,
    *,
    column: str | None = None,
    key: Any = None,
) -> None:
    if _json_safe(before) != _json_safe(after):
        changes.append(MetadataPatchChange(
            field=field_name,
            action=action,
            before=copy.deepcopy(before),
            after=copy.deepcopy(after),
            column=column,
            key=copy.deepcopy(key),
        ))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return [
            (type(key).__name__, repr(key), _json_safe(item))
            for key, item in value.items()
        ]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value
