from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.metadata.comparison import compare_metadata


runner = CliRunner()


def _dataset(label: str, *, missing_range: int = 99) -> Dataset:
    metadata = DatasetMetadata(dataset_label=label, notes=["Reviewed"])
    metadata.add_variable(VariableMetadata(
        name="status", label="Status", value_labels={1: "Active"},
        missing_ranges=[{"lo": missing_range, "hi": missing_range}],
        storage_type="int64", display_format="F1", measure="nominal",
    ))
    return Dataset(
        pd.DataFrame({"status": [1]}),
        normalized_metadata=metadata,
        column_metadata={"status": ColumnMetadata(name="status", logical_type="integer")},
    )


def test_metadata_diff_compares_dataset_and_missing_range_metadata_only():
    result = compare_metadata(_dataset("Left"), _dataset("Right", missing_range=98))

    assert not result.same_metadata
    assert {(change.column, change.field) for change in result.changes} >= {
        (None, "dataset_label"), ("status", "missing_ranges"),
    }
    assert all(change.field != "values" for change in result.changes)
    assert result.summary["dataset_label"] == 1
    assert result.left_provenance["dataset"] == "primary_file"


def test_metadata_diff_compares_notes_storage_display_and_measurement():
    left = _dataset("Same")
    right = _dataset("Same")
    right.normalized_metadata.notes = ["Changed"]
    variable = right.normalized_metadata.get_variable("status")
    variable.storage_type = "float64"
    variable.display_format = "F8.2"
    variable.measure = "scale"

    result = compare_metadata(left, right)

    assert {change.field for change in result.changes} >= {
        "notes", "storage_type", "display_format", "measurement_level",
    }


def test_metadata_diff_ignores_different_data_values_when_metadata_matches():
    left = _dataset("Same")
    right = _dataset("Same")
    right.dataframe.loc[0, "status"] = 999

    assert compare_metadata(left, right).same_metadata


def test_metadata_diff_preserves_value_label_key_types():
    left = _dataset("Same")
    right = _dataset("Same")
    left.normalized_metadata.get_variable("status").value_labels = {1: "Yes"}
    right.normalized_metadata.get_variable("status").value_labels = {True: "Yes"}

    result = compare_metadata(left, right)

    assert any(change.field == "value_labels" for change in result.changes)


def test_metadata_diff_cli_json_strict_and_report(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"status": [1]}).to_csv(left, index=False)
    pd.DataFrame({"status": [2]}).to_csv(right, index=False)
    sidecar = Dataset.sidecar_path(right)
    payload = {
        "sidecar_version": 3,
        "dataset_metadata": {"dataset_label": "Right", "notes": [], "raw_metadata": {}},
        "columns": [{"name": "status", "label": "Changed"}],
    }
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "diff.json"

    result = runner.invoke(app, [
        "metadata-diff", str(left), str(right), "--json", "--strict", "--report", str(report),
    ])

    assert result.exit_code == 1
    assert json.loads(result.output)["same_metadata"] is False
    assert json.loads(report.read_text(encoding="utf-8"))["total_changes"] >= 1


def test_metadata_diff_cli_human_output(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"status": [1]}).to_csv(left, index=False)
    pd.DataFrame({"status": [1]}).to_csv(right, index=False)

    result = runner.invoke(app, ["metadata-diff", str(left), str(right)])

    assert result.exit_code == 0
    assert "Metadata Diff" in result.output
    assert "Same metadata" in result.output
