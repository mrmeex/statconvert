from pathlib import Path

import pandas as pd
import pytest

from statconvert.contracts import load_contract, validate_contract
from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.streaming.errors import StreamingSchemaError
from statconvert.streaming.validation import (
    STREAMING_RULE_CLASSIFICATIONS,
    validate_streaming_contract,
)


def test_all_existing_named_rules_have_streaming_classifications() -> None:
    assert STREAMING_RULE_CLASSIFICATIONS == {
        "not_null": "chunk_local_bounded",
        "allowed_values": "chunk_local_bounded",
        "range": "chunk_local_bounded",
        "regex": "chunk_local_bounded",
        "length": "chunk_local_bounded",
        "row_count": "dataset_aggregate_bounded",
        "unique": "retained_key_state",
    }


def test_streaming_contract_matches_in_memory_rule_results(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    frame = pd.DataFrame(
        {
            "id": [1, 2, 2, 4, 5, 6, 6],
            "site": ["a", "a", "a", "b", "b", "b", "b"],
            "status": ["ok", "bad", "bad-2", "ok", "bad-3", "ok", "bad-4"],
            "age": [10, -1, 200, 20, 30, 40, 50],
            "email": ["a@x", "bad", "c@x", "d@x", "bad-2", "f@x", "g@x"],
            "code": ["AA", "B", "CCC", None, "TOOLONG", "DD", "EE"],
        }
    )
    frame.to_csv(source, index=False)
    contract_path = _write_full_contract(tmp_path / "contract.toml")

    streamed = validate_streaming_contract(source, contract_path, chunk_size=2)
    expected = validate_contract(Dataset(frame), load_contract(contract_path))

    assert streamed.rows_processed == 7
    assert streamed.chunks_processed == 4
    assert streamed.rules_checked == 7
    assert streamed.columns_checked == 6
    actual_by_code = {
        (issue.code, issue.source_rule): issue
        for issue in streamed.contract_validation.issues
    }
    expected_by_code = {
        (issue.code, issue.source_rule): issue
        for issue in expected.issues
    }
    assert actual_by_code.keys() == expected_by_code.keys()
    for key, issue in actual_by_code.items():
        reference = expected_by_code[key]
        assert issue.severity == reference.severity
        assert issue.affected_rows == reference.affected_rows
        assert issue.actual == reference.actual
        assert len(issue.sample_values) <= 5


def test_streaming_contract_reports_structural_and_missing_rule_columns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.csv"
    pd.DataFrame({"b": [1], "a": [2], "extra": [3]}).to_csv(
        source,
        index=False,
    )
    contract = tmp_path / "contract.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
require_columns = true
allow_extra_columns = false
column_order = "prefix"

[[columns]]
name = "a"

    [[columns]]
    name = "b"

    [[columns]]
    name = "c"

[[rules]]
name = "missing_rule_column"
type = "not_null"
column = "missing"
""".lstrip(),
        encoding="utf-8",
    )

    result = validate_streaming_contract(source, contract, chunk_size=1)

    codes = {issue.code for issue in result.contract_validation.issues}
    assert {
        "missing_column",
        "unexpected_column",
        "column_order_mismatch",
        "rule_missing_column",
    } <= codes


def test_streaming_uniqueness_counts_all_duplicate_rows_across_chunks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.csv"
    pd.DataFrame(
        {
            "id": [1, 2, 1, 1, 3],
            "site": ["a", "a", "a", "a", "b"],
        }
    ).to_csv(source, index=False)
    contract = tmp_path / "contract.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true

[[columns]]
name = "id"
unique = true

[[rules]]
name = "unique_site_id"
type = "unique"
columns = ["site", "id"]
severity = "warning"
""".lstrip(),
        encoding="utf-8",
    )

    result = validate_streaming_contract(source, contract, chunk_size=2)
    issues = {
        issue.code: issue
        for issue in result.contract_validation.issues
    }

    assert issues["uniqueness_violation"].affected_rows == 3
    assert issues["rule_uniqueness_violation"].affected_rows == 3
    assert issues["rule_uniqueness_violation"].severity == "warning"
    assert issues["rule_uniqueness_violation"].source_rule == "unique_site_id"


