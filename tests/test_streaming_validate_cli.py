import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


@pytest.mark.parametrize("extension", [".csv", ".jsonl", ".ndjson"])
def test_validate_stream_supports_approved_inputs(
    tmp_path: Path,
    extension: str,
) -> None:
    source = tmp_path / f"records{extension}"
    frame = pd.DataFrame({"id": [1, 2, 2], "status": ["ok", "bad", "bad"]})
    _write_records(frame, source)
    contract = _write_contract(tmp_path / "contract.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--stream",
            "--chunk-size",
            "2",
        ],
    )

    assert result.exit_code == 1
    assert "Streaming enabled: yes" in result.output
    assert "Chunk size: 2" in result.output
    assert "Chunks processed: 2" in result.output
    assert "Rows processed: 3" in result.output
    assert "Schema contract validation: failed" in result.output
    assert "rule_allowed_values_violation" in result.output
    assert "rule_uniqueness_violation" in result.output


def test_validate_stream_json_is_parseable_and_additive(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1, 1], "status": ["bad", "bad"]}), source)
    contract = _write_contract(tmp_path / "contract.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--stream",
            "--chunk-size",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["validation"] == []
    assert payload["streaming"] == {
        "enabled": True,
        "chunk_size": 1,
        "chunks_processed": 2,
        "rows_processed": 2,
        "rules_checked": 2,
        "columns_checked": 2,
    }
    assert payload["schema_contract"]["status"] == "failed"
    issue = payload["schema_contract"]["issues"][0]
    assert {
        "severity",
        "code",
        "expected",
        "actual",
        "affected_rows",
        "sample_values",
        "source_rule",
    } <= issue.keys()


def test_validate_stream_requires_contract(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1]}), source)

    result = runner.invoke(app, ["validate", str(source), "--stream"])

    assert result.exit_code == 1
    assert "requires --schema-contract" in result.output
    assert "full in-memory validation" in result.output


def test_validate_chunk_size_without_stream_fails(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1]}), source)

    result = runner.invoke(
        app,
        ["validate", str(source), "--chunk-size", "2"],
    )

    assert result.exit_code == 1
    assert "--chunk-size requires --stream" in result.output


@pytest.mark.parametrize("value", ["0", "-1"])
def test_validate_stream_rejects_invalid_chunk_size(
    tmp_path: Path,
    value: str,
) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1]}), source)
    contract = _write_contract(tmp_path / "contract.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--stream",
            "--chunk-size",
            value,
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value for '--chunk-size'" in result.output


@pytest.mark.parametrize(
    ("extension", "message"),
    [
        (".json", "JSON array files"),
        (".sav", "only CSV, JSONL, and NDJSON"),
        (".xlsx", "only CSV, JSONL, and NDJSON"),
    ],
)
def test_validate_stream_rejects_unsupported_formats(
    tmp_path: Path,
    extension: str,
    message: str,
) -> None:
    source = tmp_path / f"records{extension}"
    source.write_bytes(b"placeholder")
    contract = _write_contract(tmp_path / "contract.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--stream",
        ],
    )

    normalized = " ".join(result.output.split())
    assert result.exit_code == 1
    if extension == ".json":
        assert message in normalized
    else:
        assert "Streaming validation" in normalized
    assert "without" in normalized.lower()
    assert "--stream" in normalized


def test_validate_stream_preserves_warning_strict_exit_policy(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1], "status": ["bad"]}), source)
    contract = tmp_path / "warning.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true

[[rules]]
name = "known_status"
type = "allowed_values"
column = "status"
values = ["ok"]
severity = "warning"
""".lstrip(),
        encoding="utf-8",
    )
    command = [
        "validate",
        str(source),
        "--schema-contract",
        str(contract),
        "--stream",
    ]

    warning = runner.invoke(app, command)
    strict = runner.invoke(app, [*command, "--strict"])

    assert warning.exit_code == 0
    assert "passed with warnings" in warning.output
    assert strict.exit_code == 1
    assert "Validation status: failed" in strict.output


def test_validate_non_streaming_json_shape_remains_list(tmp_path: Path) -> None:
    source = tmp_path / "records.csv"
    _write_records(pd.DataFrame({"id": [1]}), source)

    result = runner.invoke(app, ["validate", str(source), "--json"])

    assert result.exit_code == 0
    assert isinstance(json.loads(result.output), list)


@pytest.mark.parametrize("extension", [".csv", ".jsonl", ".ndjson"])
def test_exported_starter_contract_passes_streaming_validation(
    tmp_path: Path,
    extension: str,
) -> None:
    source = tmp_path / f"records{extension}"
    _write_records(
        pd.DataFrame({"id": [1, 2, 3], "status": ["ok", "ok", "ok"]}),
        source,
    )
    contract = tmp_path / "starter.toml"

    exported = runner.invoke(
        app,
        [
            "schema",
            str(source),
            "--export-contract",
            str(contract),
        ],
    )
    validated = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--stream",
            "--chunk-size",
            "2",
        ],
    )

    assert exported.exit_code == 0, exported.output
    assert validated.exit_code == 0, validated.output
    assert "Schema contract validation: passed" in validated.output


@pytest.mark.parametrize(
    "command",
    ["report", "transform", "compare", "collect", "schema"],
)
def test_validate_streaming_options_do_not_leak(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--stream" not in result.output
    assert "--chunk-size" not in result.output


def _write_contract(path: Path) -> Path:
    path.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false

[[columns]]
name = "id"

[[columns]]
name = "status"

[[rules]]
name = "known_status"
type = "allowed_values"
column = "status"
values = ["ok"]

[[rules]]
name = "unique_id"
type = "unique"
columns = ["id"]
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _write_records(frame: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_json(path, orient="records", lines=True)
