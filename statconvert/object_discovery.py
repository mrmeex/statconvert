from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from statconvert.batch.exceptions import BatchError
from statconvert.batch.planning import discover_input_files
from statconvert.output_paths import validate_output_file_path
from statconvert.output_names import sanitize_output_name
from statconvert.registry import (
    can_read_format,
    format_supports_objects,
    list_dataset_objects,
    supported_extensions,
)
from statconvert.serialization import make_json_safe


DISCOVERY_COLUMNS = (
    "include",
    "input_file",
    "input_relative_path",
    "input_object",
    "output_name",
    "file_format",
    "file_supported",
    "object_index",
    "object_name",
    "object_kind",
    "object_supported",
    "rows",
    "columns",
    "message",
)


@dataclass(frozen=True)
class ObjectDiscoveryRow:
    """One editable, manifest-ready object discovery record."""

    include: bool
    input_file: str
    input_relative_path: str
    input_object: str | None
    output_name: str | None
    file_format: str | None
    file_supported: bool
    object_index: int | None
    object_name: str | None
    object_kind: str | None
    object_supported: bool
    rows: int | None
    columns: int | None
    message: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return fields in the stable report column order."""

        values = asdict(self)
        return {column: values[column] for column in DISCOVERY_COLUMNS}


@dataclass(frozen=True)
class ObjectDiscoveryFile:
    """Group discovery rows belonging to one input file."""

    input_file: str
    input_relative_path: str
    file_format: str | None
    file_supported: bool
    objects: tuple[ObjectDiscoveryRow, ...]

    def to_json_dict(self) -> dict[str, Any]:
        object_fields = tuple(
            column
            for column in DISCOVERY_COLUMNS
            if column
            not in {
                "input_file",
                "input_relative_path",
                "file_format",
                "file_supported",
            }
        )
        return {
            "input_file": self.input_file,
            "input_relative_path": self.input_relative_path,
            "file_format": self.file_format,
            "file_supported": self.file_supported,
            "objects": [
                {field: row.to_dict()[field] for field in object_fields}
                for row in self.objects
            ],
        }


@dataclass(frozen=True)
class ObjectDiscoveryReport:
    """Manifest-ready object discovery results for one file or directory."""

    input_path: str
    recursive: bool
    files: tuple[ObjectDiscoveryFile, ...]

    @property
    def rows(self) -> list[ObjectDiscoveryRow]:
        return [row for file_info in self.files for row in file_info.objects]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "recursive": self.recursive,
            "files": [file_info.to_json_dict() for file_info in self.files],
        }


def build_object_discovery_report(
    input_path: str | Path,
    *,
    recursive: bool = False,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_unsupported: bool = False,
    excluded_file: str | Path | None = None,
) -> ObjectDiscoveryReport:
    """Inspect one file or a folder without converting any datasets."""

    root = Path(input_path)
    input_is_file = root.is_file()
    files = discover_input_files(
        root,
        recursive=recursive,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
    )
    if excluded_file is not None:
        excluded_key = _path_key(Path(excluded_file))
        files = [path for path in files if _path_key(path) != excluded_key]

    discovered: list[ObjectDiscoveryFile] = []
    for path in files:
        file_info = _discover_file(
            path,
            root=root,
            input_is_file=input_is_file,
            include_unsupported=include_unsupported,
        )
        if file_info is not None:
            discovered.append(file_info)

    if not discovered:
        if files:
            raise BatchError("No supported input files were discovered.")
        raise BatchError("No input files were discovered.")

    return ObjectDiscoveryReport(
        input_path=str(root),
        recursive=recursive,
        files=tuple(discovered),
    )


def write_object_discovery_report(
    report: ObjectDiscoveryReport,
    output_path: str | Path,
    *,
    json_output: bool = False,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> Path:
    """Write a flat CSV or grouped JSON report using normal output safeguards."""

    path = Path(output_path)
    expected_suffix = ".json" if json_output else ".csv"
    if path.suffix.lower() != expected_suffix:
        raise ValueError(
            f"Object discovery {'JSON' if json_output else 'CSV'} output must use "
            f"a {expected_suffix} file extension."
        )
    path = validate_output_file_path(
        path,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )

    if json_output:
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(
                make_json_safe(report.to_json_dict()),
                output_file,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            output_file.write("\n")
    else:
        with path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=DISCOVERY_COLUMNS)
            writer.writeheader()
            writer.writerows(_csv_row(row) for row in report.rows)
    return path


def _discover_file(
    path: Path,
    *,
    root: Path,
    input_is_file: bool,
    include_unsupported: bool,
) -> ObjectDiscoveryFile | None:
    extension = path.suffix.lower()
    relative_path = Path(path.name) if input_is_file else path.relative_to(root)
    input_file = str(path) if input_is_file else relative_path.as_posix()
    input_relative_path = relative_path.as_posix()
    file_format = extension.lstrip(".") or None
    file_supported = extension in supported_extensions() and can_read_format(extension)

    if not file_supported:
        if not include_unsupported:
            return None
        row = ObjectDiscoveryRow(
            include=False,
            input_file=input_file,
            input_relative_path=input_relative_path,
            input_object=None,
            output_name=None,
            file_format=file_format,
            file_supported=False,
            object_index=None,
            object_name=None,
            object_kind=None,
            object_supported=False,
            rows=None,
            columns=None,
            message=f"Unsupported input file format: {extension or '<none>'}",
        )
        return _file_group(row)

    if not format_supports_objects(extension):
        row = ObjectDiscoveryRow(
            include=True,
            input_file=input_file,
            input_relative_path=input_relative_path,
            input_object=None,
            output_name=sanitize_output_name(path.stem, fallback="dataset"),
            file_format=file_format,
            file_supported=True,
            object_index=None,
            object_name=None,
            object_kind="dataset",
            object_supported=True,
            rows=None,
            columns=None,
            message=None,
        )
        return _file_group(row)

    try:
        objects = list_dataset_objects(path)
    except Exception as exc:
        row = ObjectDiscoveryRow(
            include=False,
            input_file=input_file,
            input_relative_path=input_relative_path,
            input_object=None,
            output_name=None,
            file_format=file_format,
            file_supported=True,
            object_index=None,
            object_name=None,
            object_kind=None,
            object_supported=False,
            rows=None,
            columns=None,
            message=str(exc),
        )
        return _file_group(row)

    rows = tuple(
        ObjectDiscoveryRow(
            include=info.supported,
            input_file=input_file,
            input_relative_path=input_relative_path,
            input_object=info.name,
            output_name=(
                sanitize_output_name(
                    f"{path.stem}__{info.name}",
                    fallback=f"{path.stem}__object",
                )
                if info.supported
                else None
            ),
            file_format=file_format,
            file_supported=True,
            object_index=info.index,
            object_name=info.name,
            object_kind=info.kind,
            object_supported=info.supported,
            rows=info.rows,
            columns=info.columns,
            message=info.message,
        )
        for info in objects
    )
    if not rows:
        rows = (
            ObjectDiscoveryRow(
                include=False,
                input_file=input_file,
                input_relative_path=input_relative_path,
                input_object=None,
                output_name=None,
                file_format=file_format,
                file_supported=True,
                object_index=None,
                object_name=None,
                object_kind=None,
                object_supported=False,
                rows=None,
                columns=None,
                message="No dataset objects were found.",
            ),
        )
    first = rows[0]
    return ObjectDiscoveryFile(
        input_file=first.input_file,
        input_relative_path=first.input_relative_path,
        file_format=first.file_format,
        file_supported=first.file_supported,
        objects=rows,
    )


def _file_group(row: ObjectDiscoveryRow) -> ObjectDiscoveryFile:
    return ObjectDiscoveryFile(
        input_file=row.input_file,
        input_relative_path=row.input_relative_path,
        file_format=row.file_format,
        file_supported=row.file_supported,
        objects=(row,),
    )


def _csv_row(row: ObjectDiscoveryRow) -> dict[str, Any]:
    return {
        key: "" if value is None else value
        for key, value in row.to_dict().items()
    }


def _path_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix().casefold()
