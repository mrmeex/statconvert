from __future__ import annotations

import json

import pandas as pd
import pyreadstat
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.metadata.diagnostics import build_metadata_diagnostics
from statconvert.metadata.sidecar import dataset_to_payload
from statconvert.serialization import to_json_text
from statconvert.registry import read_dataset


runner = CliRunner()


def _dataset(source) -> Dataset:
    metadata = DatasetMetadata(dataset_label="Survey")
    metadata.add_variable(VariableMetadata(
        name="status", label="Status", value_labels={1: "Active", 3: "Unused"},
        missing_ranges=[{"lo": 90, "hi": 99}], storage_type="int64",
    ))
    return Dataset(
        pd.DataFrame({"status": [1, 2]}),
        source_format="csv",
        source_file=str(source),
        normalized_metadata=metadata,
    )


def test_diagnostics_reports_coverage_and_unused_labels(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1, 2]}).to_csv(source, index=False)
    result = build_metadata_diagnostics(_dataset(source), source)

    assert result.valid
    assert result.coverage.columns_with_labels == 1
    assert result.coverage.columns_with_missing_ranges == 1
    assert {issue.code for issue in result.issues} >= {
        "metadata_unused_value_label", "metadata_missing_range_present",
    }
    assert json.loads(to_json_text(result))["coverage"]["notes_count"] == 0


def test_sidecar_validation_diagnoses_schema_problems_without_writing(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    sidecar = tmp_path / "metadata.json"
    payload = dataset_to_payload(_dataset(source))
    payload["future"] = True
    payload["columns"][0]["future_column"] = True
    payload["columns"][0]["name"] = "renamed"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    before = sidecar.read_bytes()

    result = build_metadata_diagnostics(
        _dataset(source), source, sidecar_input=sidecar, require_sidecar=True,
    )

    assert not result.valid
    assert {issue.code for issue in result.issues} >= {
        "sidecar_unknown_top_level_field", "sidecar_unknown_column_field",
        "sidecar_missing_data_column",
    }
    assert sidecar.read_bytes() == before
    assert not Dataset.sidecar_path(source).exists()


def test_metadata_validate_sidecar_json_and_strict_exit_codes(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1, 2]}).to_csv(source, index=False)
    sidecar = tmp_path / "metadata.json"
    payload = dataset_to_payload(_dataset(source))
    payload["future"] = True
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    normal = runner.invoke(app, [
        "metadata", str(source), "--validate-sidecar", "--sidecar-input", str(sidecar), "--json",
    ])
    strict = runner.invoke(app, [
        "metadata", str(source), "--validate-sidecar", "--sidecar-input", str(sidecar), "--strict",
    ])

    assert normal.exit_code == 0
    assert json.loads(normal.output)["source"]["sidecar_present"] is True
    assert strict.exit_code == 1


def test_missing_sidecar_is_a_clear_validation_error(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)

    result = runner.invoke(app, ["metadata", str(source), "--validate-sidecar", "--json"])

    assert result.exit_code == 1
    assert "sidecar_not_found" in result.output


def test_diagnose_human_and_json_are_read_only(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1, 2]}).to_csv(source, index=False)
    before = source.read_bytes()

    human = runner.invoke(app, ["metadata", str(source), "--diagnose"])
    machine = runner.invoke(app, ["metadata", str(source), "--diagnose", "--json"])

    assert human.exit_code == 0
    assert "Metadata Diagnostics" in human.output
    assert json.loads(machine.output)["valid"] is True
    assert source.read_bytes() == before
    assert not Dataset.sidecar_path(source).exists()


