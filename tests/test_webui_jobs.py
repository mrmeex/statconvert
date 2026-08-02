from __future__ import annotations

from threading import Event

import pytest

from statconvert.webui.jobs import ActiveJobError, JobManager


def test_job_manager_reports_progress_and_success() -> None:
    manager = JobManager(max_workers=1)
    release = Event()

    def task(context):
        context.emit("working", progress=0.5, data={"rows": 2})
        release.wait(timeout=2)
        return {"rows": 4}

    record = manager.submit("convert", task)
    release.set()
    result = record.future.result(timeout=2)
    snapshot = manager.snapshot(record.job_id)
    manager.shutdown()

    assert result is None
    assert snapshot is not None
    assert snapshot["status"] == "succeeded"
    assert snapshot["progress"] == 1.0
    assert snapshot["result"] == {"rows": 4}
    assert any(event["kind"] == "working" for event in snapshot["events"])


def test_running_job_cancellation_is_best_effort() -> None:
    manager = JobManager(max_workers=1)
    started = Event()
    release = Event()

    def task(context):
        started.set()
        release.wait(timeout=2)
        return {"cancel_was_requested": context.cancel_requested}

    record = manager.submit("validate", task)
    assert started.wait(timeout=2)
    cancelled = manager.cancel(record.job_id)
    release.set()
    record.future.result(timeout=2)
    snapshot = manager.snapshot(record.job_id)
    manager.shutdown()

    assert cancelled is not None
    assert cancelled.cancel_requested is True
    assert snapshot is not None
    assert snapshot["status"] == "succeeded"
    assert snapshot["result"]["cancel_was_requested"] is True
    assert any(event["kind"] == "cancel_requested" for event in snapshot["events"])


def test_unique_workflow_submission_rejects_only_while_active() -> None:
    manager = JobManager(max_workers=2)
    started = Event()
    release = Event()

    def task(context):
        del context
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    first = manager.submit_unique("batch", task)
    assert started.wait(timeout=2)
    assert manager.active_snapshot("batch")["job_id"] == first.job_id
    with pytest.raises(ActiveJobError, match="already running"):
        manager.submit_unique("batch", task)

    # Exclusivity is workflow-scoped and does not affect other UI work.
    other = manager.submit("convert", lambda context: {"ok": not context.cancel_requested})
    other.future.result(timeout=2)
    release.set()
    first.future.result(timeout=2)
    assert manager.active_snapshot("batch") is None

    second = manager.submit_unique("batch", lambda context: {"ok": True})
    second.future.result(timeout=2)
    manager.shutdown()
    assert manager.snapshot(second.job_id)["status"] == "succeeded"


def test_failed_and_cancelled_batches_release_unique_submission() -> None:
    failed_manager = JobManager(max_workers=1)

    def fail(context):
        del context
        raise RuntimeError("expected failure")

    failed = failed_manager.submit_unique("batch", fail)
    failed.future.result(timeout=2)
    assert failed_manager.snapshot(failed.job_id)["status"] == "failed"
    after_failure = failed_manager.submit_unique("batch", lambda context: {"ok": True})
    after_failure.future.result(timeout=2)
    failed_manager.shutdown()

    manager = JobManager(max_workers=1)
    release = Event()
    blocker = manager.submit("convert", lambda context: release.wait(timeout=2))
    cancelled = manager.submit_unique("batch", lambda context: {"ok": True})
    assert manager.cancel(cancelled.job_id).status == "cancelled"
    after_cancel = manager.submit_unique("batch", lambda context: {"ok": True})
    release.set()
    blocker.future.result(timeout=2)
    after_cancel.future.result(timeout=2)
    manager.shutdown()
    assert manager.snapshot(after_cancel.job_id)["status"] == "succeeded"
