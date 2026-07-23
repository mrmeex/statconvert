from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.exceptions import MetadataSidecarError, OutputPathError
from statconvert.metadata.adapters import metadata_from_sidecar
from statconvert.metadata.model import DatasetMetadata


CURRENT_SIDECAR_VERSION = 3
SUPPORTED_SIDECAR_VERSIONS = (2, CURRENT_SIDECAR_VERSION)
SIDECAR_SUFFIX = ".statconvert-metadata.json"

METADATA_SOURCE_PRIMARY = "primary_file"
METADATA_SOURCE_NATIVE = "native_file"
METADATA_SOURCE_AUTOMATIC_SIDECAR = "automatic_sidecar"
METADATA_SOURCE_EXPLICIT_SIDECAR = "explicit_sidecar"
METADATA_SOURCE_EMBEDDED_ARROW = "embedded_arrow"
_AUTOMATIC_PAYLOAD_UNSET = object()
_AUTOMATIC_SIDECAR_READS_ENABLED: ContextVar[bool] = ContextVar(
    "automatic_sidecar_reads_enabled",
    default=True,
)


@dataclass(frozen=True)
class MetadataPayload:
    """Validated, backend-neutral metadata transport payload."""

    version: int
    source_format: str | None
    source_file: str | None
    dataset_label: str | None
    notes: tuple[str, ...]
    raw_metadata: dict[str, Any]
    columns: dict[str, ColumnMetadata]
    provenance: dict[str, Any]
    has_dataset_metadata: bool


@dataclass(frozen=True)
class MetadataRestoreResult:
    """Normalized metadata and provenance after applying available sources."""

    metadata: DatasetMetadata
    column_metadata: dict[str, ColumnMetadata]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class MetadataApplyResult:
    """Outcome of validating or activating one metadata sidecar."""

    target_path: Path
    source_path: Path
    already_active: bool
    unmatched_data_columns: tuple[str, ...]


def sidecar_path(filename: str | Path) -> Path:
    """Return the standardized sibling sidecar path."""

    return Path(f"{filename}{SIDECAR_SUFFIX}")


@contextmanager
def without_automatic_sidecar():
    """Temporarily read primary/native/embedded metadata without the sibling."""

    token = _AUTOMATIC_SIDECAR_READS_ENABLED.set(False)
    try:
        yield
    finally:
        _AUTOMATIC_SIDECAR_READS_ENABLED.reset(token)


def dataset_to_payload(dataset: Dataset) -> dict[str, Any]:
    """Serialize current normalized metadata as deterministic version 3 data."""

    dataset.sync_metadata()
    metadata = dataset.get_normalized_metadata()
    columns = []
    for dataframe_column in dataset.dataframe.columns:
        name = str(dataframe_column)
        columns.append(_column_to_payload(dataset.column_metadata[name]))

    return {
        "sidecar_version": CURRENT_SIDECAR_VERSION,
        "created_by": "statconvert",
        "source_format": dataset.source_format,
        "source_file": _json_value(dataset.source_file),
        "dataset_metadata": {
            "dataset_label": metadata.dataset_label,
            "notes": [_json_value(note) for note in metadata.notes],
            "raw_metadata": _safe_raw_metadata(metadata.raw_metadata),
        },
        "columns": columns,
        "provenance": _safe_mapping(dataset.metadata_provenance),
    }


def serialize_payload(payload: Mapping[str, Any]) -> str:
    """Return stable UTF-8 JSON text for a validated-compatible payload."""

    return json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def payload_bytes(dataset: Dataset) -> bytes:
    """Return the current dataset payload encoded for embedded metadata."""

    return serialize_payload(dataset_to_payload(dataset)).encode("utf-8")


def write_sidecar(dataset: Dataset, filename: str | Path) -> Path:
    """Write the current payload to the standardized sidecar path."""

    path = sidecar_path(filename)
    _write_payload(
        dataset_to_payload(dataset),
        path,
        source="automatic metadata sidecar",
    )
    return path


