"""Read-only system routes for the local browser UI shell."""

from __future__ import annotations

import platform
import asyncio
import json
import sys
from importlib.metadata import PackageNotFoundError, version as package_version

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from statconvert.version import get_runtime_dependency_status, get_statconvert_version
from statconvert.webui.dependencies import ui_dependency_status
from statconvert.webui.jobs import JobManager, TERMINAL_JOB_STATUSES
from statconvert.webui.launcher import validate_host
from statconvert.webui.settings import (
    remember_path,
    reset_ui_settings,
    save_ui_settings,
    settings_file_path,
    settings_from_payload,
    settings_payload,
)
from statconvert.webui.services import (
    browse_local_path,
    config_export,
    config_init,
    config_load,
    config_validate,
    collect_manifest_example,
    create_collect_manifest,
    execute_collect,
    execute_compare,
    execute_config_request,
    execute_report,
    execute_batch,
    execute_convert,
    execute_transform,
    execute_validate,
    execute_with_ui_logging,
    export_inspect_metadata_script,
    preview_inspect_metadata_sidecar,
    save_inspect_metadata_sidecar,
    inspect_describe,
    inspect_frequencies,
    inspect_info,
    inspect_labels,
    inspect_local_path,
    inspect_metadata,
    inspect_missing,
    inspect_objects,
    inspect_peek,
    inspect_schema,
    inspect_summary,
    inspection_command,
    plan_batch,
    plan_collect,
    plan_compare,
    plan_convert,
    plan_transform,
    plan_report,
    plan_validate,
    preview_transform,
    reference_backends,
    reference_capabilities,
    reference_formats,
    transform_functions,
    validate_transform_expression,
)

from .errors import job_not_found_response
from .models import (
    BatchRequest,
    CollectRequest,
    CollectManifestStarterRequest,
    ColumnsRequest,
    ConvertRequest,
    CompareRequest,
    ConfigExportRequest,
    ConfigInitRequest,
    ConfigTextRequest,
    DatasetRequest,
    EnvironmentResponse,
    ExpressionValidationRequest,
    FrequencyRequest,
    HealthResponse,
    JobCreatedResponse,
    MetadataScriptExportRequest,
    MetadataSidecarEditRequest,
    ObjectInspectionRequest,
    PathInspectionRequest,
    PathBrowseRequest,
    PeekRequest,
    PlanResponse,
    ReportRequest,
    RememberPathRequest,
    SettingsUpdateRequest,
    TransformRequest,
    ValidateRequest,
    VersionResponse,
)


