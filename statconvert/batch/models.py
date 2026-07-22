from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BATCH_STATUS_PENDING = "pending"
BATCH_STATUS_SKIPPED = "skipped"
BATCH_STATUS_BLOCKED = "blocked"
BATCH_STATUS_SUCCESS = "success"
BATCH_STATUS_FAILED = "failed"

BATCH_PROGRESS_STARTED = "started"
BATCH_PROGRESS_ITEM_STARTED = "item_started"
BATCH_PROGRESS_ITEM_FINISHED = "item_finished"
BATCH_PROGRESS_FINISHED = "finished"


MULTI_WORKER_MEMORY_NOTE = (
    "Each worker may hold one dataset in memory. "
    "For very large files, reduce --workers."
)


@dataclass
class BatchWorkloadSummary:
    """Lightweight planning metadata derived without reading datasets."""

    planned_items: int = 0
    planned_files: int = 0
    supported_files: int = 0
    skipped_files: int = 0
    total_input_bytes: int = 0
    largest_input_file_bytes: int = 0
    workers: int = 1
    recursive: bool = False
    preserve_structure: bool = True
    target_format: str = ""
    transform_enabled: bool = False
    validation_enabled: bool = False
    object_mode: str = "none"
    memory_note: str | None = None


@dataclass(frozen=True)
class BatchProgressEvent:
    """Backend-neutral execution status emitted to optional observers."""

    kind: str
    item_index: int | None = None
    total_items: int | None = None
    worker_id: int | None = None
    input_path: Path | None = None
    output_path: Path | None = None
    status: str | None = None
    message: str | None = None


@dataclass
class BatchPlanningOptions:
    """
    Options used to build a batch conversion plan.
    """

    input_path: Path
    output_path: Path
    target_extension: str
    recursive: bool = False
    overwrite: bool = False
    include_unsupported: bool = True
    preserve_structure: bool = True
    patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    object_manifest: Path | None = None
    all_objects: bool = False
    workers: int = 1
    transform_enabled: bool = False
    validation_enabled: bool = False
    object_mode: str = "none"


@dataclass
class BatchItem:
    """
    One planned batch conversion item.
    """

    input_file: Path
    output_file: Path | None
    input_extension: str | None = None
    output_extension: str | None = None
    status: str = BATCH_STATUS_PENDING
    reason: str | None = None
    relative_path: Path | None = None
    input_object: str | None = None
    output_name: str | None = None
    object_index: int | None = None
    object_name: str | None = None
    manifest_row_number: int | None = None
    rows: int | None = None
    columns: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
    validation_issues: int | None = None
    validation_errors: int | None = None
    validation_warnings: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class BatchPlan:
    """
    Planned batch conversion work.
    """

    options: BatchPlanningOptions
    items: list[BatchItem] = field(default_factory=list)
    workload: BatchWorkloadSummary = field(init=False)


    def __post_init__(self) -> None:
        self.workload = _build_workload_summary(self.options, self.items)


    @property
    def total_count(self) -> int:
        """
        Return the number of items in the plan.
        """

        return len(
            self.items
        )


    @property
    def pending_count(self) -> int:
        """
        Return the number of pending items.
        """

        return len(
            self.pending_items()
        )


    @property
    def skipped_count(self) -> int:
        """
        Return the number of skipped items.
        """

        return len(
            self.skipped_items()
        )


    @property
    def blocked_count(self) -> int:
        """
        Return the number of blocked items.
        """

        return len(
            self.blocked_items()
        )


    @property
    def has_blockers(self) -> bool:
        """
        Return whether any item is blocked.
        """

        return self.blocked_count > 0


    def pending_items(self) -> list[BatchItem]:
        """
        Return items ready for execution.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_PENDING
        ]


    def skipped_items(self) -> list[BatchItem]:
        """
        Return skipped items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_SKIPPED
        ]


    def blocked_items(self) -> list[BatchItem]:
        """
        Return blocked items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_BLOCKED
        ]


@dataclass
class BatchResult:
    """
    Result of executing a batch conversion plan.
    """

    plan: BatchPlan
    items: list[BatchItem] = field(default_factory=list)
    workload: BatchWorkloadSummary | None = None


    def __post_init__(self) -> None:
        if self.workload is None:
            self.workload = self.plan.workload


    @property
    def total_count(self) -> int:
        """
        Return the number of result items.
        """

        return len(
            self.items
        )


    @property
    def success_count(self) -> int:
        """
        Return the number of successful items.
        """

        return len(
            self.success_items()
        )


    @property
    def failed_count(self) -> int:
        """
        Return the number of failed items.
        """

        return len(
            self.failed_items()
        )


    @property
    def skipped_count(self) -> int:
        """
        Return the number of skipped items.
        """

        return len(
            self.skipped_items()
        )


    @property
    def blocked_count(self) -> int:
        """
        Return the number of blocked items.
        """

        return len(
            self.blocked_items()
        )


    @property
    def completed_count(self) -> int:
        """
        Return items with a terminal execution status.
        """

        return sum(
            [
                self.success_count,
                self.failed_count,
                self.skipped_count,
                self.blocked_count,
            ]
        )


    @property
    def has_failures(self) -> bool:
        """
        Return whether any item failed during execution.
        """

        return self.failed_count > 0


    @property
    def has_blockers(self) -> bool:
        """
        Return whether any item remained blocked.
        """

        return self.blocked_count > 0


    def success_items(self) -> list[BatchItem]:
        """
        Return successful items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_SUCCESS
        ]


    def failed_items(self) -> list[BatchItem]:
        """
        Return failed items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_FAILED
        ]


    def skipped_items(self) -> list[BatchItem]:
        """
        Return skipped items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_SKIPPED
        ]


    def blocked_items(self) -> list[BatchItem]:
        """
        Return blocked items.
        """

        return [
            item
            for item in self.items
            if item.status == BATCH_STATUS_BLOCKED
        ]


def _build_workload_summary(
    options: BatchPlanningOptions,
    items: list[BatchItem],
) -> BatchWorkloadSummary:
    """Summarize unique input files using filesystem metadata only."""

    grouped: dict[str, list[BatchItem]] = {}
    paths: dict[str, Path] = {}
    for item in items:
        key = str(item.input_file.resolve()).casefold()
        grouped.setdefault(key, []).append(item)
        paths.setdefault(key, item.input_file)

    total_input_bytes = 0
    largest_input_file_bytes = 0
    for path in paths.values():
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:
            size = 0
        total_input_bytes += size
        largest_input_file_bytes = max(largest_input_file_bytes, size)

    skipped_files = sum(
        all(item.status == BATCH_STATUS_SKIPPED for item in file_items)
        for file_items in grouped.values()
    )
    return BatchWorkloadSummary(
        planned_items=len(items),
        planned_files=len(grouped),
        supported_files=len(grouped) - skipped_files,
        skipped_files=skipped_files,
        total_input_bytes=total_input_bytes,
        largest_input_file_bytes=largest_input_file_bytes,
        workers=options.workers,
        recursive=options.recursive,
        preserve_structure=options.preserve_structure,
        target_format=options.target_extension,
        transform_enabled=options.transform_enabled,
        validation_enabled=options.validation_enabled,
        object_mode=options.object_mode,
        memory_note=(MULTI_WORKER_MEMORY_NOTE if options.workers > 1 else None),
    )
