from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BATCH_STATUS_PENDING = "pending"
BATCH_STATUS_SKIPPED = "skipped"
BATCH_STATUS_BLOCKED = "blocked"
BATCH_STATUS_SUCCESS = "success"
BATCH_STATUS_FAILED = "failed"

BATCH_PHASE_FILESYSTEM_PLAN = "filesystem_plan"
BATCH_PHASE_FULL_PLAN = "full_plan"
BATCH_PHASE_EXECUTION = "execution"
BATCH_MODE_DRY_RUN = "dry_run"
BATCH_MODE_FILESYSTEM_PLAN = "filesystem_plan"
BATCH_MODE_FULL_PLAN = "full_plan"
BATCH_MODE_EXECUTION = "execution"

BATCH_READ_NOT_CHECKED = "not_checked"
BATCH_READ_READY = "ready"
BATCH_READ_FAILED = "failed"
BATCH_READ_SKIPPED = "skipped"

BATCH_DETAIL_LIMIT = 100

OVERWRITE_NOT_NEEDED = "not_needed"
OVERWRITE_WOULD_REPLACE = "would_replace"
OVERWRITE_BLOCKED = "blocked"
OVERWRITE_NOT_CHECKED = "not_checked"

DIRECTORY_EXISTS = "exists"
DIRECTORY_WOULD_CREATE = "would_create"
DIRECTORY_BLOCKED = "blocked"
DIRECTORY_NOT_NEEDED = "not_needed"
DIRECTORY_NOT_CHECKED = "not_checked"

SIDECAR_NOT_CHECKED = "not_checked"
SIDECAR_POTENTIAL_PATH = "potential_path"

BATCH_PLAN_DISPLAY_ITEM_LIMIT = 500
BATCH_DRY_RUN_UNCHECKED = (
    "schema",
    "transform_recipe_compatibility",
    "transfer_policy_decisions",
    "required_metadata_sidecars",
)

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
    streaming_enabled: bool = False
    chunk_size: int | None = None
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
    streaming_enabled: bool = False
    chunk_size: int | None = None
    object_mode: str = "none"
    phase: str = BATCH_PHASE_FILESYSTEM_PLAN
    mode: str = BATCH_MODE_EXECUTION
    create_dirs: bool = False
    filesystem_preflight: bool = False
    recipe_path: Path | None = None
    recipe_name: str | None = None
    recipe_step_count: int = 0
    policy: str | None = None
    optimize_types: bool = False


@dataclass
class BatchDiagnostic:
    """One bounded, backend-neutral recipe or policy diagnostic."""

    code: str
    message: str
    severity: str
    step_index: int | None = None
    step_type: str | None = None
    column: str | None = None
    field: str | None = None
    suggestion: str | None = None


@dataclass
class BatchRecipeOutcome:
    """Per-item portable-recipe planning or execution state."""

    requested: bool = False
    recipe_path: Path | None = None
    recipe_name: str | None = None
    syntax_status: str = "not_requested"
    compatibility_status: str = "not_requested"
    execution_status: str = "not_requested"
    step_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    diagnostics: list[BatchDiagnostic] = field(default_factory=list)
    diagnostics_omitted: int = 0


@dataclass
class BatchPolicyOutcome:
    """Per-item transfer-policy planning and application state."""

    requested: bool = False
    policy_name: str | None = None
    status: str = "not_requested"
    decision_counts: dict[str, int] = field(default_factory=dict)
    issue_counts: dict[str, int] = field(default_factory=dict)
    issue_code_counts: dict[str, int] = field(default_factory=dict)
    metadata_disposition_counts: dict[str, int] = field(default_factory=dict)
    diagnostics: list[BatchDiagnostic] = field(default_factory=list)
    diagnostics_omitted: int = 0
    optimization_requested: bool = False
    applied_count: int = 0
    kept_count: int = 0
    manual_count: int = 0


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
    reason_code: str | None = None
    relative_path: Path | None = None
    input_object: str | None = None
    output_name: str | None = None
    object_index: int | None = None
    object_name: str | None = None
    manifest_row_number: int | None = None
    rows: int | None = None
    columns: int | None = None
    rows_before: int | None = None
    columns_before: int | None = None
    rows_after: int | None = None
    columns_after: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
    validation_issues: int | None = None
    validation_errors: int | None = None
    validation_warnings: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    streaming: bool = False
    chunk_size: int | None = None
    chunks_processed: int | None = None
    rows_processed: int | None = None
    input_size_bytes: int | None = None
    overwrite_disposition: str = OVERWRITE_NOT_CHECKED
    directory_disposition: str = DIRECTORY_NOT_CHECKED
    sidecar_disposition: str = SIDECAR_NOT_CHECKED
    potential_sidecar_path: Path | None = None
    same_path: bool = False
    duplicate_output: bool = False
    existing_output: bool = False
    output_inside_input_excluded: bool = False
    read_state: str = BATCH_READ_NOT_CHECKED
    subsystem: str = "filesystem"
    recipe: BatchRecipeOutcome = field(default_factory=BatchRecipeOutcome)
    policy: BatchPolicyOutcome = field(default_factory=BatchPolicyOutcome)