def create_api_router(
    *,
    host: str,
    port: int,
    open_url: str,
    static_assets_present: bool,
    job_manager: JobManager,
) -> APIRouter:
    """Create the initial system API router."""

    router = APIRouter(prefix="/api")

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @router.get("/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(version=get_statconvert_version())

    @router.get("/environment", response_model=EnvironmentResponse)
    async def environment() -> EnvironmentResponse:
        return EnvironmentResponse(
            python_version=platform.python_version(),
            platform=platform.system(),
            server_host=host,
            server_port=port,
            static_assets_present=static_assets_present,
            ui_dependencies=ui_dependency_status(),
        )

    @router.get("/settings")
    async def get_settings() -> dict[str, object]:
        return {"data": settings_payload()}

    @router.put("/settings")
    async def put_settings(request: SettingsUpdateRequest) -> dict[str, object]:
        save_ui_settings(settings_from_payload(request.settings))
        return {"data": settings_payload()}

    @router.post("/settings/reset")
    async def reset_settings() -> dict[str, object]:
        reset_ui_settings()
        return {"data": settings_payload()}

    @router.post("/settings/remember-path")
    async def remember_selected_path(request: RememberPathRequest) -> dict[str, object]:
        remember_path(request.path, output=request.kind == "output")
        return {"data": settings_payload()}

    @router.get("/about")
    async def about() -> dict[str, object]:
        dependencies = dict(get_runtime_dependency_status())
        for package in ("fastapi", "uvicorn"):
            try:
                dependencies[package] = package_version(package)
            except PackageNotFoundError:
                dependencies[package] = "not installed"
        return {
            "data": {
                "version": get_statconvert_version(),
                "license": "AGPL-3.0-or-later",
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "executable": sys.executable,
                "dependencies": dependencies,
                "ui_mode": "local browser UI",
                "bound_address": f"{host}:{port}",
                "host": host,
                "port": port,
                "open_url": open_url,
                "static_assets_present": static_assets_present,
                "settings_file_path": str(settings_file_path()),
                "log_directory": settings_payload()["effective_log_directory"],
                "privacy": {
                    "local_only": True,
                    "telemetry": False,
                    "cloud_processing": False,
                    "accounts": False,
                    "remote_server_mode": False,
                },
                "links": {
                    "product": "https://mrmeex.github.io/statconvert/",
                    "documentation": "https://mrmeex.github.io/statconvert/",
                    "github": "https://github.com/mrmeex/statconvert",
                    "releases": "https://github.com/mrmeex/statconvert/releases",
                },
            }
        }

    @router.post("/files/inspect-path")
    async def inspect_path(request: PathInspectionRequest) -> dict[str, object]:
        return {"data": inspect_local_path(request.path)}

    @router.post("/files/browse")
    async def browse_path(request: PathBrowseRequest) -> dict[str, object]:
        validate_host(host)
        return {
            "data": browse_local_path(
                root_path=request.root_path,
                directory=request.directory,
                selection=request.selection,
                extensions=request.extensions,
            )
        }

    @router.post("/inspect/objects")
    async def objects(request: ObjectInspectionRequest) -> dict[str, object]:
        options = ["--recursive"] if request.recursive else []
        return {
            "data": inspect_objects(request.path, recursive=request.recursive),
            "command": inspection_command("objects", request.path, options=options),
        }

    @router.post("/inspect/info")
    async def info(request: DatasetRequest) -> dict[str, object]:
        return _inspect_response("info", request, inspect_info)

    @router.post("/inspect/peek")
    async def peek(request: PeekRequest) -> dict[str, object]:
        return {
            "data": inspect_peek(
                request.path,
                request.object_selector,
                rows=request.rows,
            ),
            "command": inspection_command(
                "peek",
                request.path,
                object_selector=request.object_selector,
                options=["--rows", str(request.rows)],
            ),
        }

    @router.post("/inspect/schema")
    async def schema(request: DatasetRequest) -> dict[str, object]:
        return _inspect_response("schema", request, inspect_schema)

    @router.post("/inspect/labels")
    async def labels(request: DatasetRequest) -> dict[str, object]:
        return _inspect_response("labels", request, inspect_labels)

    @router.post("/inspect/metadata")
    async def metadata(request: DatasetRequest) -> dict[str, object]:
        return _inspect_response("metadata", request, inspect_metadata)

    @router.post("/inspect/metadata/export-script")
    async def metadata_export_script(
        request: MetadataScriptExportRequest,
    ) -> dict[str, object]:
        result = export_inspect_metadata_script(request)
        return {
            "data": {
                "output_path": result["output_path"],
                "format": result["format"],
            },
            "command": result["command"],
        }

    @router.post("/inspect/metadata/sidecar/preview")
    async def metadata_sidecar_preview(
        request: MetadataSidecarEditRequest,
    ) -> dict[str, object]:
        return {"data": preview_inspect_metadata_sidecar(request)}

    @router.post("/inspect/metadata/sidecar/save")
    async def metadata_sidecar_save(
        request: MetadataSidecarEditRequest,
    ) -> dict[str, object]:
        return {"data": save_inspect_metadata_sidecar(request)}

    @router.post("/inspect/summary")
    async def summary(request: DatasetRequest) -> dict[str, object]:
        return _inspect_response("summary", request, inspect_summary)

    @router.post("/inspect/describe")
    async def describe(request: ColumnsRequest) -> dict[str, object]:
        options = [
            option
            for column in request.columns or []
            for option in ("--columns", column)
        ]
        return {
            "data": inspect_describe(
                request.path,
                request.object_selector,
                request.columns,
            ),
            "command": inspection_command(
                "describe",
                request.path,
                object_selector=request.object_selector,
                options=options,
            ),
        }

    @router.post("/inspect/frequencies")
    async def frequencies(request: FrequencyRequest) -> dict[str, object]:
        options = [
            option
            for column in request.columns or []
            for option in ("--columns", column)
        ]
        options.extend(["--top", str(request.top)])
        if request.include_missing:
            options.append("--include-missing")
        return {
            "data": inspect_frequencies(
                request.path,
                request.object_selector,
                request.columns,
                top=request.top,
                include_missing=request.include_missing,
                max_unique=request.max_unique,
            ),
            "command": inspection_command(
                "frequencies",
                request.path,
                object_selector=request.object_selector,
                options=options,
            ),
        }

    @router.post("/inspect/missing")
    async def missing(request: ColumnsRequest) -> dict[str, object]:
        options = [
            option
            for column in request.columns or []
            for option in ("--columns", column)
        ]
        return {
            "data": inspect_missing(
                request.path,
                request.object_selector,
                request.columns,
            ),
            "command": inspection_command(
                "missing",
                request.path,
                object_selector=request.object_selector,
                options=options,
            ),
        }

    @router.post("/workflows/plan-convert", response_model=PlanResponse)
    async def convert_plan(request: ConvertRequest) -> dict[str, object]:
        return plan_convert(request)

    @router.post("/workflows/plan-batch", response_model=PlanResponse)
    async def batch_plan(request: BatchRequest) -> dict[str, object]:
        return plan_batch(request)

    @router.post("/workflows/plan-validate", response_model=PlanResponse)
    async def validate_plan(request: ValidateRequest) -> dict[str, object]:
        return plan_validate(request)

    @router.get("/transform/functions")
    async def functions() -> dict[str, object]:
        return {"data": transform_functions()}

    @router.post("/transform/validate-expression")
    async def validate_expression(
        request: ExpressionValidationRequest,
    ) -> dict[str, object]:
        return {"data": validate_transform_expression(request)}

    @router.post("/transform/plan", response_model=PlanResponse)
    async def transform_plan(request: TransformRequest) -> dict[str, object]:
        return plan_transform(request)

    @router.post("/transform/preview-recipe")
    async def transform_preview(request: TransformRequest) -> dict[str, object]:
        return {"data": preview_transform(request)}

    @router.post("/config/init")
    async def init_config(request: ConfigInitRequest) -> dict[str, object]:
        return {"data": config_init(request)}

    @router.post("/config/load")
    async def load_workflow_config(request: ConfigTextRequest) -> dict[str, object]:
        return {"data": config_load(request)}

    @router.post("/config/validate")
    async def validate_workflow_config(request: ConfigTextRequest) -> dict[str, object]:
        return {"data": config_validate(request)}

    @router.post("/config/export")
    async def export_workflow_config(request: ConfigExportRequest) -> dict[str, object]:
        return {"data": config_export(request)}

    @router.post("/workflows/plan-compare", response_model=PlanResponse)
    async def compare_plan(request: CompareRequest) -> dict[str, object]:
        return plan_compare(request)

    @router.post("/workflows/plan-report", response_model=PlanResponse)
    async def report_plan(request: ReportRequest) -> dict[str, object]:
        return plan_report(request)

    @router.post("/workflows/plan-collect", response_model=PlanResponse)
    async def collect_plan(request: CollectRequest) -> dict[str, object]:
        return plan_collect(request)

    @router.get("/collect/manifest-example")
    async def collection_manifest_example() -> dict[str, object]:
        return {"data": collect_manifest_example()}

    @router.post("/collect/create-manifest")
    async def collection_manifest_create(
        request: CollectManifestStarterRequest,
    ) -> dict[str, object]:
        return {"data": create_collect_manifest(request)}

    @router.get("/reference/formats")
    async def formats_reference() -> dict[str, object]:
        return {"data": reference_formats()}

    @router.get("/reference/backends")
    async def backends_reference() -> dict[str, object]:
        return {"data": reference_backends()}

    @router.get("/reference/capabilities")
    async def capabilities_reference() -> dict[str, object]:
        return {"data": reference_capabilities()}

    @router.post("/execute/convert", response_model=JobCreatedResponse)
    async def convert_execute(request: ConvertRequest) -> JobCreatedResponse:
        record = job_manager.submit(
            "convert",
            lambda context: execute_with_ui_logging(
                "convert", context, lambda: execute_convert(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="convert",
            status=record.status,
        )

    @router.post("/execute/batch", response_model=JobCreatedResponse)
    async def batch_execute(request: BatchRequest) -> JobCreatedResponse:
        plan_batch(request)
        record = job_manager.submit_unique(
            "batch",
            lambda context: execute_with_ui_logging(
                "batch", context, lambda: execute_batch(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="batch",
            status=record.status,
        )

    @router.post("/execute/validate", response_model=JobCreatedResponse)
    async def validate_execute(request: ValidateRequest) -> JobCreatedResponse:
        plan_validate(request)
        record = job_manager.submit(
            "validate",
            lambda context: execute_with_ui_logging(
                "validate", context, lambda: execute_validate(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="validate",
            status=record.status,
        )

    @router.post("/execute/transform", response_model=JobCreatedResponse)
    async def transform_execute(request: TransformRequest) -> JobCreatedResponse:
        plan_transform(request)
        record = job_manager.submit(
            "transform",
            lambda context: execute_with_ui_logging(
                "transform", context, lambda: execute_transform(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="transform",
            status=record.status,
        )

    @router.post("/config/run", response_model=JobCreatedResponse)
    async def run_workflow_config(request: ConfigTextRequest) -> JobCreatedResponse:
        config_validate(request)
        record = job_manager.submit(
            "config",
            lambda context: execute_with_ui_logging(
                "config", context, lambda: execute_config_request(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="config",
            status=record.status,
        )

    @router.post("/execute/compare", response_model=JobCreatedResponse)
    async def compare_execute(request: CompareRequest) -> JobCreatedResponse:
        plan_compare(request)
        record = job_manager.submit(
            "compare",
            lambda context: execute_with_ui_logging(
                "compare", context, lambda: execute_compare(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="compare",
            status=record.status,
        )

    @router.post("/execute/report", response_model=JobCreatedResponse)
    async def report_execute(request: ReportRequest) -> JobCreatedResponse:
        plan_report(request)
        record = job_manager.submit(
            "report",
            lambda context: execute_with_ui_logging(
                "report", context, lambda: execute_report(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="report",
            status=record.status,
        )

    @router.post("/execute/collect", response_model=JobCreatedResponse)
    async def collect_execute(request: CollectRequest) -> JobCreatedResponse:
        plan_collect(request)
        record = job_manager.submit(
            "collect",
            lambda context: execute_with_ui_logging(
                "collect", context, lambda: execute_collect(request, context)
            ),
        )
        return JobCreatedResponse(
            job_id=record.job_id,
            workflow="collect",
            status=record.status,
        )

    @router.get("/jobs/active", response_model=None)
    async def active_job(workflow: str) -> dict[str, object]:
        return {"data": job_manager.active_snapshot(workflow)}

    @router.get("/jobs/{job_id}", response_model=None)
    async def job_status(job_id: str) -> dict[str, object] | JSONResponse:
        snapshot = job_manager.snapshot(job_id)
        if snapshot is None:
            return job_not_found_response(job_id)
        return snapshot

    @router.post("/jobs/{job_id}/cancel", response_model=None)
    async def cancel_job(job_id: str) -> dict[str, object] | JSONResponse:
        record = job_manager.cancel(job_id)
        if record is None:
            return job_not_found_response(job_id)
        return record.to_dict()

    @router.get("/jobs/{job_id}/events", response_model=None)
    async def job_events(job_id: str) -> StreamingResponse | JSONResponse:
        if job_manager.get(job_id) is None:
            return job_not_found_response(job_id)

        async def stream():
            sequence = 0
            while True:
                events = job_manager.events_after(job_id, sequence) or []
                for event in events:
                    sequence = int(event["sequence"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                snapshot = job_manager.snapshot(job_id)
                if snapshot is None or (
                    snapshot["status"] in TERMINAL_JOB_STATUSES and not events
                ):
                    return
                await asyncio.sleep(0.2)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return router


def _inspect_response(
    command: str,
    request: DatasetRequest,
    operation,
) -> dict[str, object]:
    return {
        "data": operation(request.path, request.object_selector),
        "command": inspection_command(
            command,
            request.path,
            object_selector=request.object_selector,
        ),
    }
