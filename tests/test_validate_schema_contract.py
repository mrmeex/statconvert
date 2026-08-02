from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.cli import app
from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


runner = CliRunner()


def test_exported_starter_contract_validates_source_dataset(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path)
    contract = tmp_path / "schema.toml"

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
        ],
    )

    assert exported.exit_code == 0
    assert validated.exit_code == 0
    assert "Validation Issues" in validated.output
    assert "Schema contract validation: passed" in validated.output


def test_validate_contract_reports_all_core_drift_rules(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drift.csv"
    pd.DataFrame(
        {
            "code": ["bad", None],
            "id": [1, 1],
            "score": [0, 11],
            "status": ["active", "other"],
            "extra": ["x", "y"],
        }
    ).to_csv(source, index=False)
    contract = tmp_path / "drift.toml"
    contract.write_text(
        """
contract_version = 1

[dataset]
require_columns = true
allow_extra_columns = false
column_order = "exact"

[[columns]]
name = "id"
storage_type = "string"
logical_type = "string"
unique = true

[[columns]]
name = "code"
nullable = false
regex = "^[A-Z]+$"

[[columns]]
name = "score"
min = 1
max = 10

[[columns]]
name = "status"
allowed_values = ["active"]

[[columns]]
name = "missing"
required = true
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    for code in (
        "missing_column",
        "unexpected_column",
        "column_order_mismatch",
        "storage_type_mismatch",
        "logical_type_mismatch",
        "nullable_violation",
        "uniqueness_violation",
        "allowed_values_violation",
        "range_violation",
        "regex_violation",
    ):
        assert code in result.output
    assert "Schema contract validation: failed" in result.output
    assert "Affected rows" in result.output


def test_missing_contract_file_fails_friendly(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "validate",
            str(_write_csv(tmp_path)),
            "--schema-contract",
            str(tmp_path / "missing.toml"),
        ],
    )

    assert result.exit_code == 1
    assert "Schema contract file does not exist" in result.output
    assert "Traceback" not in result.output


def test_invalid_contract_toml_fails_friendly(tmp_path: Path) -> None:
    contract = tmp_path / "invalid.toml"
    contract.write_text("[dataset\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "validate",
            str(_write_csv(tmp_path)),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    assert "Schema contract contains invalid TOML" in result.output
    assert "Traceback" not in result.output


def test_unsupported_contract_version_fails_friendly(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "future.toml"
    contract.write_text(
        "contract_version = 99\n[dataset]\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(_write_csv(tmp_path)),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    assert "unsupported contract_version 99" in result.output
    assert "Traceback" not in result.output


def test_contract_json_is_nested_and_parseable(tmp_path: Path) -> None:
    source = _write_csv(tmp_path)
    contract = tmp_path / "schema.toml"
    runner.invoke(
        app,
        [
            "schema",
            str(source),
            "--export-contract",
            str(contract),
        ],
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--json",
        ],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert isinstance(payload["validation"], list)
    assert payload["validation"][0]["code"] == "readable"
    assert payload["schema_contract"]["path"] == str(contract)
    assert payload["schema_contract"]["valid"] is True
    assert payload["schema_contract"]["issue_count"] == 0
    assert payload["schema_contract"]["error_count"] == 0
    assert payload["schema_contract"]["issues"] == []


def test_contract_json_includes_detailed_failure_fields(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path)
    contract = tmp_path / "missing.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true

[[columns]]
name = "missing"
required = true
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--json",
        ],
    )
    payload = json.loads(result.output)
    issue = payload["schema_contract"]["issues"][0]

    assert result.exit_code == 1
    assert issue == {
        "severity": "error",
        "code": "missing_column",
        "message": "Required column is missing: missing.",
        "column": "missing",
        "expected": "present",
        "actual": "missing",
        "affected_rows": None,
        "sample_values": [],
        "source_rule": "column.required",
    }


def test_validate_json_without_contract_keeps_existing_list_shape(
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        ["validate", str(_write_csv(tmp_path)), "--json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert isinstance(payload, list)
    assert payload[0]["code"] == "readable"


def test_existing_validation_remains_additive_with_contract(
    tmp_path: Path,
) -> None:
    source = tmp_path / "duplicates.csv"
    pd.DataFrame({"id": [1, 1]}).to_csv(source, index=False)
    contract = tmp_path / "schema.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false
[[columns]]
name = "id"
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 0
    assert "duplicate_rows" in result.output
    assert "Schema contract validation: passed" in result.output


def test_selected_workbook_object_validates_contract(
    tmp_path: Path,
) -> None:
    workbook = _write_workbook(tmp_path)
    contract = tmp_path / "data.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false
[[columns]]
name = "DataId"
storage_type = "int64"
nullable = false
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(workbook),
            "--object",
            "Data",
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 0
    assert "Schema contract validation: passed" in result.output


def test_ambiguous_workbook_contract_validation_fails_friendly(
    tmp_path: Path,
) -> None:
    workbook = _write_workbook(tmp_path)
    contract = tmp_path / "schema.toml"
    contract.write_text(
        "contract_version = 1\n[dataset]\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(workbook),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    assert "multiple sheets" in result.output


def test_csv_sidecar_metadata_satisfies_contract_types(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path)
    _resolved_dataset().write_sidecar(source)
    contract = _write_resolved_contract(tmp_path / "sidecar.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 0
    assert "Schema contract validation: passed" in result.output


def test_embedded_parquet_metadata_satisfies_contract_types(
    tmp_path: Path,
) -> None:
    source = tmp_path / "embedded.parquet"
    ArrowBackend().write(_resolved_dataset(), source)
    Dataset.sidecar_path(source).unlink()
    contract = _write_resolved_contract(tmp_path / "embedded.toml")

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 0
    assert "Schema contract validation: passed" in result.output


def test_sidecar_wins_over_embedded_metadata_for_contract_types(
    tmp_path: Path,
) -> None:
    source = tmp_path / "precedence.parquet"
    ArrowBackend().write(_resolved_dataset(), source)
    sidecar = Dataset.sidecar_path(source)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["columns"][0]["physical_type"] = "int16"
    payload["columns"][0]["logical_type"] = "sidecar_identifier"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    contract = tmp_path / "precedence.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false

[[columns]]
name = "id"
storage_type = "int16"
logical_type = "sidecar_identifier"
nullable = false

[[columns]]
name = "status"
storage_type = "string"
logical_type = "string"
nullable = false
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 0
    assert "Schema contract validation: passed" in result.output


def test_validate_help_owns_schema_contract_option() -> None:
    validate_help = runner.invoke(app, ["validate", "--help"])
    schema_help = runner.invoke(app, ["schema", "--help"])
    config_help = runner.invoke(app, ["config", "--help"])

    assert validate_help.exit_code == 0
    assert "--schema-contract" in validate_help.output
    assert "--schema-contract" not in schema_help.output
    assert "--schema-contract" not in config_help.output


def _write_csv(tmp_path: Path) -> Path:
    source = tmp_path / "people.csv"
    pd.DataFrame(
        {
            "id": [1, 2],
            "status": ["active", "inactive"],
        }
    ).to_csv(source, index=False)
    return source


def _write_workbook(tmp_path: Path) -> Path:
    workbook = tmp_path / "book.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame({"DataId": [1]}).to_excel(
            writer,
            sheet_name="Data",
            index=False,
        )
        pd.DataFrame({"LookupCode": ["A"]}).to_excel(
            writer,
            sheet_name="Lookup",
            index=False,
        )
    return workbook


def _write_resolved_contract(path: Path) -> Path:
    path.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false

[[columns]]
name = "id"
storage_type = "int32"
logical_type = "identifier"
nullable = false

[[columns]]
name = "status"
storage_type = "string"
logical_type = "string"
nullable = false
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _resolved_dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
    )
    metadata.add_variable(
        VariableMetadata(name="id", storage_type="int32")
    )
    metadata.add_variable(
        VariableMetadata(name="status", storage_type="string")
    )
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "id": [1, 2],
                "status": ["active", "inactive"],
            }
        ),
        source_format="sav",
        normalized_metadata=metadata,
        column_metadata={
            "id": ColumnMetadata(
                name="id",
                physical_type="int32",
                logical_type="identifier",
            ),
            "status": ColumnMetadata(
                name="status",
                physical_type="string",
                logical_type="string",
            ),
        },
    )
