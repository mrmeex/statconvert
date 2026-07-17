from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

from statconvert.batch.exceptions import BatchError
from statconvert.batch.models import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SKIPPED,
    BATCH_STATUS_SUCCESS,
    BatchItem,
    BatchPlan,
    BatchResult,
)
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.inspection import ValidationIssue, validate_dataset
from statconvert.transformations.pipeline import TransformationPipeline


BatchItemCallback = Callable[[BatchItem], None]


def execute_batch_plan(
    plan: BatchPlan,
    fail_fast: bool = False,
    create_output_dirs: bool = True,
    workers: int = 1,
    validate: bool = False,
    strict_validation: bool = False,
    target_format: str | None = None,
    on_item_start: BatchItemCallback | None = None,
    on_item_finish: BatchItemCallback | None = None,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
    transform_pipeline: TransformationPipeline | None = None,
) -> BatchResult:
    """
    Execute pending items sequentially or with a bounded thread pool.
    """

    if workers < 1:
        raise BatchError(
            "Workers must be 1 or greater."
        )
    if strict_validation and not validate:
        raise BatchError(
            "Strict validation requires --validate."
        )

    validation_target = target_format or plan.options.target_extension

    result_items = [
        replace(
            item
        )
        for item in plan.items
    ]
    if workers == 1:
        _execute_sequential(
            result_items,
            fail_fast=fail_fast,
            create_output_dirs=create_output_dirs,
            overwrite=plan.options.overwrite,
            validate=validate,
            strict_validation=strict_validation,
            target_format=validation_target,
            object_selector=object_selector,
            read_options=read_options,
            write_options=write_options,
            on_option_warning=on_option_warning,
            transform_pipeline=transform_pipeline,
            on_item_start=on_item_start,
            on_item_finish=on_item_finish,
        )
    else:
        _execute_parallel(
            result_items,
            fail_fast=fail_fast,
            create_output_dirs=create_output_dirs,
            overwrite=plan.options.overwrite,
            workers=workers,
            validate=validate,
            strict_validation=strict_validation,
            target_format=validation_target,
            object_selector=object_selector,
            read_options=read_options,
            write_options=write_options,
            on_option_warning=on_option_warning,
            transform_pipeline=transform_pipeline,
            on_item_start=on_item_start,
            on_item_finish=on_item_finish,
        )

    return BatchResult(
        plan=plan,
        items=result_items,
    )


def _execute_sequential(
    items: list[BatchItem],
    fail_fast: bool,
    create_output_dirs: bool,
    overwrite: bool,
    validate: bool,
    strict_validation: bool,
    target_format: str | None,
    object_selector: str | None,
    read_options: DatasetReadOptions | None,
    write_options: DatasetWriteOptions | None,
    on_option_warning: Callable[[str], None] | None,
    transform_pipeline: TransformationPipeline | None,
    on_item_start: BatchItemCallback | None,
    on_item_finish: BatchItemCallback | None,
) -> None:
    """Execute items in plan order, preserving the original behavior."""

    fail_fast_triggered = False

    for item in items:
        if fail_fast_triggered:
            _mark_not_processed_due_to_fail_fast(
                item
            )
            _call_callback(
                on_item_finish,
                item,
            )
            continue

        if item.status in {
            BATCH_STATUS_SKIPPED,
            BATCH_STATUS_BLOCKED,
        }:
            _call_callback(
                on_item_finish,
                item,
            )
            continue

        if item.status != BATCH_STATUS_PENDING:
            _call_callback(
                on_item_finish,
                item,
            )
            continue

        _call_callback(
            on_item_start,
            item,
        )
        _execute_one_item(
            item,
            create_output_dirs=create_output_dirs,
            overwrite=overwrite,
            validate=validate,
            strict_validation=strict_validation,
            target_format=target_format,
            object_selector=object_selector,
            read_options=read_options,
            write_options=write_options,
            on_option_warning=on_option_warning,
            transform_pipeline=transform_pipeline,
        )
        _call_callback(
            on_item_finish,
            item,
        )

        if fail_fast and item.status == BATCH_STATUS_FAILED:
            fail_fast_triggered = True