def export_sidecar(
    dataset: Dataset,
    input_filename: str | Path,
    *,
    output_path: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Explicitly export resolved Dataset metadata with safe output handling."""

    input_path = Path(input_filename)
    target = Path(output_path) if output_path is not None else sidecar_path(input_path)
    if target.resolve(strict=False) == input_path.resolve(strict=False):
        raise OutputPathError(
            f"Metadata sidecar path would replace the input file: {target}",
            suggestion="Choose a different sidecar export path.",
        )

    parent = target.parent
    if parent != Path(".") and not parent.exists():
        raise OutputPathError(
            f"Parent folder does not exist: {parent}",
            suggestion="Create the folder first, or choose a different export path.",
        )
    if parent.exists() and not parent.is_dir():
        raise OutputPathError(
            f"Parent path is not a folder: {parent}",
            suggestion="Choose an export path whose parent is a folder.",
        )
    if target.exists() and not overwrite:
        raise OutputPathError(
            f"Metadata sidecar already exists: {target}",
            suggestion=(
                "Use --overwrite-sidecar to replace it, or choose a different "
                "export path."
            ),
        )

    _write_payload(
        dataset_to_payload(dataset),
        target,
        source="explicit metadata sidecar export",
    )
    return target


def read_sidecar(filename: str | Path) -> MetadataPayload | None:
    """Read and validate an automatically discovered sidecar if present."""

    if not _AUTOMATIC_SIDECAR_READS_ENABLED.get():
        return None
    path = sidecar_path(filename)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MetadataSidecarError(
            f"Could not read metadata sidecar: {path}. {exc}"
        ) from exc
    return parse_payload_text(text, source=str(path))


def read_sidecar_path(path: str | Path) -> MetadataPayload:
    """Read and validate one explicitly selected sidecar path."""

    source_path = Path(path)
    if not source_path.exists():
        raise MetadataSidecarError(
            f"Metadata sidecar file does not exist: {source_path}",
            suggestion="Check --sidecar-input and provide an existing sidecar file.",
        )
    if not source_path.is_file():
        raise MetadataSidecarError(
            f"Metadata sidecar path is not a file: {source_path}",
            suggestion="Provide a metadata sidecar JSON file.",
        )
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MetadataSidecarError(
            f"Could not read metadata sidecar: {source_path}. {exc}"
        ) from exc
    return parse_payload_text(text, source=str(source_path))


def apply_sidecar(
    dataset: Dataset,
    input_filename: str | Path,
    *,
    source_path: str | Path | None = None,
    overwrite: bool = False,
) -> MetadataApplyResult:
    """Validate or activate a sidecar at the standardized sibling path."""

    input_path = Path(input_filename)
    target = sidecar_path(input_path)
    source = Path(source_path) if source_path is not None else target

    if source_path is None and not target.exists():
        raise MetadataSidecarError(
            f"No standardized sidecar found for {input_path}.\nExpected: {target}",
            suggestion=(
                "Use --sidecar-input PATH to apply a sidecar from another location."
            ),
        )

    payload = read_sidecar_path(source)
    unmatched = validate_payload_columns(
        payload,
        dataset.dataframe,
        input_filename=input_path,
    )
    same_path = (
        source.resolve(strict=False)
        == target.resolve(strict=False)
    )
    if same_path:
        return MetadataApplyResult(
            target_path=target,
            source_path=source,
            already_active=True,
            unmatched_data_columns=unmatched,
        )

    if target.exists() and not overwrite:
        raise OutputPathError(
            f"Metadata sidecar already exists: {target}",
            suggestion="Use --overwrite-sidecar to replace it.",
        )

    normalized = _payload_for_explicit_apply(
        payload,
        dataset=dataset,
        source_path=source,
    )
    _write_payload(
        normalized,
        target,
        source="explicit metadata sidecar apply",
    )
    return MetadataApplyResult(
        target_path=target,
        source_path=source,
        already_active=False,
        unmatched_data_columns=unmatched,
    )


def parse_payload_bytes(data: bytes, *, source: str) -> MetadataPayload:
    """Decode and validate an embedded metadata payload."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MetadataSidecarError(
            f"Metadata payload is not valid UTF-8: {source}."
        ) from exc
    return parse_payload_text(text, source=source)


