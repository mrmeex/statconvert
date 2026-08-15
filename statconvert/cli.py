from dataclasses import asdict
import logging as py_logging
from pathlib import Path
from typing import Annotated, Any

import typer

from statconvert.batch import (
    BatchError,
    build_batch_plan,
    execute_batch_plan,
    write_batch_plan_report,
    write_batch_result_report,
)
from statconvert.compare import (
    CompareError,
    CompareOptions,
    compare_datasets,
    comparison_to_json_payload,
    resolve_compare_object_selectors,
    write_compare_report,
)
from statconvert.converter import (
    transform as convert_file,
    transform_all_objects as convert_all_objects,
    transform_with_policy,
)
from statconvert.collection import (
    CollectionPlanItem,
    build_collection_plan,
    execute_collection_plan,
)
from statconvert.config import (
    config_from_options,
    create_template,
    execute_config,
    load_config,
    write_config,
)
from statconvert.contracts import (
    export_schema_contract,
    validate_schema_contract_file,
)
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.inspection import (
    ColumnProfile,
    MissingProfile,
    ValidationFailedError,
    frequency_tables,
    missing_profile,
    profile_columns,
    summarize_dataset,
    validate_dataset,
)
from statconvert.logging import command_log_wrapper, get_logger, log_command_outcome
from statconvert.output_paths import (
    validate_output_parent_directory,
    validate_output_root_directory,
)
from statconvert.object_discovery import (
    build_object_discovery_report,
    write_object_discovery_report,
)
from statconvert.reporting import (
    build_dataset_report,
    dataset_report_summary_dict,
    resolve_report_options,
    write_dataset_report,
)
from statconvert.registry import (
    get_backend_name,
    get_file_format,
    get_reader_for_file,
    get_writer_for_file,
    list_backends,
    list_dataset_objects,
    list_formats,
    read_dataset,
    resolve_format_info,
    resolve_format_or_backend,
)
from statconvert.exceptions import (
    ConfigError,
    ContractError,
    ConversionError,
    DataDictionaryError,
    MetadataSidecarError,
    MetadataScriptError,
    ObjectSelectionNotSupportedError,
)
from statconvert.streaming.execution import execute_streaming_convert
from statconvert.streaming.options import (
    DEFAULT_STREAMING_CHUNK_SIZE,
    validate_chunk_size,
)
from statconvert.streaming.validation import (
    require_streaming_validation_input,
    validate_streaming_contract,
)
from statconvert.metadata.sidecar import (
    apply_sidecar as apply_metadata_sidecar,
    export_sidecar as export_metadata_sidecar,
    without_automatic_sidecar,
)
from statconvert.metadata.comparison import compare_metadata
from statconvert.metadata.diagnostics import build_metadata_diagnostics
from statconvert.metadata.reporting import write_metadata_diff_report
from statconvert.metadata.editing import (
    parse_metadata_patch,
    preview_metadata_patch,
    preview_sidecar_apply,
    save_metadata_sidecar,
)
from statconvert.metadata.dictionary import export_data_dictionary
from statconvert.metadata.scripts import export_metadata_script
from statconvert.transformer import transform_file
from statconvert.transformations import (
    compile_transform_recipe,
    parse_portable_recipe,
    portable_recipe_from_transform_recipe,
    portable_recipe_template,
    portable_recipe_to_toml,
    preflight_transform_output,
    preview_full_transform,
    recipe_from_ordered_steps,
    save_portable_recipe,
)
from statconvert.transformations.cli_parsing import build_pipeline_from_cli_options
from statconvert.transformations.compatibility import recipe_from_transform_options
from statconvert.transformations.planning import plan_transform_recipe
from statconvert.transformations.recipes import TransformStepType
from statconvert.transfer import (
    TransferIssue,
    TransferPlanningError,
    build_transfer_plan,
    resolve_policy,
    resolve_target_capabilities,
)
from statconvert.version import format_version_status

from statconvert.ui import (
    console,
    emit_json,
    show_backends_table,
    show_batch_plan,
    show_batch_result,
    show_batch_workload,
    run_batch_with_progress,
    show_capabilities_panel,
    show_collection_plan,
    show_collection_result,
    show_config_created,
    show_config_valid,
    show_config_written,
    show_dataset_header,
    show_dataset_comparison,
    show_dataset_info,
    show_dataset_objects,
    show_object_discovery_report,
    show_dataset_summary,
    show_dataset_report_written,
    show_column_profiles,
    show_frequency_tables,
    show_missing_profiles,
    show_schema_contract_validation,
    show_streaming_conversion_result,
    show_streaming_validation_summary,
    show_validation_issues,
    show_formats_table,
    show_labels,
    show_metadata_summary,
    show_metadata_diagnostics,
    show_metadata_diff,
    show_metadata_patch_preview,
    show_preview,
    show_objects_not_supported,
    show_schema,
    show_error,
    show_warning,
    show_full_transform_preview,
    show_transform_recipe_validation,
    show_transfer_plan,
    show_transfer_plan_summary,
    show_transformation_summary,
)

from statconvert.context import context

from statconvert.ui.errors import (
    handle_exception,
    show_success,
)

app = typer.Typer(
    name="statconvert",
    help="Universal statistical data converter"
)
config_app = typer.Typer(
    name="config",
    help="Create, validate and run repeatable TOML workflow configurations.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")
transform_recipe_app = typer.Typer(
    name="transform-recipe",
    help="Validate and create portable transform recipe TOML.",
    no_args_is_help=True,
)
app.add_typer(transform_recipe_app, name="transform-recipe")

LogFileOption = Annotated[
    str | None,
    typer.Option(
        "--log",
        help="Write developer diagnostics to this log file.",
    ),
]
LogLevelOption = Annotated[
    str,
    typer.Option(
        "--log-level",
        help="Minimum file log level: debug, info, warning or error.",
    ),
]
LogAppendOption = Annotated[
    bool,
    typer.Option(
        "--log-append",
        help="Append to the log file instead of overwriting it.",
    ),
]
DeveloperLogOption = Annotated[
    bool,
    typer.Option(
        "--developer-log",
        help="Include module and line details in the log file.",
    ),
]
ObjectSelectorOption = Annotated[
    str | None,
    typer.Option(
        "--object",
        help=(
            "Dataset object inside a container file, such as an Excel sheet "
            "or RData object."
        ),
    ),
]
LeftObjectSelectorOption = Annotated[
    str | None,
    typer.Option(
        "--left-object",
        help="Dataset object inside the left container file.",
    ),
]
RightObjectSelectorOption = Annotated[
    str | None,
    typer.Option(
        "--right-object",
        help="Dataset object inside the right container file.",
    ),
]
InputEncodingOption = Annotated[
    str | None,
    typer.Option(
        "--input-encoding",
        help=(
            "Text encoding to use when reading supported input formats, for example "
            "utf-8, latin1, or cp1252."
        ),
    ),
]
OutputEncodingOption = Annotated[
    str | None,
    typer.Option(
        "--output-encoding",
        help=(
            "Text encoding to use when writing supported output formats, for example "
            "utf-8, utf-8-sig, or cp1252."
        ),
    ),
]
CsvDelimiterOption = Annotated[
    str | None,
    typer.Option(
        "--csv-delimiter",
        help=(
            "Single-character delimiter to use for supported CSV input/output paths, "
            "for example , or ;."
        ),
    ),
]
CsvDecimalOption = Annotated[
    str | None,
    typer.Option(
        "--csv-decimal",
        help=(
            "Single-character decimal separator to use for supported CSV input/output "
            "paths, for example . or ,."
        ),
    ),
]
OverwriteOption = Annotated[
    bool,
    typer.Option(
        "--overwrite",
        help="Replace the output file if it already exists.",
    ),
]
CreateDirsOption = Annotated[
    bool,
    typer.Option(
        "--create-dirs",
        help="Create missing output directories when writing files.",
    ),
]
StreamOption = Annotated[
    bool,
    typer.Option(
        "--stream",
        help=(
            "Use bounded streaming for CSV, JSONL and NDJSON source/target pairs."
        ),
    ),
]
ChunkSizeOption = Annotated[
    int | None,
    typer.Option(
        "--chunk-size",
        min=1,
        help=(
            "Rows per streaming chunk. Requires --stream; defaults to 100000."
        ),
    ),
]
BatchStreamOption = Annotated[
    bool,
    typer.Option(
        "--stream",
        help=(
            "Use bounded streaming for CSV, JSONL and NDJSON source/target pairs."
        ),
        rich_help_panel="Streaming",
    ),
]
BatchChunkSizeOption = Annotated[
    int | None,
    typer.Option(
        "--chunk-size",
        min=1,
        help=(
            "Rows per streaming chunk. Requires --stream; defaults to 100000."
        ),
        rich_help_panel="Streaming",
    ),
]
WriteConfigOption = Annotated[
    str | None,
    typer.Option(
        "--write-config",
        help="Write this command as TOML without running it.",
    ),
]
OverwriteConfigOption = Annotated[
    bool,
    typer.Option(
        "--overwrite-config",
        help="Replace the --write-config file if it already exists.",
    ),
]
ExportSidecarOption = Annotated[
    bool,
    typer.Option(
        "--export-sidecar",
        help=(
            "Export the currently resolved metadata as a version 3 sidecar. "
            "Uses the standardized sibling path unless --sidecar-output is set."
        ),
    ),
]
ApplySidecarOption = Annotated[
    bool,
    typer.Option(
        "--apply-sidecar",
        help=(
            "Validate the standardized sidecar, or activate --sidecar-input "
            "at the standardized sibling path."
        ),
    ),
]
SidecarOutputOption = Annotated[
    str | None,
    typer.Option(
        "--sidecar-output",
        help="Custom path for --export-sidecar.",
    ),
]
SidecarInputOption = Annotated[
    str | None,
    typer.Option(
        "--sidecar-input",
        help="Custom sidecar source for --apply-sidecar.",
    ),
]
OverwriteSidecarOption = Annotated[
    bool,
    typer.Option(
        "--overwrite-sidecar",
        help="Replace an existing sidecar export or applied standardized sidecar.",
    ),
]
ExportDictionaryOption = Annotated[
    str | None,
    typer.Option(
        "--export-dictionary",
        help="Export resolved metadata as a human-readable .csv or .xlsx dictionary.",
    ),
]
OverwriteDictionaryOption = Annotated[
    bool,
    typer.Option(
        "--overwrite-dictionary",
        help="Replace an existing data dictionary export.",
    ),
]
ExportScriptOption = Annotated[
    str | None,
    typer.Option(
        "--export-script",
        help="Export resolved metadata as an .R, .do, or .sps helper script.",
    ),
]
OverwriteScriptOption = Annotated[
    bool,
    typer.Option(
        "--overwrite-script",
        help="Replace an existing metadata helper script.",
    ),
]
ExportContractOption = Annotated[
    str | None,
    typer.Option(
        "--export-contract",
        help="Export the resolved dataset schema as a starter TOML contract.",
    ),
]
OverwriteContractOption = Annotated[
    bool,
    typer.Option(
        "--overwrite-contract",
        help="Replace an existing schema contract export.",
    ),
]


@config_app.command("init")
def config_init(
    command: str,
    output_file: str = typer.Option(
        "workflow.toml",
        "--output",
        "-o",
        help="TOML file to create.",
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
):
    """Create a validated starter config for one command."""

    try:
        template = create_template(command)
        path = write_config(
            template,
            output_file,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )
        show_config_created(path, template.command)
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@config_app.command("validate")
def config_validate(config_file: str):
    """Validate a TOML workflow config without executing it."""

    try:
        config = load_config(config_file)
        if config.command == "transform" and "steps" in config.options:
            read_options, _ = _dataset_io_options(
                config.options.get("input_encoding"),
                config.options.get("output_encoding"),
                config.options.get("csv_delimiter"),
                config.options.get("csv_decimal"),
            )
            dataset = read_dataset(
                config.options["input"],
                object_selector=config.options.get("object"),
                options=read_options,
            )
            recipe = recipe_from_ordered_steps(
                input_file=config.options["input"],
                output_file=config.options["output"],
                steps=config.options["steps"],
                overwrite=bool(config.options.get("overwrite", False)),
            )
            compile_transform_recipe(
                recipe,
                [str(column) for column in dataset.columns],
            )
        show_config_valid(Path(config_file), config.command)
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@config_app.command("run")
def config_run(config_file: str):
    """Validate and run a supported single-command workflow config."""

    try:
        config = load_config(config_file)
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
    except typer.Exit:
        raise
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@transform_recipe_app.command("validate")
def transform_recipe_validate(
    recipe_file: str,
    input_file: str | None = typer.Option(
        None,
        "--input",
        help="Optionally validate ordered column compatibility against a dataset.",
    ),
    object_selector: ObjectSelectorOption = None,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a plain machine-readable validation result.",
    ),
) -> None:
    """Validate a portable recipe without writing files."""

    try:
        portable = parse_portable_recipe(recipe_file)
        issues: list[dict[str, Any]] = []
        mode = "syntax"
        valid = True
        if input_file is not None:
            mode = "input_bound"
            get_reader_for_file(input_file)
            dataset = read_dataset(input_file, object_selector=object_selector)
            bound = portable.bind(
                input_file=input_file,
                output_file="validation-only.output",
            )
            plan = plan_transform_recipe(
                bound,
                [str(column) for column in dataset.columns],
                mode="full",
            )
            valid = plan.valid
            issues = [
                issue.to_dict() for issue in (*plan.errors, *plan.warnings)
            ]
        payload: dict[str, Any] = {
            "valid": valid,
            "mode": mode,
            "schema_version": portable.version,
            "recipe": portable.to_dict(),
            "issues": issues,
        }
    except Exception as exc:
        payload = {
            "valid": False,
            "mode": "input_bound" if input_file is not None else "syntax",
            "schema_version": None,
            "recipe": None,
            "issues": [
                {
                    "code": "transform_recipe_invalid",
                    "severity": "error",
                    "message": str(exc),
                }
            ],
        }

    if json_output:
        emit_json(payload)
    else:
        show_transform_recipe_validation(payload)
    if not payload["valid"]:
        raise typer.Exit(1)


