from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.exceptions import DataDictionaryError, OutputPathError


DICTIONARY_EXTENSIONS = (".csv", ".xlsx")
DICTIONARY_COLUMNS = (
    "column_name",
    "position",
    "storage_type",
    "logical_type",
    "variable_label",
    "measurement_level",
    "display_format",
    "missing_values",
    "value_labels",
    "metadata_source",
    "dataset_label",
    "dataset_notes",
    "raw_type",
    "format_source",
    "value_label_count",
    "missing_value_count",
)


@dataclass(frozen=True)
class DataDictionaryRow:
    """One physical column and its resolved, review-oriented metadata."""

    column_name: str
    position: int
    storage_type: str
    logical_type: str
    variable_label: str
    measurement_level: str
    display_format: str
    missing_values: str
    value_labels: str
    metadata_source: str
    dataset_label: str
    dataset_notes: str
    raw_type: str
    format_source: str
    value_label_count: int
    missing_value_count: int


@dataclass(frozen=True)
class DataDictionary:
    """Resolved metadata prepared for a human-readable export."""

    rows: tuple[DataDictionaryRow, ...]
    dataset_label: str
    dataset_notes: str
    source_format: str
    source_file: str
    metadata_source: str
    provenance: str
    value_labels: tuple[tuple[str, str, str], ...]


def build_data_dictionary(dataset: Dataset) -> DataDictionary:
    """Build a deterministic dictionary without inferring new metadata."""

    dataset.sync_metadata()
    metadata = dataset.get_normalized_metadata()
    provenance = dataset.metadata_provenance or {}
    column_sources = provenance.get("columns", {})
    if not isinstance(column_sources, Mapping):
        column_sources = {}

    dataset_label = metadata.dataset_label or ""
    dataset_notes = _join_values(metadata.notes)
    source_format = metadata.source_format or dataset.source_format or ""
    source_file = str(dataset.source_file or "")
    dataset_source = _text(provenance.get("dataset"))
    rows: list[DataDictionaryRow] = []
    long_value_labels: list[tuple[str, str, str]] = []

    for index, dataframe_column in enumerate(dataset.dataframe.columns):
        name = str(dataframe_column)
        variable = metadata.get_variable(name)
        column = dataset.column_metadata.get(name)
        value_labels = variable.value_labels if variable is not None else {}
        missing_values = variable.missing_values if variable is not None else []
        missing_ranges = variable.missing_ranges if variable is not None else []
        combined_missing = [
            *missing_values,
            *(_format_range(item) for item in missing_ranges),
        ]
        rows.append(
            DataDictionaryRow(
                column_name=name,
                position=index + 1,
                storage_type=(
                    (variable.storage_type if variable is not None else None)
                    or (column.physical_type if column is not None else None)
                    or str(dataset.dataframe.iloc[:, index].dtype)
                ),
                logical_type=(
                    _text(column.logical_type) if column is not None else ""
                ),
                variable_label=(
                    _text(variable.label) if variable is not None else ""
                ),
                measurement_level=(
                    _text(variable.measure) if variable is not None else ""
                ),
                display_format=(
                    _text(variable.display_format) if variable is not None else ""
                ),
                missing_values=_join_values(combined_missing),
                value_labels=_format_value_labels(value_labels),
                metadata_source=_text(
                    column_sources.get(name, dataset_source or "primary_file")
                ),
                dataset_label=dataset_label,
                dataset_notes=dataset_notes,
                raw_type=(
                    _text(column.readstat_variable_type)
                    if column is not None
                    else ""
                ),
                format_source=(
                    _text(column.source_format)
                    if column is not None and column.source_format
                    else source_format
                ),
                value_label_count=len(value_labels),
                missing_value_count=len(missing_values) + len(missing_ranges),
            )
        )
        for value, label in sorted(
            value_labels.items(),
            key=lambda item: (type(item[0]).__name__, _text(item[0])),
        ):
            long_value_labels.append((name, _text(value), _text(label)))

    return DataDictionary(
        rows=tuple(rows),
        dataset_label=dataset_label,
        dataset_notes=dataset_notes,
        source_format=source_format,
        source_file=source_file,
        metadata_source=dataset_source,
        provenance=_stable_json(provenance),
        value_labels=tuple(long_value_labels),
    )


