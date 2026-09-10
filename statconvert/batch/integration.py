from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Callable

from statconvert.batch.models import (
    BATCH_DETAIL_LIMIT,
    BATCH_MODE_FULL_PLAN,
    BATCH_PHASE_FULL_PLAN,
    BATCH_READ_FAILED,
    BATCH_READ_READY,
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_PENDING,
    BatchDiagnostic,
    BatchItem,
    BatchPlan,
)
from statconvert.batch.planning import output_writes_metadata_sidecar
from statconvert.dataset import Dataset
from statconvert.dataset_options import DatasetReadOptions
from statconvert.metadata.sidecar import SIDECAR_SUFFIX
from statconvert.transfer import (
    TransferPlanningError,
    apply_transfer_plan,
    build_transfer_plan,
)
from statconvert.transformations import PortableTransformRecipe, compile_transform_recipe
from statconvert.transformations.planning import plan_transform_recipe


class BatchIntegrationError(Exception):
    """A recipe or policy prevented one batch item from continuing."""

    def __init__(self, message: str, *, code: str, subsystem: str) -> None:
        super().__init__(message)
        self.code = code
        self.subsystem = subsystem


def process_batch_dataset(
    item: BatchItem,
    dataset: Dataset,
    *,
    recipe: PortableTransformRecipe | None = None,
    policy: str | None = None,
    optimize_types: bool = False,
    execution: bool,
    overwrite: bool,
    protected_paths: frozenset[str] = frozenset(),
) -> Dataset:
    """Apply existing recipe and policy machinery to one safely copied dataset."""

    item.read_state = BATCH_READ_READY
    item.rows_before = dataset.rows
    item.columns_before = len(dataset.columns)
    working = dataset.copy(deep=True) if recipe is not None or optimize_types else dataset

    if recipe is not None:
        working = _process_recipe(item, working, recipe, execution=execution)
    if policy is not None:
        working = _process_policy(
            item,
            working,
            policy=policy,
            optimize_types=optimize_types,
            overwrite=overwrite,
            protected_paths=protected_paths,
        )

    item.rows_after = working.rows
    item.columns_after = len(working.columns)
    item.rows = working.rows
    item.columns = len(working.columns)
    return working


def build_batch_full_plan(
    plan: BatchPlan,
    *,
    recipe: PortableTransformRecipe | None = None,
    policy: str | None = None,
    optimize_types: bool = False,
    workers: int = 1,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
) -> BatchPlan:
    """Read and assess pending items without creating any outputs or directories."""

    planned = BatchPlan(
        options=replace(
            plan.options,
            phase=BATCH_PHASE_FULL_PLAN,
            mode=BATCH_MODE_FULL_PLAN,
        ),
        items=deepcopy(plan.items),
    )
    pending = [
        (index, item)
        for index, item in enumerate(planned.items)
        if item.status == BATCH_STATUS_PENDING
    ]
    if workers == 1:
        for _, item in pending:
            _plan_one_item(
                item,
                recipe=recipe,
                policy=policy,
                optimize_types=optimize_types,
                object_selector=object_selector,
                read_options=read_options,
                on_option_warning=on_option_warning,
                overwrite=plan.options.overwrite,
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _plan_one_item,
                    item,
                    recipe=recipe,
                    policy=policy,
                    optimize_types=optimize_types,
                    object_selector=object_selector,
                    read_options=read_options,
                    on_option_warning=on_option_warning,
                    overwrite=plan.options.overwrite,
                ): index
                for index, item in pending
            }
            for future in as_completed(futures):
                future.result()
    _mark_sidecar_collisions(planned)
    return planned


def _plan_one_item(
    item: BatchItem,
    *,
    recipe: PortableTransformRecipe | None,
    policy: str | None,
    optimize_types: bool,
    object_selector: str | None,
    read_options: DatasetReadOptions | None,
    on_option_warning: Callable[[str], None] | None,
    overwrite: bool,
) -> None:
    from statconvert.registry import read_dataset

    selected_object = item.input_object or object_selector
    try:
        dataset = read_dataset(
            item.input_file,
            object_selector=selected_object,
            options=read_options,
            on_option_warning=on_option_warning,
        )
    except Exception as exc:
        item.read_state = BATCH_READ_FAILED
        _block(
            item,
            code="INPUT_READ_FAILED",
            message=f"Dataset could not be read: {exc}",
            subsystem="read",
        )
        return

    try:
        process_batch_dataset(
            item,
            dataset,
            recipe=recipe,
            policy=policy,
            optimize_types=optimize_types,
            execution=False,
            overwrite=overwrite,
        )
    except BatchIntegrationError as exc:
        _block(item, code=exc.code, message=str(exc), subsystem=exc.subsystem)
    except Exception as exc:
        _block(
            item,
            code="FULL_PLAN_ITEM_FAILED",
            message=f"Item planning failed: {exc}",
            subsystem="policy" if policy is not None else "recipe",
        )