def _execute_parallel(
    items: list[BatchItem],
    fail_fast: bool,
    create_output_dirs: bool,
    overwrite: bool,
    workers: int,
    validate: bool,
    strict_validation: bool,
    target_format: str | None,
    object_selector: str | None,
    read_options: DatasetReadOptions | None,
    write_options: DatasetWriteOptions | None,
    on_option_warning: Callable[[str], None] | None,
    transform_pipeline: TransformationPipeline | None,
    on_item_start: BatchItemCallback | None,
    on_item_finish: BatchItemCallback | None,
) -> None:
    """Execute pending items concurrently while collecting results on the main thread."""

    pending = [
        (index, item)
        for index, item in enumerate(items)
        if item.status == BATCH_STATUS_PENDING
    ]
    terminal = [item for item in items if item.status != BATCH_STATUS_PENDING]

    for item in terminal:
        _call_callback(on_item_finish, item)

    futures: dict[Future[BatchItem], tuple[int, BatchItem]] = {}
    fail_fast_triggered = False

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, item in pending:
            _call_callback(on_item_start, item)
            future = executor.submit(
                _execute_one_item,
                replace(item),
                create_output_dirs,
                overwrite,
                validate,
                strict_validation,
                target_format,
                object_selector,
                read_options,
                write_options,
                on_option_warning,
                transform_pipeline,
            )
            futures[future] = (index, item)

        for future in as_completed(futures):
            index, planned_item = futures[future]

            if future.cancelled():
                _mark_not_processed_due_to_fail_fast(planned_item)
                completed_item = planned_item
            else:
                completed_item = _collect_worker_result(future, planned_item)

            items[index] = completed_item
            _call_callback(on_item_finish, completed_item)

            if (
                fail_fast
                and completed_item.status == BATCH_STATUS_FAILED
                and not fail_fast_triggered
            ):
                fail_fast_triggered = True
                # Work already running is allowed to finish. Futures that have not
                # started are cancelled and later marked skipped in plan order.
                for remaining in futures:
                    if remaining is not future:
                        remaining.cancel()


def _execute_one_item(
    item: BatchItem,
    create_output_dirs: bool = True,
    overwrite: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    target_format: str | None = None,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
    transform_pipeline: TransformationPipeline | None = None,
) -> BatchItem:
    """Complete one independent item and return it to the collecting thread."""

    _execute_item(
        item,
        create_output_dirs=create_output_dirs,
        overwrite=overwrite,
        validate=validate,
        strict_validation=strict_validation,
        target_format=target_format,
        object_selector=object_selector,
        read_options=read_options,
        write_options=write_options,
        on_option_warning=on_option_warning,
        transform_pipeline=transform_pipeline,
    )
    return item


def _collect_worker_result(
    future: Future[BatchItem],
    item: BatchItem,
) -> BatchItem:
    """Convert an unexpected worker exception into a normal failed item."""

    try:
        return future.result()
    except Exception as exc:
        item.status = BATCH_STATUS_FAILED
        item.reason = "Conversion failed"
        item.error = str(exc)
        item.finished_at = _timestamp()
        return item


