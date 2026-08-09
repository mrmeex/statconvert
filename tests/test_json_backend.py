import json

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from statconvert.backends.json_backend import JsonBackend
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.registry import get_backend_for_file


def test_json_roundtrip(tmp_path):

    backend = JsonBackend()
    output_file = tmp_path / "output.json"

    expected = pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
        }
    )

    backend.write(
        Dataset(dataframe=expected),
        output_file
    )

    result = backend.read(output_file)

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["file_type"] == ".json"
    assert result.metadata["lines"] is False
    assert result.metadata["backend"] == "json"


def test_ndjson_roundtrip(tmp_path):

    backend = JsonBackend()
    output_file = tmp_path / "output.ndjson"

    expected = pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
        }
    )

    backend.write(
        Dataset(dataframe=expected),
        output_file
    )

    result = backend.read(output_file)

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["file_type"] == ".ndjson"
    assert result.metadata["lines"] is True
    assert result.metadata["backend"] == "json"


def test_jsonl_roundtrip(tmp_path):

    backend = JsonBackend()
    output_file = tmp_path / "output.jsonl"

    expected = pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
        }
    )

    backend.write(
        Dataset(dataframe=expected),
        output_file
    )

    result = backend.read(output_file)

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["file_type"] == ".jsonl"
    assert result.metadata["lines"] is True
    assert result.metadata["backend"] == "json"


def test_registry_resolves_json_formats_to_json_backend(tmp_path):

    assert isinstance(
        get_backend_for_file(tmp_path / "sample.json"),
        JsonBackend
    )
    assert isinstance(
        get_backend_for_file(tmp_path / "sample.ndjson"),
        JsonBackend
    )
    assert isinstance(
        get_backend_for_file(tmp_path / "sample.jsonl"),
        JsonBackend
    )


def test_json_writer_serializes_large_records_in_bounded_chunks(
    tmp_path,
    monkeypatch,
):
    backend = JsonBackend()
    output_file = tmp_path / "bounded.json"
    dataframe = pd.DataFrame(
        {
            "id": range(backend.write_chunk_rows + 5),
            "text": ["value"] * (backend.write_chunk_rows + 5),
        }
    )
    observed_rows = []
    original = pd.DataFrame.to_json

    def tracked_to_json(self, *args, **kwargs):
        observed_rows.append(len(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_json", tracked_to_json)

    backend.write(Dataset(dataframe=dataframe), output_file)

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(payload) == len(dataframe)
    assert payload[0] == {"id": 0, "text": "value"}
    assert payload[-1] == {
        "id": backend.write_chunk_rows + 4,
        "text": "value",
    }
    assert observed_rows == [backend.write_chunk_rows, 5]


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_chunk_writer_preserves_one_record_per_line(
    tmp_path,
    extension,
):
    backend = JsonBackend()
    output_file = tmp_path / f"bounded{extension}"
    dataframe = pd.DataFrame({"id": [1, 2], "text": ["é", "中文"]})

    backend.write(Dataset(dataframe=dataframe), output_file)

    records = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [{"id": 1, "text": "é"}, {"id": 2, "text": "中文"}]


def test_chunked_json_text_matches_existing_pandas_formatting(tmp_path):
    backend = JsonBackend()
    backend.write_chunk_rows = 2
    dataframe = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [1.5, None, 3.25],
            "text": ["é", "中文", "plain"],
        }
    )
    json_path = tmp_path / "formatted.json"
    jsonl_path = tmp_path / "formatted.jsonl"

    backend.write(Dataset(dataframe=dataframe), json_path)
    backend.write(Dataset(dataframe=dataframe), jsonl_path)

    assert json_path.read_text(encoding="utf-8") == dataframe.to_json(
        orient="records",
        force_ascii=False,
        indent=2,
    )
    assert jsonl_path.read_text(encoding="utf-8") == dataframe.to_json(
        orient="records",
        force_ascii=False,
        lines=True,
    )


@pytest.mark.parametrize(
    ("extension", "format_name"),
    [(".jsonl", "JSON Lines"), (".ndjson", "NDJSON")],
)
def test_malformed_json_lines_normal_read_has_format_specific_error(
    tmp_path,
    extension,
    format_name,
):
    source = tmp_path / f"broken{extension}"
    source.write_text('{"value": 1}\nnot-json\n', encoding="utf-8")

    with pytest.raises(
        ConversionError,
        match=f"Failed reading {format_name} file",
    ):
        JsonBackend().read(source)


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_normal_roundtrip_writes_and_restores_sidecar(
    tmp_path,
    extension,
):
    backend = JsonBackend()
    output_file = tmp_path / f"metadata{extension}"
    dataset = Dataset(pd.DataFrame({"value": [1, 2]}))

    backend.write(dataset, output_file)
    restored = backend.read(output_file)

    assert Dataset.sidecar_path(output_file).exists()
    assert restored.metadata_provenance["dataset"] == "automatic_sidecar"
