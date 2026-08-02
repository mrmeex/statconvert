from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyreadstat
import pytest
from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.json_backend import JsonBackend
from statconvert.cli import app
from statconvert.converter import transform
from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataSidecarError
from statconvert.metadata import (
    DatasetMetadata,
    VariableMetadata,
    build_basic_metadata,
    metadata_from_sidecar,
)
from statconvert.transformations import (
    SelectColumnsTransformation,
    TransformationPipeline,
)
from statconvert.transformer import transform_file
from statconvert.metadata.sidecar import (
    dataset_to_payload,
    serialize_payload,
    validate_explicit_sidecar_target,
)


runner = CliRunner()


def _metadata_rich_dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label="Survey",
        notes=["Imported"],
        raw_metadata={"study": "Customer survey"},
    )
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Status",
            value_labels={1: "Active", 2: "Inactive"},
            missing_values=[-99],
            missing_ranges=[{"lo": -10, "hi": -1}],
            storage_type="int32",
            display_format="F8.0",
            display_width=10,
            measure="nominal",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="score",
            label="Score",
            storage_type="float64",
            measure="scale",
        )
    )
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "status": [1, 2],
                "score": [1.5, 2.5],
            }
        ),
        source_format="sav",
        normalized_metadata=metadata,
    )


def _write_sidecar_csv(path: Path) -> Path:
    CSVBackend().write(_metadata_rich_dataset(), path)
    return path


def test_standardized_sidecar_path_remains_stable_and_writes_version_3(tmp_path):
    path = _write_sidecar_csv(tmp_path / "survey.csv")
    sidecar = Dataset.sidecar_path(path)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert sidecar == Path(f"{path}.statconvert-metadata.json")
    assert payload["sidecar_version"] == 3
    assert payload["source_format"] == "sav"
    assert payload["dataset_metadata"] == {
        "dataset_label": "Survey",
        "notes": ["Imported"],
        "raw_metadata": {"study": "Customer survey"},
    }
    assert [column["name"] for column in payload["columns"]] == [
        "status",
        "score",
    ]


def test_sidecar_restores_metadata_without_changing_data_values(tmp_path):
    path = _write_sidecar_csv(tmp_path / "survey.csv")

    restored = CSVBackend().read(path)

    assert restored.dataframe.to_dict(orient="list") == {
        "status": [1, 2],
        "score": [1.5, 2.5],
    }
    assert restored.variable_labels() == {
        "status": "Status",
        "score": "Score",
    }
    assert restored.value_labels() == {
        "status": {1: "Active", 2: "Inactive"}
    }
    assert restored.get_normalized_metadata().dataset_label == "Survey"
    assert restored.get_normalized_metadata().notes == ["Imported"]
    assert restored.get_normalized_metadata().raw_metadata["study"] == (
        "Customer survey"
    )
    assert restored.metadata_provenance["dataset"] == "automatic_sidecar"


def test_version_2_sidecar_remains_readable(tmp_path):
    path = tmp_path / "legacy.csv"
    pd.DataFrame({"status": [1]}).to_csv(path, index=False)
    payload = dataset_to_payload(_metadata_rich_dataset())
    payload["sidecar_version"] = 2
    payload.pop("dataset_metadata")
    payload.pop("provenance")
    payload["columns"] = [
        column
        for column in payload["columns"]
        if column["name"] == "status"
    ]
    Dataset.sidecar_path(path).write_text(
        serialize_payload(payload),
        encoding="utf-8",
    )

    restored = CSVBackend().read(path)

    assert restored.variable_labels()["status"] == "Status"
    assert restored.get_normalized_metadata().dataset_label is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not valid JSON"),
        (
            '{"sidecar_version": 99, "columns": []}',
            "Unsupported metadata payload version 99",
        ),
        (
            '{"sidecar_version": 3, "dataset_metadata": {}}',
            "columns must be a list",
        ),
        (
            '{"sidecar_version": 3, "columns": []}',
            "dataset_metadata must be an object",
        ),
    ],
)
def test_invalid_sidecar_payloads_fail_cleanly(tmp_path, content, message):
    path = tmp_path / "invalid.csv"
    pd.DataFrame({"x": [1]}).to_csv(path, index=False)
    Dataset.sidecar_path(path).write_text(content, encoding="utf-8")

    with pytest.raises(MetadataSidecarError, match=message):
        CSVBackend().read(path)


def test_malformed_sidecar_is_a_friendly_cli_error(tmp_path):
    path = tmp_path / "invalid.csv"
    pd.DataFrame({"x": [1]}).to_csv(path, index=False)
    Dataset.sidecar_path(path).write_text("{", encoding="utf-8")

    result = runner.invoke(app, ["metadata", str(path)])

    assert result.exit_code == 1
    assert "Metadata payload is not valid JSON" in result.output
    assert "Traceback" not in result.output