@dataclass
class BatchPlan:
    """
    Planned batch conversion work.
    """

    options: BatchPlanningOptions
    items: list[BatchItem] = field(default_factory=list)
    workload: BatchWorkloadSummary = field(init=False)
    phase: str = field(init=False)
    mode: str = field(init=False)
    checks_not_performed: tuple[str, ...] = field(init=False)


    def __post_init__(self) -> None:
        self.workload = _build_workload_summary(self.options, self.items)
        self.phase = self.options.phase
        self.mode = self.options.mode
        self.checks_not_performed = (
            BATCH_DRY_RUN_UNCHECKED
            if self.mode in {BATCH_MODE_DRY_RUN, BATCH_MODE_FILESYSTEM_PLAN}
            else ()
        )
        for item in self.items:
            if item.status == BATCH_STATUS_SKIPPED:
                item.read_state = BATCH_READ_SKIPPED
            if self.options.recipe_path is not None:
                item.recipe = BatchRecipeOutcome(
                    requested=True,
                    recipe_path=self.options.recipe_path,
                    recipe_name=self.options.recipe_name,
                    syntax_status="ready",
                    compatibility_status="not_checked",
                    execution_status="not_checked",
                    step_count=self.options.recipe_step_count,
                )
            if self.options.policy is not None:
                item.policy = BatchPolicyOutcome(
                    requested=True,
                    policy_name=self.options.policy,
                    status="not_checked",
                    optimization_requested=self.options.optimize_types,
                )


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

    @property
    def reason_counts(self) -> dict[str, int]:
        """Return complete deterministic counts for stable item reason codes."""

        counts: dict[str, int] = {}
        for item in self.items:
            if item.reason_code is None:
                continue
            counts[item.reason_code] = counts.get(item.reason_code, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def would_replace_count(self) -> int:
        return sum(
            item.overwrite_disposition == OVERWRITE_WOULD_REPLACE
            for item in self.items
        )

    @property
    def would_create_directory_count(self) -> int:
        return sum(
            item.directory_disposition == DIRECTORY_WOULD_CREATE
            for item in self.items
        )

    @property
    def path_conflict_count(self) -> int:
        return sum(
            item.same_path or item.duplicate_output or item.existing_output
            for item in self.items
        )

    def summary_dict(self) -> dict[str, Any]:
        """Return complete filesystem-plan counts without item detail."""

        return {
            "total": self.total_count,
            "pending": self.pending_count,
            "skipped": self.skipped_count,
            "blocked": self.blocked_count,
            "would_replace": self.would_replace_count,
            "would_create_directories": self.would_create_directory_count,
            "path_conflicts": self.path_conflict_count,
            "reason_counts": self.reason_counts,
            "total_input_bytes": self.workload.total_input_bytes,
        }


@dataclass
class BatchResult:
    """
    Result of executing a batch conversion plan.
    """

    plan: BatchPlan
    items: list[BatchItem] = field(default_factory=list)
    workload: BatchWorkloadSummary | None = None
    phase: str = field(init=False, default=BATCH_PHASE_EXECUTION)
    mode: str = field(init=False, default=BATCH_MODE_EXECUTION)


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

    @property
    def total_streamed_rows(self) -> int:
        """Return streamed rows across successful items."""

        return sum(
            item.rows_processed or 0
            for item in self.success_items()
            if item.streaming
        )

    @property
    def total_streamed_chunks(self) -> int:
        """Return streamed chunks across successful items."""

        return sum(
            item.chunks_processed or 0
            for item in self.success_items()
            if item.streaming
        )


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
        streaming_enabled=options.streaming_enabled,
        chunk_size=options.chunk_size,
        object_mode=options.object_mode,
        memory_note=(MULTI_WORKER_MEMORY_NOTE if options.workers > 1 else None),
    )
