import json
from pathlib import Path

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.streaming import DatasetChunk, StreamingExecutionResult


def test_dataset_chunk_records_stable_offsets() -> None:
    dataset = Dataset(pd.DataFrame({"value": [10, 20]}))

    chunk = DatasetChunk(
        dataset=dataset,
        index=2,
        start_row=4,
        rows=2,
        total_rows=8,
    )

    assert chunk.index == 2
    assert chunk.start_row == 4
    assert chunk.rows == 2
    assert chunk.total_rows == 8


def test_dataset_chunk_rejects_inconsistent_row_count() -> None:
    dataset = Dataset(pd.DataFrame({"value": [10]}))

    with pytest.raises(ValueError, match="must match dataset.rows"):
        DatasetChunk(dataset=dataset, index=0, start_row=0, rows=2)


def test_streaming_execution_result_serializes_to_plain_json(tmp_path: Path) -> None:
    result = StreamingExecutionResult(
        source_path=tmp_path / "input.csv",
        target_path=tmp_path / "output.jsonl",
        source_extension=".csv",
        target_extension=".jsonl",
        chunk_size=2,
        chunks_processed=3,
        rows_processed=5,
        completed=True,
        output_path=tmp_path / "output.jsonl",
        sidecar_path=tmp_path / "output.jsonl.statconvert-metadata.json",
    )

    payload = result.to_dict()

    assert payload["rows_processed"] == 5
    assert payload["completed"] is True
    assert json.loads(json.dumps(payload)) == payload