def parse_payload_text(text: str, *, source: str) -> MetadataPayload:
    """Parse one versioned payload with friendly validation failures."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetadataSidecarError(
            f"Metadata payload is not valid JSON: {source}. "
            f"Line {exc.lineno}, column {exc.colno}: {exc.msg}."
        ) from exc
    return parse_payload(payload, source=source)


def parse_payload(payload: Any, *, source: str) -> MetadataPayload:
    """Validate and normalize version 2 or version 3 payload data."""

    if not isinstance(payload, Mapping):
        raise _malformed(source, "the top-level value must be an object")

    version = payload.get("sidecar_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _malformed(source, "sidecar_version must be an integer")
    if version not in SUPPORTED_SIDECAR_VERSIONS:
        supported = ", ".join(str(item) for item in SUPPORTED_SIDECAR_VERSIONS)
        raise MetadataSidecarError(
            f"Unsupported metadata payload version {version}: {source}. "
            f"Supported versions: {supported}."
        )

    source_format = _optional_string(
        payload.get("source_format"),
        source=source,
        field_name="source_format",
    )
    source_file = _optional_string(
        payload.get("source_file"),
        source=source,
        field_name="source_file",
    )
    columns_value = payload.get("columns")
    if not isinstance(columns_value, list):
        raise _malformed(source, "columns must be a list")
    columns = _parse_columns(columns_value, source=source)

    has_dataset_metadata = version >= 3
    dataset_label = None
    notes: tuple[str, ...] = ()
    raw_metadata: dict[str, Any] = {}
    if has_dataset_metadata:
        dataset_value = payload.get("dataset_metadata")
        if not isinstance(dataset_value, Mapping):
            raise _malformed(source, "dataset_metadata must be an object")
        dataset_label = _optional_string(
            dataset_value.get("dataset_label"),
            source=source,
            field_name="dataset_metadata.dataset_label",
        )
        notes_value = dataset_value.get("notes", [])
        if not isinstance(notes_value, list) or not all(
            isinstance(note, str) for note in notes_value
        ):
            raise _malformed(
                source,
                "dataset_metadata.notes must be a list of strings",
            )
        notes = tuple(notes_value)
        raw_value = dataset_value.get("raw_metadata", {})
        if raw_value is None:
            raw_value = {}
        if not isinstance(raw_value, Mapping):
            raise _malformed(
                source,
                "dataset_metadata.raw_metadata must be an object",
            )
        raw_metadata = copy.deepcopy(dict(raw_value))

    provenance_value = payload.get("provenance", {})
    if provenance_value is None:
        provenance_value = {}
    if not isinstance(provenance_value, Mapping):
        raise _malformed(source, "provenance must be an object")

    return MetadataPayload(
        version=version,
        source_format=source_format,
        source_file=source_file,
        dataset_label=dataset_label,
        notes=notes,
        raw_metadata=raw_metadata,
        columns=columns,
        provenance=copy.deepcopy(dict(provenance_value)),
        has_dataset_metadata=has_dataset_metadata,
    )


def restore_metadata(
    *,
    dataframe: pd.DataFrame,
    base_metadata: DatasetMetadata,
    filename: str | Path,
    embedded_payload: MetadataPayload | None = None,
    automatic_payload: MetadataPayload | None | object = _AUTOMATIC_PAYLOAD_UNSET,
    base_source: str = METADATA_SOURCE_PRIMARY,
) -> MetadataRestoreResult:
    """Apply embedded metadata and then the canonical sibling sidecar."""

    metadata = copy.deepcopy(base_metadata)
    column_metadata: dict[str, ColumnMetadata] = {}
    provenance: dict[str, Any] = {
        "dataset": base_source,
        "columns": {
            str(column): base_source
            for column in dataframe.columns
        },
    }

    if embedded_payload is not None:
        metadata, embedded_columns, provenance = apply_payload(
            dataframe=dataframe,
            base_metadata=metadata,
            payload=embedded_payload,
            source=METADATA_SOURCE_EMBEDDED_ARROW,
            provenance=provenance,
        )
        column_metadata.update(embedded_columns)

    automatic = (
        read_sidecar(filename)
        if automatic_payload is _AUTOMATIC_PAYLOAD_UNSET
        else automatic_payload
    )
    if automatic is not None:
        if not isinstance(automatic, MetadataPayload):
            raise TypeError("automatic_payload must be MetadataPayload or None")
        metadata, sidecar_columns, provenance = apply_payload(
            dataframe=dataframe,
            base_metadata=metadata,
            payload=automatic,
            source=METADATA_SOURCE_AUTOMATIC_SIDECAR,
            provenance=provenance,
        )
        column_metadata.update(sidecar_columns)

    return MetadataRestoreResult(
        metadata=metadata,
        column_metadata=column_metadata,
        provenance=provenance,
    )


def apply_payload(
    *,
    dataframe: pd.DataFrame,
    base_metadata: DatasetMetadata,
    payload: MetadataPayload,
    source: str,
    provenance: Mapping[str, Any] | None = None,
) -> tuple[DatasetMetadata, dict[str, ColumnMetadata], dict[str, Any]]:
    """Apply one validated metadata payload without altering data values."""

    validate_payload_columns(payload, dataframe)

    metadata = metadata_from_sidecar(base_metadata, payload.columns)
    result_provenance = copy.deepcopy(dict(provenance or {}))
    result_provenance.setdefault("columns", {})
    for name in payload.columns:
        result_provenance["columns"][name] = source

    if payload.has_dataset_metadata:
        metadata.dataset_label = payload.dataset_label
        metadata.notes = list(payload.notes)
        metadata.raw_metadata = {
            **metadata.raw_metadata,
            **copy.deepcopy(payload.raw_metadata),
        }
        result_provenance["dataset"] = source
        result_provenance["dataset_label"] = source
        result_provenance["notes"] = source
        if payload.raw_metadata:
            result_provenance["raw_metadata"] = source

    result_provenance["last_applied"] = source
    result_provenance["transport_provenance"] = copy.deepcopy(payload.provenance)
    return metadata, copy.deepcopy(payload.columns), result_provenance


def validate_payload_columns(
    payload: MetadataPayload,
    dataframe: pd.DataFrame,
    *,
    input_filename: str | Path | None = None,
) -> tuple[str, ...]:
    """Validate name-based application and return data columns without metadata."""

    physical_columns = {str(column) for column in dataframe.columns}
    unknown_columns = sorted(set(payload.columns) - physical_columns)
    if unknown_columns:
        joined = ", ".join(unknown_columns)
        target = f" in {input_filename}" if input_filename is not None else ""
        raise MetadataSidecarError(
            f"Sidecar references columns not present{target}: {joined}",
            suggestion=(
                "Edit the sidecar or use a data file with matching column names."
            ),
        )
    return tuple(
        str(column)
        for column in dataframe.columns
        if str(column) not in payload.columns
    )


def validate_explicit_sidecar_target(
    *,
    is_container: bool,
    object_selector: str | None,
) -> None:
    """Enforce the future flat-sidecar container application policy."""

    if is_container and not (object_selector or "").strip():
        raise MetadataSidecarError(
            "A flat metadata sidecar cannot be applied to an ambiguous container "
            "without an explicit object selector."
        )


def _parse_columns(
    values: list[Any],
    *,
    source: str,
) -> dict[str, ColumnMetadata]:
    allowed_fields = {field.name for field in fields(ColumnMetadata)}
    columns: dict[str, ColumnMetadata] = {}
    for index, raw_item in enumerate(values):
        if not isinstance(raw_item, Mapping):
            raise _malformed(source, f"columns[{index}] must be an object")
        item = dict(raw_item)
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise _malformed(
                source,
                f"columns[{index}].name must be a non-empty string",
            )
        if name in columns:
            raise _malformed(source, f"duplicate column metadata name: {name}")

        value_label_items = item.pop("value_label_items", None)
        if value_label_items is not None:
            if not isinstance(value_label_items, list):
                raise _malformed(
                    source,
                    f"columns[{index}].value_label_items must be a list",
                )
            labels: dict[Any, Any] = {}
            for label_index, entry in enumerate(value_label_items):
                if not isinstance(entry, Mapping) or "value" not in entry:
                    raise _malformed(
                        source,
                        "columns"
                        f"[{index}].value_label_items[{label_index}] is malformed",
                    )
                labels[entry.get("value")] = entry.get("label")
            item["value_labels"] = labels

        filtered = {
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key in allowed_fields
        }
        try:
            columns[name] = ColumnMetadata(**filtered)
        except TypeError as exc:
            raise _malformed(
                source,
                f"columns[{index}] could not be decoded: {exc}",
            ) from exc
    return columns


def _optional_string(
    value: Any,
    *,
    source: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _malformed(source, f"{field_name} must be a string or null")
    return value


def _safe_raw_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        normalized = _json_value(dict(value))
    except (TypeError, ValueError):
        return {}
    return normalized if isinstance(normalized, dict) else {}


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        normalized = _json_value(dict(value))
    except (TypeError, ValueError):
        return {}
    return normalized if isinstance(normalized, dict) else {}


def _column_to_payload(column: ColumnMetadata) -> dict[str, Any]:
    item = _json_value(asdict(column))
    item["value_label_items"] = [
        {
            "value": _json_value(value),
            "label": _json_value(label),
        }
        for value, label in column.value_labels.items()
    ]
    return item


def _payload_for_explicit_apply(
    payload: MetadataPayload,
    *,
    dataset: Dataset,
    source_path: Path,
) -> dict[str, Any]:
    metadata = dataset.get_normalized_metadata()
    if payload.has_dataset_metadata:
        dataset_label = payload.dataset_label
        notes = list(payload.notes)
        raw_metadata = copy.deepcopy(payload.raw_metadata)
    else:
        dataset_label = metadata.dataset_label
        notes = list(metadata.notes)
        raw_metadata = _safe_raw_metadata(metadata.raw_metadata)

    source_provenance = _safe_mapping(payload.provenance)
    provenance: dict[str, Any] = {
        "dataset": METADATA_SOURCE_EXPLICIT_SIDECAR,
        "columns": {
            name: METADATA_SOURCE_EXPLICIT_SIDECAR
            for name in payload.columns
        },
        "applied_from": str(source_path),
    }
    if source_provenance:
        provenance["source_provenance"] = source_provenance

    return {
        "sidecar_version": CURRENT_SIDECAR_VERSION,
        "created_by": "statconvert",
        "source_format": payload.source_format,
        "source_file": payload.source_file,
        "dataset_metadata": {
            "dataset_label": dataset_label,
            "notes": notes,
            "raw_metadata": raw_metadata,
        },
        "columns": [
            _column_to_payload(column)
            for column in payload.columns.values()
        ],
        "provenance": provenance,
    }


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    raise TypeError(f"Unsupported metadata value type: {type(value).__name__}")


def _malformed(source: str, detail: str) -> MetadataSidecarError:
    return MetadataSidecarError(
        f"Metadata payload is malformed: {source}. {detail}."
    )


def _write_payload(
    payload: Mapping[str, Any],
    path: Path,
    *,
    source: str,
) -> None:
    """Validate and write one deterministic current-schema payload."""

    parse_payload(payload, source=source)
    try:
        path.write_text(
            serialize_payload(payload),
            encoding="utf-8",
        )
    except OSError as exc:
        raise MetadataSidecarError(
            f"Could not write metadata sidecar: {path}. {exc}"
        ) from exc
