from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from statconvert.backends.objects import DatasetObjectInfo, NamedDataset
from statconvert.dataset import Dataset
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.exceptions import ConversionError
from statconvert.inspection import (
    ValidationFailedError,
    ValidationIssue,
    validate_for_write,
    validation_should_fail,
)
from statconvert.logging import get_logger
from statconvert.output_paths import validate_output_file_path
from statconvert.registry import (
    get_reader_for_file,
    get_writer_for_file,
    format_supports_multi_object_write,
    format_supports_objects,
    list_dataset_objects,
    read_dataset,
    validate_dataset_object_names,
    write_dataset,
    write_dataset_objects,
)
from statconvert.ui import show_verbose
from statconvert.ui.progress import progress


@dataclass(frozen=True)
class MultiObjectConversionResult:
    """Summary of one container-to-container conversion."""

    objects: tuple[NamedDataset, ...]
    skipped_objects: tuple[DatasetObjectInfo, ...]

    @property
    def rows(self) -> int:
        return sum(item.dataset.rows for item in self.objects)


def transform(
    input_file: str,
    output_file: str,
    overwrite: bool = False,
    create_dirs: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    on_validation: Callable[[list[ValidationIssue]], None] | None = None,
    object_selector: str | None = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
) -> Dataset:
    """
    Convert one dataset file to another format.
    """

    input_path = Path(input_file)
    output_path = Path(output_file)
    logger = get_logger()

    if not input_path.exists():
        raise ConversionError(
            f"Input file does not exist: {input_file}"
        )

    # Determine reader and writer

    try:
        reader = get_reader_for_file(input_file)
        writer = get_writer_for_file(output_file)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
    validate_output_file_path(
        output_path,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )
    logger.debug(
        "Conversion backends resolved: reader=%s writer=%s",
        reader.__class__.__name__,
        writer.__class__.__name__,
    )

    # Read dataset
    
    show_verbose(f"Reader backend : {reader.__class__.__name__}")
    show_verbose(f"Reading        : {input_file}")

    with progress(f"Reading {input_path.name}"):

        dataset = read_dataset(
            input_file,
            object_selector=object_selector,
            options=read_options,
            on_option_warning=on_option_warning,
        )

    logger.info(
        "Input read completed: input_file=%s rows=%s columns=%s",
        input_file,
        dataset.rows,
        len(dataset.columns),
    )

    if validate or strict_validation:
        logger.debug("Validating dataset before conversion write")
        issues = validate_for_write(
            dataset,
            target_format=output_path.suffix.lower() or None,
            strict=strict_validation,
        )
        if on_validation is not None:
            on_validation(issues)
        logger.info(
            "Conversion validation completed: issues=%s errors=%s warnings=%s",
            len(issues),
            sum(issue.severity == "error" for issue in issues),
            sum(issue.severity == "warning" for issue in issues),
        )
        if validation_should_fail(issues, strict=strict_validation):
            raise ValidationFailedError(issues)

    # Write dataset
    
    show_verbose(f"Writer backend : {writer.__class__.__name__}")
    show_verbose(f"Writing        : {output_file}")

    show_verbose(f"Rows           : {dataset.rows:,}")
    show_verbose(f"Columns        : {len(dataset.columns):,}")

    with progress(f"Writing {output_path.name}"):

        write_dataset(
            dataset,
            output_file,
            options=write_options,
            on_option_warning=on_option_warning,
        )

    logger.info("Output write completed: output_file=%s", output_file)
        
    return dataset


def transform_all_objects(
    input_file: str,
    output_file: str,
    overwrite: bool = False,
    create_dirs: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    on_validation: (
        Callable[[str, list[ValidationIssue]], None] | None
    ) = None,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
) -> MultiObjectConversionResult:
    """Convert all supported objects in one input container to one container."""

    input_path = Path(input_file)
    output_path = Path(output_file)
    logger = get_logger()

    if not input_path.exists():
        raise ConversionError(f"Input file does not exist: {input_file}")

    try:
        reader = get_reader_for_file(input_file)
        writer = get_writer_for_file(output_file)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None

    if not format_supports_objects(input_path.suffix):
        raise ConversionError(
            "--all-objects requires a multi-object input format.\n"
            "For single-dataset inputs, omit --all-objects."
        )
    if not format_supports_multi_object_write(output_path.suffix):
        raise ConversionError(
            "--all-objects requires a multi-object output format such as "
            "xlsx or ods.\n"
            "Use batch --all-objects to write each object to separate files."
        )

    validate_output_file_path(
        output_path,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )
    logger.debug(
        "Multi-object conversion backends resolved: reader=%s writer=%s",
        reader.__class__.__name__,
        writer.__class__.__name__,
    )

    show_verbose(f"Reader backend : {reader.__class__.__name__}")
    show_verbose(f"Listing objects: {input_file}")
    with progress(f"Listing objects in {input_path.name}"):
        object_info = list_dataset_objects(input_path)

    supported = [item for item in object_info if item.supported]
    skipped = [item for item in object_info if not item.supported]
    if not supported:
        raise ConversionError(
            f"No supported dataset objects were found in {input_path.name}."
        )

    output_names = [
        item.name if item.name.strip() else _fallback_object_name(item)
        for item in supported
    ]
    validate_dataset_object_names(output_names, output_path)

    named_datasets: list[NamedDataset] = []
    for info, output_name in zip(supported, output_names, strict=True):
        selector = info.name if info.name.strip() else str(info.index)
        show_verbose(f"Reading object  : {output_name}")
        with progress(f"Reading {input_path.name}: {output_name}"):
            dataset = read_dataset(
                input_path,
                object_selector=selector,
                options=read_options,
                on_option_warning=on_option_warning,
            )

        if validate or strict_validation:
            issues = validate_for_write(
                dataset,
                target_format=output_path.suffix.lower() or None,
                strict=strict_validation,
            )
            if on_validation is not None:
                on_validation(output_name, issues)
            if validation_should_fail(issues, strict=strict_validation):
                raise ValidationFailedError(issues)

        named_datasets.append(
            NamedDataset(
                name=output_name,
                dataset=dataset,
                source_object_index=info.index,
                source_object_name=info.name or None,
            )
        )

    show_verbose(f"Writer backend : {writer.__class__.__name__}")
    show_verbose(f"Writing objects: {output_file}")
    with progress(f"Writing {output_path.name}"):
        write_dataset_objects(
            named_datasets,
            output_path,
            options=write_options,
            on_option_warning=on_option_warning,
        )

    logger.info(
        "Multi-object output write completed: output_file=%s objects=%s "
        "skipped=%s rows=%s",
        output_file,
        len(named_datasets),
        len(skipped),
        sum(item.dataset.rows for item in named_datasets),
    )
    return MultiObjectConversionResult(
        objects=tuple(named_datasets),
        skipped_objects=tuple(skipped),
    )


def _fallback_object_name(info: DatasetObjectInfo) -> str:
    """Return the documented fallback for an unnamed input object."""

    if info.index is None:
        raise ConversionError(
            "An input object has no usable name or index. "
            "Custom output object renaming is not supported by "
            "convert --all-objects yet."
        )
    return f"object_{info.index}"
