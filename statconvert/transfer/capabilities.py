from __future__ import annotations

from dataclasses import dataclass, replace

from statconvert.backends.excel_constraints import XLS_MAX_COLUMNS, XLS_MAX_DATA_ROWS
from statconvert.registry import FORMAT_INFO, get_format_capabilities, normalize_extension

from .policies import TransferPlanningError


METADATA_FIELDS = (
    "dataset_label",
    "notes",
    "variable_label",
    "value_labels",
    "missing_values",
    "missing_ranges",
    "storage_type",
    "logical_type",
    "display_format",
    "display_width",
    "measurement_level",
    "role",
    "width",
    "decimals",
    "raw_metadata",
)


@dataclass(frozen=True)
class TargetTypeCapabilities:
    """Conservative extension-level type and metadata planning contract."""

    extension: str
    backend: str
    format_name: str
    writable: bool
    type_families: frozenset[str]
    verified_integer_widths: tuple[int, ...] = ()
    verified_unsigned: bool = False
    verified_float32: bool = False
    verified_timezone: bool = False
    metadata_mode: str = "unknown"
    native_metadata_fields: frozenset[str] = frozenset()
    embedded_metadata_fields: frozenset[str] = frozenset()
    sidecar_metadata_fields: frozenset[str] = frozenset()
    string_length_unit: str = "unicode_code_points"
    max_rows: int | None = None
    max_columns: int | None = None
    caveat: str = ""

    def supports_family(self, family: str) -> bool:
        return family in self.type_families


_SIDECAR_FIELDS = frozenset(METADATA_FIELDS)
_EMBEDDED_FIELDS = frozenset(METADATA_FIELDS)
_COMMON = frozenset({"integer", "float", "boolean", "string", "date", "datetime"})


def _capabilities() -> dict[str, TargetTypeCapabilities]:
    sidecar = {
        ".csv": ("csv", "CSV"),
        ".xlsx": ("excel", "Excel Workbook"),
        ".xls": ("excel", "Excel 97-2003 Workbook"),
        ".ods": ("ods", "OpenDocument Spreadsheet"),
        ".json": ("json", "JSON"),
        ".jsonl": ("json", "JSON Lines"),
        ".ndjson": ("json", "Newline-delimited JSON"),
        ".rds": ("r", "RDS"),
        ".rdata": ("r", "RData"),
        ".rda": ("r", "RData"),
    }
    result = {
        extension: TargetTypeCapabilities(
            extension=extension,
            backend=backend,
            format_name=name,
            writable=True,
            type_families=_COMMON | frozenset({"category"}),
            metadata_mode="sidecar",
            sidecar_metadata_fields=_SIDECAR_FIELDS,
            caveat="Primary-file type fidelity is format-specific; normalized metadata is sidecar-only.",
        )
        for extension, (backend, name) in sidecar.items()
    }
    result[".xls"] = replace(
        result[".xls"],
        max_rows=XLS_MAX_DATA_ROWS,
        max_columns=XLS_MAX_COLUMNS,
        caveat=(
            "Legacy BIFF has hard row/column limits; normalized metadata is sidecar-only."
        ),
    )
    for extension, name in ((".parquet", "Apache Parquet"), (".feather", "Apache Feather")):
        result[extension] = TargetTypeCapabilities(
            extension=extension,
            backend="arrow",
            format_name=name,
            writable=True,
            type_families=_COMMON | frozenset({"category"}),
            verified_integer_widths=(8, 16, 32, 64),
            verified_unsigned=True,
            verified_float32=True,
            verified_timezone=True,
            metadata_mode="embedded + sidecar",
            embedded_metadata_fields=_EMBEDDED_FIELDS,
            sidecar_metadata_fields=_SIDECAR_FIELDS,
            caveat="A sibling sidecar is canonical when both metadata copies exist.",
        )
    result[".sav"] = TargetTypeCapabilities(
        extension=".sav",
        backend="pyreadstat",
        format_name="SPSS SAV",
        writable=True,
        type_families=_COMMON | frozenset({"category"}),
        metadata_mode="native, limited",
        native_metadata_fields=frozenset({
            "dataset_label", "notes", "variable_label", "value_labels",
            "missing_values", "missing_ranges", "display_format", "measurement_level",
        }),
        caveat="Native metadata writeback is limited and no automatic sidecar is written.",
    )
    result[".dta"] = TargetTypeCapabilities(
        extension=".dta",
        backend="pyreadstat",
        format_name="Stata",
        writable=True,
        type_families=_COMMON | frozenset({"category"}),
        metadata_mode="native, limited",
        native_metadata_fields=frozenset({
            "dataset_label", "variable_label", "value_labels", "display_format",
        }),
        caveat="Native metadata writeback is limited and no automatic sidecar is written.",
    )
    result[".xpt"] = TargetTypeCapabilities(
        extension=".xpt",
        backend="pyreadstat",
        format_name="SAS XPORT",
        writable=True,
        type_families=frozenset({"integer", "float", "string", "date", "datetime"}),
        metadata_mode="native, limited",
        native_metadata_fields=frozenset({"dataset_label", "variable_label", "display_format"}),
        caveat="Value labels and user-missing definitions are not written natively.",
    )
    return result


TARGET_CAPABILITIES = _capabilities()


def resolve_target_capabilities(target: str) -> TargetTypeCapabilities:
    """Resolve a registered extension using the existing format naming convention."""

    extension = normalize_extension(target)
    if extension not in FORMAT_INFO:
        raise TransferPlanningError(
            f"Unsupported target format: {target}.",
            code="TRANSFER_TARGET_UNKNOWN",
            suggestion="Use a registered writable extension such as parquet, csv, xlsx, sav, dta, or xpt.",
        )
    registry_capability = get_format_capabilities(extension)
    if not registry_capability.can_write:
        info = FORMAT_INFO[extension]
        alternative = info.get("write_alternative")
        suggestion = f"Use {alternative} instead." if alternative else "Choose a writable target format."
        raise TransferPlanningError(
            f"Target format is not writable: {extension}.",
            code="TRANSFER_TARGET_UNWRITABLE",
            suggestion=suggestion,
        )
    capability = TARGET_CAPABILITIES.get(extension)
    if capability is None:
        raise TransferPlanningError(
            f"Target type capabilities are not verified: {extension}.",
            code="TRANSFER_TARGET_UNVERIFIED",
            suggestion="Choose a target with a reviewed transfer capability declaration.",
        )
    return capability
