from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from statconvert.batch.exceptions import BatchError
from statconvert.output_names import sanitize_output_name


TRUE_VALUES = {"true", "yes", "1", "y"}
FALSE_VALUES = {"false", "no", "0", "n", ""}


@dataclass(frozen=True)
class ObjectManifestRow:
    """One parsed object-manifest row."""

    row_number: int
    include: bool
    input_file: str
    input_object: str | None
    output_name: str | None
    object_supported: bool | None
    file_supported: bool | None
    message: str | None
    raw: dict[str, str]


@dataclass(frozen=True)
class ObjectManifest:
    """Parsed object manifest including skipped rows."""

    path: Path
    rows: tuple[ObjectManifestRow, ...]

    @property
    def included_rows(self) -> list[ObjectManifestRow]:
        return [row for row in self.rows if row.include]


def read_object_manifest(
    path: str | Path,
    *,
    error_label: str = "Object manifest",
    validate_output_names: bool = True,
) -> ObjectManifest:
    """Read and validate a full discovery CSV or minimal manual manifest."""

    manifest_path = Path(path)
    if not manifest_path.exists():
        raise BatchError(f"{error_label} file does not exist: {manifest_path}")
    if not manifest_path.is_file():
        raise BatchError(f"{error_label} is not a file: {manifest_path}")

    try:
        with manifest_path.open(encoding="utf-8-sig", newline="") as manifest_file:
            reader = csv.DictReader(manifest_file)
            if reader.fieldnames is None:
                raise BatchError(
                    f"{error_label} is missing required column: input_file"
                )
            fieldnames = [name.strip() for name in reader.fieldnames]
            if "input_file" not in fieldnames:
                raise BatchError(
                    f"{error_label} is missing required column: input_file"
                )
            rows = tuple(
                _parse_row(
                    row_number,
                    _normalize_raw(raw),
                    error_label=error_label,
                    validate_output_names=validate_output_names,
                )
                for row_number, raw in enumerate(reader, start=2)
            )
    except BatchError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise BatchError(
            f"Unable to read {error_label.lower()} '{manifest_path}': {exc}"
        ) from None

    return ObjectManifest(path=manifest_path, rows=rows)


def validate_output_name(value: str, *, row_number: int) -> str:
    """Require a user-provided output base name to already be filesystem-safe."""

    name = value.strip()
    if not name or name in {".", ".."}:
        raise BatchError(
            f"Object manifest row {row_number} has an unsafe output_name: {value}"
        )
    if Path(name).name != name or sanitize_output_name(name, fallback="") != name:
        raise BatchError(
            f"Object manifest row {row_number} has an unsafe output_name: {value}"
        )
    return name


def _parse_row(
    row_number: int,
    raw: dict[str, str],
    *,
    error_label: str,
    validate_output_names: bool,
) -> ObjectManifestRow:
    include = _parse_include(
        raw.get("include"),
        row_number=row_number,
        error_label=error_label,
    )
    input_file = raw.get("input_file", "").strip()
    if not include:
        return ObjectManifestRow(
            row_number=row_number,
            include=False,
            input_file=input_file,
            input_object=_optional_text(raw.get("input_object")),
            output_name=_optional_text(raw.get("output_name")),
            object_supported=None,
            file_supported=None,
            message=_optional_text(raw.get("message")),
            raw=raw,
        )

    if not input_file:
        raise BatchError(
            f"{error_label} row {row_number} is included but input_file is blank."
        )

    object_supported = _parse_optional_bool(
        raw.get("object_supported"),
        field="object_supported",
        row_number=row_number,
        error_label=error_label,
    )
    file_supported = _parse_optional_bool(
        raw.get("file_supported"),
        field="file_supported",
        row_number=row_number,
        error_label=error_label,
    )
    message = _optional_text(raw.get("message"))
    if object_supported is False:
        raise BatchError(
            _unsupported_message(
                row_number,
                "object_supported",
                message,
                error_label=error_label,
            )
        )
    if file_supported is False:
        raise BatchError(
            _unsupported_message(
                row_number,
                "file_supported",
                message,
                error_label=error_label,
            )
        )

    output_name = _optional_text(raw.get("output_name"))
    if output_name is not None and validate_output_names:
        output_name = validate_output_name(output_name, row_number=row_number)

    return ObjectManifestRow(
        row_number=row_number,
        include=True,
        input_file=input_file,
        input_object=_optional_text(raw.get("input_object")),
        output_name=output_name,
        object_supported=object_supported,
        file_supported=file_supported,
        message=message,
        raw=raw,
    )


def _parse_include(
    value: str | None,
    *,
    row_number: int,
    error_label: str,
) -> bool:
    if value is None:
        return True
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise BatchError(
        f"{error_label} row {row_number} has an invalid include value: "
        f"{value.strip()}"
    )


def _parse_optional_bool(
    value: str | None,
    *,
    field: str,
    row_number: int,
    error_label: str,
) -> bool | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES - {""}:
        return False
    raise BatchError(
        f"{error_label} row {row_number} has an invalid {field} value: "
        f"{value.strip()}"
    )


def _normalize_raw(raw: dict[str | None, str | None]) -> dict[str, str]:
    return {
        str(key).strip(): "" if value is None else value
        for key, value in raw.items()
        if key is not None
    }


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _unsupported_message(
    row_number: int,
    field: str,
    message: str | None,
    *,
    error_label: str,
) -> str:
    detail = f": {message}" if message else "."
    if error_label == "Object manifest":
        return (
            f"{error_label} row {row_number} is included but "
            f"{field} is false{detail}"
        )
    return (
        f"{error_label} row {row_number} is included but\n"
        f"{field} is false{detail}"
    )
