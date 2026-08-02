from pathlib import Path

import pandas as pd
import pytest

from statconvert.backends.csv_backend import CSVBackend
from statconvert.dataset import Dataset
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.exceptions import ConversionError, OutputPathError
from statconvert.metadata.sidecar import sidecar_path
from statconvert.streaming import (
    ChunkedReadOptions,
    ChunkedWriteOptions,
    DatasetChunk,
    StreamingSchemaError,
)
from statconvert.streaming.execution import execute_streaming_convert


def test_csv_reader_yields_deterministic_chunk_positions(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    pd.DataFrame({"value": range(5)}).to_csv(source, index=False)

    chunks = list(CSVBackend().iter_chunks(str(source), ChunkedReadOptions(2)))

    assert [(item.index, item.start_row, item.rows) for item in chunks] == [
        (0, 0, 2),
        (1, 2, 2),
        (2, 4, 1),
    ]
    assert [item.total_rows for item in chunks] == [None, None, None]


def test_csv_reader_preserves_encoding_delimiter_and_decimal(tmp_path: Path) -> None:
    source = tmp_path / "latin1.csv"
    target = tmp_path / "normalized.csv"
    expected = pd.DataFrame({"city": ["Zürich", "Málaga"], "amount": [1.5, 2.75]})
    expected.to_csv(
        source,
        index=False,
        encoding="latin1",
        sep=";",
        decimal=",",
    )

    execute_streaming_convert(
        source,
        target,
        chunk_size=1,
        read_options=DatasetReadOptions(
            encoding="latin1",
            csv_delimiter=";",
            csv_decimal=",",
        ),
        write_options=DatasetWriteOptions(
            encoding="utf-8",
            csv_delimiter="|",
            csv_decimal=".",
        ),
    )

    actual = pd.read_csv(target, sep="|", encoding="utf-8")
    pd.testing.assert_frame_equal(actual, expected)


def test_header_only_csv_yields_one_schema_chunk(tmp_path: Path) -> None:
    source = tmp_path / "header.csv"
    source.write_text("a,b\n", encoding="utf-8")

    chunks = list(CSVBackend().iter_chunks(str(source), ChunkedReadOptions(2)))

    assert len(chunks) == 1
    assert chunks[0].rows == 0
    assert list(chunks[0].dataset.dataframe.columns) == ["a", "b"]


def test_empty_csv_fails_with_friendly_chunk_error(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    source.write_text("", encoding="utf-8")

    with pytest.raises(ConversionError, match="Failed reading chunked CSV file"):
        list(CSVBackend().iter_chunks(str(source), ChunkedReadOptions(2)))


def test_csv_writer_writes_header_once(tmp_path: Path) -> None:
    target = tmp_path / "output.csv"
    writer = CSVBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(2),
    )
    writer.write_chunk(
        DatasetChunk(Dataset(pd.DataFrame({"a": [1, 2]})), 0, 0, 2)
    )
    writer.write_chunk(
        DatasetChunk(Dataset(pd.DataFrame({"a": [3]})), 1, 2, 1)
    )

    written_sidecar = writer.finalize()

    assert target.read_text(encoding="utf-8").splitlines() == ["a", "1", "2", "3"]
    assert written_sidecar == sidecar_path(target)
    assert written_sidecar.exists()


def test_csv_writer_rejects_existing_target_before_temp_creation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "output.csv"
    target.write_text("original\n", encoding="utf-8")

    with pytest.raises(OutputPathError, match="already exists"):
        CSVBackend().open_chunk_writer(
            str(target),
            ChunkedWriteOptions(2),
        )

    assert target.read_text(encoding="utf-8") == "original\n"
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp"))


def test_csv_writer_creates_parent_only_when_requested(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "output.csv"

    with pytest.raises(OutputPathError, match="does not exist"):
        CSVBackend().open_chunk_writer(
            str(target),
            ChunkedWriteOptions(2),
        )

    writer = CSVBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(2),
        create_dirs=True,
    )
    writer.write_chunk(DatasetChunk(Dataset(pd.DataFrame({"a": [1]})), 0, 0, 1))
    writer.finalize()

    assert target.exists()


def test_schema_failure_preserves_existing_target_and_cleans_temp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "output.csv"
    target.write_text("original\n", encoding="utf-8")
    writer = CSVBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(2),
        overwrite=True,
    )
    writer.write_chunk(
        DatasetChunk(Dataset(pd.DataFrame({"a": [1], "b": [2]})), 0, 0, 1)
    )

    with pytest.raises(StreamingSchemaError, match="ordered columns changed"):
        writer.write_chunk(
            DatasetChunk(Dataset(pd.DataFrame({"b": [3], "a": [4]})), 1, 1, 1)
        )

    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp"))


def test_writer_context_without_finalize_cleans_temporary_output(
    tmp_path: Path,
) -> None:
    target = tmp_path / "cancelled.csv"

    with CSVBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(2),
    ) as writer:
        writer.write_chunk(
            DatasetChunk(Dataset(pd.DataFrame({"a": [1]})), 0, 0, 1)
        )

    assert not target.exists()
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".cancelled.csv.statconvert-*.tmp"))
