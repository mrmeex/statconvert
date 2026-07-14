from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.objects import DatasetObjectInfo
from statconvert.dataset import Dataset
from statconvert.exceptions import ObjectSelectionNotSupportedError

from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.excel_backend import ExcelBackend
from statconvert.backends.json_backend import JsonBackend
from statconvert.backends.ods_backend import ODSBackend
from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.backends.r_backend import RBackend


#
# Backend registry
#
# These are the actual conversion engines.
#
BACKENDS: dict[str, Backend] = {
    "arrow": ArrowBackend(),
    "csv": CSVBackend(),
    "excel": ExcelBackend(),
    "json": JsonBackend(),
    "ods": ODSBackend(),
    "pyreadstat": PyReadstatBackend(),
    "r": RBackend(),
}


#
# Supported file formats
#
# Extension -> format information
#
FORMAT_INFO = {
    ".csv": {
        "name": "CSV",
        "backend": "csv",
    },

    ".xlsx": {
        "name": "Excel Workbook",
        "backend": "excel",
        "is_container": True,
        "object_selection": True,
        "object_kind": "sheet",
        "supports_multiple_sheets": True,
        "supports_multiple_tables": False,
    },

    ".xls": {
        "name": "Excel 97-2003 Workbook",
        "backend": "excel",
        "can_read": find_spec("xlrd") is not None,
        "can_write": find_spec("xlwt") is not None,
        "is_container": True,
        "object_selection": True,
        "object_kind": "sheet",
        "supports_multiple_sheets": True,
        "supports_multiple_tables": False,
    },

    ".sav": {
        "name": "SPSS SAV",
        "backend": "pyreadstat",
    },

    ".zsav": {
        "name": "SPSS Compressed (ZSAV)",
        "backend": "pyreadstat",
        "can_write": False,
    },

    ".por": {
        "name": "SPSS Portable",
        "backend": "pyreadstat",
        "can_write": False,
    },

    ".dta": {
        "name": "Stata",
        "backend": "pyreadstat",
    },

    ".sas7bdat": {
        "name": "SAS Dataset",
        "backend": "pyreadstat",
        "can_write": False,
    },

    ".xpt": {
        "name": "SAS XPORT",
        "backend": "pyreadstat",
    },

    ".json": {
        "name": "JSON",
        "backend": "json",
    },

    ".ndjson": {
        "name": "Newline Delimited JSON",
        "backend": "json",
    },

    ".jsonl": {
        "name": "JSON Lines",
        "backend": "json",
    },

    ".parquet": {
        "name": "Apache Parquet",
        "backend": "arrow",
    },

    ".feather": {
        "name": "Apache Feather",
        "backend": "arrow",
    },

    ".rds": {
        "name": "RDS",
        "backend": "r",
        "is_container": False,
        "object_selection": False,
        "object_kind": None,
        "supports_multiple_sheets": False,
        "supports_multiple_tables": False,
    },

    ".rdata": {
        "name": "RData",
        "backend": "r",
        "is_container": True,
        "object_selection": True,
        "object_kind": "r_object",
        "supports_multiple_sheets": False,
        "supports_multiple_tables": True,
    },

    ".rda": {
        "name": "RData",
        "backend": "r",
        "is_container": True,
        "object_selection": True,
        "object_kind": "r_object",
        "supports_multiple_sheets": False,
        "supports_multiple_tables": True,
    },

    ".ods": {
        "name": "OpenDocument Spreadsheet",
        "backend": "ods",
        "is_container": True,
        "object_selection": True,
        "object_kind": "sheet",
        "supports_multiple_sheets": True,
        "supports_multiple_tables": False,
    },
}


def get_extension(filename: str) -> str:
    """
    Return the lowercase extension of a filename.
    """

    extension = Path(filename).suffix.lower()

    if extension not in FORMAT_INFO:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    return extension


def get_file_format(filename: str) -> str:
    """
    Return the human-readable file format.
    """

    extension = get_extension(filename)

    return FORMAT_INFO[extension]["name"]


def get_backend_name(filename: str) -> str:
    """
    Return the backend name for a file.
    """

    extension = get_extension(filename)

    return FORMAT_INFO[extension]["backend"]


def get_backend(
    backend_name: str
) -> Backend:
    """
    Return the backend instance.
    """

    if backend_name not in BACKENDS:
        raise ValueError(
            f"No backend installed: {backend_name}"
        )

    return BACKENDS[backend_name]