def test_streaming_validation_rejects_schema_drift(tmp_path: Path) -> None:
    source = tmp_path / "drift.jsonl"
    source.write_text('{"a": 1}\n{"a": 2, "b": 3}\n', encoding="utf-8")
    contract = _write_simple_contract(tmp_path / "contract.toml", "a")

    with pytest.raises(StreamingSchemaError, match="schema drift"):
        validate_streaming_contract(source, contract, chunk_size=1)


def test_streaming_validation_rejects_malformed_json_lines(tmp_path: Path) -> None:
    source = tmp_path / "broken.jsonl"
    source.write_text('{"a": 1}\nnot-json\n', encoding="utf-8")
    contract = _write_simple_contract(tmp_path / "contract.toml", "a")

    with pytest.raises(Exception, match="Failed reading chunked JSON Lines"):
        validate_streaming_contract(source, contract, chunk_size=1)


def test_streaming_validation_handles_header_only_and_empty_lines(
    tmp_path: Path,
) -> None:
    csv_source = tmp_path / "header.csv"
    csv_source.write_text("a,b\n", encoding="utf-8")
    csv_contract = _write_simple_contract(tmp_path / "csv.toml", "a", "b")
    json_source = tmp_path / "empty.jsonl"
    json_source.write_text("", encoding="utf-8")
    json_contract = tmp_path / "json.toml"
    json_contract.write_text(
        """
contract_version = 1
[dataset]
require_columns = false
allow_extra_columns = true

[[rules]]
name = "zero_rows"
type = "row_count"
max = 0
""".lstrip(),
        encoding="utf-8",
    )

    csv_result = validate_streaming_contract(csv_source, csv_contract, chunk_size=2)
    json_result = validate_streaming_contract(json_source, json_contract, chunk_size=2)

    assert (csv_result.chunks_processed, csv_result.rows_processed) == (1, 0)
    assert csv_result.contract_validation.valid
    assert (json_result.chunks_processed, json_result.rows_processed) == (1, 0)
    assert json_result.contract_validation.valid


def test_streaming_validation_uses_resolved_sidecar_logical_type(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.csv"
    frame = pd.DataFrame({"code": ["a", "b"]})
    frame.to_csv(source, index=False)
    Dataset(
        frame,
        column_metadata={
            "code": ColumnMetadata(name="code", logical_type="categorical"),
        },
    ).write_sidecar(source)
    contract = tmp_path / "contract.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false

[[columns]]
name = "code"
logical_type = "categorical"
""".lstrip(),
        encoding="utf-8",
    )

    result = validate_streaming_contract(source, contract, chunk_size=1)

    assert result.contract_validation.valid
    assert result.contract_validation.issues == ()


def _write_full_contract(path: Path) -> Path:
    path.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false
column_order = "exact"

[[columns]]
name = "id"
unique = true

[[columns]]
name = "site"

[[columns]]
name = "status"
allowed_values = ["ok"]

[[columns]]
name = "age"
min = 0
max = 120

[[columns]]
name = "email"
regex = "^[^@]+@[^@]+$"

[[columns]]
name = "code"
nullable = false

[[rules]]
name = "known_status"
type = "allowed_values"
column = "status"
values = ["ok"]
severity = "warning"

[[rules]]
name = "valid_age"
type = "range"
column = "age"
min = 0
max = 120

[[rules]]
name = "valid_email"
type = "regex"
column = "email"
pattern = "^[^@]+@[^@]+$"

[[rules]]
name = "short_code"
type = "length"
column = "code"
min = 2
max = 4

[[rules]]
name = "code_required"
type = "not_null"
column = "code"

[[rules]]
name = "unique_site_id"
type = "unique"
columns = ["site", "id"]

[[rules]]
name = "expected_rows"
type = "row_count"
min = 8
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _write_simple_contract(path: Path, *columns: str) -> Path:
    definitions = "\n".join(
        f'[[columns]]\nname = "{column}"\n'
        for column in columns
    )
    path.write_text(
        "contract_version = 1\n[dataset]\nallow_extra_columns = false\n\n"
        + definitions,
        encoding="utf-8",
    )
    return path