@transform_recipe_app.command("template")
def transform_recipe_template_command(
    output_file: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional recipe TOML path to create.",
    ),
    overwrite_recipe: bool = typer.Option(
        False,
        "--overwrite-recipe",
        help="Replace an existing recipe output.",
    ),
    create_dirs: bool = typer.Option(
        False,
        "--create-dirs",
        help="Create missing recipe parent directories.",
    ),
) -> None:
    """Print or atomically save a safe portable recipe template."""

    try:
        recipe = portable_recipe_template()
        if output_file is None:
            typer.echo(portable_recipe_to_toml(recipe), nl=False)
            return
        path = save_portable_recipe(
            recipe,
            output_file,
            overwrite=overwrite_recipe,
            create_dirs=create_dirs,
        )
        show_success(f"Transform recipe created: {path}")
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


def _run_batch_config(
    *,
    _config_option_names: frozenset[str],
    **arguments: Any,
) -> None:
    """Adapt config field presence to batch's existing CLI-source validation."""

    parameter_names = {
        "select": "select",
        "drop": "drop",
        "rename": "rename",
        "type": "type_items",
        "type_errors": "type_errors",
        "datetime_format": "datetime_format",
        "filter": "filter_items",
        "filter_mode": "filter_mode",
        "recode": "recode",
        "recode_default": "recode_default",
        "update_value_labels": "update_value_labels",
        "ignore_missing_columns": "ignore_missing_columns",
        "reset_index": "reset_index",
    }
    supplied_parameters = {
        parameter_name
        for config_name, parameter_name in parameter_names.items()
        if config_name in _config_option_names
    }
    batch_context = _ConfigBatchContext(supplied_parameters)
    batch(ctx=batch_context, **arguments)


def _run_transform_config(
    *,
    ordered_steps: list[dict[str, Any]] | None = None,
    **arguments: Any,
) -> None:
    """Run legacy options or one canonical ordered recipe through shared logic."""

    if ordered_steps is None:
        transform(
            recipe_file=None,
            save_recipe_file=None,
            overwrite_recipe=False,
            create_recipe_dirs=False,
            preview=False,
            json_output=False,
            sort_items=None,
            sort_nulls="last",
            distinct_columns=None,
            distinct_keep="first",
            row_number_column=None,
            row_number_start=1,
            row_number_step=1,
            **arguments,
        )
        return

    input_file = arguments["input_file"]
    output_file = arguments["output_file"]
    overwrite = arguments["overwrite"]
    dry_run = arguments["dry_run"]
    recipe = recipe_from_ordered_steps(
        input_file=input_file,
        output_file=output_file,
        steps=ordered_steps,
        overwrite=overwrite,
    )
    with command_log_wrapper(
        command="transform",
        parameters={
            "input_file": input_file,
            "output_file": output_file,
            "ordered_recipe": True,
            "recipe_step_count": len(recipe.steps),
            "dry_run": dry_run,
        },
        log_file=arguments.get("log_file"),
        log_level=arguments.get("log_level", "info"),
        log_append=arguments.get("log_append", False),
        developer_log=arguments.get("developer_log", False),
    ):
        read_options, write_options = _dataset_io_options(
            arguments.get("input_encoding"),
            arguments.get("output_encoding"),
            arguments.get("csv_delimiter"),
            arguments.get("csv_decimal"),
        )
        dataset = transform_file(
            input_file=input_file,
            output_file=output_file,
            recipe=recipe,
            overwrite=overwrite,
            create_dirs=arguments["create_dirs"],
            dry_run=dry_run,
            validate=arguments["validate_inputs"],
            strict_validation=arguments["strict_validation"],
            object_selector=arguments.get("object_selector"),
            read_options=read_options,
            write_options=write_options,
            on_option_warning=show_warning,
            on_validation=lambda issues: show_validation_issues(
                issues,
                strict=arguments["strict_validation"],
                target_format=Path(output_file).suffix.lower() or None,
            ),
        )
        show_transformation_summary(
            input_file=input_file,
            output_file=output_file,
            pipeline=None,
            transformed_dataset=dataset,
            dry_run=dry_run,
            ordered_recipe=True,
            recipe_step_count=len(recipe.steps),
            derived_count=sum(
                step.step_type == TransformStepType.DERIVE for step in recipe.steps
            ),
            expression_filter_count=sum(
                step.step_type == TransformStepType.FILTER for step in recipe.steps
            ),
            recode_count=sum(
                step.step_type == TransformStepType.RECODE for step in recipe.steps
            ),
        )
        show_success("Transformation completed.")


def _run_compare_config(**arguments: Any) -> None:
    compare(ctx=_ConfigArgsContext(), **arguments)


def _run_report_config(**arguments: Any) -> None:
    report(ctx=_ConfigArgsContext(), **arguments)


class _ConfigParameterSource:
    name = "COMMANDLINE"


class _ConfigArgsContext:
    """Minimal extra-argument view required by selected command callbacks."""

    args: tuple[str, ...] = ()


class _ConfigBatchContext(_ConfigArgsContext):
    """Minimal parameter-source view required by the batch callback."""

    def __init__(self, supplied_parameters: set[str]) -> None:
        self.supplied_parameters = supplied_parameters

    def get_parameter_source(self, name: str) -> _ConfigParameterSource | None:
        if name in self.supplied_parameters:
            return _ConfigParameterSource()
        return None


_BATCH_TRANSFORM_PARAMETER_NAMES = (
    "select",
    "drop",
    "rename",
    "type_items",
    "type_errors",
    "datetime_format",
    "filter_items",
    "filter_mode",
    "recode",
    "recode_default",
    "update_value_labels",
    "ignore_missing_columns",
    "reset_index",
)


def _batch_transform_options_supplied(ctx: Any) -> bool:
    return any(
        (source := ctx.get_parameter_source(option_name)) is not None
        and source.name == "COMMANDLINE"
        for option_name in _BATCH_TRANSFORM_PARAMETER_NAMES
    )


def _validate_batch_streaming_options(
    *,
    stream: bool,
    transform_items: bool,
    validate_inputs: bool,
    object_selector: str | None,
    object_manifest: str | None,
    all_objects: bool,
    write_config_file: str | None,
) -> None:
    """Reject batch modes that do not yet have a streaming contract."""

    if not stream:
        return
    if transform_items:
        raise BatchError(
            "Batch streaming does not support transforms yet.",
            suggestion="Run without --stream, or remove the batch transform options.",
        )
    if validate_inputs:
        raise BatchError(
            "Batch streaming does not support validation yet.",
            suggestion="Run without --stream, or remove --validate.",
        )
    if object_selector is not None or object_manifest is not None or all_objects:
        raise BatchError(
            "Batch streaming does not support object selection or containers.",
            suggestion=(
                "Run without --stream, or batch plain CSV, JSONL, and NDJSON files."
            ),
        )
    if write_config_file is not None:
        raise BatchError(
            "Batch streaming config integration is not available yet.",
            suggestion="Run the batch directly, or write a non-streaming batch config.",
        )


def _validate_streaming_validate_options(
    *,
    stream: bool,
    schema_contract: str | None,
    object_selector: str | None,
    to_format: str | None,
    write_config_file: str | None,
) -> None:
    """Reject validate modes without a faithful streaming contract."""

    if not stream:
        return
    if schema_contract is None:
        raise ConversionError(
            "Streaming validation requires --schema-contract.",
            suggestion=(
                "Run without --stream for full in-memory validation, or provide "
                "a schema contract."
            ),
        )
    if object_selector is not None:
        raise ConversionError(
            "Streaming validation does not support object selection.",
            suggestion="Run without --stream, or validate a CSV, JSONL, or NDJSON file.",
        )
    if to_format is not None:
        raise ConversionError(
            "Streaming validation does not support --to conversion-readiness checks.",
            suggestion="Run without --stream to use destination-readiness validation.",
        )
    if write_config_file is not None:
        raise ConversionError(
            "Streaming validation config integration is not available yet.",
            suggestion=(
                "Run validation directly, or write a non-streaming validation config."
            ),
        )


def _write_command_config(
    command: str,
    config_file: str,
    *,
    overwrite_config: bool,
    create_config_dirs: bool,
    **options: Any,
) -> None:
    """Serialize one command invocation and show the standard completion message."""

    config = config_from_options(command, **options)
    path = write_config(
        config,
        config_file,
        overwrite=overwrite_config,
        create_dirs=create_config_dirs,
        overwrite_option="--overwrite-config",
    )
    show_config_written(path, command)


def _validate_write_config_options(
    write_config_file: str | None,
    overwrite_config: bool,
) -> None:
    if overwrite_config and write_config_file is None:
        raise ConfigError("--overwrite-config requires --write-config PATH.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(format_version_status())
        raise typer.Exit()


def _dataset_io_options(
    input_encoding: str | None,
    output_encoding: str | None,
    csv_delimiter: str | None,
    csv_decimal: str | None,
) -> tuple[DatasetReadOptions, DatasetWriteOptions]:
    return (
        DatasetReadOptions(
            encoding=input_encoding,
            csv_delimiter=csv_delimiter,
            csv_decimal=csv_decimal,
        ),
        DatasetWriteOptions(
            encoding=output_encoding,
            csv_delimiter=csv_delimiter,
            csv_decimal=csv_decimal,
        ),
    )


def _streaming_chunk_size(
    *,
    stream: bool,
    chunk_size: int | None,
) -> int | None:
    """Resolve the convert-only opt-in streaming chunk size."""

    if not stream:
        if chunk_size is not None:
            raise ConversionError("--chunk-size requires --stream.")
        return None
    resolved = chunk_size or DEFAULT_STREAMING_CHUNK_SIZE
    try:
        return validate_chunk_size(resolved)
    except ValueError as exc:
        raise ConversionError(str(exc)) from exc


def _validate_streaming_convert_options(
    *,
    stream: bool,
    object_selector: str | None,
    all_objects: bool,
    validate_inputs: bool,
    strict_validation: bool,
    write_config_file: str | None,
) -> None:
    """Reject convert features not supported by the streaming path."""

    if not stream:
        return
    if object_selector is not None or all_objects:
        raise ConversionError(
            "--stream does not support --object or --all-objects.",
            suggestion="Run without --stream for container object conversion.",
        )
    if validate_inputs or strict_validation:
        raise ConversionError(
            "--stream does not support --validate or --strict-validation yet.",
            suggestion="Run without --stream to use conversion validation.",
        )
    if write_config_file is not None:
        raise ConversionError(
            "--stream is not supported by convert workflow configuration yet.",
            suggestion="Omit --stream when using --write-config.",
        )


def _validate_convert_transfer_options(
    *,
    policy: str | None,
    type_plan_only: bool,
    optimize_types: bool,
    stream: bool,
    all_objects: bool,
    write_config_file: str | None,
) -> str | None:
    """Resolve explicit transfer options without changing the legacy path."""

    if policy is None:
        if type_plan_only:
            raise ConversionError("--type-plan requires --policy POLICY.")
        if optimize_types:
            raise ConversionError(
                "--optimize-types requires --policy smallest-types."
            )
        return None

    resolved_policy = resolve_policy(policy)
    if type_plan_only and optimize_types:
        raise ConversionError("Use either --type-plan or --optimize-types, not both.")
    if optimize_types and resolved_policy != "smallest-types":
        raise ConversionError(
            "--optimize-types requires --policy smallest-types."
        )
    if stream:
        raise ConversionError(
            "Policy/type planning requires full-dataset planning and cannot use --stream.",
            suggestion="Streaming policy planning is deferred; run without --stream.",
        )
    if all_objects:
        raise ConversionError(
            "--policy is supported only for single-dataset conversion in 1.4.0.",
            suggestion="Use --object to select one object, or omit --policy.",
        )
    if write_config_file is not None:
        raise ConversionError(
            "Transfer policy options are not supported by workflow configuration yet.",
            suggestion="Run the conversion directly without --write-config.",
        )
    return resolved_policy


def _show_dataset_option_warning(message: str, *, json_output: bool = False) -> None:
    if json_output:
        typer.echo(message, err=True)
        return
    show_warning(message)


@app.callback()
def main(
    version_status: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show StatConvert and runtime dependency versions.",
        ),
    ] = False,
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show full traceback when errors occur.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output.",
    ),
):
    """
    Global application options.
    """

    context.debug = debug
    context.verbose = verbose


def _read_dataset(
    input_file: str,
    *,
    object_selector: str | None = None,
):
    """
    Read a dataset through the registry.
    """

    logger = get_logger()
    logger.debug("Reading input dataset: %s", input_file)

    dataset = read_dataset(
        input_file,
        object_selector=object_selector,
    )

    logger.info(
        "Dataset read: input_file=%s backend=%s rows=%s columns=%s",
        input_file,
        get_backend_name(input_file),
        dataset.rows,
        len(dataset.columns),
    )
    return dataset


def _show_dataset_header(
    input_file: str,
    dataset
) -> None:
    """
    Display the standard dataset header.
    """

    show_dataset_header(
        filename=input_file,
        file_format=get_file_format(
            input_file
        ),
        backend=get_backend_name(
            input_file
        ),
        rows=dataset.rows,
        columns=len(dataset.columns),
    )


def _show_object_validation(
    object_name: str,
    issues,
    *,
    strict: bool,
    target_format: str | None,
) -> None:
    """Display validation issues with their source object context."""

    console.print(f"[bold]Object: {object_name}[/bold]")
    show_validation_issues(
        issues,
        strict=strict,
        target_format=target_format,
    )


def _show_collection_validation(
    item: CollectionPlanItem,
    issues,
    *,
    strict: bool,
    target_format: str | None,
) -> None:
    """Display validation issues with manifest row and input context."""

    selector = f" [{item.input_object}]" if item.input_object else ""
    console.print(
        f"[bold]Manifest row {item.row_number}: "
        f"{item.input_file}{selector}[/bold]"
    )
    show_validation_issues(
        issues,
        strict=strict,
        target_format=target_format,
    )