def export_data_dictionary(
    dataset: Dataset,
    input_filename: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write resolved metadata as CSV or XLSX with safe output handling."""

    input_path = Path(input_filename)
    target = Path(output_path)
    extension = target.suffix.lower()
    if extension not in DICTIONARY_EXTENSIONS:
        raise DataDictionaryError(
            f"Unsupported dictionary output format: {extension or '(none)'}",
            suggestion="Use .csv or .xlsx.",
        )
    if target.resolve(strict=False) == input_path.resolve(strict=False):
        raise OutputPathError(
            f"Data dictionary path would replace the input file: {target}",
            suggestion="Choose a different dictionary output path.",
        )

    parent = target.parent
    if parent != Path(".") and not parent.exists():
        raise OutputPathError(
            f"Parent folder does not exist: {parent}",
            suggestion="Create the folder first.",
        )
    if parent.exists() and not parent.is_dir():
        raise OutputPathError(
            f"Parent path is not a folder: {parent}",
            suggestion="Choose a dictionary path whose parent is a folder.",
        )
    if target.exists() and not overwrite:
        raise OutputPathError(
            f"Data dictionary already exists: {target}",
            suggestion=(
                "Use --overwrite-dictionary to replace it, or choose a "
                "different path."
            ),
        )
    dictionary = build_data_dictionary(dataset)
    if extension == ".csv":
        _write_csv(dictionary, target)
    else:
        _write_xlsx(dictionary, target)
    return target


def _write_csv(dictionary: DataDictionary, target: Path) -> None:
    try:
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=DICTIONARY_COLUMNS)
            writer.writeheader()
            writer.writerows(asdict(row) for row in dictionary.rows)
    except OSError as exc:
        raise DataDictionaryError(
            f"Could not write data dictionary: {target}. {exc}"
        ) from exc


def _write_xlsx(dictionary: DataDictionary, target: Path) -> None:
    rows = [asdict(row) for row in dictionary.rows]
    dictionary_frame = pd.DataFrame(rows, columns=DICTIONARY_COLUMNS)
    dataset_frame = pd.DataFrame(
        [
            {"field": "dataset_label", "value": dictionary.dataset_label},
            {"field": "dataset_notes", "value": dictionary.dataset_notes},
            {"field": "source_format", "value": dictionary.source_format},
            {"field": "source_file", "value": dictionary.source_file},
            {"field": "metadata_source", "value": dictionary.metadata_source},
            {"field": "provenance", "value": dictionary.provenance},
        ]
    )
    value_label_rows = [
        {"column_name": column, "value": value, "label": label}
        for column, value, label in dictionary.value_labels
    ]
    value_labels_frame = pd.DataFrame(
        value_label_rows,
        columns=("column_name", "value", "label"),
    )

    try:
        with pd.ExcelWriter(
            target,
            engine="xlsxwriter",
            engine_kwargs={
                "options": {
                    "strings_to_formulas": False,
                    "strings_to_urls": False,
                }
            },
        ) as workbook:
            dictionary_frame.to_excel(
                workbook,
                sheet_name="Dictionary",
                index=False,
            )
            dataset_frame.to_excel(workbook, sheet_name="Dataset", index=False)
            value_labels_frame.to_excel(
                workbook,
                sheet_name="Value Labels",
                index=False,
            )
    except (OSError, ValueError) as exc:
        raise DataDictionaryError(
            f"Could not write data dictionary: {target}. {exc}"
        ) from exc


def _format_value_labels(labels: Mapping[Any, Any]) -> str:
    entries = sorted(
        labels.items(),
        key=lambda item: (type(item[0]).__name__, _text(item[0])),
    )
    return "; ".join(f"{_text(value)} = {_text(label)}" for value, label in entries)


def _format_range(value: Mapping[str, Any]) -> str:
    low = value.get("low", value.get("lo"))
    high = value.get("high", value.get("hi"))
    return f"[{_text(low)}, {_text(high)}]"


def _join_values(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, (str, bytes)):
        return _text(values)
    try:
        items = list(values)
    except TypeError:
        items = [values]
    return "; ".join(_text(value) for value in items)


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=_text,
        )
    except (TypeError, ValueError):
        return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, set):
        return _stable_json(sorted(value, key=lambda item: _text(item)))
    if isinstance(value, (Mapping, list, tuple)):
        return _stable_json(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
