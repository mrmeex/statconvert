from pathlib import Path
from typing import Callable

from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.inspection import (
    ValidationFailedError,
    ValidationIssue,
    validate_for_write,
    validation_should_fail,
)
from statconvert.logging import get_logger
from statconvert.registry import get_reader_for_file, get_writer_for_file, read_dataset
from statconvert.ui import show_verbose
from statconvert.ui.progress import progress


def transform(
    input_file: str,
    output_file: str,
    overwrite: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    on_validation: Callable[[list[ValidationIssue]], None] | None = None,
    object_selector: str | None = None,
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

    if output_path.exists() and not overwrite:
        raise ConversionError(
            f"Output exists: {output_file}. "
            "Use --overwrite to replace it."
        )

    # Determine reader and writer

    try:
        reader = get_reader_for_file(input_file)
        writer = get_writer_for_file(output_file)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
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

        writer.write(
            dataset,
            output_file
        )

    logger.info("Output write completed: output_file=%s", output_file)
        
    return dataset
