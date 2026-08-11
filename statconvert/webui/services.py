"""Presentation-neutral adapters for the first functional browser workflows."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib
from typing import Any, Callable

from statconvert.batch import (
    BatchError,
    batch_plan_to_rows,
    batch_result_to_rows,
    build_batch_plan,
    execute_batch_plan,
    write_batch_result_report,
)
from statconvert.contracts import validate_schema_contract_file
from statconvert.collection import build_collection_plan, execute_collection_plan
from statconvert.compare import (
    CompareOptions,
    compare_datasets,
    comparison_to_json_payload,
    resolve_compare_object_selectors,
    write_compare_report,
)
from statconvert.config import (
    create_template,
    execute_config,
    load_config,
    to_toml,
    validate_config,
    write_config,
)
from statconvert.converter import transform as convert_file
from statconvert.dataset import Dataset
from statconvert.exceptions import ConfigError, StatConvertError
from statconvert.inspection import (
    frequency_tables,
    missing_profile,
    profile_columns,
    summarize_dataset,
    validate_dataset,
)
from statconvert.metadata.scripts import export_metadata_script
from statconvert.metadata.diagnostics import build_metadata_diagnostics
from statconvert.metadata.editing import (
    parse_metadata_patch_data,
    preview_metadata_patch,
    save_metadata_sidecar,
)
from statconvert.object_discovery import build_object_discovery_report
from statconvert.object_manifest import read_object_manifest
from statconvert.output_paths import validate_output_root_directory
from statconvert.registry import (
    list_backend_capabilities,
    list_backends,
    list_formats,
    can_write_format,
    format_supports_objects,
    get_file_format,
    get_reader_for_file,
    get_writer_for_file,
    normalize_extension,
    read_dataset,
)
from statconvert.reporting import (
    build_dataset_report,
    dataset_report_summary_dict,
    resolve_report_options,
    write_dataset_report,
)
from statconvert.serialization import make_json_safe
from statconvert.streaming.execution import execute_streaming_convert
from statconvert.streaming.options import (
    DEFAULT_STREAMING_CHUNK_SIZE,
    validate_chunk_size,
)
from statconvert.streaming.plan import build_streaming_plan
from statconvert.streaming.validation import (
    require_streaming_validation_input,
    validate_streaming_contract,
)
from statconvert.transformer import transform_file
from statconvert.transformations import (
    compile_transform_recipe,
    parse_portable_recipe,
    portable_recipe_from_ordered_steps,
    portable_recipe_to_toml,
    preflight_transform_output,
    preview_full_transform,
    preview_transform_recipe as build_transform_preview,
    recipe_from_ordered_steps,
    save_portable_recipe,
)
from statconvert.transformations.expressions import parse_expression
from statconvert.transformations.language import expression_function_specs
from statconvert.transformations.planning import (
    plan_transform_recipe as build_transform_recipe_plan,
)

from .api.models import (
    BatchRequest,
    CollectRequest,
    CollectManifestStarterRequest,
    CompareRequest,
    ConfigExportRequest,
    ConfigInitRequest,
    ConfigTextRequest,
    ConvertRequest,
    ExpressionValidationRequest,
    MetadataScriptExportRequest,
    MetadataSidecarEditRequest,
    ReportRequest,
    TransformRequest,
    TransformRecipeLoadRequest,
    TransformRecipeSaveRequest,
    ValidateRequest,
)
from .jobs import JobContext
from .settings import logging_cli_arguments, ui_logging_context


MAX_INSPECT_COLUMNS = 200
MAX_METADATA_VALUES = 100
MAX_TRANSFORM_PREVIEW_ROWS = 100
COLLECT_MANIFEST_EXAMPLE = (
    "input_file,input_object,output_object\n"
    "data.csv,,Data\n"
    "workbook.xlsx,Sheet1,Lookup\n"
)


class WebUiRequestError(StatConvertError):
    """A browser request is invalid before business-layer execution."""


def inspect_local_path(path_text: str) -> dict[str, Any]:
    """Return safe facts for one explicit local path."""

    path = _existing_path(path_text)
    details: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "exists": True,
        "is_file": path.is_file(),
        "is_directory": path.is_dir(),
    }
    if path.is_file():
        details["size_bytes"] = path.stat().st_size
        details["extension"] = path.suffix.lower()
        try:
            details["format"] = get_file_format(str(path))
            details["readable"] = True
        except ValueError as exc:
            details["format"] = None
            details["readable"] = False
            details["message"] = str(exc)
    return details


def browse_local_path(
    *,
    root_path: str,
    directory: str,
    selection: str,
    extensions: list[str],
) -> dict[str, Any]:
    """List one directory while staying under a user-confirmed local root."""

    root = _existing_directory(root_path).resolve()
    current = _existing_directory(directory).resolve()
    if not _is_relative_to(current, root):
        raise WebUiRequestError(
            f"Browse directory is outside the confirmed root: {current}",
            suggestion="Choose a directory inside the confirmed starting folder.",
        )
    normalized_extensions = {
        extension.strip().casefold()
        if extension.strip().startswith(".")
        else f".{extension.strip().casefold()}"
        for extension in extensions
        if extension.strip()
    }
    entries = []
    try:
        children = sorted(
            current.iterdir(),
            key=lambda path: (not path.is_dir(), path.name.casefold()),
        )
    except OSError as exc:
        raise WebUiRequestError(f"Unable to browse directory {current}: {exc}") from None
    for child in children:
        is_directory = child.is_dir()
        if not is_directory and selection == "directory":
            continue
        if (
            not is_directory
            and normalized_extensions
            and child.suffix.casefold() not in normalized_extensions
        ):
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "is_directory": is_directory,
                "size_bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return {
        "root_path": str(root),
        "directory": str(current),
        "parent": str(current.parent) if current != root else None,
        "selection": selection,
        "entries": entries[:1000],
        "truncated": len(entries) > 1000,
    }


def inspect_objects(path: str, *, recursive: bool) -> dict[str, Any]:
    report = build_object_discovery_report(path, recursive=recursive)
    return make_json_safe(report.to_json_dict())


def inspect_info(path: str, object_selector: str | None) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    return {
        **make_json_safe(dataset.summary()),
        "source_file": dataset.source_file or path,
        "metadata": make_json_safe(dataset.metadata_summary()),
        "column_details": _inspect_schema_rows(dataset),
    }


def inspect_peek(
    path: str,
    object_selector: str | None,
    *,
    rows: int,
) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    frame = dataset.preview(rows)
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": make_json_safe(frame.to_dict(orient="records")),
        "returned_rows": len(frame),
        "total_rows": dataset.rows,
    }


def _inspect_schema_rows(dataset: Dataset) -> list[dict[str, Any]]:
    """Return the bounded, presentation-neutral column overview."""

    storage_types = dataset.storage_types()
    variables = dataset.variables_metadata()
    rows = []
    for name in [str(column) for column in dataset.columns[:MAX_INSPECT_COLUMNS]]:
        variable = variables.get(name)
        rows.append(
            {
                "name": name,
                "storage_type": storage_types.get(name),
                "label": variable.label if variable else None,
                "display_format": variable.display_format if variable else None,
                "measure": variable.measure if variable else None,
                "role": variable.role if variable else None,
                "value_label_count": (
                    len(variable.value_labels) if variable else 0
                ),
            }
        )
    return rows


def inspect_schema(path: str, object_selector: str | None) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    rows = _inspect_schema_rows(dataset)
    return {
        "columns": rows,
        "returned_columns": len(rows),
        "total_columns": len(dataset.columns),
        "truncated": len(dataset.columns) > len(rows),
    }


def inspect_labels(path: str, object_selector: str | None) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    value_labels = dataset.value_labels()
    bounded_value_labels = {
        column: [
            {"value": make_json_safe(value), "label": label}
            for value, label in list(labels.items())[:MAX_METADATA_VALUES]
        ]
        for column, labels in list(value_labels.items())[:MAX_INSPECT_COLUMNS]
    }
    return {
        "variable_labels": dataset.variable_labels(),
        "value_labels": bounded_value_labels,
        "limits": {
            "columns": MAX_INSPECT_COLUMNS,
            "values_per_column": MAX_METADATA_VALUES,
        },
    }


def inspect_metadata(path: str, object_selector: str | None) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    metadata = dataset.get_normalized_metadata()
    provenance = dataset.metadata_provenance or {}
    column_provenance = provenance.get("columns", {})
    column_sources: dict[str, int] = {}
    if isinstance(column_provenance, dict):
        for source in column_provenance.values():
            name = str(source)
            column_sources[name] = column_sources.get(name, 0) + 1
    variables = []
    for variable in list(metadata.variables.values())[:MAX_INSPECT_COLUMNS]:
        variables.append(
            {
                "name": variable.name,
                "label": variable.label,
                "storage_type": variable.storage_type,
                "display_format": variable.display_format,
                "display_width": variable.display_width,
                "measure": variable.measure,
                "role": variable.role,
                "width": variable.width,
                "decimals": variable.decimals,
                "missing_values": make_json_safe(
                    variable.missing_values[:MAX_METADATA_VALUES]
                ),
                "missing_ranges": make_json_safe(
                    variable.missing_ranges[:MAX_METADATA_VALUES]
                ),
                "value_labels": [
                    {"value": make_json_safe(value), "label": label}
                    for value, label in list(variable.value_labels.items())[
                        :MAX_METADATA_VALUES
                    ]
                ],
            }
        )
    diagnostics = build_metadata_diagnostics(
        dataset,
        path,
        object_name=object_selector,
        max_columns=MAX_INSPECT_COLUMNS,
    )
    return {
        "dataset": {
            "source_format": metadata.source_format,
            "source_backend": metadata.source_backend,
            "dataset_label": metadata.dataset_label,
            "notes": metadata.notes[:MAX_METADATA_VALUES],
            "metadata_source": provenance.get("dataset"),
            "column_sources": column_sources,
        },
        "summary": dataset.metadata_summary(),
        "variables": variables,
        "returned_variables": len(variables),
        "total_variables": len(metadata.variables),
        "truncated": len(metadata.variables) > len(variables),
        "diagnostics": make_json_safe(asdict(diagnostics)),
    }


def inspect_summary(path: str, object_selector: str | None) -> dict[str, Any]:
    return make_json_safe(asdict(summarize_dataset(_read(path, object_selector))))


def inspect_describe(
    path: str,
    object_selector: str | None,
    columns: list[str] | None,
) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    selected = _bounded_columns(columns)
    profiles = profile_columns(dataset, columns=selected)
    serialized = make_json_safe([asdict(profile) for profile in profiles])
    return {
        "profiles": serialized,
        "column_profiles": [
            {
                key: value
                for key, value in profile.items()
                if key not in {"numeric", "categorical"}
            }
            for profile in serialized
        ],
        "numeric_statistics": [
            {"column": profile["name"], **profile["numeric"]}
            for profile in serialized
            if profile.get("numeric")
        ],
        "categorical_statistics": [
            {"column": profile["name"], **profile["categorical"]}
            for profile in serialized
            if profile.get("categorical")
        ],
        "returned_columns": len(profiles),
    }


def export_inspect_metadata_script(
    request: MetadataScriptExportRequest,
) -> dict[str, Any]:
    """Write a helper script through the existing metadata exporter."""

    input_path = _existing_file(request.path)
    output_path = Path(request.output_path)
    expected_extensions = {"r": ".r", "spss": ".sps", "stata": ".do"}
    expected = expected_extensions[request.format]
    if output_path.suffix.lower() != expected:
        raise WebUiRequestError(
            f"{request.format.upper()} metadata scripts require the {expected} extension.",
            suggestion=f"Choose an output filename ending in {expected}.",
        )
    dataset = _read(str(input_path), request.object_selector)
    written = export_metadata_script(
        dataset,
        input_path,
        output_path,
        overwrite=request.overwrite,
    )
    options = ["--export-script", str(written)]
    if request.overwrite:
        options.append("--overwrite-script")
    return {
        "output_path": str(written),
        "format": request.format,
        "command": inspection_command(
            "metadata",
            str(input_path),
            object_selector=request.object_selector,
            options=options,
        ),
    }


def preview_inspect_metadata_sidecar(
    request: MetadataSidecarEditRequest,
) -> dict[str, Any]:
    """Preview a closed browser patch without creating directories or files."""

    input_path = _existing_file(request.path)
    dataset = _read(str(input_path), request.object_selector)
    patch = parse_metadata_patch_data(request.patch)
    preview, _ = preview_metadata_patch(
        dataset,
        input_path,
        patch,
        request.output_path,
        overwrite=request.overwrite,
        object_name=request.object_selector,
        dry_run=True,
    )
    return make_json_safe(asdict(preview))


def save_inspect_metadata_sidecar(
    request: MetadataSidecarEditRequest,
) -> dict[str, Any]:
    """Revalidate and atomically save one explicitly confirmed browser preview."""

    if not request.confirmed_preview:
        raise WebUiRequestError(
            "Saving metadata requires a confirmed valid preview.",
            suggestion="Preview the current patch, then confirm and save it.",
        )
    input_path = _existing_file(request.path)
    dataset = _read(str(input_path), request.object_selector)
    patch = parse_metadata_patch_data(request.patch)
    preview, edited = preview_metadata_patch(
        dataset,
        input_path,
        patch,
        request.output_path,
        overwrite=request.overwrite,
        object_name=request.object_selector,
        dry_run=False,
    )
    result = save_metadata_sidecar(preview, edited, overwrite=request.overwrite)
    return make_json_safe(asdict(result))


def inspect_frequencies(
    path: str,
    object_selector: str | None,
    columns: list[str] | None,
    *,
    top: int,
    include_missing: bool,
    max_unique: int | None,
) -> dict[str, Any]:
    dataset = _read(path, object_selector)
    selected = _bounded_columns(columns)
    tables = frequency_tables(
        dataset,
        columns=selected,
        top=top,
        include_missing=include_missing,
        max_unique=max_unique,
    )
    return {
        "tables": make_json_safe([asdict(table) for table in tables]),
        "returned_columns": len(tables),
        "top": top,
    }


def inspect_missing(
    path: str,
    object_selector: str | None,
    columns: list[str] | None,
) -> dict[str, Any]:
    profiles = missing_profile(
        _read(path, object_selector),
        columns=_bounded_columns(columns),
    )
    return {
        "profiles": make_json_safe([asdict(profile) for profile in profiles]),
        "returned_columns": len(profiles),
    }


def plan_convert(request: ConvertRequest) -> dict[str, Any]:
    request = _effective_convert_request(request)
    input_path = _existing_file(request.input_path)
    output_path = Path(request.output_path)
    reader = get_reader_for_file(str(input_path))
    writer = get_writer_for_file(str(output_path))
    _validate_target_matches_output(request.target_format, output_path)
    _validate_output_file_plan(
        output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    chunk_size = _effective_chunk_size(request.stream, request.chunk_size)
    streaming_details = None
    if request.stream:
        if request.object_selector is not None:
            raise WebUiRequestError(
                "Streaming conversion does not support object selection.",
                suggestion="Clear the object selector or turn off streaming.",
            )
        streaming_plan = build_streaming_plan(str(input_path), str(output_path))
        streaming_plan.require_executable()
        streaming_details = make_json_safe(streaming_plan)
    return {
        "workflow": "convert",
        "valid": True,
        "command": convert_command(request, chunk_size=chunk_size),
        "details": {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "input_backend": reader.__class__.__name__,
            "output_backend": writer.__class__.__name__,
            "stream": request.stream,
            "chunk_size": chunk_size,
            "streaming": streaming_details,
        },
        "warnings": [],
    }


def execute_convert(request: ConvertRequest, context: JobContext) -> dict[str, Any]:
    request = _effective_convert_request(request)
    plan = plan_convert(request)
    chunk_size = _effective_chunk_size(request.stream, request.chunk_size)
    context.emit("planned", message="Conversion plan validated.", progress=0.1)
    if request.stream:
        result = execute_streaming_convert(
            request.input_path,
            request.output_path,
            chunk_size=chunk_size or DEFAULT_STREAMING_CHUNK_SIZE,
            overwrite=request.overwrite,
            create_dirs=request.create_dirs,
            on_progress=lambda event: context.emit(
                event.event_type,
                progress=_streaming_progress(event.cumulative_rows, event.total_rows),
                data=make_json_safe(event),
            ),
        )
        payload = result.to_dict()
    else:
        context.emit("reading", message="Reading input dataset.", progress=0.2)
        dataset = convert_file(
            request.input_path,
            request.output_path,
            overwrite=request.overwrite,
            create_dirs=request.create_dirs,
            object_selector=request.object_selector,
        )
        payload = {
            "output_path": request.output_path,
            "rows": dataset.rows,
            "columns": len(dataset.columns),
            "streaming": False,
        }
    return {
        "plan": plan,
        "conversion": payload,
    }


def plan_batch(request: BatchRequest) -> dict[str, Any]:
    _validate_batch_request(request)
    _effective_chunk_size(request.stream, request.chunk_size)
    plan = _build_ui_batch_plan(request)
    if request.stream:
        for item in plan.pending_items():
            if item.output_file is None:
                continue
            build_streaming_plan(
                str(item.input_file),
                str(item.output_file),
            ).require_executable()
    container_files = sorted(
        {
            str(item.input_file)
            for item in plan.items
            if item.input_extension
            and format_supports_objects(item.input_extension)
        }
    )
    warnings: list[str] = []
    object_choice_required = bool(
        container_files and request.object_mode == "automatic"
    )
    if object_choice_required:
        warnings.append(
            "Container files were found. Choose Convert all supported objects or "
            "Convert a specific object before running this batch."
        )
    if request.object_mode == "specific":
        warnings.append(
            "The selected object name or zero-based index is applied to every input "
            "file; files without that object will report a per-file failure."
        )
    if plan.has_blockers:
        warnings.append(
            "The plan contains blocked items and cannot run until resolved."
        )
    return {
        "workflow": "batch",
        "valid": not plan.has_blockers and not object_choice_required,
        "command": batch_command(request),
        "details": {
            "workload": make_json_safe(plan.workload),
            "counts": {
                "total": plan.total_count,
                "pending": plan.pending_count,
                "skipped": plan.skipped_count,
                "blocked": plan.blocked_count,
            },
            "items": make_json_safe(batch_plan_to_rows(plan)[:500]),
            "truncated": plan.total_count > 500,
            "container_files": container_files,
            "object_choice_required": object_choice_required,
            "object_mode": request.object_mode,
            "workers": request.workers or 1,
            "workers_automatic": request.workers is None,
        },
        "warnings": warnings,
    }


def execute_batch(request: BatchRequest, context: JobContext) -> dict[str, Any]:
    plan_payload = plan_batch(request)
    if not plan_payload["valid"]:
        if plan_payload["details"].get("object_choice_required"):
            raise BatchError(
                "Batch contains container files that require an object-handling choice.",
                suggestion=(
                    "Choose all supported objects or a specific object, then plan again."
                ),
            )
        raise BatchError(
            "Batch plan contains blocked items.",
            suggestion="Resolve output collisions or enable overwrite, then plan again.",
        )
    plan = _build_ui_batch_plan(request)
    validate_output_root_directory(
        request.output_path,
        create_dirs=request.create_dirs,
    )
    total = max(plan.total_count, 1)
    completed = 0
    context.emit(
        "batch_items_initialized",
        message=f"{plan.total_count} batch items planned.",
        progress=0.0,
        data={
            "total": plan.total_count,
            "items": [
                {
                    "item_index": index,
                    "input_path": str(item.input_file),
                    "output_path": str(item.output_file) if item.output_file else None,
                    "status": (
                        "queued" if item.status == "pending" else item.status
                    ),
                    "message": item.reason,
                }
                for index, item in enumerate(plan.items)
            ],
        },
    )

    def progress(event: Any) -> None:
        nonlocal completed
        if event.kind == "item_finished":
            completed += 1
        ui_status = {
            "pending": "queued",
            "success": "done",
            "failed": "failed",
            "skipped": "skipped",
            "blocked": "failed",
        }.get(event.status, event.status)
        if event.kind == "item_started":
            ui_status = "running"
        context.emit(
            event.kind,
            message=event.message,
            progress=min(0.95, completed / total),
            data={
                **make_json_safe(event),
                "ui_status": ui_status,
                "completed": completed,
                "total": plan.total_count,
            },
        )

    execution_options: dict[str, Any] = {
        "fail_fast": request.fail_fast,
        "create_output_dirs": request.create_dirs,
        "object_selector": (
            request.object_selector if request.object_mode == "specific" else None
        ),
        "on_progress": progress,
    }
    if request.workers is not None:
        execution_options["workers"] = request.workers
    result = execute_batch_plan(plan, **execution_options)
    if request.report_path:
        write_batch_result_report(result, request.report_path)
    return {
        "plan": plan_payload,
        "summary": {
            "total": result.total_count,
            "success": result.success_count,
            "failed": result.failed_count,
            "skipped": result.skipped_count,
            "blocked": result.blocked_count,
        },
        "items": make_json_safe(batch_result_to_rows(result)),
        "report_path": request.report_path,
    }


def transform_functions() -> dict[str, Any]:
    """Return the active safe-expression registry for the visual picker."""

    functions = [spec.to_dict() for spec in expression_function_specs()]
    return {
        "functions": functions,
        "count": len(functions),
        "categories": sorted({str(item["category"]) for item in functions}),
    }


def validate_transform_expression(
    request: ExpressionValidationRequest,
) -> dict[str, Any]:
    """Parse one expression without evaluating dataset values."""

    payload = parse_expression(request.expression).to_dict()
    payload["purpose"] = request.purpose
    payload["source_spans"] = "half-open"
    return make_json_safe(payload)


def plan_transform(request: TransformRequest) -> dict[str, Any]:
    """Read the input schema and plan one canonical ordered recipe."""

    request = _effective_transform_request(request)
    input_path = _existing_file(request.input_path)
    output_path = Path(request.output_path)
    get_reader_for_file(str(input_path))
    get_writer_for_file(str(output_path))
    _validate_target_matches_output(request.target_format, output_path)
    output_preflight = preflight_transform_output(
        input_path,
        output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
        write=False,
    )
    if output_preflight.sidecar_exists and not request.overwrite:
        raise WebUiRequestError(
            f"Metadata sidecar already exists: {output_preflight.sidecar_path}",
            suggestion="Enable overwrite or choose a different output path.",
        )
    _validate_output_file_plan(
        output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    dataset = _read(request.input_path, request.object_selector)
    recipe = _transform_recipe(request)
    plan = build_transform_recipe_plan(
        recipe,
        [str(column) for column in dataset.columns],
    )
    toml = _transform_toml(request)
    return {
        "workflow": "transform",
        "valid": plan.valid,
        "command": transform_command(request),
        "details": {
            "plan": make_json_safe(plan.to_dict()),
            "toml": toml,
            "command_note": (
                "Portable recipes contain ordered steps only. Save the canonical TOML "
                "and run the displayed transform command, or run directly from this UI."
            ),
            "input_path": str(input_path),
            "output_path": str(output_path),
            "object_selector": request.object_selector,
        },
        "warnings": [issue.message for issue in plan.warnings],
    }


def preview_transform(request: TransformRequest) -> dict[str, Any]:
    """Return bounded before/after rows without writing the output path."""

    request = _effective_transform_request(request)
    if request.preview_limit > MAX_TRANSFORM_PREVIEW_ROWS:
        raise WebUiRequestError(
            f"Transform preview is limited to {MAX_TRANSFORM_PREVIEW_ROWS} rows."
        )
    input_path = _existing_file(request.input_path)
    output_path = Path(request.output_path)
    get_reader_for_file(str(input_path))
    get_writer_for_file(str(output_path))
    _validate_target_matches_output(request.target_format, output_path)
    preflight_transform_output(
        input_path,
        output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
        write=False,
    )
    dataset = _read(request.input_path, request.object_selector)
    preview = build_transform_preview(
        dataset,
        _transform_recipe(request),
        limit=request.preview_limit,
    ).to_dict()
    before = dataset.dataframe.head(request.preview_limit)
    return {
        **preview,
        "mode": "sample_preview",
        "before_rows": make_json_safe(before.to_dict(orient="records")),
    }


def preview_full_transform_request(request: TransformRequest) -> dict[str, Any]:
    """Return exact full-Dataset impact without creating output targets."""

    request = _effective_transform_request(request)
    input_path = _existing_file(request.input_path)
    output_path = Path(request.output_path)
    get_reader_for_file(str(input_path))
    get_writer_for_file(str(output_path))
    _validate_target_matches_output(request.target_format, output_path)
    preflight = preflight_transform_output(
        input_path,
        output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
        write=False,
    )
    dataset = _read(request.input_path, request.object_selector)
    portable = _portable_transform_recipe(request)
    return preview_full_transform(
        dataset,
        portable.bind(
            input_file=request.input_path,
            output_file=request.output_path,
            overwrite=request.overwrite,
        ),
        input_path=input_path,
        output_preflight=preflight,
        object_selector=request.object_selector,
        portable_recipe=portable,
        sample_limit=request.preview_limit,
    ).to_dict()


def load_transform_recipe(request: TransformRecipeLoadRequest) -> dict[str, Any]:
    """Parse one explicit portable recipe without changing workflow paths."""

    path = _existing_file(request.path)
    recipe = parse_portable_recipe(path)
    return {
        "path": str(path),
        "recipe": recipe.to_dict(),
        "canonical_toml": portable_recipe_to_toml(recipe),
    }


def save_transform_recipe(request: TransformRecipeSaveRequest) -> dict[str, Any]:
    """Normalize and atomically save visible browser steps on the backend."""

    recipe = portable_recipe_from_ordered_steps(
        [step.to_step_dict() for step in request.steps],
        name=request.name,
        description=request.description,
    )
    path = save_portable_recipe(
        recipe,
        request.output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    return {
        "path": str(path),
        "recipe": recipe.to_dict(),
        "canonical_toml": portable_recipe_to_toml(recipe),
    }


def execute_transform(
    request: TransformRequest,
    context: JobContext,
) -> dict[str, Any]:
    """Execute an ordered recipe through the existing transform service."""

    request = _effective_transform_request(request)
    plan = plan_transform(request)
    if not plan["valid"]:
        raise WebUiRequestError(
            "Transform recipe contains invalid steps.",
            suggestion="Resolve every step error before running the recipe.",
        )
    context.emit("planned", message="Transform recipe validated.", progress=0.1)
    context.emit("transforming", message="Reading and transforming dataset.", progress=0.3)
    transformed = transform_file(
        input_file=request.input_path,
        output_file=request.output_path,
        recipe=_transform_recipe(request),
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
        object_selector=request.object_selector,
    )
    context.emit("written", message="Transformed output written.", progress=0.95)
    return {
        "plan": plan,
        "output_path": request.output_path,
        "rows": transformed.rows,
        "columns": len(transformed.columns),
        "column_names": [str(column) for column in transformed.columns],
    }


def plan_validate(request: ValidateRequest) -> dict[str, Any]:
    input_path = _existing_file(request.path)
    get_reader_for_file(str(input_path))
    if request.target_format:
        _normalize_writable_target(request.target_format)
    if request.schema_contract:
        _existing_file(request.schema_contract)
    if request.stream:
        if not request.schema_contract:
            raise WebUiRequestError(
                "Streaming validation requires a schema contract.",
                suggestion="Select a TOML schema contract or turn off streaming.",
            )
        if request.object_selector is not None:
            raise WebUiRequestError(
                "Streaming validation does not support object selection.",
                suggestion="Clear the object selector or turn off streaming.",
            )
        if request.target_format is not None:
            raise WebUiRequestError(
                "Streaming validation does not support target-readiness checks.",
                suggestion="Clear the target format or turn off streaming.",
            )
        require_streaming_validation_input(input_path)
    chunk_size = _effective_chunk_size(request.stream, request.chunk_size)
    return {
        "workflow": "validate",
        "valid": True,
        "command": validate_command(request, chunk_size=chunk_size),
        "details": {
            "input_path": str(input_path),
            "target_format": request.target_format,
            "schema_contract": request.schema_contract,
            "strict": request.strict,
            "stream": request.stream,
            "chunk_size": chunk_size,
        },
        "warnings": [],
    }


def execute_validate(request: ValidateRequest, context: JobContext) -> dict[str, Any]:
    plan = plan_validate(request)
    context.emit("planned", message="Validation options checked.", progress=0.1)
    if request.stream:
        result = validate_streaming_contract(
            request.path,
            request.schema_contract or "",
            chunk_size=_effective_chunk_size(request.stream, request.chunk_size)
            or DEFAULT_STREAMING_CHUNK_SIZE,
        )
        contract_payload = result.contract_validation.to_dict(strict=request.strict)
        issues = contract_payload["issues"]
        streaming = result.streaming_dict()
    else:
        context.emit("reading", message="Reading dataset.", progress=0.25)
        dataset = _read(request.path, request.object_selector)
        target = (
            _normalize_writable_target(request.target_format)
            if request.target_format
            else None
        )
        issues = [
            asdict(issue)
            for issue in validate_dataset(
                dataset,
                target_format=target,
                strict=request.strict,
            )
        ]
        contract_payload = None
        if request.schema_contract:
            contract_payload = validate_schema_contract_file(
                dataset,
                request.schema_contract,
            ).to_dict(strict=request.strict)
            issues.extend(contract_payload["issues"])
        streaming = None
    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    passed = error_count == 0 and (not request.strict or warning_count == 0)
    return {
        "plan": plan,
        "passed": passed,
        "status": "passed" if passed else "failed",
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": make_json_safe(issues),
        "schema_contract": make_json_safe(contract_payload),
        "streaming": make_json_safe(streaming),
    }


def config_init(request: ConfigInitRequest) -> dict[str, Any]:
    """Create canonical starter TOML, optionally writing it through config services."""

    config = create_template(request.command)
    output_path = None
    if request.output_path:
        output_path = str(
            write_config(
                config,
                request.output_path,
                overwrite=request.overwrite,
                create_dirs=request.create_dirs,
            )
        )
    return {
        "command": config.command,
        "toml": to_toml(config),
        "output_path": output_path,
        "cli_command": config_init_command(request),
    }


def config_load(request: ConfigTextRequest) -> dict[str, Any]:
    """Load one local config path and return its validated canonical TOML."""

    if not request.config_path:
        raise WebUiRequestError("A config path is required for loading.")
    path = _existing_file(request.config_path)
    config = load_config(path)
    return {
        "config_path": str(path),
        "command": config.command,
        "toml": path.read_text(encoding="utf-8"),
        "canonical_toml": to_toml(config),
        "cli_command": _display_command(["statconvert", "config", "validate", str(path)]),
    }


def config_validate(request: ConfigTextRequest) -> dict[str, Any]:
    """Validate supplied or path-based TOML through the existing schema."""

    config = _validated_config(request)
    _validate_config_semantics(config)
    return {
        "valid": True,
        "command": config.command,
        "fields": sorted(config.options),
        "canonical_toml": to_toml(config),
        "cli_command": config_validate_command(request),
    }


def config_export(request: ConfigExportRequest) -> dict[str, Any]:
    """Write editor TOML only after existing schema validation succeeds."""

    config = _config_from_toml(request.toml_text)
    path = write_config(
        config,
        request.output_path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    return {
        "command": config.command,
        "output_path": str(path),
        "toml": to_toml(config),
    }


def execute_config_request(
    request: ConfigTextRequest,
    context: JobContext,
) -> dict[str, Any]:
    """Run a validated config through the existing config execution dispatcher."""

    config = _validated_config(request)
    context.emit("validated", message="Config validated.", progress=0.15)
    from statconvert.cli import (
        _run_batch_config,
        _run_compare_config,
        _run_report_config,
        _run_transform_config,
        collect,
        convert,
        validate,
    )

    context.emit(
        "executing",
        message=f"Running {config.command} config.",
        progress=0.35,
    )
    execute_config(
        config,
        {
            "convert": convert,
            "transform": _run_transform_config,
            "batch": _run_batch_config,
            "compare": _run_compare_config,
            "validate": validate,
            "report": _run_report_config,
            "collect": collect,
        },
    )
    return {
        "command": config.command,
        "config_path": request.config_path,
        "cli_command": config_run_command(request),
        "status": "completed",
    }


def plan_compare(request: CompareRequest) -> dict[str, Any]:
    """Validate two dataset selections and summarize the existing comparison plan."""

    left_selector, right_selector = resolve_compare_object_selectors(
        request.object_selector,
        request.left_object_selector,
        request.right_object_selector,
    )
    left = _read(request.left_path, left_selector)
    right = _read(request.right_path, right_selector)
    options = _compare_options(request)
    if not request.compare_values and request.sample_size is not None:
        raise WebUiRequestError("Sample size cannot be used when value comparison is disabled.")
    return {
        "workflow": "compare",
        "valid": True,
        "command": compare_command(request),
        "details": {
            "left_path": request.left_path,
            "right_path": request.right_path,
            "left_rows": left.rows,
            "right_rows": right.rows,
            "left_columns": [str(column) for column in left.columns],
            "right_columns": [str(column) for column in right.columns],
            "row_matching": "key" if options.key_columns else "positional",
            "compare_values": request.compare_values,
            "sample_size": request.sample_size,
            "max_differences": request.max_differences,
            "report_path": request.report_path,
        },
        "warnings": [],
    }


def execute_compare(request: CompareRequest, context: JobContext) -> dict[str, Any]:
    """Compare datasets through the backend-neutral comparison service."""

    plan = plan_compare(request)
    left_selector, right_selector = resolve_compare_object_selectors(
        request.object_selector,
        request.left_object_selector,
        request.right_object_selector,
    )
    context.emit("reading", message="Reading comparison datasets.", progress=0.2)
    left = _read(request.left_path, left_selector)
    right = _read(request.right_path, right_selector)
    context.emit("comparing", message="Comparing datasets.", progress=0.55)
    comparison = compare_datasets(
        left,
        right,
        compare_values=request.compare_values,
        sample_size=request.sample_size,
        columns=request.columns,
        options=_compare_options(request),
    )
    if request.report_path:
        context.emit("writing", message="Writing comparison report.", progress=0.85)
        write_compare_report(comparison, request.report_path, request.report_format)
    payload = comparison_to_json_payload(comparison)
    return {
        "plan": plan,
        "is_identical": comparison.is_identical,
        "is_compatible": comparison.is_compatible,
        "has_errors": comparison.has_errors,
        "has_warnings": comparison.has_warnings,
        "report_path": request.report_path,
        "comparison": make_json_safe(payload),
    }


def plan_report(request: ReportRequest) -> dict[str, Any]:
    """Validate dataset-report options without writing output."""

    dataset = _read(request.input_path, request.object_selector)
    report_options = _report_options(request)
    _validate_output_file_plan(
        Path(request.output_path),
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    if request.schema_contract and not report_options.include_validation:
        raise WebUiRequestError(
            "A schema contract requires the report validation section."
        )
    return {
        "workflow": "report",
        "valid": True,
        "command": report_command(request),
        "details": {
            "input_path": request.input_path,
            "output_path": request.output_path,
            "rows": dataset.rows,
            "columns": len(dataset.columns),
            "preset": report_options.preset,
            "sections": [
                name
                for name in (
                    "summary", "schema", "metadata", "labels", "missing",
                    "describe", "frequencies", "validation",
                )
                if getattr(report_options, f"include_{name}")
            ],
            "max_table_rows": report_options.max_table_rows,
        },
        "warnings": [],
    }


def execute_report(request: ReportRequest, context: JobContext) -> dict[str, Any]:
    """Build and write a report through existing reporting services."""

    plan = plan_report(request)
    options = _report_options(request)
    context.emit("reading", message="Reading report dataset.", progress=0.2)
    dataset = _read(request.input_path, request.object_selector)
    contract_validation = (
        validate_schema_contract_file(dataset, request.schema_contract)
        if request.schema_contract
        else None
    )
    context.emit("building", message="Building dataset report.", progress=0.55)
    report = build_dataset_report(
        dataset,
        include_summary=options.include_summary,
        include_schema=options.include_schema,
        include_metadata=options.include_metadata,
        include_labels=options.include_labels,
        include_missing=options.include_missing,
        include_describe=options.include_describe,
        include_frequencies=options.include_frequencies,
        include_validation=options.include_validation,
        columns=request.columns,
        frequency_top=request.frequency_top,
        frequency_include_missing=request.frequency_include_missing,
        frequency_max_unique=request.frequency_max_unique,
        validation_target_format=request.target_format,
        strict_validation=request.strict_validation,
        label_preview_values=options.max_preview_values,
        schema_contract_validation=contract_validation,
    )
    context.emit("writing", message="Writing dataset report.", progress=0.85)
    write_dataset_report(
        report,
        request.output_path,
        output_format=request.output_format,
        max_table_rows=options.max_table_rows,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    return {
        "plan": plan,
        **dataset_report_summary_dict(
            report,
            request.output_path,
            request.output_format,
            preset=options.preset,
            max_table_rows=options.max_table_rows,
            max_preview_values=options.max_preview_values,
        ),
    }


def plan_collect(request: CollectRequest) -> dict[str, Any]:
    """Build the existing manifest collection plan without reading full datasets."""

    plan = build_collection_plan(
        request.manifest_path,
        request.output_path,
        base_dir=request.base_dir,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
        dry_run=False,
    )
    return {
        "workflow": "collect",
        "valid": True,
        "command": collect_command(request),
        "details": {
            "manifest_path": str(plan.manifest_file),
            "output_path": str(plan.output_file),
            "base_dir": str(plan.base_dir),
            "objects": len(plan.items),
            "items": [
                {
                    "row_number": item.row_number,
                    "input_file": str(item.input_file),
                    "input_object": item.input_object,
                    "output_object": item.output_object,
                }
                for item in plan.items
            ],
        },
        "warnings": [],
    }


def collect_manifest_example() -> dict[str, Any]:
    """Return the current minimal manual collection-manifest example."""

    return {
        "csv": COLLECT_MANIFEST_EXAMPLE,
        "required_columns": ["input_file"],
        "optional_columns": ["input_object", "output_object", "include"],
        "notes": [
            "Paths may be absolute or relative to the manifest/base directory.",
            "input_object is required only when selecting from a multi-object file.",
            "output_object controls the worksheet/object name in the result.",
        ],
    }


def create_collect_manifest(
    request: CollectManifestStarterRequest,
) -> dict[str, Any]:
    """Write and parse-check one current-schema starter CSV."""

    path = Path(request.output_path)
    if path.suffix.lower() != ".csv":
        raise WebUiRequestError(
            "A collection manifest must use the .csv extension.",
            suggestion="Choose a starter manifest path ending in .csv.",
        )
    _validate_output_file_plan(
        path,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    if request.create_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(COLLECT_MANIFEST_EXAMPLE, encoding="utf-8")
        manifest = read_object_manifest(
            path,
            error_label="Object collection manifest",
        )
    except OSError as exc:
        raise WebUiRequestError(
            f"Unable to write collection manifest '{path}': {exc}"
        ) from None
    return {
        "output_path": str(path),
        "rows": len(manifest.rows),
        "csv": COLLECT_MANIFEST_EXAMPLE,
    }


def execute_collect(request: CollectRequest, context: JobContext) -> dict[str, Any]:
    """Execute a manifest collection through the existing collection service."""

    plan_response = plan_collect(request)
    plan = build_collection_plan(
        request.manifest_path,
        request.output_path,
        base_dir=request.base_dir,
        overwrite=request.overwrite,
        create_dirs=request.create_dirs,
    )
    context.emit("reading", message="Reading collection inputs.", progress=0.25)
    result = execute_collection_plan(
        plan,
        validate=request.validate_inputs,
        strict_validation=request.strict_validation,
    )
    return {
        "plan": plan_response,
        "output_path": str(result.plan.output_file),
        "objects": len(result.objects),
        "rows": result.rows,
        "object_names": [item.name for item in result.objects],
    }


def reference_formats() -> dict[str, Any]:
    """Return live registered format records."""

    rows = [
        {"extension": extension, **make_json_safe(info)}
        for extension, info in list_formats().items()
    ]
    rows.sort(key=lambda row: (str(row["name"]).casefold(), row["extension"]))
    return {"rows": rows, "count": len(rows), "command": "statconvert formats"}


def reference_backends() -> dict[str, Any]:
    """Return live registered backend records."""

    capabilities = list_backend_capabilities()
    rows = [
        {
            "backend": name,
            "implementation": backend.__class__.__name__,
            **make_json_safe(asdict(capabilities[name])),
        }
        for name, backend in list_backends().items()
    ]
    return {"rows": rows, "count": len(rows), "command": "statconvert backends"}


def reference_capabilities() -> dict[str, Any]:
    """Return live format-refined capability records."""

    rows = []
    for extension, info in list_formats().items():
        backend = info["backend"]
        capability = asdict(list_backend_capabilities()[backend])
        capability.update(
            {
                key: info[key]
                for key in (
                    "can_read", "can_write", "is_container", "object_selection",
                    "object_kind", "multi_object_write", "output_object_kind",
                    "supports_multiple_sheets", "supports_multiple_tables",
                    "supports_streaming",
                )
            }
        )
        rows.append(
            {
                "extension": extension,
                "format": info["name"],
                "backend": backend,
                **make_json_safe(capability),
            }
        )
    rows.sort(key=lambda row: (str(row["format"]).casefold(), row["extension"]))
    return {"rows": rows, "count": len(rows), "command": "statconvert capabilities"}


def config_init_command(request: ConfigInitRequest) -> str:
    arguments = ["statconvert", "config", "init", request.command]
    if request.output_path:
        arguments.extend(["--output", request.output_path])
    if request.overwrite:
        arguments.append("--overwrite")
    if request.create_dirs:
        arguments.append("--create-dirs")
    return _display_command(arguments)


def config_validate_command(request: ConfigTextRequest) -> str:
    path = request.config_path or "<saved-workflow.toml>"
    return _display_command(["statconvert", "config", "validate", path])


def config_run_command(request: ConfigTextRequest) -> str:
    path = request.config_path or "<saved-workflow.toml>"
    return _display_command(
        ["statconvert", "config", "run", path, *logging_cli_arguments("config")]
    )


def compare_command(request: CompareRequest) -> str:
    arguments = ["statconvert", "compare", request.left_path, request.right_path]
    if request.object_selector:
        arguments.extend(["--object", request.object_selector])
    if request.left_object_selector:
        arguments.extend(["--left-object", request.left_object_selector])
    if request.right_object_selector:
        arguments.extend(["--right-object", request.right_object_selector])
    if not request.compare_values:
        arguments.append("--no-values")
    if request.sample_size is not None:
        arguments.extend(["--sample", str(request.sample_size)])
    for column in request.columns or []:
        arguments.extend(["--columns", column])
    for column in request.ignore_columns:
        arguments.extend(["--ignore-columns", column])
    if request.numeric_tolerance:
        arguments.extend(["--numeric-tolerance", str(request.numeric_tolerance)])
    if request.key_columns:
        arguments.extend(["--key", ",".join(request.key_columns)])
    arguments.extend(["--max-differences", str(request.max_differences)])
    if request.strict:
        arguments.append("--strict")
    if request.report_path:
        arguments.extend(["--report", request.report_path])
    if request.report_format:
        arguments.extend(["--report-format", request.report_format])
    arguments.extend(logging_cli_arguments("compare"))
    return _display_command(arguments)


def report_command(request: ReportRequest) -> str:
    arguments = ["statconvert", "report", request.input_path, "--output", request.output_path]
    if request.object_selector:
        arguments.extend(["--object", request.object_selector])
    if request.output_format:
        arguments.extend(["--format", request.output_format])
    if request.overwrite:
        arguments.append("--overwrite")
    if request.create_dirs:
        arguments.append("--create-dirs")
    if request.preset:
        arguments.extend(["--preset", request.preset])
    for section in request.sections or []:
        arguments.extend(["--section", section])
    if request.frequencies:
        arguments.append("--frequencies")
    for column in request.columns or []:
        arguments.extend(["--columns", column])
    arguments.extend(["--max-table-rows", str(request.max_table_rows)])
    if request.target_format:
        arguments.extend(["--target-format", request.target_format])
    if request.strict_validation:
        arguments.append("--strict-validation")
    if request.schema_contract:
        arguments.extend(["--schema-contract", request.schema_contract])
    arguments.extend(logging_cli_arguments("report"))
    return _display_command(arguments)


def collect_command(request: CollectRequest) -> str:
    arguments = ["statconvert", "collect", request.manifest_path, request.output_path]
    if request.base_dir:
        arguments.extend(["--base-dir", request.base_dir])
    if request.overwrite:
        arguments.append("--overwrite")
    if request.create_dirs:
        arguments.append("--create-dirs")
    if request.validate_inputs:
        arguments.append("--validate")
    if request.strict_validation:
        arguments.append("--strict-validation")
    arguments.extend(logging_cli_arguments("collect"))
    return _display_command(arguments)


def _validated_config(request: ConfigTextRequest):
    if request.toml_text is not None:
        return _config_from_toml(request.toml_text)
    if request.config_path:
        return load_config(request.config_path)
    raise WebUiRequestError("Provide TOML text or a config path.")


def _config_from_toml(toml_text: str):
    try:
        raw = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config error: invalid TOML: {exc}") from exc
    return validate_config(raw)


def _validate_config_semantics(config) -> None:
    """Mirror the existing extra ordered-transform check from config validate."""

    if config.command != "transform" or "steps" not in config.options:
        return
    dataset = read_dataset(
        config.options["input"],
        object_selector=config.options.get("object"),
    )
    recipe = recipe_from_ordered_steps(
        input_file=config.options["input"],
        output_file=config.options["output"],
        steps=config.options["steps"],
        overwrite=bool(config.options.get("overwrite", False)),
    )
    compile_transform_recipe(recipe, [str(column) for column in dataset.columns])


def _compare_options(request: CompareRequest) -> CompareOptions:
    return CompareOptions(
        ignore_columns=tuple(request.ignore_columns),
        numeric_tolerance=request.numeric_tolerance,
        key_columns=tuple(request.key_columns),
        max_differences=request.max_differences,
    )


def _report_options(request: ReportRequest):
    return resolve_report_options(
        preset=request.preset,
        sections=request.sections,
        frequencies=request.frequencies,
        max_table_rows=request.max_table_rows,
        max_preview_values=request.max_preview_values,
    )


def inspection_command(
    command: str,
    path: str,
    *,
    object_selector: str | None = None,
    options: list[str] | None = None,
) -> str:
    arguments = ["statconvert", command, path]
    if object_selector:
        arguments.extend(["--object", object_selector])
    arguments.extend(options or [])
    return _display_command(arguments)


def convert_command(request: ConvertRequest, *, chunk_size: int | None) -> str:
    arguments = ["statconvert", "convert", request.input_path, request.output_path]
    if request.object_selector:
        arguments.extend(["--object", request.object_selector])
    if request.overwrite:
        arguments.append("--overwrite")
    if request.create_dirs:
        arguments.append("--create-dirs")
    if request.stream:
        arguments.append("--stream")
        arguments.extend(["--chunk-size", str(chunk_size)])
    arguments.extend(logging_cli_arguments("convert"))
    return _display_command(arguments)


def batch_command(request: BatchRequest) -> str:
    arguments = [
        "statconvert",
        "batch",
        request.input_path,
        request.output_path,
        "--to",
        request.target_format,
    ]
    if request.recursive:
        arguments.append("--recursive")
    if request.overwrite:
        arguments.append("--overwrite")
    if request.create_dirs:
        arguments.append("--create-dirs")
    if not request.preserve_structure:
        arguments.append("--flatten")
    if request.object_mode == "all":
        arguments.append("--all-objects")
    elif request.object_mode == "specific" and request.object_selector:
        arguments.extend(["--object", request.object_selector])
    if request.fail_fast:
        arguments.append("--fail-fast")
    if request.workers is not None:
        arguments.extend(["--workers", str(request.workers)])
    for pattern in request.patterns:
        arguments.extend(["--pattern", pattern])
    for pattern in request.exclude_patterns:
        arguments.extend(["--exclude-pattern", pattern])
    if request.report_path:
        arguments.extend(["--report", request.report_path])
    if request.stream:
        arguments.append("--stream")
        arguments.extend(
            [
                "--chunk-size",
                str(_effective_chunk_size(request.stream, request.chunk_size)),
            ]
        )
    arguments.extend(logging_cli_arguments("batch"))
    return _display_command(arguments)


def transform_command(request: TransformRequest) -> str:
    """Explain the supported CLI entry point for a canonical ordered recipe."""

    arguments = [
        "statconvert",
        "transform",
        request.input_path,
        request.output_path,
        "--recipe",
        "<saved-transform-recipe.toml>",
    ]
    if request.object_selector:
        arguments.extend(("--object", request.object_selector))
    if request.overwrite:
        arguments.append("--overwrite")
    arguments.extend(logging_cli_arguments("transform"))
    return _display_command(arguments)


def validate_command(request: ValidateRequest, *, chunk_size: int | None) -> str:
    arguments = ["statconvert", "validate", request.path]
    if request.object_selector:
        arguments.extend(["--object", request.object_selector])
    if request.target_format:
        arguments.extend(["--to", request.target_format])
    if request.strict:
        arguments.append("--strict")
    if request.schema_contract:
        arguments.extend(["--schema-contract", request.schema_contract])
    if request.stream:
        arguments.append("--stream")
        arguments.extend(["--chunk-size", str(chunk_size)])
    arguments.extend(logging_cli_arguments("validate"))
    return _display_command(arguments)


def execute_with_ui_logging(
    workflow: str,
    context: JobContext,
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Execute one UI job inside the existing StatConvert logging lifecycle."""

    with ui_logging_context(workflow, context.job_id) as log_file:
        result = execute()
    if log_file is not None:
        result["log_file"] = str(log_file)
    return result