def _process_recipe(
    item: BatchItem,
    dataset: Dataset,
    recipe: PortableTransformRecipe,
    *,
    execution: bool,
) -> Dataset:
    if item.output_file is None:
        raise BatchIntegrationError(
            "Recipe cannot run without a planned output.",
            code="RECIPE_OUTPUT_NOT_PLANNED",
            subsystem="recipe",
        )
    outcome = item.recipe
    outcome.step_count = len(recipe.steps)
    bound = recipe.bind(
        input_file=str(item.input_file),
        output_file=str(item.output_file),
        overwrite=False,
    )
    compatibility = plan_transform_recipe(bound, dataset.columns)
    diagnostics = sorted(
        (
            *(("error", issue) for issue in compatibility.errors),
            *(("warning", issue) for issue in compatibility.warnings),
        ),
        key=lambda entry: (entry[1].step_index, entry[0], entry[1].code, entry[1].message),
    )
    outcome.warning_count = len(compatibility.warnings)
    outcome.error_count = len(compatibility.errors)
    outcome.diagnostics = [
        BatchDiagnostic(
            code=issue.code,
            message=issue.message,
            severity=severity,
            step_index=issue.step_index,
            step_type=issue.step_type.value,
            column=issue.referenced_column,
            field=issue.field,
            suggestion=issue.suggestion,
        )
        for severity, issue in diagnostics[:BATCH_DETAIL_LIMIT]
    ]
    outcome.diagnostics_omitted = len(diagnostics) - len(outcome.diagnostics)
    if not compatibility.valid:
        outcome.compatibility_status = "blocked"
        outcome.execution_status = "not_run"
        raise BatchIntegrationError(
            "Transform recipe is incompatible with this dataset.",
            code="RECIPE_COMPATIBILITY_BLOCKED",
            subsystem="recipe",
        )
    outcome.compatibility_status = "warnings" if compatibility.warnings else "ready"
    try:
        transformed = compile_transform_recipe(bound, dataset.columns).apply(dataset)
    except Exception as exc:
        outcome.execution_status = "failed"
        raise BatchIntegrationError(
            f"Transform recipe failed: {exc}",
            code="RECIPE_EXECUTION_FAILED",
            subsystem="recipe",
        ) from exc
    outcome.execution_status = "success" if execution else "simulated"
    return transformed