@app.command("type-plan")
def type_plan(
    input_file: str,
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Required registered target extension, with or without the leading dot.",
        ),
    ],
    policy: Annotated[
        str,
        typer.Option(
            "--policy",
            help=(
                "Planning policy: safe, strict, analysis-ready, "
                "preserve-metadata, or smallest-types."
            ),
        ),
    ] = "safe",
    object_selector: ObjectSelectorOption = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a plain bounded machine-readable plan."),
    ] = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
) -> None:
    """Fully scan and plan a target-aware transfer without writing anything."""

    resolved_policy = policy
    try:
        resolved_policy = resolve_policy(policy)
        resolve_target_capabilities(target)
        with command_log_wrapper(
            command="type-plan",
            parameters={
                "input_file": input_file,
                "target": target,
                "policy": resolved_policy,
                "object": object_selector,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ):
            dataset = _read_dataset(input_file, object_selector=object_selector)
            plan = build_transfer_plan(
                dataset,
                source_path=input_file,
                target=target,
                policy=resolved_policy,
                object_selector=object_selector,
            )
            get_logger().info(
                "Transfer plan completed: policy=%s target=%s status=%s rows=%s "
                "columns=%s warnings=%s errors=%s",
                plan.policy,
                plan.target["extension"],
                plan.status,
                plan.scan["rows_scanned"],
                plan.scan["columns_scanned"],
                plan.summary["warning_count"],
                plan.summary["error_count"],
            )
            if json_output:
                emit_json(plan.to_dict())
            else:
                show_transfer_plan(plan)
            if plan.status == "blocked":
                raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        if json_output:
            code = (
                exc.code
                if isinstance(exc, TransferPlanningError)
                else "TRANSFER_POLICY_BLOCKED"
            )
            issue = TransferIssue(
                code=code,
                severity="error",
                message=getattr(exc, "message", str(exc)),
                suggestion=getattr(exc, "suggestion", None),
                policy=resolved_policy,
                target=target,
            )
            emit_json(
                {
                    "schema_version": 1,
                    "source": {"path": input_file, "object": object_selector},
                    "target": {"requested": target},
                    "policy": resolved_policy,
                    "status": "blocked",
                    "scan": {"full_scan": False, "rows_scanned": 0, "columns_scanned": 0},
                    "summary": {"warning_count": 0, "error_count": 1},
                    "decisions": [],
                    "metadata": [],
                    "issues": [issue.to_dict()],
                    "output": None,
                    "truncated": {
                        "decisions": False,
                        "decisions_omitted": 0,
                        "metadata": False,
                        "metadata_omitted": 0,
                        "issues": False,
                        "issues_omitted": 0,
                    },
                }
            )
        else:
            handle_exception(exc)
        raise typer.Exit(1)


@app.command()
def convert(
    input_file: str,
    output_file: str,
    object_selector: ObjectSelectorOption = None,
    all_objects: bool = typer.Option(
        False,
        "--all-objects",
        help=(
            "Convert every supported input object into one multi-object "
            "output file."
        ),
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    stream: StreamOption = False,
    chunk_size: ChunkSizeOption = None,
    policy: str | None = typer.Option(
        None,
        "--policy",
        help=(
            "Opt into transfer planning: safe, strict, analysis-ready, "
            "preserve-metadata, or smallest-types."
        ),
    ),
    type_plan_only: bool = typer.Option(
        False,
        "--type-plan",
        help="Show the transfer plan without writing anything; requires --policy.",
    ),
    optimize_types: bool = typer.Option(
        False,
        "--optimize-types",
        help="Apply exact type decisions; requires --policy smallest-types.",
    ),
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    validate_inputs: bool = typer.Option(
        False,
        "--validate",
        help="Validate the dataset against the output format before writing.",
    ),
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Treat validation warnings as failures and imply --validate.",
    ),
    input_encoding: InputEncodingOption = None,
    output_encoding: OutputEncodingOption = None,
    csv_delimiter: CsvDelimiterOption = None,
    csv_decimal: CsvDecimalOption = None,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Convert one dataset, or all objects in one container, to another format.
    """

    validation_failure: ValidationFailedError | None = None

    try:
        # Config execution calls command functions directly, so newly added Typer
        # defaults must be normalized when the option was not serialized.
        policy = policy if isinstance(policy, str) else None
        type_plan_only = type_plan_only if isinstance(type_plan_only, bool) else False
        optimize_types = optimize_types if isinstance(optimize_types, bool) else False
        resolved_policy = _validate_convert_transfer_options(
            policy=policy,
            type_plan_only=type_plan_only,
            optimize_types=optimize_types,
            stream=stream,
            all_objects=all_objects,
            write_config_file=write_config_file,
        )
        effective_chunk_size = _streaming_chunk_size(
            stream=stream,
            chunk_size=chunk_size,
        )
        _validate_streaming_convert_options(
            stream=stream,
            object_selector=object_selector,
            all_objects=all_objects,
            validate_inputs=validate_inputs,
            strict_validation=strict_validation,
            write_config_file=write_config_file,
        )
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            _write_command_config(
                "convert",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=create_dirs,
                input_file=input_file,
                output_file=output_file,
                object_selector=object_selector,
                all_objects=all_objects,
                overwrite=overwrite,
                create_dirs=create_dirs,
                validate_inputs=validate_inputs,
                strict_validation=strict_validation,
                input_encoding=input_encoding,
                output_encoding=output_encoding,
                csv_delimiter=csv_delimiter,
                csv_decimal=csv_decimal,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        with command_log_wrapper(
            command="convert",
            parameters={
                "input_file": input_file,
                "output_file": output_file,
                "object": object_selector,
                "all_objects": all_objects,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
                "stream": stream,
                "chunk_size": effective_chunk_size,
                "policy": resolved_policy,
                "type_plan": type_plan_only,
                "optimize_types": optimize_types,
                "validate": validate_inputs,
                "strict_validation": strict_validation,
                "input_encoding": input_encoding,
                "output_encoding": output_encoding,
                "csv_delimiter": csv_delimiter,
                "csv_decimal": csv_decimal,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            read_options, write_options = _dataset_io_options(
                input_encoding,
                output_encoding,
                csv_delimiter,
                csv_decimal,
            )
            if object_selector is not None and all_objects:
                raise ConversionError(
                    "Use either --object or --all-objects, not both."
                )
            try:
                if stream:
                    streaming_result = execute_streaming_convert(
                        input_file,
                        output_file,
                        chunk_size=effective_chunk_size,
                        overwrite=overwrite,
                        create_dirs=create_dirs,
                        read_options=read_options,
                        write_options=write_options,
                    )
                elif all_objects:
                    conversion_result = convert_all_objects(
                        input_file=input_file,
                        output_file=output_file,
                        overwrite=overwrite,
                        create_dirs=create_dirs,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=show_warning,
                        on_validation=lambda name, issues: (
                            _show_object_validation(
                                name,
                                issues,
                                strict=strict_validation,
                                target_format=(
                                    Path(output_file).suffix.lower() or None
                                ),
                            )
                        ),
                    )
                elif resolved_policy is None:
                    dataset = convert_file(
                        input_file=input_file,
                        output_file=output_file,
                        overwrite=overwrite,
                        create_dirs=create_dirs,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        object_selector=object_selector,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=show_warning,
                        on_validation=lambda issues: show_validation_issues(
                            issues,
                            strict=strict_validation,
                            target_format=(
                                Path(output_file).suffix.lower() or None
                            ),
                        ),
                    )
                else:
                    policy_result = transform_with_policy(
                        input_file=input_file,
                        output_file=output_file,
                        policy=resolved_policy,
                        type_plan_only=type_plan_only,
                        optimize_types=optimize_types,
                        overwrite=overwrite,
                        create_dirs=create_dirs,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        object_selector=object_selector,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=show_warning,
                        on_transfer_plan=(
                            show_transfer_plan
                            if type_plan_only
                            else show_transfer_plan_summary
                        ),
                        on_validation=lambda issues: show_validation_issues(
                            issues,
                            strict=strict_validation,
                            target_format=(
                                Path(output_file).suffix.lower() or None
                            ),
                        ),
                    )
                    dataset = policy_result.dataset
            except ValidationFailedError as exc:
                validation_failure = exc
                _log_validation_block(
                    logger,
                    command="convert",
                    exc=exc,
                    strict=strict_validation,
                )
            else:
                if stream:
                    logger.info(
                        "Streaming conversion result: output_file=%s chunks=%s "
                        "rows=%s chunk_size=%s sidecar=%s",
                        output_file,
                        streaming_result.chunks_processed,
                        streaming_result.rows_processed,
                        streaming_result.chunk_size,
                        streaming_result.sidecar_path,
                    )
                    show_streaming_conversion_result(streaming_result)
                elif all_objects:
                    for skipped in conversion_result.skipped_objects:
                        name = (
                            skipped.name
                            or (
                                f"object_{skipped.index}"
                                if skipped.index is not None
                                else "<unnamed>"
                            )
                        )
                        message = skipped.message or "Unsupported object"
                        show_warning(
                            f"Skipped unsupported object: {name} - {message}"
                        )
                    logger.info(
                        "Multi-object conversion result: output_file=%s "
                        "objects=%s skipped=%s rows=%s",
                        output_file,
                        len(conversion_result.objects),
                        len(conversion_result.skipped_objects),
                        conversion_result.rows,
                    )
                    show_success("Multi-object conversion completed.")
                    console.print(
                        f"Objects converted: {len(conversion_result.objects):,}"
                    )
                    console.print(
                        f"Rows converted: {conversion_result.rows:,}"
                    )
                elif type_plan_only:
                    logger.info(
                        "Non-writing conversion type plan: policy=%s target=%s "
                        "status=%s warnings=%s errors=%s",
                        policy_result.transfer_plan.policy,
                        policy_result.transfer_plan.target["extension"],
                        policy_result.transfer_plan.status,
                        policy_result.transfer_plan.summary["warning_count"],
                        policy_result.transfer_plan.summary["error_count"],
                    )
                else:
                    if (
                        resolved_policy is not None
                        and policy_result.application is not None
                    ):
                        console.print(
                            "Exact type decisions applied: "
                            f"{policy_result.application.applied_count:,}"
                        )
                        console.print(
                            "Unsupported proposals retained unchanged: "
                            f"{len(policy_result.application.unsupported_proposals):,}"
                        )
                        logger.info(
                            "Transfer application result: applied=%s retained=%s "
                            "unsupported_proposals=%s",
                            policy_result.application.applied_count,
                            len(policy_result.application.retained_columns),
                            len(policy_result.application.unsupported_proposals),
                        )
                    logger.info(
                        "Conversion result: output_file=%s rows=%s columns=%s",
                        output_file,
                        dataset.rows,
                        len(dataset.columns),
                    )

                    show_success("Conversion completed.")
                    console.print(f"Rows converted: {dataset.rows:,}")

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)

    if validation_failure is not None:
        show_error(
            "Validation failed. Output was not written."
        )
        raise typer.Exit(1)


@app.command()
def collect(
    manifest: str,
    output_file: str,
    base_dir: str | None = typer.Option(
        None,
        "--base-dir",
        help=(
            "Resolve relative manifest input_file values from this directory. "
            "Defaults to the manifest directory."
        ),
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and display the collection plan without reading or writing data.",
    ),
    validate_inputs: bool = typer.Option(
        False,
        "--validate",
        help="Validate each selected dataset before writing the container.",
    ),
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Treat validation warnings as failures and imply --validate.",
    ),
    input_encoding: InputEncodingOption = None,
    output_encoding: OutputEncodingOption = None,
    csv_delimiter: CsvDelimiterOption = None,
    csv_decimal: CsvDecimalOption = None,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Collect manifest-selected datasets into one multi-object output file."""

    validation_failure: ValidationFailedError | None = None
    try:
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            _write_command_config(
                "collect",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=create_dirs,
                manifest=manifest,
                output_file=output_file,
                base_dir=base_dir,
                overwrite=overwrite,
                create_dirs=create_dirs,
                dry_run=dry_run,
                validate_inputs=validate_inputs,
                strict_validation=strict_validation,
                input_encoding=input_encoding,
                output_encoding=output_encoding,
                csv_delimiter=csv_delimiter,
                csv_decimal=csv_decimal,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        with command_log_wrapper(
            command="collect",
            parameters={
                "manifest": manifest,
                "output_file": output_file,
                "base_dir": base_dir,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
                "dry_run": dry_run,
                "validate": validate_inputs,
                "strict_validation": strict_validation,
                "input_encoding": input_encoding,
                "output_encoding": output_encoding,
                "csv_delimiter": csv_delimiter,
                "csv_decimal": csv_decimal,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            read_options, write_options = _dataset_io_options(
                input_encoding,
                output_encoding,
                csv_delimiter,
                csv_decimal,
            )
            plan = build_collection_plan(
                manifest,
                output_file,
                base_dir=base_dir,
                overwrite=overwrite,
                create_dirs=create_dirs,
                dry_run=dry_run,
            )
            if dry_run:
                show_collection_plan(plan)
                logger.info(
                    "Collection dry-run plan: manifest=%s output=%s objects=%s",
                    manifest,
                    output_file,
                    len(plan.items),
                )
            else:
                try:
                    result = execute_collection_plan(
                        plan,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=show_warning,
                        on_validation=lambda item, issues: (
                            _show_collection_validation(
                                item,
                                issues,
                                strict=strict_validation,
                                target_format=(
                                    Path(output_file).suffix.lower() or None
                                ),
                            )
                        ),
                    )
                except ValidationFailedError as exc:
                    validation_failure = exc
                    _log_validation_block(
                        logger,
                        command="collect",
                        exc=exc,
                        strict=strict_validation,
                    )
                else:
                    logger.info(
                        "Collection result: output_file=%s objects=%s rows=%s",
                        output_file,
                        len(result.objects),
                        result.rows,
                    )
                    show_collection_result(result)
                    show_success("Object collection completed.")

    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)

    if validation_failure is not None:
        show_error("Validation failed. Output was not written.")
        raise typer.Exit(1)


@app.command()
def transform(
    input_file: str,
    output_file: str,
    recipe_file: str | None = typer.Option(
        None,
        "--recipe",
        help="Load path-independent ordered steps from portable recipe TOML.",
    ),
    save_recipe_file: str | None = typer.Option(
        None,
        "--save-recipe",
        help="Save current transform flags as a portable recipe without running.",
    ),
    overwrite_recipe: bool = typer.Option(
        False,
        "--overwrite-recipe",
        help="Replace an existing --save-recipe target.",
    ),
    create_recipe_dirs: bool = typer.Option(
        False,
        "--create-recipe-dirs",
        help="Create missing parent directories for --save-recipe.",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Apply the full transform to a copy and report exact impact without writing.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a plain JSON result for --preview.",
    ),
    object_selector: ObjectSelectorOption = None,
    extra_columns: list[str] | None = typer.Argument(
        None,
        hidden=True,
    ),
    select: list[str] | None = typer.Option(
        None,
        "--select",
        help="Keep selected columns. Repeat for multiple columns.",
    ),
    drop: list[str] | None = typer.Option(
        None,
        "--drop",
        help="Drop selected columns. Repeat for multiple columns.",
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help="Rename a column using OLD=NEW. Can be repeated.",
    ),
    type_items: list[str] | None = typer.Option(
        None,
        "--type",
        help="Convert a column using COLUMN=TYPE. Can be repeated.",
    ),
    type_errors: str = typer.Option(
        "raise",
        "--type-errors",
        help="Type conversion error mode: raise, coerce or ignore.",
    ),
    datetime_format: str | None = typer.Option(
        None,
        "--datetime-format",
        help="Datetime parsing format for type conversion.",
    ),
    derive_items: list[str] | None = typer.Option(
        None,
        "--derive",
        help="Append a derived column using COLUMN=EXPRESSION. Can be repeated.",
    ),
    filter_items: list[str] | None = typer.Option(
        None,
        "--filter",
        help="Filter rows using COLUMN,OPERATOR,VALUE. Can be repeated.",
    ),
    filter_expression_items: list[str] | None = typer.Option(
        None,
        "--filter-expression",
        help="Filter rows using a safe boolean expression. Can be repeated.",
    ),
    filter_mode: str = typer.Option(
        "and",
        "--filter-mode",
        help="Combine filters with and or or.",
    ),
    recode: list[str] | None = typer.Option(
        None,
        "--recode",
        help="Recode values using COLUMN:OLD=NEW,OLD=NEW. Can be repeated.",
    ),
    recode_default: str | None = typer.Option(
        None,
        "--recode-default",
        help="Default value for unmapped non-missing recode values.",
    ),
    update_value_labels: bool = typer.Option(
        True,
        "--update-value-labels/--no-update-value-labels",
        help="Update normalized value labels during recode.",
    ),
    ignore_missing_columns: bool = typer.Option(
        False,
        "--ignore-missing-columns",
        help="Ignore missing columns for select, drop and rename.",
    ),
    reset_index: bool = typer.Option(
        True,
        "--reset-index/--no-reset-index",
        help="Reset row index after filtering.",
    ),
    sort_items: list[str] | None = typer.Option(
        None,
        "--sort",
        help="Stable sort key COLUMN[:asc|desc]. Repeat for multiple keys.",
    ),
    sort_nulls: str = typer.Option(
        "last",
        "--sort-nulls",
        help="Place missing sort values first or last for direct sort keys.",
    ),
    distinct_columns: list[str] | None = typer.Option(
        None,
        "--distinct",
        help="Distinct key column. Repeat for a composite key.",
    ),
    distinct_keep: str = typer.Option(
        "first",
        "--distinct-keep",
        help="Keep the first or last row for each distinct key.",
    ),
    row_number_column: str | None = typer.Option(
        None,
        "--row-number",
        help="Append a deterministic integer row-number column.",
    ),
    row_number_start: int = typer.Option(
        1,
        "--row-number-start",
        help="First generated row number.",
    ),
    row_number_step: int = typer.Option(
        1,
        "--row-number-step",
        help="Positive increment between generated row numbers.",
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Apply transformations without writing the output file.",
    ),
    validate_inputs: bool = typer.Option(
        False,
        "--validate",
        help="Validate the transformed dataset before writing.",
    ),
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Treat validation warnings as failures and imply --validate.",
    ),
    input_encoding: InputEncodingOption = None,
    output_encoding: OutputEncodingOption = None,
    csv_delimiter: CsvDelimiterOption = None,
    csv_decimal: CsvDecimalOption = None,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Transform a dataset and write it to another supported format.
    """

    validation_failure: ValidationFailedError | None = None
    portable_recipe = None
    bound_recipe = None

    try:
        _validate_write_config_options(write_config_file, overwrite_config)
        direct_operations = any(
            (
                select,
                drop,
                rename,
                type_items,
                derive_items,
                filter_items,
                filter_expression_items,
                recode,
                sort_items,
                distinct_columns,
                row_number_column,
                extra_columns,
            )
        )
        direct_modifiers = (
            type_errors != "raise"
            or datetime_format is not None
            or filter_mode != "and"
            or recode_default is not None
            or not update_value_labels
            or ignore_missing_columns
            or not reset_index
            or sort_nulls != "last"
            or distinct_keep != "first"
            or row_number_start != 1
            or row_number_step != 1
        )
        if recipe_file is not None and (direct_operations or direct_modifiers):
            raise ConversionError(
                "--recipe cannot be combined with direct transform operation options."
            )
        if recipe_file is not None and save_recipe_file is not None:
            raise ConversionError("Use either --recipe or --save-recipe, not both.")
        if preview and dry_run:
            raise ConversionError("Use either --preview or --dry-run, not both.")
        if json_output and not preview:
            raise ConversionError("--json is supported only with --preview.")
        if save_recipe_file is not None and (
            dry_run or preview or write_config_file is not None or recipe_file is not None
        ):
            raise ConversionError(
                "--save-recipe cannot be combined with --recipe, --dry-run, "
                "--preview, or --write-config."
            )
        if recipe_file is not None and write_config_file is not None:
            raise ConversionError("--recipe cannot be combined with --write-config.")
        if sort_items is None and sort_nulls != "last":
            raise ConversionError("--sort-nulls requires at least one --sort option.")
        if distinct_columns is None and distinct_keep != "first":
            raise ConversionError(
                "--distinct-keep requires at least one --distinct option."
            )
        if row_number_column is None and (
            row_number_start != 1 or row_number_step != 1
        ):
            raise ConversionError(
                "--row-number-start and --row-number-step require --row-number."
            )
        if write_config_file is not None and (
            sort_items or distinct_columns or row_number_column is not None
        ):
            raise ConversionError(
                "New row operations are not legacy workflow-config fields. "
                "Use --save-recipe to export them."
            )

        if save_recipe_file is not None:
            selected, dropped = _attach_extra_column_args(
                extra_columns=extra_columns,
                select=select,
                drop=drop,
            )
            internal_recipe = recipe_from_transform_options(
                input_file=input_file,
                output_file=output_file,
                select_columns=selected,
                drop_columns=dropped,
                rename_items=rename,
                type_items=type_items,
                type_errors=type_errors,
                datetime_format=datetime_format,
                derive_items=derive_items,
                filter_items=filter_items,
                filter_expression_items=filter_expression_items,
                filter_mode=filter_mode,
                recode_items=recode,
                recode_default=recode_default,
                update_value_labels=update_value_labels,
                ignore_missing_columns=ignore_missing_columns,
                reset_index=reset_index,
                sort_items=sort_items,
                sort_nulls=sort_nulls,
                distinct_columns=distinct_columns,
                distinct_keep=distinct_keep,
                row_number_column=row_number_column,
                row_number_start=row_number_start,
                row_number_step=row_number_step,
            )
            portable = portable_recipe_from_transform_recipe(internal_recipe)
            path = save_portable_recipe(
                portable,
                save_recipe_file,
                overwrite=overwrite_recipe,
                create_dirs=create_recipe_dirs,
            )
            show_success(f"Transform recipe saved: {path}")
            return

        if recipe_file is not None:
            portable_recipe = parse_portable_recipe(recipe_file)
            bound_recipe = portable_recipe.bind(
                input_file=input_file,
                output_file=output_file,
                overwrite=overwrite,
            )

        if preview:
            if portable_recipe is None:
                selected, dropped = _attach_extra_column_args(
                    extra_columns=extra_columns,
                    select=select,
                    drop=drop,
                )
                internal_recipe = recipe_from_transform_options(
                    input_file=input_file,
                    output_file=output_file,
                    select_columns=selected,
                    drop_columns=dropped,
                    rename_items=rename,
                    type_items=type_items,
                    type_errors=type_errors,
                    datetime_format=datetime_format,
                    derive_items=derive_items,
                    filter_items=filter_items,
                    filter_expression_items=filter_expression_items,
                    filter_mode=filter_mode,
                    recode_items=recode,
                    recode_default=recode_default,
                    update_value_labels=update_value_labels,
                    ignore_missing_columns=ignore_missing_columns,
                    reset_index=reset_index,
                    sort_items=sort_items,
                    sort_nulls=sort_nulls,
                    distinct_columns=distinct_columns,
                    distinct_keep=distinct_keep,
                    row_number_column=row_number_column,
                    row_number_start=row_number_start,
                    row_number_step=row_number_step,
                )
                portable_recipe = portable_recipe_from_transform_recipe(internal_recipe)
                bound_recipe = internal_recipe
            assert bound_recipe is not None
            get_reader_for_file(input_file)
            get_writer_for_file(output_file)
            output_preflight = preflight_transform_output(
                input_file,
                output_file,
                overwrite=overwrite,
                create_dirs=create_dirs,
                write=False,
            )
            read_options, _ = _dataset_io_options(
                input_encoding,
                output_encoding,
                csv_delimiter,
                csv_decimal,
            )
            source_dataset = read_dataset(
                input_file,
                object_selector=object_selector,
                options=read_options,
            )
            preview_result = preview_full_transform(
                source_dataset,
                bound_recipe,
                input_path=input_file,
                output_preflight=output_preflight,
                object_selector=object_selector,
                portable_recipe=portable_recipe,
            ).to_dict()
            if json_output:
                emit_json(preview_result)
            else:
                show_full_transform_preview(preview_result)
            if not preview_result["valid"]:
                raise typer.Exit(1)
            return

        if write_config_file is not None:
            select, drop = _attach_extra_column_args(
                extra_columns=extra_columns,
                select=select,
                drop=drop,
            )
            build_pipeline_from_cli_options(
                select_columns=select,
                drop_columns=drop,
                rename_items=rename,
                type_items=type_items,
                type_errors=type_errors,
                datetime_format=datetime_format,
                derive_items=derive_items,
                filter_items=filter_items,
                filter_expression_items=filter_expression_items,
                filter_mode=filter_mode,
                recode_items=recode,
                recode_default=recode_default,
                update_value_labels=update_value_labels,
                ignore_missing_columns=ignore_missing_columns,
                reset_index=reset_index,
            )
            _write_command_config(
                "transform",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=create_dirs,
                input_file=input_file,
                output_file=output_file,
                object_selector=object_selector,
                select=select,
                drop=drop,
                rename=rename,
                type_items=type_items,
                type_errors=type_errors,
                datetime_format=datetime_format,
                derive_items=derive_items,
                filter_items=filter_items,
                filter_expression_items=filter_expression_items,
                filter_mode=filter_mode,
                recode=recode,
                recode_default=recode_default,
                update_value_labels=update_value_labels,
                ignore_missing_columns=ignore_missing_columns,
                reset_index=reset_index,
                overwrite=overwrite,
                create_dirs=create_dirs,
                dry_run=dry_run,
                validate_inputs=validate_inputs,
                strict_validation=strict_validation,
                input_encoding=input_encoding,
                output_encoding=output_encoding,
                csv_delimiter=csv_delimiter,
                csv_decimal=csv_decimal,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        with command_log_wrapper(
            command="transform",
            parameters={
                "input_file": input_file,
                "output_file": output_file,
                "object": object_selector,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
                "select": select,
                "drop": drop,
                "rename": rename,
                "type": type_items,
                "derive": derive_items,
                "filters": filter_items,
                "filter_expressions": filter_expression_items,
                "recode": recode,
                "sort": sort_items,
                "distinct": distinct_columns,
                "row_number": row_number_column,
                "validate": validate_inputs,
                "strict_validation": strict_validation,
                "dry_run": dry_run,
                "input_encoding": input_encoding,
                "output_encoding": output_encoding,
                "csv_delimiter": csv_delimiter,
                "csv_decimal": csv_decimal,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            read_options, write_options = _dataset_io_options(
                input_encoding,
                output_encoding,
                csv_delimiter,
                csv_decimal,
            )
            select, drop = _attach_extra_column_args(
                extra_columns=extra_columns,
                select=select,
                drop=drop,
            )
            pipeline = None
            if bound_recipe is None:
                pipeline = build_pipeline_from_cli_options(
                    select_columns=select,
                    drop_columns=drop,
                    rename_items=rename,
                    type_items=type_items,
                    type_errors=type_errors,
                    datetime_format=datetime_format,
                    derive_items=derive_items,
                    filter_items=filter_items,
                    filter_expression_items=filter_expression_items,
                    filter_mode=filter_mode,
                    recode_items=recode,
                    recode_default=recode_default,
                    update_value_labels=update_value_labels,
                    ignore_missing_columns=ignore_missing_columns,
                    reset_index=reset_index,
                    sort_items=sort_items,
                    sort_nulls=sort_nulls,
                    distinct_columns=distinct_columns,
                    distinct_keep=distinct_keep,
                    row_number_column=row_number_column,
                    row_number_start=row_number_start,
                    row_number_step=row_number_step,
                )
            try:
                dataset = transform_file(
                    input_file=input_file,
                    output_file=output_file,
                    pipeline=pipeline,
                    recipe=bound_recipe,
                    overwrite=overwrite,
                    create_dirs=create_dirs,
                    dry_run=dry_run,
                    validate=validate_inputs,
                    strict_validation=strict_validation,
                    object_selector=object_selector,
                    read_options=read_options,
                    write_options=write_options,
                    on_option_warning=show_warning,
                    on_validation=lambda issues: show_validation_issues(
                        issues,
                        strict=strict_validation,
                        target_format=Path(output_file).suffix.lower() or None,
                    ),
                )
            except ValidationFailedError as exc:
                validation_failure = exc
                _log_validation_block(
                    logger,
                    command="transform",
                    exc=exc,
                    strict=strict_validation,
                )
            else:
                logger.info(
                    "Transformation result: output_file=%s rows=%s columns=%s "
                    "dry_run=%s",
                    output_file,
                    dataset.rows,
                    len(dataset.columns),
                    dry_run,
                )

                show_transformation_summary(
                    input_file=input_file,
                    output_file=output_file,
                    pipeline=pipeline,
                    transformed_dataset=dataset,
                    dry_run=dry_run,
                    ordered_recipe=bound_recipe is not None,
                    recipe_step_count=(
                        len(bound_recipe.steps) if bound_recipe is not None else None
                    ),
                )

                if not dry_run:
                    show_success(
                        "Transformation completed."
                    )

    except typer.Exit:
        raise
    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)

    if validation_failure is not None:
        show_error(
            "Validation failed. Output was not written."
        )
        raise typer.Exit(1)


def _attach_extra_column_args(
    extra_columns: list[str] | None,
    select: list[str] | None,
    drop: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """
    Support compact --select/--drop column lists accepted as trailing args.
    """

    if not extra_columns:
        return select, drop

    if select and not drop:
        return list(
            select
        ) + list(
            extra_columns
        ), drop

    if drop and not select:
        return select, list(
            drop
        ) + list(
            extra_columns
        )

    raise ValueError(
        "Extra column values are only supported after a single --select or --drop option."
    )


@app.command()
def formats(
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    List supported file formats.
    """

    try:
        with command_log_wrapper(
            command="formats",
            parameters={},
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            formats_list = list_formats()
            logger.info("Format discovery result: formats=%s", len(formats_list))
            show_formats_table(formats_list)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def backends(
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    List available backend engines.
    """

    try:
        with command_log_wrapper(
            command="backends",
            parameters={},
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            backends_list = list_backends()
            logger.info("Backend discovery result: backends=%s", len(backends_list))
            show_backends_table(backends_list)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def capabilities(
    target: str,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display capability details for a format or backend.
    """

    try:
        with command_log_wrapper(
            command="capabilities",
            parameters={"target": target},
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            target_info = resolve_format_or_backend(target)
            logger.info("Capability lookup completed: target=%s", target)
            show_capabilities_panel(target_info)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def objects(
    input_path: str,
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Include files in subdirectories when INPUT_PATH is a folder.",
    ),
    patterns: list[str] | None = typer.Option(
        None,
        "--pattern",
        help="Include filename or relative-path glob matches. Can be repeated.",
    ),
    exclude_patterns: list[str] | None = typer.Option(
        None,
        "--exclude-pattern",
        help="Exclude filename or relative-path glob matches. Can be repeated.",
    ),
    include_unsupported: bool = typer.Option(
        False,
        "--include-unsupported",
        help="Include unsupported files as excluded discovery rows.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Write a manifest-ready CSV report, or JSON with --json.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit dataset objects as plain JSON.",
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Discover dataset-like objects in a file or folder."""

    try:
        with command_log_wrapper(
            command="objects",
            parameters={
                "input_path": input_path,
                "recursive": recursive,
                "pattern": patterns,
                "exclude_pattern": exclude_patterns,
                "include_unsupported": include_unsupported,
                "output": output,
                "json": json_output,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            path = Path(input_path)
            legacy_single_file = (
                path.is_file()
                and output is None
                and not recursive
                and not patterns
                and not exclude_patterns
                and not include_unsupported
            )
            if legacy_single_file:
                try:
                    dataset_objects = list_dataset_objects(input_path)
                except ObjectSelectionNotSupportedError:
                    dataset_objects = []
                    logger.info("Object listing is not supported for input format")
                    if json_output:
                        emit_json(dataset_objects)
                    else:
                        show_objects_not_supported(path.suffix.lower())
                    return

                logger.info("Object listing completed: objects=%s", len(dataset_objects))
                if json_output:
                    emit_json(dataset_objects)
                else:
                    show_dataset_objects(dataset_objects)
                return

            report = build_object_discovery_report(
                input_path,
                recursive=recursive,
                patterns=patterns,
                exclude_patterns=exclude_patterns,
                include_unsupported=include_unsupported,
                excluded_file=output,
            )
            logger.info(
                "Object discovery completed: files=%s objects=%s",
                len(report.files),
                len(report.rows),
            )
            if output is not None:
                written_path = write_object_discovery_report(
                    report,
                    output,
                    json_output=json_output,
                    overwrite=overwrite,
                    create_dirs=create_dirs,
                )
                logger.info("Object discovery report written: %s", written_path)
                console.print(f"Object discovery report written: {written_path}")
            elif json_output:
                emit_json(report.to_json_dict())
            else:
                show_object_discovery_report(report)

    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@app.command()
def info(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display information about a dataset.
    """

    try:
        with command_log_wrapper(
            command="info",
            parameters={"input_file": input_file, "object": object_selector},
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ):
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            _show_dataset_header(input_file, dataset)
            show_dataset_info(dataset)


    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)

@app.command()
def schema(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    export_contract: ExportContractOption = None,
    overwrite_contract: OverwriteContractOption = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display normalized dataset schema.
    """

    try:
        with command_log_wrapper(
            command="schema",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "export_contract": export_contract,
                "overwrite_contract": overwrite_contract,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            if overwrite_contract and export_contract is None:
                raise ContractError(
                    "--overwrite-contract requires --export-contract."
                )
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            contract_path = None
            if export_contract is not None:
                contract_path = export_schema_contract(
                    dataset,
                    input_file,
                    export_contract,
                    overwrite=overwrite_contract,
                )
                logger.info(
                    "Schema contract written: output_file=%s",
                    contract_path,
                )
            _show_dataset_header(input_file, dataset)
            show_schema(dataset)
            if contract_path is not None:
                show_success(f"Schema contract written: {contract_path}")

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def labels(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    limit: int = typer.Option(
        100,
        "--limit",
        help="Maximum number of value labels to show.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display variable labels and value labels.
    """

    try:
        with command_log_wrapper(
            command="labels",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "limit": limit,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ):
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            _show_dataset_header(input_file, dataset)
            show_labels(dataset, limit)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def metadata(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    export_sidecar: ExportSidecarOption = False,
    apply_sidecar: ApplySidecarOption = False,
    sidecar_output: SidecarOutputOption = None,
    sidecar_input: SidecarInputOption = None,
    overwrite_sidecar: OverwriteSidecarOption = False,
    export_dictionary: ExportDictionaryOption = None,
    overwrite_dictionary: OverwriteDictionaryOption = False,
    export_script: ExportScriptOption = None,
    overwrite_script: OverwriteScriptOption = False,
    patch_file: Annotated[
        str | None, typer.Option("--patch", help="Apply a closed TOML metadata patch.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview sidecar changes without writing.")
    ] = False,
    diagnose: Annotated[
        bool, typer.Option("--diagnose", help="Run read-only metadata diagnostics.")
    ] = False,
    validate_sidecar: Annotated[
        bool, typer.Option("--validate-sidecar", help="Validate a sidecar without applying it.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit diagnostics as JSON.")
    ] = False,
    strict: Annotated[
        bool, typer.Option("--strict", help="Treat diagnostic warnings as failures.")
    ] = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display normalized metadata summary.
    """

    try:
        with command_log_wrapper(
            command="metadata",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "export_sidecar": export_sidecar,
                "apply_sidecar": apply_sidecar,
                "sidecar_output": sidecar_output,
                "sidecar_input": sidecar_input,
                "overwrite_sidecar": overwrite_sidecar,
                "export_dictionary": export_dictionary,
                "overwrite_dictionary": overwrite_dictionary,
                "export_script": export_script,
                "overwrite_script": overwrite_script,
                "patch": patch_file,
                "dry_run": dry_run,
                "diagnose": diagnose,
                "validate_sidecar": validate_sidecar,
                "json": json_output,
                "strict": strict,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ):
            diagnostic_mode = diagnose or validate_sidecar
            patch_mode = patch_file is not None
            apply_save_mode = bool(
                apply_sidecar and sidecar_input is not None
                and (sidecar_output is not None or dry_run)
            )
            if diagnose and validate_sidecar:
                raise MetadataSidecarError(
                    "Use either --diagnose or --validate-sidecar, not both."
                )
            if (json_output or strict) and not (
                diagnostic_mode or patch_mode or apply_save_mode
            ):
                raise MetadataSidecarError(
                    "--json and --strict require --diagnose or --validate-sidecar."
                )
            if diagnostic_mode and any((
                export_sidecar,
                apply_sidecar,
                patch_mode,
                export_dictionary is not None,
                export_script is not None,
            )):
                raise MetadataSidecarError(
                    "Metadata diagnostics cannot be combined with export or apply options."
                )
            if patch_mode and any((export_sidecar, apply_sidecar)):
                raise MetadataSidecarError(
                    "--patch cannot be combined with --export-sidecar or --apply-sidecar."
                )
            if patch_mode and sidecar_output is None:
                raise MetadataSidecarError("--patch requires --sidecar-output.")
            if apply_save_mode and sidecar_output is None:
                raise MetadataSidecarError(
                    "Sidecar apply preview/save requires --sidecar-output."
                )
            if dry_run and not (patch_mode or apply_save_mode):
                raise MetadataSidecarError(
                    "--dry-run requires --patch or an apply-sidecar save workflow."
                )
            if export_sidecar and apply_sidecar:
                raise MetadataSidecarError(
                    "Use either --export-sidecar or --apply-sidecar, not both."
                )
            if sidecar_output is not None and not (
                export_sidecar or patch_mode or apply_save_mode
            ):
                raise MetadataSidecarError(
                    "--sidecar-output requires --export-sidecar, --patch, or apply-sidecar save."
                )
            if sidecar_input is not None and not (apply_sidecar or validate_sidecar):
                raise MetadataSidecarError(
                    "--sidecar-input requires --apply-sidecar or --validate-sidecar."
                )
            if overwrite_sidecar and not (
                export_sidecar or apply_sidecar or patch_mode
            ):
                raise MetadataSidecarError(
                    "--overwrite-sidecar requires --export-sidecar or "
                    "--apply-sidecar."
                )
            if overwrite_dictionary and export_dictionary is None:
                raise DataDictionaryError(
                    "--overwrite-dictionary requires --export-dictionary."
                )
            if overwrite_script and export_script is None:
                raise MetadataScriptError(
                    "--overwrite-script requires --export-script."
                )
            if (
                apply_sidecar and not apply_save_mode
                and get_backend_name(input_file) == "pyreadstat"
            ):
                raise MetadataSidecarError(
                    "Explicit sidecar apply is not supported for native "
                    "statistical formats handled by pyreadstat.",
                    suggestion=(
                        "Convert to a sidecar-aware format before applying "
                        "metadata. Native-file metadata is not modified."
                    ),
                )
            if diagnostic_mode:
                if validate_sidecar:
                    with without_automatic_sidecar():
                        dataset = _read_dataset(
                            input_file,
                            object_selector=object_selector,
                        )
                else:
                    try:
                        dataset = _read_dataset(
                            input_file,
                            object_selector=object_selector,
                        )
                    except MetadataSidecarError:
                        with without_automatic_sidecar():
                            dataset = _read_dataset(
                                input_file,
                                object_selector=object_selector,
                            )
                diagnostics = build_metadata_diagnostics(
                    dataset,
                    input_file,
                    sidecar_input=sidecar_input,
                    require_sidecar=validate_sidecar,
                    object_name=object_selector,
                )
                if json_output:
                    emit_json(asdict(diagnostics))
                else:
                    _show_dataset_header(input_file, dataset)
                    show_metadata_diagnostics(diagnostics)
                if diagnostics.has_errors or (strict and diagnostics.has_warnings):
                    raise typer.Exit(1)
                return
            if patch_mode or apply_save_mode:
                if apply_save_mode:
                    with without_automatic_sidecar():
                        dataset = _read_dataset(
                            input_file,
                            object_selector=object_selector,
                        )
                    preview, edited = preview_sidecar_apply(
                        dataset,
                        input_file,
                        sidecar_input,
                        sidecar_output,
                        overwrite=overwrite_sidecar,
                        object_name=object_selector,
                        dry_run=dry_run,
                    )
                else:
                    dataset = _read_dataset(
                        input_file,
                        object_selector=object_selector,
                    )
                    metadata_patch = parse_metadata_patch(patch_file)
                    preview, edited = preview_metadata_patch(
                        dataset,
                        input_file,
                        metadata_patch,
                        sidecar_output,
                        overwrite=overwrite_sidecar,
                        object_name=object_selector,
                        dry_run=dry_run,
                    )
                strict_warning = strict and any(
                    issue.severity == "warning"
                    for issue in (*preview.conflicts, *preview.issues)
                )
                result = preview
                if not dry_run and preview.valid and not strict_warning:
                    result = save_metadata_sidecar(
                        preview,
                        edited,
                        overwrite=overwrite_sidecar,
                    )
                if json_output:
                    emit_json(asdict(result))
                else:
                    show_metadata_patch_preview(result)
                if not preview.valid or strict_warning:
                    raise typer.Exit(1)
                return
            if apply_sidecar and sidecar_input is not None:
                with without_automatic_sidecar():
                    dataset = _read_dataset(
                        input_file,
                        object_selector=object_selector,
                    )
            else:
                dataset = _read_dataset(
                    input_file,
                    object_selector=object_selector,
                )
            exported_path = None
            dictionary_path = None
            script_path = None
            applied_result = None
            if export_sidecar:
                exported_path = export_metadata_sidecar(
                    dataset,
                    input_file,
                    output_path=sidecar_output,
                    overwrite=overwrite_sidecar,
                )
            elif apply_sidecar:
                applied_result = apply_metadata_sidecar(
                    dataset,
                    input_file,
                    source_path=sidecar_input,
                    overwrite=overwrite_sidecar,
                )
                if sidecar_input is not None:
                    dataset = _read_dataset(
                        input_file,
                        object_selector=object_selector,
                    )
            if export_dictionary is not None:
                dictionary_path = export_data_dictionary(
                    dataset,
                    input_file,
                    export_dictionary,
                    overwrite=overwrite_dictionary,
                )
            if export_script is not None:
                script_path = export_metadata_script(
                    dataset,
                    input_file,
                    export_script,
                    overwrite=overwrite_script,
                )
            _show_dataset_header(input_file, dataset)
            show_metadata_summary(dataset)
            if (
                applied_result is not None
                and applied_result.unmatched_data_columns
            ):
                unmatched = ", ".join(applied_result.unmatched_data_columns)
                show_warning(
                    "Sidecar metadata applies only to matching columns. "
                    f"Columns without sidecar metadata: {unmatched}"
                )
            if exported_path is not None:
                show_success(f"Metadata sidecar written: {exported_path}")
            elif applied_result is not None:
                if applied_result.already_active:
                    show_success(
                        "Metadata sidecar is valid and active: "
                        f"{applied_result.target_path}"
                    )
                else:
                    show_success(
                        f"Metadata sidecar applied: {applied_result.target_path}"
                    )
            if dictionary_path is not None:
                show_success(f"Data dictionary written: {dictionary_path}")
            if script_path is not None:
                show_success(f"Metadata helper script written: {script_path}")

    except typer.Exit:
        raise

    except Exception as exc:
        if json_output:
            emit_json({
                "valid": False,
                "writes": False,
                "target": sidecar_output,
                "source_data_modified": False,
                "sidecar_target_modified": False,
                "overwrite_required": False,
                "changes": [],
                "total_changes": 0,
                "shown_changes": 0,
                "truncated": False,
                "conflicts": [{
                    "severity": "error",
                    "code": "metadata_edit_error",
                    "message": str(exc),
                    "column": None,
                    "field": None,
                    "suggestion": getattr(exc, "suggestion", None),
                    "details": {},
                }],
                "issues": [],
                "coverage": None,
                "object_kind": None,
                "object_name": object_selector,
                "dry_run": dry_run,
            })
        else:
            handle_exception(exc)

        raise typer.Exit(1)


@app.command("metadata-diff")
def metadata_diff(
    left_file: str,
    right_file: str,
    left_object: LeftObjectSelectorOption = None,
    right_object: RightObjectSelectorOption = None,
    columns: Annotated[
        list[str] | None,
        typer.Option("--column", "--columns", help="Compare metadata for this column; repeat as needed."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
    report: Annotated[
        str | None, typer.Option("--report", help="Write a .csv, .json or .html report.")
    ] = None,
    report_format: Annotated[
        str | None, typer.Option("--report-format", help="Report format: json, csv or html.")
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with failure when metadata differs.")
    ] = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Compare normalized metadata without comparing data values."""

    try:
        with command_log_wrapper(
            command="metadata-diff",
            parameters={
                "left_file": left_file,
                "right_file": right_file,
                "left_object": left_object,
                "right_object": right_object,
                "columns": columns,
                "json": json_output,
                "report": report,
                "report_format": report_format,
                "strict": strict,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ):
            if report_format is not None and report is None:
                raise MetadataSidecarError("--report-format requires --report.")
            left = _read_dataset(left_file, object_selector=left_object)
            right = _read_dataset(right_file, object_selector=right_object)
            result = compare_metadata(left, right, columns=columns)
            if json_output:
                emit_json(asdict(result))
            else:
                show_metadata_diff(result)
            if report is not None:
                report_path = write_metadata_diff_report(result, report, report_format)
                if not json_output:
                    show_success(f"Metadata diff report written: {report_path}")
            if strict and not result.same_metadata:
                raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@app.command()
def summary(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output summary as JSON.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display a dataset-level statistical summary.
    """

    try:
        with command_log_wrapper(
            command="summary",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            dataset_summary = summarize_dataset(dataset)
            logger.info(
                "Summary result: rows=%s columns=%s missing_cells=%s",
                dataset_summary.row_count,
                dataset_summary.column_count,
                dataset_summary.total_missing_cells,
            )

            if json_output:
                emit_json(asdict(dataset_summary))
                return

            _show_dataset_header(input_file, dataset)
            show_dataset_summary(dataset_summary)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def describe(
    ctx: typer.Context,
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    columns: list[str] | None = typer.Option(
        None,
        "--columns",
        help="Columns to describe.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output column profiles as JSON.",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Only show profiles of this type: numeric, categorical, datetime or other.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display column-level descriptive profiles.
    """

    try:
        columns = _attach_extra_describe_columns(
            extra_columns=list(ctx.args), columns=columns
        )
        with command_log_wrapper(
            command="describe",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "columns": columns,
                "only": only,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            profiles = profile_columns(dataset, columns=columns)
            profiles = _filter_profiles_by_type(profiles, only)
            logger.info("Describe result: profiles=%s", len(profiles))

            if json_output:
                emit_json([asdict(profile) for profile in profiles])
                return

            _show_dataset_header(input_file, dataset)
            show_column_profiles(profiles)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def frequencies(
    ctx: typer.Context,
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    columns: list[str] | None = typer.Option(
        None,
        "--columns",
        help="Columns to show frequencies for.",
    ),
    top: int = typer.Option(
        20,
        "--top",
        help="Maximum values to show per column.",
    ),
    include_missing: bool = typer.Option(
        False,
        "--include-missing",
        help="Include missing values in frequency tables.",
    ),
    max_unique: int | None = typer.Option(
        None,
        "--max-unique",
        help="Skip default columns with more unique values than this.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output frequency tables as JSON.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display value-count frequency tables.
    """

    try:
        _validate_positive_option(
            "--top",
            top,
        )

        if max_unique is not None:
            _validate_positive_option(
                "--max-unique",
                max_unique,
            )

        columns = _attach_extra_describe_columns(
            extra_columns=list(ctx.args), columns=columns
        )
        with command_log_wrapper(
            command="frequencies",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "columns": columns,
                "top": top,
                "include_missing": include_missing,
                "max_unique": max_unique,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            tables = frequency_tables(
                dataset,
                columns=columns,
                top=top,
                include_missing=include_missing,
                max_unique=max_unique,
            )
            logger.info("Frequency result: tables=%s", len(tables))

            if json_output:
                emit_json([asdict(table) for table in tables])
                return

            _show_dataset_header(input_file, dataset)
            show_frequency_tables(tables)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def missing(
    ctx: typer.Context,
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    columns: list[str] | None = typer.Option(
        None,
        "--columns",
        help="Columns to analyze for missing values.",
    ),
    only_missing: bool = typer.Option(
        False,
        "--only-missing",
        help="Only show columns with missing values or metadata missing values.",
    ),
    threshold: float | None = typer.Option(
        None,
        "--threshold",
        help="Only show columns with missing percentage at or above this value.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output missing profiles as JSON.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display missing-value analysis.
    """

    try:
        _validate_threshold(
            threshold
        )
        columns = _attach_extra_describe_columns(
            extra_columns=list(ctx.args), columns=columns
        )
        with command_log_wrapper(
            command="missing",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "columns": columns,
                "only_missing": only_missing,
                "threshold": threshold,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            profiles = missing_profile(dataset, columns=columns)
            profiles = _filter_missing_profiles(
                profiles,
                only_missing=only_missing,
                threshold=threshold,
            )
            logger.info("Missing-value result: profiles=%s", len(profiles))

            if json_output:
                emit_json([asdict(profile) for profile in profiles])
                return

            _show_dataset_header(input_file, dataset)
            show_missing_profiles(profiles)

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)


@app.command()
def validate(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    to_format: str | None = typer.Option(
        None,
        "--to",
        help="Destination format for conversion-readiness checks.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as validation failures.",
    ),
    schema_contract: str | None = typer.Option(
        None,
        "--schema-contract",
        help="Validate the resolved dataset against a version 1 TOML contract.",
    ),
    stream: StreamOption = False,
    chunk_size: ChunkSizeOption = None,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output validation issues as JSON.",
    ),
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Validate dataset quality and conversion readiness.
    """

    exit_code = 0

    try:
        effective_chunk_size = _streaming_chunk_size(
            stream=stream,
            chunk_size=chunk_size,
        )
        if stream:
            require_streaming_validation_input(input_file)
        _validate_streaming_validate_options(
            stream=stream,
            schema_contract=schema_contract,
            object_selector=object_selector,
            to_format=to_format,
            write_config_file=write_config_file,
        )
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            _write_command_config(
                "validate",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=False,
                input_file=input_file,
                object_selector=object_selector,
                to_format=to_format,
                strict=strict,
                schema_contract=schema_contract,
                json_output=json_output,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        with command_log_wrapper(
            command="validate",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "target_format": to_format,
                "strict": strict,
                "schema_contract": schema_contract,
                "stream": stream,
                "chunk_size": effective_chunk_size,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            streaming_result = None
            dataset = None
            if stream:
                streaming_result = validate_streaming_contract(
                    input_file,
                    schema_contract or "",
                    chunk_size=effective_chunk_size or DEFAULT_STREAMING_CHUNK_SIZE,
                )
                target_extension = None
                issues = []
                contract_validation = streaming_result.contract_validation
            else:
                target_extension = _resolve_target_extension(
                    to_format
                )
                dataset = _read_dataset(
                    input_file,
                    object_selector=object_selector,
                )
                issues = validate_dataset(
                    dataset,
                    target_format=target_extension,
                    strict=strict,
                )
                contract_validation = (
                    validate_schema_contract_file(dataset, schema_contract)
                    if schema_contract is not None
                    else None
                )
            combined_issues = list(issues)
            if contract_validation is not None:
                combined_issues.extend(contract_validation.issues)
            exit_code = _validation_exit_code(
                combined_issues,
                strict,
            )
            error_count = sum(
                issue.severity == "error"
                for issue in combined_issues
            )
            warning_count = sum(
                issue.severity == "warning"
                for issue in combined_issues
            )

            logger.info(
                "Validation result: errors=%s warnings=%s strict=%s "
                "schema_contract=%s",
                error_count,
                warning_count,
                strict,
                schema_contract,
            )

            if json_output:
                validation_payload = [
                    asdict(issue)
                    for issue in issues
                ]
                if streaming_result is not None:
                    emit_json(
                        {
                            "validation": validation_payload,
                            "schema_contract": contract_validation.to_dict(
                                strict=strict,
                            ),
                            "streaming": streaming_result.streaming_dict(),
                        }
                    )
                elif contract_validation is None:
                    emit_json(validation_payload)
                else:
                    emit_json(
                        {
                            "validation": validation_payload,
                            "schema_contract": contract_validation.to_dict(
                                strict=strict,
                            ),
                        }
                    )
            else:
                if streaming_result is not None:
                    show_streaming_validation_summary(
                        streaming_result,
                        strict=strict,
                    )
                else:
                    _show_dataset_header(
                        input_file,
                        dataset,
                    )
                    show_validation_issues(
                        issues,
                        strict=strict,
                        target_format=target_extension,
                    )
                if contract_validation is not None:
                    show_schema_contract_validation(
                        contract_validation,
                        strict=strict,
                    )

            if exit_code:
                log_command_outcome(
                    "validate",
                    exit_code,
                    f"validation found {error_count} error(s) and "
                    f"{warning_count} warning(s)",
                )

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)

    if exit_code:
        raise typer.Exit(
            exit_code
        )


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def compare(
    ctx: typer.Context,
    left_file: str,
    right_file: str,
    object_selector: ObjectSelectorOption = None,
    left_object_selector: LeftObjectSelectorOption = None,
    right_object_selector: RightObjectSelectorOption = None,
    values: bool = typer.Option(
        True,
        "--values/--no-values",
        help="Compare cell values.",
    ),
    sample_size: int | None = typer.Option(
        None,
        "--sample",
        help="Compare only the first N rows of values.",
    ),
    columns: list[str] | None = typer.Option(
        None,
        "--columns",
        help="Columns for schema, metadata and value comparison.",
    ),
    ignore_columns: list[str] | None = typer.Option(
        None,
        "--ignore-columns",
        help="Comma-separated columns to ignore during comparison.",
    ),
    numeric_tolerance: float = typer.Option(
        0.0,
        "--numeric-tolerance",
        help="Absolute tolerance for numeric value differences.",
    ),
    key: str | None = typer.Option(
        None,
        "--key",
        help="Comma-separated key columns used to match rows before comparison.",
    ),
    max_differences: int = typer.Option(
        50,
        "--max-differences",
        help="Maximum number of detailed differences to display or report.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output the comparison as JSON.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat comparison warnings as failures.",
    ),
    report: str | None = typer.Option(
        None,
        "--report",
        help="Write a CSV, JSON or HTML comparison report.",
    ),
    report_format: str | None = typer.Option(
        None,
        "--report-format",
        help="Report format override: csv, json or html.",
    ),
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Compare two datasets."""

    exit_code = 0
    try:
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            columns = _attach_extra_describe_columns(list(ctx.args), columns)
            if sample_size is not None and sample_size <= 0:
                raise CompareError("--sample must be greater than 0.")
            if not values and sample_size is not None:
                raise CompareError("--sample cannot be used with --no-values.")
            _parse_ignore_columns(ignore_columns)
            _parse_key_columns(key)
            _write_command_config(
                "compare",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=False,
                left_file=left_file,
                right_file=right_file,
                object_selector=object_selector,
                left_object_selector=left_object_selector,
                right_object_selector=right_object_selector,
                values=values,
                sample_size=sample_size,
                columns=columns,
                ignore_columns=ignore_columns,
                numeric_tolerance=numeric_tolerance,
                key=key,
                max_differences=max_differences,
                json_output=json_output,
                strict=strict,
                report=report,
                report_format=report_format,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        logged_columns = list(columns or []) + list(ctx.args)
        with command_log_wrapper(
            command="compare",
            parameters={
                "left_file": left_file,
                "right_file": right_file,
                "object": object_selector,
                "left_object": left_object_selector,
                "right_object": right_object_selector,
                "values": values,
                "sample": sample_size,
                "columns": logged_columns or None,
                "ignore_columns": ignore_columns,
                "numeric_tolerance": numeric_tolerance,
                "key": key,
                "max_differences": max_differences,
                "json": json_output,
                "strict": strict,
                "report": report,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            columns = _attach_extra_describe_columns(list(ctx.args), columns)
            if sample_size is not None and sample_size <= 0:
                raise CompareError("--sample must be greater than 0.")
            if not values and sample_size is not None:
                raise CompareError("--sample cannot be used with --no-values.")
            compare_options = CompareOptions(
                ignore_columns=_parse_ignore_columns(ignore_columns),
                numeric_tolerance=numeric_tolerance,
                key_columns=_parse_key_columns(key),
                max_differences=max_differences,
            )

            left_selector, right_selector = resolve_compare_object_selectors(
                object_selector,
                left_object_selector,
                right_object_selector,
            )
            left = _read_dataset(
                left_file,
                object_selector=left_selector,
            )
            right = _read_dataset(
                right_file,
                object_selector=right_selector,
            )
            logger.debug("Comparing datasets")
            comparison = compare_datasets(
                left,
                right,
                compare_values=values,
                sample_size=sample_size,
                columns=columns,
                options=compare_options,
            )
            exit_code = int(
                comparison.has_errors or (strict and comparison.has_warnings)
            )

            logger.info(
                "Comparison result: is_identical=%s has_errors=%s "
                "has_warnings=%s strict=%s",
                comparison.is_identical,
                comparison.has_errors,
                comparison.has_warnings,
                strict,
            )

            if report is not None:
                logger.debug("Writing comparison report: %s", report)
                write_compare_report(comparison, report, report_format)
                logger.info("Comparison report written: output_file=%s", report)

            if json_output:
                emit_json(comparison_to_json_payload(comparison))
            else:
                show_dataset_comparison(comparison)
                if report is not None:
                    show_success(f"Report written: {report}")

            if exit_code:
                log_command_outcome(
                    "compare",
                    exit_code,
                    "comparison differences matched the command exit policy",
                )

    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)

    if exit_code:
        raise typer.Exit(exit_code)


def _parse_ignore_columns(values: list[str] | None) -> tuple[str, ...]:
    """Parse repeatable comma-separated ignored column lists."""

    parsed: list[str] = []
    for value in values or []:
        items = [item.strip() for item in value.split(",")]
        if not items or any(not item for item in items):
            raise CompareError(f"Invalid ignore column list: {value}")
        for item in items:
            if item not in parsed:
                parsed.append(item)
    return tuple(parsed)


def _parse_key_columns(value: str | None) -> tuple[str, ...]:
    """Parse one comma-separated row key while preserving column order."""

    if value is None:
        return ()
    columns = tuple(column.strip() for column in value.split(","))
    if not columns or any(not column for column in columns):
        raise CompareError(f"Invalid key column list: {value}")
    seen: set[str] = set()
    for column in columns:
        if column in seen:
            raise CompareError(f"Duplicate key column specified: {column}")
        seen.add(column)
    return columns


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def report(
    ctx: typer.Context,
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    output_file: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output report file (.html, .htm, .json or .csv).",
    ),
    output_format: str | None = typer.Option(
        None,
        "--format",
        help="Report format override: html, json or csv.",
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Section preset: quick, full, validation or metadata.",
    ),
    sections: list[str] | None = typer.Option(
        None,
        "--section",
        help="Include only this report section. Repeatable.",
    ),
    no_summary: bool = typer.Option(False, "--no-summary", help="Omit dataset summary."),
    no_schema: bool = typer.Option(False, "--no-schema", help="Omit schema."),
    no_metadata: bool = typer.Option(False, "--no-metadata", help="Omit metadata summary."),
    no_labels: bool = typer.Option(False, "--no-labels", help="Omit labels."),
    no_missing: bool = typer.Option(False, "--no-missing", help="Omit missing-value analysis."),
    no_describe: bool = typer.Option(False, "--no-describe", help="Omit descriptive profiles."),
    frequencies: bool = typer.Option(False, "--frequencies", help="Include frequency tables."),
    no_validation: bool = typer.Option(False, "--no-validation", help="Omit validation."),
    columns: list[str] | None = typer.Option(
        None,
        "--columns",
        help="Columns for descriptive profiles and frequencies.",
    ),
    frequency_top: int = typer.Option(
        20,
        "--frequency-top",
        help="Maximum frequency values per column.",
    ),
    frequency_include_missing: bool = typer.Option(
        False,
        "--frequency-include-missing",
        help="Include missing values in frequencies.",
    ),
    frequency_max_unique: int | None = typer.Option(
        None,
        "--frequency-max-unique",
        help="Skip default frequency columns above this unique-value count.",
    ),
    max_table_rows: int = typer.Option(
        1000,
        "--max-table-rows",
        help="Maximum rows rendered per HTML or CSV table.",
    ),
    max_preview_values: int = typer.Option(
        5,
        "--max-preview-values",
        help="Maximum value-label mappings shown in previews.",
    ),
    target_format: str | None = typer.Option(
        None,
        "--target-format",
        help="Validate suitability for a target dataset format.",
    ),
    policy: str | None = typer.Option(
        None,
        "--policy",
        help=(
            "Add a target-aware transfer-policy section; requires --target-format."
        ),
    ),
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Enable strict validation behavior in the report.",
    ),
    schema_contract: str | None = typer.Option(
        None,
        "--schema-contract",
        help="Include version 1 TOML schema-contract validation results.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print a concise JSON summary after writing the report.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Suppress the normal terminal summary.",
    ),
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Generate a profile report for one dataset."""

    try:
        # Preserve direct config execution for configs created before this option existed.
        policy = policy if isinstance(policy, str) else None
        resolved_policy = None
        if policy is not None:
            if target_format is None:
                raise ConversionError("--policy requires --target-format TARGET.")
            if write_config_file is not None:
                raise ConversionError(
                    "Report transfer policies are not supported by workflow configuration yet."
                )
            resolved_policy = resolve_policy(policy)
            resolve_target_capabilities(target_format)
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            _validate_positive_option("--frequency-top", frequency_top)
            if frequency_max_unique is not None:
                _validate_positive_option(
                    "--frequency-max-unique",
                    frequency_max_unique,
                )
            resolve_report_options(
                preset=preset,
                sections=sections,
                no_summary=no_summary,
                no_schema=no_schema,
                no_metadata=no_metadata,
                no_labels=no_labels,
                no_missing=no_missing,
                no_describe=no_describe,
                frequencies=frequencies,
                no_validation=no_validation,
                max_table_rows=max_table_rows,
                max_preview_values=max_preview_values,
            )
            columns = _attach_extra_describe_columns(list(ctx.args), columns)
            _write_command_config(
                "report",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=create_dirs,
                input_file=input_file,
                object_selector=object_selector,
                output_file=output_file,
                output_format=output_format,
                overwrite=overwrite,
                create_dirs=create_dirs,
                preset=preset,
                sections=sections,
                no_summary=no_summary,
                no_schema=no_schema,
                no_metadata=no_metadata,
                no_labels=no_labels,
                no_missing=no_missing,
                no_describe=no_describe,
                frequencies=frequencies,
                no_validation=no_validation,
                columns=columns,
                frequency_top=frequency_top,
                frequency_include_missing=frequency_include_missing,
                frequency_max_unique=frequency_max_unique,
                max_table_rows=max_table_rows,
                max_preview_values=max_preview_values,
                target_format=target_format,
                strict_validation=strict_validation,
                schema_contract=schema_contract,
                json_output=json_output,
                quiet=quiet,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
            )
            return
        logged_columns = list(columns or []) + list(ctx.args)
        with command_log_wrapper(
            command="report",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "output": output_file,
                "format": output_format,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
                "preset": preset,
                "sections": sections,
                "columns": logged_columns or None,
                "frequencies": frequencies,
                "max_table_rows": max_table_rows,
                "max_preview_values": max_preview_values,
                "target_format": target_format,
                "policy": resolved_policy,
                "strict_validation": strict_validation,
                "schema_contract": schema_contract,
                "json": json_output,
                "quiet": quiet,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            _validate_positive_option("--frequency-top", frequency_top)
            if frequency_max_unique is not None:
                _validate_positive_option(
                    "--frequency-max-unique",
                    frequency_max_unique,
                )
            report_options = resolve_report_options(
                preset=preset,
                sections=sections,
                no_summary=no_summary,
                no_schema=no_schema,
                no_metadata=no_metadata,
                no_labels=no_labels,
                no_missing=no_missing,
                no_describe=no_describe,
                frequencies=frequencies,
                no_validation=no_validation,
                max_table_rows=max_table_rows,
                max_preview_values=max_preview_values,
            )
            if schema_contract is not None and not report_options.include_validation:
                raise ContractError(
                    "--schema-contract requires the report validation section."
                )
            columns = _attach_extra_describe_columns(list(ctx.args), columns)
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            contract_validation = (
                validate_schema_contract_file(dataset, schema_contract)
                if schema_contract is not None
                else None
            )
            transfer_plan = (
                build_transfer_plan(
                    dataset,
                    source_path=input_file,
                    target=target_format,
                    policy=resolved_policy,
                    object_selector=object_selector,
                )
                if resolved_policy is not None and target_format is not None
                else None
            )
            logger.debug("Building dataset report")
            dataset_report = build_dataset_report(
                dataset,
                include_summary=report_options.include_summary,
                include_schema=report_options.include_schema,
                include_metadata=report_options.include_metadata,
                include_labels=report_options.include_labels,
                include_missing=report_options.include_missing,
                include_describe=report_options.include_describe,
                include_frequencies=report_options.include_frequencies,
                include_validation=report_options.include_validation,
                columns=columns,
                frequency_top=frequency_top,
                frequency_include_missing=frequency_include_missing,
                frequency_max_unique=frequency_max_unique,
                validation_target_format=target_format,
                strict_validation=strict_validation,
                label_preview_values=report_options.max_preview_values,
                schema_contract_validation=contract_validation,
                transfer_plan=transfer_plan,
            )
            logger.debug("Writing dataset report: %s", output_file)
            write_dataset_report(
                dataset_report,
                output_file,
                output_format=output_format,
                max_table_rows=report_options.max_table_rows,
                overwrite=overwrite,
                create_dirs=create_dirs,
            )

            resolved_output_format = (
                output_format
                or Path(output_file).suffix.lstrip(".").lower()
            )
            logger.info("Dataset report written: output_file=%s", output_file)
            logger.info(
                "Report result: output_file=%s format=%s sections=%s issues=%s",
                output_file,
                resolved_output_format,
                dataset_report.section_count,
                dataset_report.issue_count,
            )

            if json_output:
                emit_json(
                    dataset_report_summary_dict(
                        dataset_report,
                        output_file,
                        output_format,
                        preset=report_options.preset,
                        max_table_rows=report_options.max_table_rows,
                        max_preview_values=report_options.max_preview_values,
                    )
                )
            elif not quiet:
                show_dataset_report_written(
                    dataset_report,
                    output_file,
                    output_format,
                    preset=report_options.preset,
                    max_table_rows=report_options.max_table_rows,
                    max_preview_values=report_options.max_preview_values,
                )
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@app.command()
def batch(
    ctx: typer.Context,
    input_path: str,
    output_path: str,
    to_format: str = typer.Option(
        ...,
        "--to",
        help="Target output format, for example csv, parquet, sav or xlsx.",
    ),
    object_selector: ObjectSelectorOption = None,
    object_manifest: str | None = typer.Option(
        None,
        "--object-manifest",
        help="Use included rows from an object discovery CSV as batch tasks.",
    ),
    all_objects: bool = typer.Option(
        False,
        "--all-objects",
        help="Expand container files and convert every supported dataset object.",
    ),
    transform_items: bool = typer.Option(
        False,
        "--transform",
        help="Apply the existing transformation pipeline to every batch item.",
    ),
    select: list[str] | None = typer.Option(
        None,
        "--select",
        help="Select columns in every batch item. Can be repeated.",
    ),
    drop: list[str] | None = typer.Option(
        None,
        "--drop",
        help="Drop columns from every batch item. Can be repeated.",
    ),
    rename: list[str] | None = typer.Option(
        None,
        "--rename",
        help="Rename a column using OLD=NEW. Can be repeated.",
    ),
    type_items: list[str] | None = typer.Option(
        None,
        "--type",
        help="Convert a column using COLUMN=TYPE. Can be repeated.",
    ),
    type_errors: str = typer.Option(
        "raise",
        "--type-errors",
        help="Type conversion error mode: raise, coerce or ignore.",
    ),
    datetime_format: str | None = typer.Option(
        None,
        "--datetime-format",
        help="Datetime parsing format for type conversion.",
    ),
    filter_items: list[str] | None = typer.Option(
        None,
        "--filter",
        help="Filter rows using COLUMN,OPERATOR,VALUE. Can be repeated.",
    ),
    filter_mode: str = typer.Option(
        "and",
        "--filter-mode",
        help="Combine filters with and or or.",
    ),
    recode: list[str] | None = typer.Option(
        None,
        "--recode",
        help="Recode values using COLUMN:OLD=NEW,OLD=NEW. Can be repeated.",
    ),
    recode_default: str | None = typer.Option(
        None,
        "--recode-default",
        help="Default value for unmapped non-missing recode values.",
    ),
    update_value_labels: bool = typer.Option(
        True,
        "--update-value-labels/--no-update-value-labels",
        help="Update normalized value labels during recode.",
    ),
    ignore_missing_columns: bool = typer.Option(
        False,
        "--ignore-missing-columns",
        help="Ignore missing columns for select, drop and rename.",
    ),
    reset_index: bool = typer.Option(
        True,
        "--reset-index/--no-reset-index",
        help="Reset row index after filtering.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Include files in subdirectories and calculate paths from the input root.",
    ),
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
    stream: BatchStreamOption = False,
    chunk_size: BatchChunkSizeOption = None,
    write_config_file: WriteConfigOption = None,
    overwrite_config: OverwriteConfigOption = False,
    preserve_structure: bool = typer.Option(
        True,
        "--preserve-structure/--flatten",
        help="Preserve relative folders, or flatten all outputs into one directory.",
    ),
    include_unsupported: bool = typer.Option(
        True,
        "--include-unsupported/--supported-only",
        help="Show unsupported inputs as skipped, or omit them from the plan.",
    ),
    patterns: list[str] | None = typer.Option(
        None,
        "--pattern",
        help="Include filename or relative-path glob matches. Can be repeated.",
    ),
    exclude_patterns: list[str] | None = typer.Option(
        None,
        "--exclude-pattern",
        help="Exclude filename or relative-path glob matches after includes. Repeatable.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the batch plan without converting files.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop execution after the first failed conversion.",
    ),
    allow_blocked: bool = typer.Option(
        False,
        "--allow-blocked",
        help="Execute pending items even when the plan contains blocked items.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output the batch plan or result as JSON.",
    ),
    report: str | None = typer.Option(
        None,
        "--report",
        help="Write a CSV or JSON batch report.",
    ),
    report_format: str | None = typer.Option(
        None,
        "--report-format",
        help="Report format override: csv or json.",
    ),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        help="Disable file-level progress display.",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        help="Number of parallel worker threads to use for batch conversion. Default: 1.",
    ),
    validate_inputs: bool = typer.Option(
        False,
        "--validate",
        help="Validate each pending dataset before conversion.",
    ),
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Treat validation warnings as failures. Requires --validate.",
    ),
    input_encoding: InputEncodingOption = None,
    output_encoding: OutputEncodingOption = None,
    csv_delimiter: CsvDelimiterOption = None,
    csv_decimal: CsvDecimalOption = None,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Convert many datasets to one target format.
    """

    exit_code = 0

    try:
        effective_chunk_size = _streaming_chunk_size(
            stream=stream,
            chunk_size=chunk_size,
        )
        _validate_batch_streaming_options(
            stream=stream,
            transform_items=transform_items,
            validate_inputs=validate_inputs,
            object_selector=object_selector,
            object_manifest=object_manifest,
            all_objects=all_objects,
            write_config_file=write_config_file,
        )
        _validate_write_config_options(write_config_file, overwrite_config)
        if write_config_file is not None:
            transform_pipeline = build_pipeline_from_cli_options(
                select_columns=select,
                drop_columns=drop,
                rename_items=rename,
                type_items=type_items,
                type_errors=type_errors,
                datetime_format=datetime_format,
                filter_items=filter_items,
                filter_mode=filter_mode,
                recode_items=recode,
                recode_default=recode_default,
                update_value_labels=update_value_labels,
                ignore_missing_columns=ignore_missing_columns,
                reset_index=reset_index,
            )
            transform_options_supplied = _batch_transform_options_supplied(ctx)
            if transform_items and transform_pipeline.is_empty():
                raise BatchError(
                    "--transform requires at least one transformation option."
                )
            if not transform_items and transform_options_supplied:
                raise BatchError("Transformation options require --transform.")
            transform_config_options: dict[str, Any] = {}
            if transform_items:
                transform_config_options = {
                    "select": select,
                    "drop": drop,
                    "rename": rename,
                    "type_items": type_items,
                    "type_errors": type_errors,
                    "datetime_format": datetime_format,
                    "filter_items": filter_items,
                    "filter_mode": filter_mode,
                    "recode": recode,
                    "recode_default": recode_default,
                    "update_value_labels": update_value_labels,
                    "ignore_missing_columns": ignore_missing_columns,
                    "reset_index": reset_index,
                }
            _write_command_config(
                "batch",
                write_config_file,
                overwrite_config=overwrite_config,
                create_config_dirs=create_dirs,
                input_path=input_path,
                output_path=output_path,
                to_format=to_format,
                object_selector=object_selector,
                object_manifest=object_manifest,
                all_objects=all_objects,
                transform_items=transform_items,
                recursive=recursive,
                overwrite=overwrite,
                create_dirs=create_dirs,
                preserve_structure=preserve_structure,
                include_unsupported=include_unsupported,
                patterns=patterns,
                exclude_patterns=exclude_patterns,
                dry_run=dry_run,
                fail_fast=fail_fast,
                allow_blocked=allow_blocked,
                json_output=json_output,
                report=report,
                report_format=report_format,
                no_progress=no_progress,
                workers=workers,
                validate_inputs=validate_inputs,
                strict_validation=strict_validation,
                input_encoding=input_encoding,
                output_encoding=output_encoding,
                csv_delimiter=csv_delimiter,
                csv_decimal=csv_decimal,
                log_file=log_file,
                log_level=log_level,
                log_append=log_append,
                developer_log=developer_log,
                **transform_config_options,
            )
            return
        with command_log_wrapper(
            command="batch",
            parameters={
                "input_path": input_path,
                "output_path": output_path,
                "to": to_format,
                "object": object_selector,
                "object_manifest": object_manifest,
                "all_objects": all_objects,
                "transform": transform_items,
                "select": select,
                "drop": drop,
                "rename": rename,
                "type": type_items,
                "filters": filter_items,
                "recode": recode,
                "recursive": recursive,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
                "stream": stream,
                "chunk_size": effective_chunk_size,
                "preserve_structure": preserve_structure,
                "include_unsupported": include_unsupported,
                "pattern": patterns,
                "exclude_pattern": exclude_patterns,
                "dry_run": dry_run,
                "fail_fast": fail_fast,
                "workers": workers,
                "report": report,
                "validate": validate_inputs,
                "strict_validation": strict_validation,
                "input_encoding": input_encoding,
                "output_encoding": output_encoding,
                "csv_delimiter": csv_delimiter,
                "csv_decimal": csv_decimal,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            read_options, write_options = _dataset_io_options(
                input_encoding,
                output_encoding,
                csv_delimiter,
                csv_decimal,
            )
            transform_pipeline = build_pipeline_from_cli_options(
                select_columns=select,
                drop_columns=drop,
                rename_items=rename,
                type_items=type_items,
                type_errors=type_errors,
                datetime_format=datetime_format,
                filter_items=filter_items,
                filter_mode=filter_mode,
                recode_items=recode,
                recode_default=recode_default,
                update_value_labels=update_value_labels,
                ignore_missing_columns=ignore_missing_columns,
                reset_index=reset_index,
            )
            transform_options_supplied = _batch_transform_options_supplied(ctx)
            if transform_items and transform_pipeline.is_empty():
                raise BatchError(
                    "--transform requires at least one transformation option."
                )
            if not transform_items and transform_options_supplied:
                raise BatchError(
                    "Transformation options require --transform."
                )
            active_transform_pipeline = (
                transform_pipeline
                if transform_items
                else None
            )
            def option_warning(message: str) -> None:
                _show_dataset_option_warning(
                    message,
                    json_output=json_output,
                )
            if object_selector is not None and object_manifest is not None:
                raise BatchError(
                    "Use either --object or --object-manifest, not both."
                )
            if object_selector is not None and all_objects:
                raise BatchError(
                    "Use either --object or --all-objects, not both."
                )
            if object_manifest is not None and all_objects:
                raise BatchError(
                    "Use either --object-manifest or --all-objects, not both."
                )
            object_mode = (
                "manifest"
                if object_manifest is not None
                else "all_objects"
                if all_objects
                else "object"
                if object_selector is not None
                else "none"
            )
            plan = build_batch_plan(
                input_path=input_path,
                output_path=output_path,
                target_extension=to_format,
                recursive=recursive,
                overwrite=overwrite,
                include_unsupported=include_unsupported,
                preserve_structure=preserve_structure,
                patterns=patterns,
                exclude_patterns=exclude_patterns,
                object_manifest=object_manifest,
                all_objects=all_objects,
                workers=workers,
                transform_enabled=transform_items,
                validation_enabled=validate_inputs,
                streaming_enabled=stream,
                chunk_size=effective_chunk_size,
                object_mode=object_mode,
            )
            input_path_value = Path(input_path)
            output_path_value = Path(output_path)
            if input_path_value.is_file() and output_path_value.suffix:
                validate_output_parent_directory(
                    output_path_value,
                    create_dirs=create_dirs,
                    dry_run=dry_run,
                )
            else:
                validate_output_root_directory(
                    output_path_value,
                    create_dirs=create_dirs,
                    dry_run=dry_run,
                )

            if dry_run:
                if report is not None:
                    write_batch_plan_report(plan, report, report_format)
                if not json_output:
                    console.print(
                        "[bold]Dry run:[/bold] planning only; no datasets will be converted."
                    )
                _show_batch_json_or_plan(
                    plan,
                    json_output,
                    report_path=report,
                )
                logger.info(
                    "Batch plan result: total=%s pending=%s skipped=%s blocked=%s",
                    plan.total_count,
                    plan.pending_count,
                    plan.skipped_count,
                    plan.blocked_count,
                )
                exit_code = 1 if plan.has_blockers else 0

            elif plan.has_blockers and not allow_blocked:
                _show_batch_json_or_plan(
                    plan,
                    json_output,
                    report_path=report,
                )

                if not json_output:
                    show_error(
                        "Batch plan contains blocked items. Fix blockers, use --overwrite, or use --dry-run to inspect the plan."
                    )

                logger.info(
                    "Batch plan result: total=%s pending=%s skipped=%s blocked=%s",
                    plan.total_count,
                    plan.pending_count,
                    plan.skipped_count,
                    plan.blocked_count,
                )
                exit_code = 1

            else:
                if json_output or no_progress:
                    if no_progress and not json_output:
                        show_batch_workload(plan, report_path=report)
                    result = execute_batch_plan(
                        plan,
                        fail_fast=fail_fast,
                        workers=workers,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        object_selector=object_selector,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=option_warning,
                        transform_pipeline=active_transform_pipeline,
                    )
                else:
                    result = run_batch_with_progress(
                        plan,
                        fail_fast=fail_fast,
                        workers=workers,
                        validate=validate_inputs,
                        strict_validation=strict_validation,
                        object_selector=object_selector,
                        read_options=read_options,
                        write_options=write_options,
                        on_option_warning=option_warning,
                        transform_pipeline=active_transform_pipeline,
                        report_path=report,
                    )

                if report is not None:
                    write_batch_result_report(result, report, report_format)

                if json_output:
                    _print_json(
                        result
                    )
                else:
                    show_batch_result(
                        result,
                        report_path=report,
                    )

                logger.info(
                    "Batch result: total=%s succeeded=%s failed=%s skipped=%s "
                    "blocked=%s",
                    result.total_count,
                    result.success_count,
                    result.failed_count,
                    result.skipped_count,
                    result.blocked_count,
                )
                exit_code = 1 if result.has_failures or result.has_blockers else 0

            if exit_code:
                log_command_outcome(
                    "batch",
                    exit_code,
                    "batch blockers or failed items matched the command exit policy",
                )

    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)

    if exit_code:
        raise typer.Exit(
            exit_code
        )


def _show_batch_json_or_plan(
    plan,
    json_output: bool,
    report_path: str | None = None,
) -> None:
    """
    Show a batch plan in either scriptable or Rich format.
    """

    if json_output:
        _print_json(
            plan
        )
        return

    show_batch_plan(
        plan,
        report_path=report_path,
    )


def _print_json(
    value,
) -> None:
    """
    Print dataclass values as JSON.
    """

    emit_json(value)


def _attach_extra_describe_columns(
    extra_columns: list[str] | None,
    columns: list[str] | None,
) -> list[str] | None:
    """
    Support compact --columns lists accepted as trailing args.
    """

    if not extra_columns:
        return columns

    if columns:
        return list(
            columns
        ) + list(
            extra_columns
        )

    raise ValueError(
        "Extra column values are only supported after --columns."
    )


def _validate_positive_option(
    option_name: str,
    value: int,
) -> None:
    """
    Validate that an integer CLI option is positive.
    """

    if value <= 0:
        raise ValueError(
            f"{option_name} must be greater than 0."
        )


def _validate_threshold(
    threshold: float | None,
) -> None:
    """
    Validate the missing-percentage threshold option.
    """

    if threshold is None:
        return

    if threshold < 0 or threshold > 100:
        raise ValueError(
            "--threshold must be between 0 and 100."
        )


def _filter_profiles_by_type(
    profiles: list[ColumnProfile],
    profile_type: str | None,
) -> list[ColumnProfile]:
    """
    Filter profiles by profile type.
    """

    if profile_type is None:
        return profiles

    supported_types = {
        "numeric",
        "categorical",
        "datetime",
        "other",
    }

    if profile_type not in supported_types:
        raise ValueError(
            "Unsupported profile type. Use numeric, categorical, datetime or other."
        )

    return [
        profile
        for profile in profiles
        if profile.profile_type == profile_type
    ]


def _filter_missing_profiles(
    profiles: list[MissingProfile],
    only_missing: bool,
    threshold: float | None,
) -> list[MissingProfile]:
    """
    Apply display filters to missing-value profiles.
    """

    filtered = profiles

    if only_missing:
        filtered = [
            profile
            for profile in filtered
            if profile.missing_count > 0 or profile.metadata_missing_values
        ]

    if threshold is not None:
        filtered = [
            profile
            for profile in filtered
            if profile.missing_percent >= threshold
        ]

    return filtered


def _resolve_target_extension(
    target: str | None,
) -> str | None:
    """
    Resolve a user-provided target format to a registered extension.
    """

    if target is None:
        return None

    result = resolve_format_info(
        target
    )

    if not result:
        raise ValueError(
            f"Unsupported target format: {target}"
        )

    extension, _ = result

    return extension


def _validation_exit_code(
    issues,
    strict: bool,
) -> int:
    """
    Return the validate command exit code for issues and strict mode.
    """

    if any(
        issue.severity == "error"
        for issue in issues
    ):
        return 1

    if strict and any(
        issue.severity == "warning"
        for issue in issues
    ):
        return 1

    return 0


def _log_validation_block(
    logger: py_logging.Logger,
    *,
    command: str,
    exc: ValidationFailedError,
    strict: bool,
) -> None:
    """Record a validation policy block as an intentional command outcome."""

    error_count = sum(issue.severity == "error" for issue in exc.issues)
    warning_count = sum(issue.severity == "warning" for issue in exc.issues)
    reason = (
        "strict_validation_failed"
        if strict and error_count == 0 and warning_count > 0
        else "validation_failed"
    )
    logger.warning(
        "Validation blocked output: errors=%s warnings=%s strict=%s. "
        "Output was not written.",
        error_count,
        warning_count,
        strict,
    )
    log_command_outcome(command, 1, reason)


@app.command()
def ui(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Loopback host for the local browser UI.",
    ),
    port: int = typer.Option(
        8765,
        "--port",
        min=1,
        max=65535,
        help="Local TCP port for the browser UI.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Start the local UI without opening a browser.",
    ),
):
    """Launch the optional local StatConvert browser interface."""

    try:
        from statconvert.webui.launcher import launch_ui

        launch_ui(
            host=host,
            port=port,
            open_browser=not no_browser,
            on_start=lambda open_url, bound_address: console.print(
                "[bold blue]StatConvert UI[/bold blue]\n"
                f"Open URL: {open_url}\n"
                f"Bound address: {bound_address}"
            ),
        )
    except KeyboardInterrupt:
        return
    except Exception as exc:
        handle_exception(exc)
        raise typer.Exit(1)


@app.command()
def peek(
    input_file: str,
    object_selector: ObjectSelectorOption = None,
    rows: int = 5,
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """
    Display the first rows of a dataset.
    """

    try:
        with command_log_wrapper(
            command="peek",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "rows": rows,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
            )
            logger.info("Preview result: requested_rows=%s", rows)
            _show_dataset_header(input_file, dataset)
            show_preview(dataset, rows)


    except Exception as exc:

        handle_exception(exc)

        raise typer.Exit(1)
