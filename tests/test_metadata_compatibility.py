from __future__ import annotations

from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.registry import list_formats


EXPECTED_FORMATS = {
    ".csv",
    ".dta",
    ".feather",
    ".json",
    ".jsonl",
    ".ndjson",
    ".ods",
    ".parquet",
    ".por",
    ".rda",
    ".rdata",
    ".rds",
    ".sas7bdat",
    ".sav",
    ".xls",
    ".xlsx",
    ".xpt",
    ".zsav",
}


def test_metadata_compatibility_inventory_covers_every_registered_format():
    assert set(list_formats()) == EXPECTED_FORMATS


def test_arrow_backend_claims_namespaced_statconvert_metadata():
    assert ArrowBackend.capabilities.supports_custom_metadata is True
