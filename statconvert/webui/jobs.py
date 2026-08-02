"""Small process-local background job registry for browser write workflows."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from statconvert.exceptions import StatConvertError
from statconvert.serialization import make_json_safe


JobTask = Callable[["JobContext"], Any]
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "cancel_requested"})


class ActiveJobError(StatConvertError):
    """A workflow already has process-local work in progress."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobEvent:
    """One bounded progress or lifecycle event."""

    sequence: int
    kind: str
    timestamp: str
    message: str | None = None
    progress: float | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(self)


@dataclass
class JobRecord:
    """Mutable state for one process-local background job."""

    job_id: str
    workflow: str
    status: str = "queued"
    progress: float = 0.0
    result: Any = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=_timestamp)
    started_at: str | None = None
    finished_at: str | None = None
    events: list[JobEvent] = field(default_factory=list)
    future: Future[Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workflow": self.workflow,
            "status": self.status,
            "progress": self.progress,
            "result": make_json_safe(self.result),
            "error": make_json_safe(self.error),
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "events": [event.to_dict() for event in self.events[-100:]],
        }


class JobContext:
    """Safe callback surface exposed to one running job."""

    def __init__(self, manager: "JobManager", job_id: str) -> None:
        self._manager = manager
        self.job_id = job_id

    @property
    def cancel_requested(self) -> bool:
        return self._manager.cancel_requested(self.job_id)

    def emit(
        self,
        kind: str,
        *,
        message: str | None = None,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        self._manager.emit(
            self.job_id,
            kind,
            message=message,
            progress=progress,
            data=data,
        )


class JobManager:
    """Thread-safe, in-memory manager with best-effort cancellation."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="statconvert-webui",
        )
        self._records: dict[str, JobRecord] = {}
        self._lock = Lock()

    def submit(self, workflow: str, task: JobTask) -> JobRecord:
        return self._submit(workflow, task, exclusive=False)

    def submit_unique(self, workflow: str, task: JobTask) -> JobRecord:
        """Submit unless the same workflow already has an active job."""

        return self._submit(workflow, task, exclusive=True)

    def _submit(
        self,
        workflow: str,
        task: JobTask,
        *,
        exclusive: bool,
    ) -> JobRecord:
        job_id = uuid4().hex
        record = JobRecord(job_id=job_id, workflow=workflow)
        with self._lock:
            active = self._active_record(workflow)
            if exclusive and active is not None:
                raise ActiveJobError(
                    f"A {workflow} job is already {active.status}: {active.job_id}",
                    suggestion="Wait for it to finish or cancel it before starting another.",
                )
            self._records[job_id] = record
            self._append_event(record, "queued", message="Job queued.", progress=0.0)
            record.future = self._executor.submit(self._run, job_id, task)
            return record

    def active_snapshot(self, workflow: str) -> dict[str, Any] | None:
        """Return the newest active job for one workflow, if any."""

        with self._lock:
            record = self._active_record(workflow)
            return None if record is None else record.to_dict()

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(job_id)
            return None if record is None else record.to_dict()

    def events_after(self, job_id: str, sequence: int) -> list[dict[str, Any]] | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            return [
                event.to_dict()
                for event in record.events
                if event.sequence > sequence
            ]

    def cancel(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            if record.status in TERMINAL_JOB_STATUSES:
                return record
            record.cancel_requested = True
            if record.future is not None and record.future.cancel():
                record.status = "cancelled"
                record.finished_at = _timestamp()
                self._append_event(
                    record,
                    "cancelled",
                    message="Queued job cancelled.",
                    progress=record.progress,
                )
            else:
                record.status = "cancel_requested"
                self._append_event(
                    record,
                    "cancel_requested",
                    message=(
                        "Cancellation requested. Active reads and writes finish at "
                        "their next safe boundary."
                    ),
                    progress=record.progress,
                )
            return record

    def cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            record = self._records.get(job_id)
            return bool(record and record.cancel_requested)

    def emit(
        self,
        job_id: str,
        kind: str,
        *,
        message: str | None = None,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            record = self._records[job_id]
            if progress is not None:
                record.progress = max(0.0, min(1.0, progress))
            self._append_event(
                record,
                kind,
                message=message,
                progress=record.progress,
                data=data,
            )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _active_record(self, workflow: str) -> JobRecord | None:
        matches = (
            record
            for record in reversed(tuple(self._records.values()))
            if record.workflow == workflow and record.status in ACTIVE_JOB_STATUSES
        )
        return next(matches, None)

    def _run(self, job_id: str, task: JobTask) -> None:
        with self._lock:
            record = self._records[job_id]
            if record.status == "cancelled":
                return
            record.status = "running"
            record.started_at = _timestamp()
            self._append_event(record, "started", message="Job started.", progress=0.0)
        context = JobContext(self, job_id)
        try:
            result = task(context)
        except Exception as exc:
            with self._lock:
                record = self._records[job_id]
                record.status = "failed"
                record.error = {
                    "code": _error_code(exc),
                    "message": str(exc),
                }
                record.finished_at = _timestamp()
                self._append_event(
                    record,
                    "failed",
                    message=str(exc),
                    progress=record.progress,
                )
            return
        with self._lock:
            record = self._records[job_id]
            record.result = make_json_safe(result)
            record.status = "succeeded"
            record.progress = 1.0
            record.finished_at = _timestamp()
            self._append_event(
                record,
                "succeeded",
                message="Job completed.",
                progress=1.0,
            )

    @staticmethod
    def _append_event(
        record: JobRecord,
        kind: str,
        *,
        message: str | None = None,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        record.events.append(
            JobEvent(
                sequence=len(record.events) + 1,
                kind=kind,
                timestamp=_timestamp(),
                message=message,
                progress=progress,
                data=make_json_safe(data or {}),
            )
        )
        if len(record.events) > 200:
            del record.events[:-200]


def _error_code(exc: Exception) -> str:
    name = exc.__class__.__name__
    return "".join(
        f"_{character.lower()}" if character.isupper() else character
        for character in name
    ).lstrip("_")
