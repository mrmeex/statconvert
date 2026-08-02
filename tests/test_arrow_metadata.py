from __future__ import annotations

import json

import pandas as pd
from pandas.testing import assert_frame_equal
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as parquet
import pytest

from statconvert.backends.arrow_backend import (
    STATCONVERT_METADATA_KEY,
    ArrowBackend,
)
from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataSidecarError
from statconvert.metadata import DatasetMetadata, VariableMetadata


def _rich_dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label="Survey",
        notes=["Imported from a labelled source"],
        raw_metadata={"study": "Arrow metadata"},
    )
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Status",
            value_labels={1: "Active", 2: "Inactive"},
            storage_type="int64",
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
            {"status": [1, 2], "score": [1.5, 2.5]}
        ),
        source_format="sav",
        normalized_metadata=metadata,
    )


def _schema(path):
    if path.suffix == ".parquet":
        return parquet.read_schema(path)
    with pa.memory_map(str(path), "r") as source:
        return pa.ipc.open_file(source).schema


@pytest.mark.parametrize("extension", [".parquet", ".feather"])
def test_arrow_write_embeds_payload_and_keeps_sidecar_and_pandas_metadata(
    tmp_path,
    extension,
):
    path = tmp_path / f"survey{extension}"
    dataset = _rich_dataset()

    ArrowBackend().write(dataset, path)

    schema_metadata = _schema(path).metadata
    assert STATCONVERT_METADATA_KEY in schema_metadata
    assert b"pandas" in schema_metadata
    assert Dataset.sidecar_path(path).exists()
    embedded = json.loads(
        schema_metadata[STATCONVERT_METADATA_KEY].decode("utf-8")
    )
    assert embedded["sidecar_version"] == 3
    assert embedded["dataset_metadata"]["dataset_label"] == "Survey"
    assert_frame_equal(pd.read_parquet(path) if extension == ".parquet"
                       else pd.read_feather(path), dataset.dataframe)


@pytest.mark.parametrize("extension", [".parquet", ".feather"])
def test_arrow_read_restores_embedded_metadata_without_sidecar(
    tmp_path,
    extension,
):
    path = tmp_path / f"survey{extension}"
    expected = _rich_dataset()
    ArrowBackend().write(expected, path)
    Dataset.sidecar_path(path).unlink()

    restored = ArrowBackend().read(path)

    assert_frame_equal(restored.dataframe, expected.dataframe)
    assert restored.get_normalized_metadata().dataset_label == "Survey"
    assert restored.get_normalized_metadata().notes == [
        "Imported from a labelled source"
    ]
    assert restored.variable_labels() == {
        "status": "Status",
        "score": "Score",
    }
    assert restored.metadata_provenance["dataset"] == "embedded_arrow"


@pytest.mark.parametrize("extension", [".parquet", ".feather"])
def test_arrow_sidecar_wins_over_embedded_metadata(tmp_path, extension):
    path = tmp_path / f"survey{extension}"
    ArrowBackend().write(_rich_dataset(), path)
    sidecar = Dataset.sidecar_path(path)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["dataset_metadata"]["dataset_label"] = "Sidecar survey"
    payload["columns"][0]["label"] = "Sidecar status"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    restored = ArrowBackend().read(path)

    assert restored.get_normalized_metadata().dataset_label == "Sidecar survey"
    assert restored.variable_labels()["status"] == "Sidecar status"
    assert restored.metadata_provenance["dataset"] == "automatic_sidecar"
    assert restored.metadata_provenance["columns"]["status"] == (
        "automatic_sidecar"
    )


@pytest.mark.parametrize("extension", [".parquet", ".feather"])
def test_malformed_embedded_arrow_metadata_fails_cleanly(
    tmp_path,
    extension,
):
    path = tmp_path / f"malformed{extension}"
    table = pa.Table.from_pandas(pd.DataFrame({"value": [1]}))
    metadata = dict(table.schema.metadata or {})
    metadata[STATCONVERT_METADATA_KEY] = b"{"
    table = table.replace_schema_metadata(metadata)
    if extension == ".parquet":
        parquet.write_table(table, path)
    else:
        feather.write_feather(table, path)

    with pytest.raises(MetadataSidecarError, match="not valid JSON"):
        ArrowBackend().read(path)
