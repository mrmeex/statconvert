from dataclasses import asdict
import logging as py_logging
from pathlib import Path
from typing import Annotated

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
)
from statconvert.collection import (
    CollectionPlanItem,
    build_collection_plan,
    execute_collection_plan,
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
    list_backends,
    list_dataset_objects,
    list_formats,
    read_dataset,
    resolve_format_info,
    resolve_format_or_backend,
)
from statconvert.exceptions import ConversionError, ObjectSelectionNotSupportedError
from statconvert.transformer import transform_file
from statconvert.transformations.cli_parsing import build_pipeline_from_cli_options
from statconvert.version import format_version_status

from statconvert.ui import (
    console,
    emit_json,
    show_backends_table,
    show_batch_plan,
    show_batch_result,
    run_batch_with_progress,
    show_capabilities_panel,
    show_collection_plan,
    show_collection_result,
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
    show_validation_issues,
    show_formats_table,
    show_labels,
    show_metadata_summary,
    show_preview,
    show_objects_not_supported,
    show_schema,
    show_error,
    show_warning,
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
        with command_log_wrapper(
            command="convert",
            parameters={
                "input_file": input_file,
                "output_file": output_file,
                "object": object_selector,
                "all_objects": all_objects,
                "overwrite": overwrite,
                "create_dirs": create_dirs,
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
                if all_objects:
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
                else:
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
            except ValidationFailedError as exc:
                validation_failure = exc
                _log_validation_block(
                    logger,
                    command="convert",
                    exc=exc,
                    strict=strict_validation,
                )
            else:
                if all_objects:
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
                else:
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
    overwrite: OverwriteOption = False,
    create_dirs: CreateDirsOption = False,
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

    try:
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
                "filters": filter_items,
                "recode": recode,
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
            pipeline = build_pipeline_from_cli_options(
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
            try:
                dataset = transform_file(
                    input_file=input_file,
                    output_file=output_file,
                    pipeline=pipeline,
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
                )

                if not dry_run:
                    show_success(
                        "Transformation completed."
                    )

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
                        show_objects_not_supported()
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
            show_schema(dataset)

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
            show_metadata_summary(dataset)

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
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output validation issues as JSON.",
    ),
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
        with command_log_wrapper(
            command="validate",
            parameters={
                "input_file": input_file,
                "object": object_selector,
                "target_format": to_format,
                "strict": strict,
                "json": json_output,
            },
            log_file=log_file,
            log_level=log_level,
            log_append=log_append,
            developer_log=developer_log,
        ) as logger:
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
            exit_code = _validation_exit_code(
                issues,
                strict,
            )
            error_count = sum(issue.severity == "error" for issue in issues)
            warning_count = sum(issue.severity == "warning" for issue in issues)

            logger.info(
                "Validation result: errors=%s warnings=%s strict=%s",
                error_count,
                warning_count,
                strict,
            )

            if json_output:
                emit_json([asdict(issue) for issue in issues])
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
    log_file: LogFileOption = None,
    log_level: LogLevelOption = "info",
    log_append: LogAppendOption = False,
    developer_log: DeveloperLogOption = False,
):
    """Compare two datasets."""

    exit_code = 0
    try:
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
    strict_validation: bool = typer.Option(
        False,
        "--strict-validation",
        help="Enable strict validation behavior in the report.",
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
                "strict_validation": strict_validation,
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
            columns = _attach_extra_describe_columns(list(ctx.args), columns)
            dataset = _read_dataset(
                input_file,
                object_selector=object_selector,
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
            transform_options_supplied = any(
                (
                    source := ctx.get_parameter_source(option_name)
                ) is not None
                and source.name == "COMMANDLINE"
                for option_name in (
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
            )
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
                _show_batch_json_or_plan(
                    plan,
                    json_output,
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
                    )

                if report is not None:
                    write_batch_result_report(result, report, report_format)

                if json_output:
                    _print_json(
                        result
                    )
                else:
                    show_batch_result(
                        result
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
        plan
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