def _read(path: str, object_selector: str | None):
    _existing_file(path)
    return read_dataset(path, object_selector=object_selector)


def _existing_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.exists():
        raise WebUiRequestError(f"Path does not exist: {path}")
    return path


def _existing_file(path_text: str) -> Path:
    path = _existing_path(path_text)
    if not path.is_file():
        raise WebUiRequestError(f"Expected a file path: {path}")
    return path


def _existing_directory(path_text: str) -> Path:
    path = _existing_path(path_text)
    if not path.is_dir():
        raise WebUiRequestError(f"Expected a directory path: {path}")
    return path


def _bounded_columns(columns: list[str] | None) -> list[str] | None:
    if columns is None:
        return None
    if len(columns) > MAX_INSPECT_COLUMNS:
        raise WebUiRequestError(
            f"At most {MAX_INSPECT_COLUMNS} columns can be inspected at once."
        )
    return columns


def _effective_chunk_size(stream: bool, chunk_size: int | None) -> int | None:
    if not stream:
        if chunk_size is not None:
            raise WebUiRequestError(
                "Chunk size requires streaming.",
                suggestion="Enable streaming or clear the chunk size.",
            )
        return None
    resolved = chunk_size or DEFAULT_STREAMING_CHUNK_SIZE
    validate_chunk_size(resolved)
    return resolved