def test_sidecar_serialization_is_deterministic():
    payload = dataset_to_payload(_metadata_rich_dataset())

    assert serialize_payload(payload) == serialize_payload(payload)
    assert serialize_payload(payload).endswith("\n")


def test_sidecar_rejects_metadata_for_missing_physical_columns(tmp_path):
    path = tmp_path / "mismatch.csv"
    pd.DataFrame({"actual": [1]}).to_csv(path, index=False)
    payload = dataset_to_payload(_metadata_rich_dataset())
    Dataset.sidecar_path(path).write_text(
        serialize_payload(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        MetadataSidecarError,
        match="Sidecar references columns not present",
    ):
        CSVBackend().read(path)


def test_future_explicit_flat_sidecar_requires_container_object_context():
    with pytest.raises(MetadataSidecarError, match="explicit object selector"):
        validate_explicit_sidecar_target(
            is_container=True,
            object_selector=None,
        )

    validate_explicit_sidecar_target(
        is_container=True,
        object_selector="Data",
    )
    validate_explicit_sidecar_target(
        is_container=False,
        object_selector=None,
    )


def test_sidecar_merge_is_deterministic_and_preserves_base_dataset_fields():
    dataframe = pd.DataFrame({"status": [1]})
    base = build_basic_metadata(
        dataframe,
        source_format="csv",
        source_backend="csv",
    )
    base.dataset_label = "Native base label"
    column_metadata = _metadata_rich_dataset().column_metadata

    merged = metadata_from_sidecar(base, column_metadata)

    assert merged.dataset_label == "Native base label"
    assert merged.get_variable("status").label == "Status"
    assert merged.get_variable("status").storage_type == "int32"


def test_info_and_metadata_commands_load_sidecar_automatically(
    tmp_path,
    monkeypatch,
):
    path = _write_sidecar_csv(tmp_path / "survey.csv")
    seen: dict[str, dict[str, str]] = {}

    monkeypatch.setattr(
        cli_module,
        "show_dataset_info",
        lambda dataset: seen.setdefault("info", dataset.variable_labels()),
    )
    monkeypatch.setattr(
        cli_module,
        "show_metadata_summary",
        lambda dataset: seen.setdefault("metadata", dataset.variable_labels()),
    )

    info_result = runner.invoke(app, ["info", str(path)])
    metadata_result = runner.invoke(app, ["metadata", str(path)])

    assert info_result.exit_code == 0
    assert metadata_result.exit_code == 0
    assert seen == {
        "info": {"status": "Status", "score": "Score"},
        "metadata": {"status": "Status", "score": "Score"},
    }


def test_convert_preserves_automatic_sidecar_metadata(tmp_path):
    source = _write_sidecar_csv(tmp_path / "survey.csv")
    output = tmp_path / "survey.xlsx"

    transform(str(source), str(output))
    restored = Dataset.read_sidecar(output)

    assert Dataset.sidecar_path(output).exists()
    assert restored["status"].label == "Status"
    assert restored["status"].value_labels == {
        1: "Active",
        2: "Inactive",
    }


def test_metadata_rich_native_input_creates_standardized_sidecar(tmp_path):
    source = tmp_path / "survey.sav"
    output = tmp_path / "survey.csv"
    pyreadstat.write_sav(
        pd.DataFrame({"status": [1, 2]}),
        source,
        column_labels={"status": "Status"},
        variable_value_labels={"status": {1: "Active", 2: "Inactive"}},
    )

    transform(str(source), str(output))

    restored = Dataset.read_sidecar(output)
    assert Dataset.sidecar_path(output).exists()
    assert restored["status"].label == "Status"
    assert restored["status"].value_labels == {
        1.0: "Active",
        2.0: "Inactive",
    }


def test_transform_writes_sidecar_for_remaining_columns(tmp_path):
    source = _write_sidecar_csv(tmp_path / "survey.csv")
    output = tmp_path / "selected.csv"
    pipeline = TransformationPipeline(
        [SelectColumnsTransformation(["status"])]
    )

    transform_file(str(source), str(output), pipeline)
    restored = CSVBackend().read(output)

    assert restored.columns == ["status"]
    assert restored.variable_labels() == {"status": "Status"}
    assert set(Dataset.read_sidecar(output)) == {"status"}


def test_batch_reads_input_sidecar_and_writes_output_sidecar(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_sidecar_csv(input_dir / "survey.csv")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "json",
            "--create-dirs",
        ],
    )

    output = output_dir / "survey.json"
    restored = JsonBackend().read(output)
    assert result.exit_code == 0
    assert output.exists()
    assert Dataset.sidecar_path(output).exists()
    assert restored.variable_labels() == {
        "status": "Status",
        "score": "Score",
    }
