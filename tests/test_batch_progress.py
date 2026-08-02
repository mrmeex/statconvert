from __future__ import annotations

from threading import Lock

import pandas as pd
from typer.testing import CliRunner

from statconvert.batch import (
    BATCH_PROGRESS_FINISHED,
    BATCH_PROGRESS_ITEM_FINISHED,
    BATCH_PROGRESS_ITEM_STARTED,
    BATCH_PROGRESS_STARTED,
    BatchProgressEvent,
    build_batch_plan,
    execute_batch_plan,
)
from statconvert.cli import app


runner = CliRunner()


def test_parallel_execution_emits_worker_progress_events(tmp_path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    _write_csv(input_dir / "two.csv")
    plan = build_batch_plan(input_dir, tmp_path / "output", "json", workers=2)
    events: list[BatchProgressEvent] = []
    lock = Lock()

    def record(event: BatchProgressEvent) -> None:
        with lock:
            events.append(event)

    result = execute_batch_plan(plan, workers=2, on_progress=record)

    assert result.success_count == 2
    assert events[0].kind == BATCH_PROGRESS_STARTED
    assert events[-1].kind == BATCH_PROGRESS_FINISHED
    started = [event for event in events if event.kind == BATCH_PROGRESS_ITEM_STARTED]
    finished = [event for event in events if event.kind == BATCH_PROGRESS_ITEM_FINISHED]
    assert len(started) == 2
    assert len(finished) == 2
    assert all(event.worker_id is not None for event in started)
    assert {event.input_path.name for event in started} == {"one.csv", "two.csv"}
    assert all(event.status == "success" for event in finished)


def test_human_batch_output_shows_workload_workers_and_completion(tmp_path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    _write_csv(input_dir / "two.csv")

    result = runner.invoke(
        app,
        [
            "batch",
            "--create-dirs",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "json",
            "--workers",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "Batch Workload" in result.output
    assert "Running batch" in result.output
    assert "Worker 1" in result.output
    assert "Worker 2" in result.output
    assert "Batch Result Summary" in result.output
    assert "Succeeded" in result.output
    assert "Each worker may hold one dataset in memory" in result.output


def test_human_batch_failure_shows_output_reason_and_next_step(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(input_dir / "one.csv")
    output_dir.mkdir()
    (output_dir / "one.json").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "json",
            "--allow-blocked",
        ],
    )

    assert result.exit_code == 1
    assert "Output file" in result.output
    assert "one.json" in result.output
    assert "Next step" in result.output
    assert "--overwrite" in result.output


def test_human_batch_result_shows_written_report_path(tmp_path) -> None:
    input_dir = tmp_path / "input"
    report = tmp_path / "reports" / "batch.json"
    _write_csv(input_dir / "one.csv")

    result = runner.invoke(
        app,
        [
            "batch",
            "--create-dirs",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "json",
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0
    assert report.exists()
    assert "Report" in result.output
    assert "batch.json" in result.output


def _write_csv(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": [1, 2], "value": ["a", "b"]}).to_csv(
        path,
        index=False,
    )