def _validate_target_matches_output(
    target_format: str | None,
    output_path: Path,
) -> None:
    if not target_format:
        return
    target = _normalize_writable_target(target_format)
    if output_path.suffix.lower() != target:
        raise WebUiRequestError(
            f"Target format {target} does not match output path {output_path}.",
            suggestion=f"Use an output path ending in {target}.",
        )


def _effective_output_path(output_path: str, target_format: str | None) -> str:
    """Append a selected target only when the user supplied no extension."""

    path = Path(output_path)
    if path.suffix or not target_format:
        return output_path
    return f"{output_path}{_normalize_writable_target(target_format)}"


def _effective_convert_request(request: ConvertRequest) -> ConvertRequest:
    output_path = _effective_output_path(request.output_path, request.target_format)
    return request.model_copy(update={"output_path": output_path})


def _effective_transform_request(request: TransformRequest) -> TransformRequest:
    output_path = _effective_output_path(request.output_path, request.target_format)
    return request.model_copy(update={"output_path": output_path})


def _validate_output_file_plan(
    output_path: Path,
    *,
    overwrite: bool,
    create_dirs: bool,
) -> None:
    if output_path.exists() and not overwrite:
        raise WebUiRequestError(
            f"Output file already exists: {output_path}",
            suggestion="Enable overwrite or choose a different output path.",
        )
    parent = output_path.parent
    if parent == Path("."):
        return
    if parent.exists() and not parent.is_dir():
        raise WebUiRequestError(f"Output directory is not a directory: {parent}")
    if not parent.exists() and not create_dirs:
        raise WebUiRequestError(
            f"Output directory does not exist: {parent}",
            suggestion="Enable create directories or choose an existing folder.",
        )