def _process_policy(
    item: BatchItem,
    dataset: Dataset,
    *,
    policy: str,
    optimize_types: bool,
    overwrite: bool,
    protected_paths: frozenset[str],
) -> Dataset:
    if item.output_file is None:
        raise BatchIntegrationError(
            "Transfer policy cannot run without a planned output.",
            code="POLICY_OUTPUT_NOT_PLANNED",
            subsystem="policy",
        )
    outcome = item.policy
    try:
        plan = build_transfer_plan(
            dataset,
            source_path=item.input_file,
            target=item.output_file.suffix,
            policy=policy,
            object_selector=item.input_object,
        )
    except TransferPlanningError as exc:
        outcome.status = "failed"
        raise BatchIntegrationError(
            f"Transfer policy planning failed: {exc}",
            code=exc.code,
            subsystem="policy",
        ) from exc
    except Exception as exc:
        outcome.status = "failed"
        raise BatchIntegrationError(
            f"Transfer policy planning failed: {exc}",
            code="TRANSFER_POLICY_PLANNING_FAILED",
            subsystem="policy",
        ) from exc
    outcome.status = plan.status
    outcome.decision_counts = dict(sorted(Counter(d.action for d in plan.decisions).items()))
    outcome.issue_counts = dict(sorted(Counter(issue.severity for issue in plan.issues).items()))
    outcome.issue_code_counts = dict(sorted(Counter(issue.code for issue in plan.issues).items()))
    outcome.metadata_disposition_counts = dict(
        sorted(Counter(entry.disposition for entry in plan.metadata).items())
    )
    outcome.manual_count = outcome.decision_counts.get("manual", 0)
    issues = list(plan.issues)
    outcome.diagnostics = [
        BatchDiagnostic(
            code=issue.code,
            message=issue.message,
            severity=issue.severity,
            column=issue.column,
            field=issue.field,
            suggestion=issue.suggestion,
        )
        for issue in issues[:BATCH_DETAIL_LIMIT]
    ]
    outcome.diagnostics_omitted = len(issues) - len(outcome.diagnostics)
    sidecar_count = outcome.metadata_disposition_counts.get("sidecar", 0)
    metadata_mode = str(plan.target.get("metadata_mode", ""))
    item.sidecar_disposition = (
        "required"
        if sidecar_count
        else "optional"
        if "sidecar" in metadata_mode
        else "none"
    )
    plans_sidecar = item.sidecar_disposition in {"required", "optional"}
    if not plans_sidecar:
        item.potential_sidecar_path = None
    if plans_sidecar and item.potential_sidecar_path is None:
        item.potential_sidecar_path = Path(f"{item.output_file}{SIDECAR_SUFFIX}")
    if plans_sidecar and item.potential_sidecar_path is not None:
        if _path_key(item.potential_sidecar_path) in protected_paths:
            raise BatchIntegrationError(
                "Required metadata sidecar conflicts with a selected source or primary output.",
                code="SIDECAR_PATH_CONFLICT",
                subsystem="preflight",
            )
        if item.potential_sidecar_path.exists() and not overwrite:
            raise BatchIntegrationError(
                "Required metadata sidecar already exists and overwrite is disabled.",
                code="SIDECAR_OUTPUT_EXISTS",
                subsystem="preflight",
            )
    if plan.status == "blocked":
        raise BatchIntegrationError(
            "Transfer policy blocked conversion.",
            code="TRANSFER_POLICY_BLOCKED",
            subsystem="policy",
        )
    if not optimize_types:
        outcome.kept_count = len(plan.decisions)
        return dataset
    try:
        application = apply_transfer_plan(dataset, plan)
    except Exception as exc:
        outcome.status = "failed"
        raise BatchIntegrationError(
            f"Transfer optimization failed: {exc}",
            code="TRANSFER_APPLICATION_FAILED",
            subsystem="policy",
        ) from exc
    outcome.applied_count = application.applied_count
    outcome.kept_count = len(application.retained_columns)
    return application.dataset


def _mark_sidecar_collisions(plan: BatchPlan) -> None:
    primary_paths = {
        _path_key(item.output_file)
        for item in plan.items
        if item.output_file is not None
    }
    source_paths = {_path_key(item.input_file) for item in plan.items}
    sidecars: dict[str, list[BatchItem]] = {}
    for item in plan.items:
        if item.status != BATCH_STATUS_PENDING or item.output_file is None:
            continue
        if (
            item.sidecar_disposition not in {"required", "optional"}
            and not output_writes_metadata_sidecar(item.output_file)
        ):
            continue
        if item.potential_sidecar_path is None:
            continue
        key = _path_key(item.potential_sidecar_path)
        sidecars.setdefault(key, []).append(item)
        if key in primary_paths or key in source_paths:
            _block(
                item,
                code="SIDECAR_PATH_CONFLICT",
                message="Required sidecar conflicts with a selected source or primary output.",
                subsystem="preflight",
            )
        elif item.potential_sidecar_path.exists() and not plan.options.overwrite:
            _block(
                item,
                code="SIDECAR_OUTPUT_EXISTS",
                message="Metadata sidecar already exists and overwrite is disabled.",
                subsystem="preflight",
            )
    for colliding in sidecars.values():
        if len(colliding) > 1:
            for item in colliding:
                _block(
                    item,
                    code="DUPLICATE_SIDECAR_PATH",
                    message="Multiple items require the same sidecar path.",
                    subsystem="preflight",
                )


def _block(item: BatchItem, *, code: str, message: str, subsystem: str) -> None:
    item.status = BATCH_STATUS_BLOCKED
    item.reason_code = code
    item.reason = message
    item.subsystem = subsystem


def _path_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix().casefold()
