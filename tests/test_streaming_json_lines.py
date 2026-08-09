from pathlib import Path

import pandas as pd
import pytest

from statconvert.backends.json_backend import JsonBackend
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata.sidecar import sidecar_path
from statconvert.streaming import (
    ChunkedReadOptions,
    ChunkedWriteOptions,
    DatasetChunk,
    StreamingNotSupportedError,
)
from statconvert.streaming.execution import execute_streaming_convert


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_reader_yields_deterministic_chunks(
    tmp_path: Path,
    extension: str,
) -> None:
    source = tmp_path / f"input{extension}"
    pd.DataFrame({"value": range(5)}).to_json(
        source,
        orient="records",
        lines=True,
    )

    chunks = list(JsonBackend().iter_chunks(str(source), ChunkedReadOptions(2)))

    assert [(item.index, item.start_row, item.rows) for item in chunks] == [
        (0, 0, 2),
        (1, 2, 2),
        (2, 4, 1),
    ]


def test_empty_json_lines_yields_one_empty_chunk_and_round_trips(
    tmp_path: Path,
) -> None:
    source = tmp_path / "empty.jsonl"
    target = tmp_path / "empty.ndjson"
    source.write_text("", encoding="utf-8")

    chunks = list(JsonBackend().iter_chunks(str(source), ChunkedReadOptions(2)))
    result = execute_streaming_convert(source, target, chunk_size=2)

    assert len(chunks) == 1
    assert chunks[0].rows == 0
    assert list(chunks[0].dataset.dataframe.columns) == []
    assert result.rows_processed == 0
    assert result.chunks_processed == 1
    assert target.read_text(encoding="utf-8") == ""
    assert sidecar_path(target).exists()


@pytest.mark.parametrize(
    ("extension", "format_name"),
    [(".jsonl", "JSON Lines"), (".ndjson", "NDJSON")],
)
def test_malformed_json_line_fails_clearly(
    tmp_path: Path,
    extension: str,
    format_name: str,
) -> None:
    source = tmp_path / f"broken{extension}"
    source.write_text('{"a": 1}\n{"a":\n', encoding="utf-8")

    with pytest.raises(
        ConversionError,
        match=f"Failed reading chunked {format_name} file",
    ):
        list(JsonBackend().iter_chunks(str(source), ChunkedReadOptions(1)))


def test_json_array_is_not_streamable(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('[{"a": 1}]', encoding="utf-8")

    with pytest.raises(StreamingNotSupportedError, match="only .jsonl and .ndjson"):
        list(JsonBackend().iter_chunks(str(source), ChunkedReadOptions(1)))


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_writer_produces_valid_records(
    tmp_path: Path,
    extension: str,
) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / f"output{extension}"
    expected = pd.DataFrame(
        {
            "value": [1, 2, 3],
            "text": ["café", "two", None],
        }
    )
    expected.to_csv(source, index=False)

    execute_streaming_convert(source, target, chunk_size=2)

    actual = pd.read_json(target, lines=True)
    pd.testing.assert_frame_equal(actual, expected)
    assert len(target.read_text(encoding="utf-8").splitlines()) == 3


@pytest.mark.parametrize(
    ("extension", "format_name"),
    [(".jsonl", "JSON Lines"), (".ndjson", "NDJSON")],
)
def test_json_lines_streaming_write_error_names_target_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    format_name: str,
) -> None:
    target = tmp_path / f"output{extension}"
    writer = JsonBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(1),
    )
    chunk = DatasetChunk(
        Dataset(pd.DataFrame({"value": [1]})),
        index=0,
        start_row=0,
        rows=1,
    )

    def fail_write(*args, **kwargs):
        raise ValueError("serialization failed")

    monkeypatch.setattr(pd.DataFrame, "to_json", fail_write)

    with pytest.raises(
        ConversionError,
        match=f"Failed writing chunked {format_name} file",
    ):
        writer.write_chunk(chunk)

    assert not target.exists()