def _execute_item(
    item: BatchItem,
    create_output_dirs: bool,
    overwrite: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    target_format: str | None = None,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
    transform_pipeline: TransformationPipeline | None = None,
) -> None:
    """
    Execute one pending batch item.
    """

    start = perf_counter()
    item.started_at = _timestamp()

    try:
        _validate_item_ready(
            item,
            overwrite=overwrite,
        )

        item_object_selector = (
            item.input_object
            if item.input_object is not None
            else object_selector
        )
        dataset = _read_file(
            str(item.input_file),
            object_selector=item_object_selector,
            read_options=read_options,
            on_option_warning=on_option_warning,
        )
        if transform_pipeline is not None:
            dataset = transform_pipeline.apply(dataset)
        item.rows = dataset.rows
        item.columns = len(dataset.columns)

        if validate:
            issues = validate_dataset(
                dataset,
                target_format=target_format,
            )
            _record_validation(item, issues)
            _raise_for_validation_issues(
                issues,
                strict_validation=strict_validation,
            )

        if create_output_dirs:
            item.output_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        _write_file(
            dataset,
            str(item.output_file),
            write_options=write_options,
            on_option_warning=on_option_warning,
        )
        item.status = BATCH_STATUS_SUCCESS
        item.reason = None
        item.error = None

    except _BatchValidationFailure as exc:
        item.status = BATCH_STATUS_FAILED
        item.reason = "Validation failed"
        item.error = str(exc)

    except Exception as exc:
        item.status = BATCH_STATUS_FAILED
        item.reason = "Conversion failed"
        item.error = str(
            exc
        )

    finally:
        item.duration_seconds = perf_counter() - start
        item.finished_at = _timestamp()


def _validate_item_ready(
    item: BatchItem,
    *,
    overwrite: bool,
) -> None:
    """
    Validate execution safety for one pending item.
    """

    if not item.input_file.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {item.input_file}"
        )

    if item.output_file is None:
        raise ValueError(
            "Output file is not planned."
        )

    if _same_path(
        item.input_file,
        item.output_file,
    ):
        raise ValueError(
            "Input and output path are the same."
        )

    if item.output_file.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {item.output_file}\n"
            "Use --overwrite to replace it."
        )


def _read_file(
    input_file: str,
    *,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
):
    """
    Convert a file through registered backends without UI output.
    """

    from statconvert.registry import read_dataset

    dataset = read_dataset(
        input_file,
        object_selector=object_selector,
        options=read_options,
        on_option_warning=on_option_warning,
    )

    return dataset


def _write_file(
    dataset,
    output_file: str,
    *,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
) -> None:
    """Write a dataset through its registered backend."""

    from statconvert.registry import write_dataset

    write_dataset(
        dataset,
        output_file,
        options=write_options,
        on_option_warning=on_option_warning,
    )


class _BatchValidationFailure(Exception):
    """Internal signal that validation should stop one conversion."""


def _record_validation(
    item: BatchItem,
    issues: list[ValidationIssue],
) -> None:
    """Record stable validation counts on a result item."""

    item.validation_issues = len(issues)
    item.validation_errors = sum(issue.severity == "error" for issue in issues)
    item.validation_warnings = sum(issue.severity == "warning" for issue in issues)


def _raise_for_validation_issues(
    issues: list[ValidationIssue],
    strict_validation: bool,
) -> None:
    """Stop conversion for errors, or warnings when strict validation is enabled."""

    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    if not errors and not (strict_validation and warnings):
        return

    summary = f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s)"
    relevant = errors + warnings if strict_validation else errors
    messages = "; ".join(issue.message for issue in relevant)
    if messages:
        summary = f"{summary}. {messages}"
    raise _BatchValidationFailure(summary)


def _mark_not_processed_due_to_fail_fast(
    item: BatchItem
) -> None:
    """
    Mark remaining pending items deterministically after fail-fast stops execution.
    """

    if item.status == BATCH_STATUS_PENDING:
        item.status = BATCH_STATUS_SKIPPED
        item.reason = "Not processed due to fail-fast"


def _same_path(
    left: Path,
    right: Path,
) -> bool:
    """
    Return whether two paths resolve to the same location.
    """

    return left.resolve(
        strict=False
    ) == right.resolve(
        strict=False
    )


def _timestamp() -> str:
    """
    Return a UTC timestamp string for execution metadata.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def _call_callback(
    callback: BatchItemCallback | None,
    item: BatchItem,
) -> None:
    """
    Invoke an optional callback.
    """

    if callback is None:
        return

    callback(
        item
    )