def _streaming_progress(cumulative_rows: int, total_rows: int | None) -> float:
    if total_rows:
        return min(0.95, cumulative_rows / total_rows)
    return 0.5


def _normalize_writable_target(target_format: str) -> str:
    target = normalize_extension(target_format)
    if not can_write_format(target):
        raise WebUiRequestError(f"Output format is not supported: {target}")
    return target


def _validate_batch_request(request: BatchRequest) -> None:
    if request.object_mode == "specific" and not request.object_selector:
        raise WebUiRequestError(
            "Specific-object mode requires an object name or zero-based index."
        )
    if request.object_mode != "specific" and request.object_selector:
        raise WebUiRequestError(
            "An object selector can only be used in specific-object mode."
        )
    if request.stream and request.object_mode != "automatic":
        raise WebUiRequestError(
            "Batch streaming does not support object handling.",
            suggestion="Turn off streaming or use automatic mode with plain text files.",
        )


def _transform_recipe(request: TransformRequest):
    return _portable_transform_recipe(request).bind(
        input_file=request.input_path,
        output_file=request.output_path,
        overwrite=request.overwrite,
    )


def _transform_toml(request: TransformRequest) -> str:
    return portable_recipe_to_toml(_portable_transform_recipe(request))


def _portable_transform_recipe(request: TransformRequest):
    return portable_recipe_from_ordered_steps(
        [step.to_step_dict() for step in request.steps],
        name=request.recipe_name,
        description=request.recipe_description,
    )


def _build_ui_batch_plan(request: BatchRequest):
    object_mode = {
        "automatic": "none",
        "all": "all_objects",
        "specific": "object",
    }[request.object_mode]
    return build_batch_plan(
        input_path=request.input_path,
        output_path=request.output_path,
        target_extension=request.target_format,
        recursive=request.recursive,
        overwrite=request.overwrite,
        preserve_structure=request.preserve_structure,
        patterns=request.patterns or None,
        exclude_patterns=request.exclude_patterns or None,
        all_objects=request.object_mode == "all",
        streaming_enabled=request.stream,
        chunk_size=_effective_chunk_size(request.stream, request.chunk_size),
        object_mode=object_mode,
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _display_command(arguments: list[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)