def get_backend_for_file(
    filename: str
) -> Backend:
    """
    Return the backend responsible for a file.
    """

    backend_name = get_backend_name(
        filename
    )

    return get_backend(
        backend_name
    )


def get_reader_for_file(filename: str) -> Backend:
    """Return the backend for a readable file format."""

    extension = get_extension(filename)
    capabilities = get_format_capabilities(extension)
    if not capabilities.can_read:
        raise ValueError(format_read_error(extension))
    return get_backend_for_file(filename)


def get_writer_for_file(filename: str) -> Backend:
    """Return the backend for a writable file format."""

    extension = get_extension(filename)
    capabilities = get_format_capabilities(extension)
    if not capabilities.can_write:
        raise ValueError(format_write_error(extension))
    return get_backend_for_file(filename)


def read_dataset(
    path: str | Path,
    *,
    object_selector: str | None = None,
) -> Dataset:
    """Read a dataset with an optional backend-neutral object selector."""

    filename = str(path)
    reader = get_reader_for_file(filename)
    if object_selector is None:
        return reader.read(filename)

    extension = get_extension(filename)
    if not format_supports_objects(extension):
        raise ObjectSelectionNotSupportedError(
            f"Object selection is not supported for {extension} files."
        )

    return reader.read_object(
        Path(path),
        object_selector,
    )


def list_dataset_objects(path: str | Path) -> list[DatasetObjectInfo]:
    """List dataset-like objects through the responsible backend."""

    input_path = Path(path)
    filename = str(input_path)
    extension = get_extension(filename)
    if not input_path.exists():
        raise ValueError(f"Input file does not exist: {filename}")
    if not format_supports_objects(extension):
        raise ObjectSelectionNotSupportedError(
            "This format does not expose multiple dataset objects."
        )

    reader = get_reader_for_file(filename)
    return reader.list_objects(input_path)


def list_formats() -> dict[str, dict[str, Any]]:
    """
    Return registered file formats.
    """

    return {
        extension: _format_info_with_capabilities(extension)
        for extension in sorted(
            FORMAT_INFO
        )
    }


def list_backends() -> dict[str, Backend]:
    """
    Return registered backend instances.
    """

    return {
        name: BACKENDS[name]
        for name in sorted(
            BACKENDS
        )
    }


def normalize_extension(
    value: str
) -> str:
    """
    Normalize an extension, bare extension, or filename.
    """

    target = value.lower().strip()

    if target.startswith(
        "."
    ):
        return target

    suffix = Path(
        target
    ).suffix

    if suffix:
        return suffix.lower()

    return f".{target}"


def resolve_format_info(
    target: str
) -> tuple[str, dict[str, Any]] | None:
    """
    Resolve a target to registered format information.
    """

    extension = normalize_extension(
        target
    )

    if extension not in FORMAT_INFO:
        return None

    return extension, _format_info_with_capabilities(extension)


def is_backend_name(
    target: str
) -> bool:
    """
    Return whether a target names a registered backend.
    """

    return target.lower().strip() in BACKENDS


def resolve_format_or_backend(
    target: str
) -> dict[str, Any]:
    """
    Resolve a target as either a backend name or a format extension.
    """

    backend_name = target.lower().strip()

    if is_backend_name(
        backend_name
    ):
        backend = get_backend(
            backend_name
        )

        return {
            "kind": "backend",
            "target": target,
            "backend_name": backend_name,
            "backend": backend,
            "capabilities": backend.capabilities,
        }

    format_result = resolve_format_info(
        target
    )

    if format_result:
        extension, info = format_result
        backend_name = info["backend"]
        backend = get_backend(
            backend_name
        )

        return {
            "kind": "format",
            "target": target,
            "extension": extension,
            "format_name": info["name"],
            "backend_name": backend_name,
            "backend": backend,
            "capabilities": get_format_capabilities(extension),
        }

    raise ValueError(
        f"Unsupported format or backend: {target}"
    )


def get_backend_capabilities(
    backend_name: str
) -> BackendCapabilities:
    """
    Return capability declarations for a backend.
    """

    return get_backend(
        backend_name
    ).capabilities


def get_backend_capabilities_for_file(
    filename: str
) -> BackendCapabilities:
    """
    Return capability declarations for the backend handling a file.
    """

    return get_format_capabilities(get_extension(filename))


