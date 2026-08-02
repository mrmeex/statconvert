from pathlib import Path
from threading import get_ident

import pandas as pd
import pytest

from statconvert.batch import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SKIPPED,
    BATCH_STATUS_SUCCESS,
    BatchError,
    BatchItem,
    BatchPlan,
    BatchPlanningOptions,
    BatchResult,
    build_batch_plan,
    execute_batch_plan,
)
from statconvert.ui.batch import console, show_batch_result, _format_current_file


def test_execute_batch_plan_converts_pending_csv_to_json(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_csv(
        input_dir / "good.csv"
    )
    plan = build_batch_plan(
        input_dir,
        output_dir,
        "json",
    )

    result = execute_batch_plan(
        plan
    )

    item = result.items[0]

    assert item.status == BATCH_STATUS_SUCCESS
    assert item.output_file.exists()
    assert item.rows == 2
    assert item.columns == 2
    assert item.duration_seconds is not None
    assert item.error is None


def test_execute_batch_plan_converts_in_parallel_and_preserves_order(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    for name in ["c.csv", "a.csv", "b.csv"]:
        _write_csv(input_dir / name)
    plan = build_batch_plan(input_dir, output_dir, "json")

    result = execute_batch_plan(plan, workers=2)

    assert [item.input_file.name for item in result.items] == [
        item.input_file.name for item in plan.items
    ]
    assert result.success_count == 3
    assert all(item.output_file.exists() for item in result.items)


@pytest.mark.parametrize("workers", [0, -1])
def test_execute_batch_plan_rejects_invalid_worker_count(tmp_path, workers):
    plan = build_batch_plan(
        _write_csv(tmp_path / "input.csv"),
        tmp_path / "output",
        "json",
    )

    with pytest.raises(BatchError, match="Workers must be 1 or greater"):
        execute_batch_plan(plan, workers=workers)


def test_parallel_execution_counts_failures_and_keeps_terminal_items(tmp_path):
    input_dir = tmp_path / "input"
    good = _write_csv(input_dir / "good.csv")
    missing = _write_csv(input_dir / "missing.csv")
    _touch(input_dir / "notes.txt")
    blocked_output = _touch(tmp_path / "output" / "blocked.json")
    _write_csv(input_dir / "blocked.csv")
    plan = build_batch_plan(input_dir, tmp_path / "output", "json")
    missing.unlink()

    result = execute_batch_plan(plan, workers=2)

    assert result.success_count == 1
    assert result.failed_count == 2
    assert result.skipped_count == 1
    assert result.blocked_count == 0
    assert good.exists()
    assert blocked_output.exists()


def test_parallel_callbacks_run_on_collecting_thread(tmp_path):
    input_dir = tmp_path / "input"
    for name in ["one.csv", "two.csv"]:
        _write_csv(input_dir / name)
    plan = build_batch_plan(input_dir, tmp_path / "output", "json")
    caller_thread = get_ident()
    starts = []
    finishes = []

    execute_batch_plan(
        plan,
        workers=2,
        on_item_start=lambda item: starts.append((get_ident(), item)),
        on_item_finish=lambda item: finishes.append((get_ident(), item)),
    )

    assert len(starts) == 2
    assert len(finishes) == 2
    assert all(thread_id == caller_thread for thread_id, _ in starts + finishes)
    assert all(isinstance(item, BatchItem) for _, item in starts + finishes)


def test_parallel_execution_creates_nested_output_directories(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "a" / "one.csv")
    _write_csv(input_dir / "b" / "two.csv")
    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        recursive=True,
    )

    result = execute_batch_plan(plan, workers=2)

    assert result.success_count == 2
    assert all(item.output_file.exists() for item in result.items)


def test_parallel_fail_fast_collects_running_and_cancels_pending_work(tmp_path):
    input_dir = tmp_path / "input"
    missing = _write_csv(input_dir / "00_missing.csv")
    for index in range(8):
        _write_csv(input_dir / f"{index + 1:02d}_good.csv")
    plan = build_batch_plan(input_dir, tmp_path / "output", "json")
    missing.unlink()

    result = execute_batch_plan(plan, workers=2, fail_fast=True)

    assert result.failed_count == 1
    assert result.total_count == plan.total_count
    assert result.completed_count == result.total_count
    assert all(
        item.status in {BATCH_STATUS_SUCCESS, BATCH_STATUS_FAILED, BATCH_STATUS_SKIPPED}
        for item in result.items
    )
    assert all(
        item.reason == "Not processed due to fail-fast"
        for item in result.skipped_items()
    )


def test_execute_batch_plan_creates_output_directories(tmp_path):

    input_file = _write_csv(
        tmp_path / "input" / "good.csv"
    )
    output_dir = tmp_path / "deep" / "output"
    plan = build_batch_plan(
        input_file,
        output_dir,
        "json",
    )

    result = execute_batch_plan(
        plan,
        create_output_dirs=True,
    )

    assert result.items[0].status == BATCH_STATUS_SUCCESS
    assert (
        output_dir / "good.json"
    ).exists()


def test_execute_batch_plan_records_success_status_rows_columns_and_duration(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    plan = build_batch_plan(
        input_file,
        tmp_path / "output",
        "json",
    )

    item = execute_batch_plan(
        plan
    ).items[0]

    assert item.status == BATCH_STATUS_SUCCESS
    assert item.rows == 2
    assert item.columns == 2
    assert item.duration_seconds >= 0
    assert item.started_at is not None
    assert item.finished_at is not None


def test_execute_batch_plan_leaves_skipped_items_skipped(tmp_path):

    input_dir = tmp_path / "input"
    _touch(
        input_dir / "notes.txt"
    )
    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        include_unsupported=True,
    )

    result = execute_batch_plan(
        plan
    )

    assert result.items[0].status == BATCH_STATUS_SKIPPED
    assert result.items[0].reason == "Unsupported input format"


def test_execute_batch_plan_fails_existing_output_without_overwrite(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    _touch(
        tmp_path / "output" / "good.json"
    )
    plan = build_batch_plan(
        input_file,
        tmp_path / "output",
        "json",
        overwrite=False,
    )

    result = execute_batch_plan(
        plan
    )

    assert result.items[0].status == BATCH_STATUS_FAILED
    assert result.items[0].reason == "Conversion failed"
    assert "--overwrite" in result.items[0].error


def test_execute_batch_plan_handles_failure_and_continues(tmp_path):

    first = _write_csv(
        tmp_path / "input" / "first.csv"
    )
    second = _write_csv(
        tmp_path / "input" / "second.csv"
    )
    plan = build_batch_plan(
        tmp_path / "input",
        tmp_path / "output",
        "json",
    )
    first.unlink()

    result = execute_batch_plan(
        plan,
        fail_fast=False,
    )
    by_name = {
        item.input_file.name: item
        for item in result.items
    }

    assert by_name[first.name].status == BATCH_STATUS_FAILED
    assert by_name[first.name].reason == "Conversion failed"
    assert by_name[first.name].error
    assert by_name[second.name].status == BATCH_STATUS_SUCCESS


def test_execute_batch_plan_fail_fast_skips_remaining_pending_items(tmp_path):

    first = _write_csv(
        tmp_path / "input" / "first.csv"
    )
    _write_csv(
        tmp_path / "input" / "second.csv"
    )
    plan = build_batch_plan(
        tmp_path / "input",
        tmp_path / "output",
        "json",
    )
    first.unlink()

    result = execute_batch_plan(
        plan,
        fail_fast=True,
    )

    assert result.items[0].status == BATCH_STATUS_FAILED
    assert result.items[1].status == BATCH_STATUS_SKIPPED
    assert result.items[1].reason == "Not processed due to fail-fast"


def test_execute_batch_plan_fails_pending_item_without_output_file(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    plan = _manual_plan(
        [
            BatchItem(
                input_file=input_file,
                output_file=None,
                status=BATCH_STATUS_PENDING,
            ),
        ]
    )

    result = execute_batch_plan(
        plan
    )

    assert result.items[0].status == BATCH_STATUS_FAILED
    assert "Output file is not planned" in result.items[0].error


def test_execute_batch_plan_does_not_overwrite_input_file(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    plan = _manual_plan(
        [
            BatchItem(
                input_file=input_file,
                output_file=input_file,
                status=BATCH_STATUS_PENDING,
            ),
        ]
    )

    result = execute_batch_plan(
        plan
    )

    assert result.items[0].status == BATCH_STATUS_FAILED
    assert "Input and output path are the same" in result.items[0].error


def test_execute_batch_plan_does_not_mutate_original_plan_items(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    plan = build_batch_plan(
        input_file,
        tmp_path / "output",
        "json",
    )

    result = execute_batch_plan(
        plan
    )

    assert plan.items[0].status == BATCH_STATUS_PENDING
    assert result.items[0].status == BATCH_STATUS_SUCCESS


def test_batch_result_counts_items_by_execution_status(tmp_path):

    items = [
        BatchItem(
            input_file=tmp_path / "success.csv",
            output_file=tmp_path / "success.json",
            status=BATCH_STATUS_SUCCESS,
        ),
        BatchItem(
            input_file=tmp_path / "failed.csv",
            output_file=tmp_path / "failed.json",
            status=BATCH_STATUS_FAILED,
        ),
        BatchItem(
            input_file=tmp_path / "skipped.txt",
            output_file=None,
            status=BATCH_STATUS_SKIPPED,
        ),
        BatchItem(
            input_file=tmp_path / "blocked.csv",
            output_file=tmp_path / "blocked.json",
            status=BATCH_STATUS_BLOCKED,
        ),
    ]
    result = BatchResult(
        plan=_manual_plan(
            []
        ),
        items=items,
    )

    assert result.total_count == 4
    assert result.success_count == 1
    assert result.failed_count == 1
    assert result.skipped_count == 1
    assert result.blocked_count == 1
    assert result.completed_count == 4
    assert result.has_failures
    assert result.has_blockers
    assert len(
        result.success_items()
    ) == 1
    assert len(
        result.failed_items()
    ) == 1
    assert len(
        result.skipped_items()
    ) == 1
    assert len(
        result.blocked_items()
    ) == 1


def test_execute_batch_plan_callbacks_are_called(tmp_path):

    input_file = _write_csv(
        tmp_path / "good.csv"
    )
    plan = build_batch_plan(
        input_file,
        tmp_path / "output",
        "json",
    )
    started = []
    finished = []

    execute_batch_plan(
        plan,
        on_item_start=started.append,
        on_item_finish=finished.append,
    )

    assert [
        item.input_file
        for item in started
    ] == [
        input_file,
    ]
    assert [
        item.input_file
        for item in finished
    ] == [
        input_file,
    ]


def test_finish_callback_is_called_for_skipped_and_blocked_items(tmp_path):
    skipped = BatchItem(
        input_file=tmp_path / "notes.txt",
        output_file=None,
        status=BATCH_STATUS_SKIPPED,
    )
    blocked = BatchItem(
        input_file=tmp_path / "blocked.csv",
        output_file=tmp_path / "blocked.json",
        status=BATCH_STATUS_BLOCKED,
    )
    started = []
    finished = []

    result = execute_batch_plan(
        _manual_plan([skipped, blocked]),
        on_item_start=started.append,
        on_item_finish=finished.append,
    )

    assert started == []
    assert [item.status for item in finished] == [
        BATCH_STATUS_SKIPPED,
        BATCH_STATUS_BLOCKED,
    ]
    assert result.completed_count == 2


def test_show_batch_result_displays_counts_and_items(tmp_path):

    result = BatchResult(
        plan=_manual_plan(
            []
        ),
        items=[
            BatchItem(
                input_file=tmp_path / "good.csv",
                output_file=tmp_path / "good.json",
                status=BATCH_STATUS_SUCCESS,
                rows=2,
                columns=2,
                duration_seconds=0.1,
            ),
        ],
    )

    with console.capture() as capture:
        show_batch_result(
            result
        )

    output = capture.get()

    assert "Batch Result Summary" in output
    assert "Batch Result Items" in output
    assert "Succeeded" in output


def test_format_current_file_truncates_long_file_names():

    file_name = "WizardAlchemyTestDataWithAVeryLongGeneratedFileName.xlsx"

    formatted = _format_current_file(
        file_name,
        max_length=24,
    )

    assert formatted == "WizardAlchemyTestData..."
    assert len(
        formatted
    ) == 24


def _write_csv(
    path: Path
) -> Path:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    pd.DataFrame(
        {
            "id": [
                1,
                2,
            ],
            "name": [
                "Ada",
                "Grace",
            ],
        }
    ).to_csv(
        path,
        index=False,
    )

    return path


def _touch(
    path: Path
) -> Path:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.touch()

    return path


def _manual_plan(
    items: list[BatchItem]
) -> BatchPlan:
    return BatchPlan(
        options=BatchPlanningOptions(
            input_path=Path(
                "input"
            ),
            output_path=Path(
                "output"
            ),
            target_extension=".json",
        ),
        items=items,
    )