def test_validation_detects_malformed_unsupported_duplicate_and_partial(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1], "extra": [2]}).to_csv(source, index=False)
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    unsupported = tmp_path / "unsupported.json"
    payload = dataset_to_payload(_dataset(source))
    payload["sidecar_version"] = 999
    unsupported.write_text(json.dumps(payload), encoding="utf-8")
    duplicate = tmp_path / "duplicate.json"
    payload = dataset_to_payload(_dataset(source))
    payload["columns"].append(dict(payload["columns"][0]))
    duplicate.write_text(json.dumps(payload), encoding="utf-8")
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps(dataset_to_payload(_dataset(source))), encoding="utf-8")

    codes = {}
    for name, path in (("malformed", malformed), ("unsupported", unsupported), ("duplicate", duplicate), ("partial", partial)):
        candidate = _dataset(source)
        if name == "partial":
            candidate.dataframe["extra"] = 2
        result = build_metadata_diagnostics(
            candidate, source, sidecar_input=path, require_sidecar=True,
        )
        codes[name] = {issue.code for issue in result.issues}

    assert "sidecar_parse_error" in codes["malformed"]
    assert "sidecar_unsupported_version" in codes["unsupported"]
    assert "sidecar_duplicate_column" in codes["duplicate"]
    assert "sidecar_uncovered_data_column" in codes["partial"]


def test_validation_detects_typed_value_label_conflicts(tmp_path):
    source = tmp_path / "survey.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    sidecar = tmp_path / "typed.json"
    payload = dataset_to_payload(_dataset(source))
    payload["columns"][0]["value_label_items"] = [
        {"value": 1, "label": "One"},
        {"value": 1, "label": "Duplicate"},
        {"value": True, "label": "Boolean collision"},
        {"value": "1", "label": "String one"},
    ]
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    result = build_metadata_diagnostics(
        _dataset(source), source, sidecar_input=sidecar, require_sidecar=True,
    )

    assert "sidecar_duplicate_typed_value_label" in {
        issue.code for issue in result.issues
    }
    assert "sidecar_value_label_type_conflict" in {
        issue.code for issue in result.issues
    }


def test_diagnostics_reports_arrow_embedded_and_sidecar_precedence(tmp_path):
    source = tmp_path / "survey.parquet"
    ArrowBackend().write(_dataset(source), source)

    result = build_metadata_diagnostics(read_dataset(str(source)), source)

    assert result.source.embedded_metadata_present
    assert result.source.sidecar_present
    assert result.source.resolved_precedence == (
        "automatic_sidecar > embedded_arrow"
    )
    assert "metadata_embedded_payload_overridden" in {
        issue.code for issue in result.issues
    }


def test_diagnostics_supports_metadata_rich_statistical_source(tmp_path):
    source = tmp_path / "survey.sav"
    pyreadstat.write_sav(
        pd.DataFrame({"status": [1.0, 2.0]}),
        source,
        file_label="Survey",
        column_labels={"status": "Status"},
        variable_value_labels={"status": {1.0: "Active", 2.0: "Inactive"}},
    )

    result = build_metadata_diagnostics(read_dataset(str(source)), source)

    assert result.source.native_metadata_present
    assert result.coverage.columns_with_labels == 1
    assert result.coverage.columns_with_value_labels == 1


def test_container_sidecar_validation_requires_selected_object(tmp_path):
    source = tmp_path / "book.xlsx"
    with pd.ExcelWriter(source, engine="xlsxwriter") as workbook:
        pd.DataFrame({"status": [1]}).to_excel(workbook, sheet_name="Data", index=False)
        pd.DataFrame({"other": [2]}).to_excel(workbook, sheet_name="Other", index=False)
    sidecar = tmp_path / "metadata.json"
    sidecar.write_text(json.dumps(dataset_to_payload(_dataset(source))), encoding="utf-8")

    ambiguous = runner.invoke(app, [
        "metadata", str(source), "--validate-sidecar", "--sidecar-input", str(sidecar),
    ])
    selected = runner.invoke(app, [
        "metadata", str(source), "--object", "Data", "--validate-sidecar",
        "--sidecar-input", str(sidecar), "--json",
    ])

    assert ambiguous.exit_code == 1
    assert selected.exit_code == 0
    assert json.loads(selected.output)["source"]["object_name"] == "Data"
    assert json.loads(selected.output)["source"]["object_kind"] == "sheet"
