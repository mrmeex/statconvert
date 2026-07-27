"""Conservative format-level streaming feasibility declarations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class StreamingSupport(str, Enum):
    """Feasibility level for one chunked backend operation."""

    SUPPORTED_NOW = "supported_now"
    POSSIBLE = "possible_with_current_dependency"
    UNSUPPORTED = "unlikely_or_unsupported"
    NEEDS_PROOF = "unknown_needs_later_proof"


class StreamingSuitability(str, Enum):
    """Suitability for the first selective streaming conversions."""

    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


@dataclass(frozen=True)
class FormatStreamingCapability:
    """Internal audit record for one registered format."""

    extension: str
    chunked_read: StreamingSupport
    chunked_write: StreamingSupport
    safe_initial_use: StreamingSuitability
    notes: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "extension": self.extension,
            "chunked_read": self.chunked_read.value,
            "chunked_write": self.chunked_write.value,
            "safe_initial_use": self.safe_initial_use.value,
            "notes": self.notes,
        }


_POSSIBLE = StreamingSupport.POSSIBLE
_SUPPORTED = StreamingSupport.SUPPORTED_NOW
_UNSUPPORTED = StreamingSupport.UNSUPPORTED
_NEEDS_PROOF = StreamingSupport.NEEDS_PROOF
_YES = StreamingSuitability.YES
_PARTIAL = StreamingSuitability.PARTIAL
_NO = StreamingSuitability.NO

_CAPABILITIES = {
    ".csv": FormatStreamingCapability(
        ".csv",
        _SUPPORTED,
        _SUPPORTED,
        _YES,
        "pandas supports chunksize reads; CSV rows can be written incrementally.",
    ),
    ".json": FormatStreamingCapability(
        ".json",
        _UNSUPPORTED,
        _POSSIBLE,
        _NO,
        "A single JSON array is not a safe initial read target; bounded records "
        "writing is possible but needs transactional output handling.",
    ),
    ".jsonl": FormatStreamingCapability(
        ".jsonl",
        _SUPPORTED,
        _SUPPORTED,
        _YES,
        "pandas supports chunksize with lines=True; records append naturally.",
    ),
    ".ndjson": FormatStreamingCapability(
        ".ndjson",
        _SUPPORTED,
        _SUPPORTED,
        _YES,
        "Equivalent line-delimited behavior to JSONL.",
    ),
    ".parquet": FormatStreamingCapability(
        ".parquet",
        _POSSIBLE,
        _NEEDS_PROOF,
        _PARTIAL,
        "PyArrow exposes batch iteration and ParquetWriter; schema stability and "
        "embedded StatConvert metadata require proof.",
    ),
    ".feather": FormatStreamingCapability(
        ".feather",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "The current convenience API materializes a table and does not provide "
        "append-style Feather output.",
    ),
    ".xlsx": FormatStreamingCapability(
        ".xlsx",
        _NEEDS_PROOF,
        _NEEDS_PROOF,
        _NO,
        "Current pandas workbook paths are whole-table and container semantics add "
        "sheet-level state.",
    ),
    ".xls": FormatStreamingCapability(
        ".xls",
        _UNSUPPORTED,
        _UNSUPPORTED,
        _NO,
        "Current xlrd/xlwt integration is a legacy whole-sheet path.",
    ),
    ".ods": FormatStreamingCapability(
        ".ods",
        _UNSUPPORTED,
        _UNSUPPORTED,
        _NO,
        "Current odfpy implementation builds whole sheet tables.",
    ),
    ".sav": FormatStreamingCapability(
        ".sav",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "pyreadstat has a chunk helper, but metadata, offset behavior, and format "
        "coverage need proof; its writer is whole-DataFrame.",
    ),
    ".zsav": FormatStreamingCapability(
        ".zsav",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "Read-only in StatConvert; pyreadstat chunk behavior needs proof.",
    ),
    ".por": FormatStreamingCapability(
        ".por",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "Read-only in StatConvert; pyreadstat chunk behavior needs proof.",
    ),
    ".dta": FormatStreamingCapability(
        ".dta",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "Chunk-capable APIs exist in dependencies, but the current metadata-aware "
        "backend and writer are whole-DataFrame.",
    ),
    ".sas7bdat": FormatStreamingCapability(
        ".sas7bdat",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "Read-only in StatConvert; dependency chunk behavior needs proof.",
    ),
    ".xpt": FormatStreamingCapability(
        ".xpt",
        _NEEDS_PROOF,
        _UNSUPPORTED,
        _NO,
        "Dependency read chunking needs proof; the current writer is whole-DataFrame.",
    ),
    ".rds": FormatStreamingCapability(
        ".rds",
        _UNSUPPORTED,
        _UNSUPPORTED,
        _NO,
        "pyreadr returns complete objects and writes complete DataFrames.",
    ),
    ".rdata": FormatStreamingCapability(
        ".rdata",
        _UNSUPPORTED,
        _UNSUPPORTED,
        _NO,
        "Workspace object discovery/selection and pyreadr I/O are whole-object.",
    ),
    ".rda": FormatStreamingCapability(
        ".rda",
        _UNSUPPORTED,
        _UNSUPPORTED,
        _NO,
        "Workspace object discovery/selection and pyreadr I/O are whole-object.",
    ),
}


def get_streaming_capability(target: str | Path) -> FormatStreamingCapability:
    """Return the conservative audit record for an extension or filename."""

    value = str(target).lower().strip()
    is_literal_extension = (
        value.startswith(".")
        and "/" not in value
        and "\\" not in value
        and value.count(".") == 1
    )
    extension = value if is_literal_extension else Path(value).suffix
    if not extension:
        extension = f".{value}"
    try:
        return _CAPABILITIES[extension]
    except KeyError:
        raise ValueError(f"Unsupported streaming format: {extension}") from None


def list_streaming_capabilities() -> dict[str, FormatStreamingCapability]:
    """Return all audit records in deterministic extension order."""

    return {
        extension: _CAPABILITIES[extension]
        for extension in sorted(_CAPABILITIES)
    }