def get_backend_capabilities_for_extension(
    extension: str
) -> BackendCapabilities:
    """
    Return capability declarations for a format extension.
    """

    format_result = resolve_format_info(
        extension
    )

    if not format_result:
        raise ValueError(
            f"Unsupported file format: {normalize_extension(extension)}"
        )

    normalized, _ = format_result
    return get_format_capabilities(normalized)


def get_format_capabilities(target: str) -> BackendCapabilities:
    """Return backend capabilities refined for one registered extension."""

    extension = normalize_extension(target)
    if extension not in FORMAT_INFO:
        raise ValueError(f"Unsupported file format: {extension}")

    info = FORMAT_INFO[extension]
    backend_capabilities = get_backend_capabilities(info["backend"])
    return replace(
        backend_capabilities,
        can_read=bool(info.get("can_read", backend_capabilities.can_read)),
        can_write=bool(info.get("can_write", backend_capabilities.can_write)),
        is_container=bool(info.get("is_container", backend_capabilities.is_container)),
        object_selection=bool(
            info.get("object_selection", backend_capabilities.object_selection)
        ),
        object_kind=info.get("object_kind", backend_capabilities.object_kind),
        supports_multiple_sheets=bool(
            info.get(
                "supports_multiple_sheets",
                backend_capabilities.supports_multiple_sheets,
            )
        ),
        supports_multiple_tables=bool(
            info.get(
                "supports_multiple_tables",
                backend_capabilities.supports_multiple_tables,
            )
        ),
    )


def format_supports_objects(extension: str) -> bool:
    """Return whether a registered extension supports object selection."""

    try:
        return get_format_capabilities(extension).object_selection
    except ValueError:
        return False


def format_object_kind(extension: str) -> str | None:
    """Return the dataset-object kind for a registered extension."""

    return get_format_capabilities(extension).object_kind


def can_read_format(target: str) -> bool:
    """Return whether a registered extension is readable."""

    try:
        return get_format_capabilities(target).can_read
    except ValueError:
        return False


def can_write_format(target: str) -> bool:
    """Return whether a registered extension is writable."""

    try:
        return get_format_capabilities(target).can_write
    except ValueError:
        return False


def format_read_error(target: str) -> str:
    """Return a friendly error for a registered non-readable format."""

    extension = normalize_extension(target)
    if extension == ".xls" and find_spec("xlrd") is None:
        return (
            "Reading .xls requires the 'xlrd' dependency. "
            "Reinstall StatConvert or convert the workbook to .xlsx."
        )
    return f"Reading {extension} is not supported."


def format_write_error(target: str) -> str:
    """Return a friendly error for a registered non-writable format."""

    extension = normalize_extension(target)
    if extension == ".xls" and find_spec("xlwt") is None:
        return (
            "Writing .xls requires dependency 'xlwt'. "
            "Reinstall StatConvert to restore format dependencies."
        )
    info = FORMAT_INFO.get(extension, {})
    alternative = info.get("write_alternative")
    if alternative:
        return f"Writing {extension} is not supported. Use {alternative} instead."
    if extension in FORMAT_INFO and get_format_capabilities(extension).can_read:
        return (
            f"Writing {extension} is not supported. "
            f"StatConvert can read {extension} files but cannot write them."
        )
    return f"Writing {extension} is not supported."


def _format_info_with_capabilities(extension: str) -> dict[str, Any]:
    """Return one format record with resolved read/write flags."""

    info = FORMAT_INFO[extension].copy()
    capabilities = get_format_capabilities(extension)
    info["can_read"] = capabilities.can_read
    info["can_write"] = capabilities.can_write
    info["is_container"] = capabilities.is_container
    info["object_selection"] = capabilities.object_selection
    info["object_kind"] = capabilities.object_kind
    info["supports_multiple_sheets"] = capabilities.supports_multiple_sheets
    info["supports_multiple_tables"] = capabilities.supports_multiple_tables
    return info


def list_backend_capabilities() -> dict[str, BackendCapabilities]:
    """
    Return capability declarations for all registered backends.
    """

    return {
        name: backend.capabilities
        for name, backend in BACKENDS.items()
    }


def supported_extensions():
    """
    Return all supported file extensions.
    """

    return sorted(FORMAT_INFO.keys())


def supported_formats():
    """
    Return all supported file format names.
    """

    return sorted(
        info["name"]
        for info in FORMAT_INFO.values()
    )
