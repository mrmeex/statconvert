from pathlib import Path

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.exceptions import ConversionError
from statconvert.metadata.sidecar import sidecar_path
from statconvert.registry import read_dataset
from statconvert.streaming import (
    ChunkedReadOptions,
    ChunkedWriteOptions,
    DatasetChunk,
    StreamingNotSupportedError,
    StreamingWriteError,
)
from statconvert.streaming.execution import execute_streaming_convert


_SUPPORTED_PAIRS = [
    (".csv", ".csv"),
    (".csv", ".jsonl"),
    (".csv", ".ndjson"),
    (".jsonl", ".csv"),
    (".ndjson", ".csv"),
    (".jsonl", ".jsonl"),
    (".jsonl", ".ndjson"),
    (".ndjson", ".jsonl"),
    (".ndjson", ".ndjson"),
]


@pytest.mark.parametrize(("source_extension", "target_extension"), _SUPPORTED_PAIRS)
def test_all_internal_streaming_pairs_round_trip(
    tmp_path: Path,
    source_extension: str,
    target_extension: str,
) -> None:
    source = tmp_path / f"input{source_extension}"
    target = tmp_path / f"output{target_extension}"
    expected = pd.DataFrame(
        {
            "row": range(5),
            "label": ["a", "b", "c", "d", "e"],
        }
    )
    if source_extension == ".csv":
        expected.to_csv(source, index=False)
    else:
        expected.to_json(source, orient="records", lines=True)

    result = execute_streaming_convert(source, target, chunk_size=2)

    actual = (
        pd.read_csv(target)
        if target_extension == ".csv"
        else pd.read_json(target, lines=True)
    )
    pd.testing.assert_frame_equal(actual, expected)
    assert result.completed is True
    assert result.chunks_processed == 3
    assert result.rows_processed == 5
    assert result.sidecar_path == sidecar_path(target)
    assert result.sidecar_path.exists()


def test_source_sidecar_metadata_survives_and_is_read_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.ndjson"
    dataframe = pd.DataFrame({"value": [1, 2, 3]})
    dataframe.to_csv(source, index=False)
    dataset = Dataset(
        dataframe,
        source_format="csv",
        source_file=str(source),
    )
    dataset.get_normalized_metadata().variables["value"].label = "Preserved label"
    dataset.sync_metadata()
    dataset.write_sidecar(source)

    import statconvert.backends.csv_backend as csv_module

    original = csv_module.read_sidecar
    calls = 0

    def counted_read_sidecar(filename):
        nonlocal calls
        calls += 1
        return original(filename)

    monkeypatch.setattr(csv_module, "read_sidecar", counted_read_sidecar)

    execute_streaming_convert(source, target, chunk_size=1)
    restored = read_dataset(target)

    assert calls == 1
    assert restored.variable_labels() == {"value": "Preserved label"}


def test_unsupported_pair_fails_before_output_creation(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    target = tmp_path / "output.csv"
    source.write_text('[{"value": 1}]', encoding="utf-8")

    with pytest.raises(StreamingNotSupportedError):
        execute_streaming_convert(source, target, chunk_size=1)

    assert not target.exists()
    assert not sidecar_path(target).exists()


def test_non_streaming_backend_optional_methods_fail_clearly(
    tmp_path: Path,
) -> None:
    backend = ArrowBackend()

    with pytest.raises(StreamingNotSupportedError, match="Chunked reading"):
        list(
            backend.iter_chunks(
                str(tmp_path / "input.parquet"),
                ChunkedReadOptions(1),
            )
        )
    with pytest.raises(StreamingNotSupportedError, match="Chunked writing"):
        backend.open_chunk_writer(
            str(tmp_path / "output.parquet"),
            ChunkedWriteOptions(1),
        )


def test_overwrite_true_replaces_target_after_success(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(source, index=False)
    target.write_text("old\nvalue\n", encoding="utf-8")

    execute_streaming_convert(
        source,
        target,
        chunk_size=1,
        overwrite=True,
    )

    assert pd.read_csv(target).to_dict(orient="list") == {"a": [1, 2]}
    assert sidecar_path(target).exists()


def test_progress_events_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.jsonl"
    pd.DataFrame({"a": [1, 2, 3]}).to_csv(source, index=False)
    events = []

    execute_streaming_convert(
        source,
        target,
        chunk_size=2,
        on_progress=events.append,
    )

    assert [event.event_type for event in events] == [
        "started",
        "chunk_completed",
        "chunk_completed",
        "completed",
    ]
    assert [event.cumulative_rows for event in events] == [0, 2, 3, 3]


def test_malformed_source_cleans_writer_temporary_files(tmp_path: Path) -> None:
    source = tmp_path / "broken.jsonl"
    target = tmp_path / "output.csv"
    source.write_text('{"a": 1}\n{"a":\n', encoding="utf-8")

    with pytest.raises(
        ConversionError,
        match="Failed reading chunked JSON Lines file",
    ):
        execute_streaming_convert(source, target, chunk_size=1)

    assert not target.exists()
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp*"))


def test_sidecar_failure_reports_committed_data_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from statconvert.backends.csv_backend import CSVBackend

    target = tmp_path / "output.csv"
    writer = CSVBackend().open_chunk_writer(
        str(target),
        ChunkedWriteOptions(1),
    )
    writer.write_chunk(DatasetChunk(Dataset(pd.DataFrame({"a": [1]})), 0, 0, 1))

    def fail_sidecar(self, filename):
        raise OSError("simulated sidecar failure")

    monkeypatch.setattr(Dataset, "write_sidecar", fail_sidecar)

    with pytest.raises(
        StreamingWriteError,
        match="data was committed successfully",
    ):
        writer.finalize()

    assert target.exists()
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp*"))
