from pathlib import Path

import pandas as pd
import pytest

from statconvert.batch import BatchError, build_batch_plan, execute_batch_plan
from statconvert.metadata.sidecar import sidecar_path
from statconvert.transformations.pipeline import TransformationPipeline


def test_streaming_batch_engine_records_metrics_and_totals(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _write_csv(source / "one.csv", 5)
    _write_json_lines(source / "two.jsonl", 3)
    _write_json_lines(source / "three.ndjson", 4)
    plan = build_batch_plan(
        source,
        tmp_path / "output",
        "csv",
        streaming_enabled=True,
        chunk_size=2,
    )

    result = execute_batch_plan(plan)

    assert [item.input_file.name for item in result.items] == [
        "one.csv",
        "three.ndjson",
        "two.jsonl",
    ]
    assert result.success_count == 3
    assert result.total_streamed_rows == 12
    assert result.total_streamed_chunks == 7
    assert all(item.streaming for item in result.items)
    assert all(item.chunk_size == 2 for item in result.items)
    assert all(sidecar_path(item.output_file).exists() for item in result.items)


def test_streaming_batch_keeps_normal_failure_policy_for_mixed_items(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _write_csv(source / "first.csv", 2)
    (source / "second.json").parent.mkdir(parents=True, exist_ok=True)
    (source / "second.json").write_text('[{"value": 1}]', encoding="utf-8")
    plan = build_batch_plan(
        source,
        tmp_path / "output",
        "jsonl",
        streaming_enabled=True,
        chunk_size=2,
    )

    result = execute_batch_plan(plan)

    assert [item.status for item in result.items] == ["success", "failed"]
    assert (tmp_path / "output" / "first.jsonl").exists()
    assert not (tmp_path / "output" / "second.jsonl").exists()
    assert "JSON array files" in (result.items[1].error or "")


def test_streaming_batch_preserves_target_after_malformed_jsonl(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "broken.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text('{"value": 1}\nnot-json\n', encoding="utf-8")
    target = tmp_path / "output" / "broken.csv"
    target.parent.mkdir(parents=True)
    target.write_text("original\n", encoding="utf-8")
    plan = build_batch_plan(
        source,
        target,
        "csv",
        overwrite=True,
        streaming_enabled=True,
        chunk_size=1,
    )

    result = execute_batch_plan(plan)

    assert result.failed_count == 1
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_streaming_batch_preserves_target_after_schema_drift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "drift.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text('{"a": 1}\n{"a": 2, "b": 3}\n', encoding="utf-8")
    target = tmp_path / "output" / "drift.csv"
    target.parent.mkdir(parents=True)
    target.write_text("original\n", encoding="utf-8")
    plan = build_batch_plan(
        source,
        target,
        "csv",
        overwrite=True,
        streaming_enabled=True,
        chunk_size=1,
    )

    result = execute_batch_plan(plan)

    assert result.failed_count == 1
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_non_streaming_batch_does_not_call_streaming_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_csv(tmp_path / "input.csv", 2)
    plan = build_batch_plan(source, tmp_path / "output.json", "json")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("streaming executor should not be called")

    monkeypatch.setattr(
        "statconvert.batch.execution.execute_streaming_convert",
        fail_if_called,
    )

    result = execute_batch_plan(plan)

    assert result.success_count == 1


@pytest.mark.parametrize(
    ("execution_option", "message"),
    [
        ("transform", "does not support transforms"),
        ("validate", "does not support validation"),
        ("object", "does not support object selection"),
    ],
)
def test_streaming_batch_engine_rejects_unimplemented_global_modes(
    tmp_path: Path,
    execution_option: str,
    message: str,
) -> None:
    source = _write_csv(tmp_path / "input.csv", 1)
    plan = build_batch_plan(
        source,
        tmp_path / "output.csv",
        "csv",
        streaming_enabled=True,
        chunk_size=2,
        object_mode="object" if execution_option == "object" else "none",
    )
    kwargs = {}
    if execution_option == "transform":
        kwargs["transform_pipeline"] = TransformationPipeline([])
    elif execution_option == "validate":
        kwargs["validate"] = True

    with pytest.raises(BatchError, match=message):
        execute_batch_plan(plan, **kwargs)

    assert not (tmp_path / "output.csv").exists()


def _write_csv(path: Path, rows: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": range(rows), "label": [f"r{i}" for i in range(rows)]}).to_csv(
        path,
        index=False,
    )
    return path


def _write_json_lines(path: Path, rows: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": range(rows), "label": [f"r{i}" for i in range(rows)]}).to_json(
        path,
        orient="records",
        lines=True,
    )
    return path
