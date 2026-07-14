from __future__ import annotations

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
from statconvert.transformations import TransformationPipeline


def transform_dataset(
    dataset: Dataset,
    pipeline: TransformationPipeline | None = None
) -> Dataset:
    """
    Apply a transformation pipeline to a dataset.
    """

    if pipeline is None or pipeline.is_empty():
        return dataset

    return pipeline.apply(
        dataset
    )


def transform_file(
    input_file: str,
    output_file: str,
    pipeline: TransformationPipeline,
    overwrite: bool = False,
    dry_run: bool = False,
    validate: bool = False,
    strict_validation: bool = False,
    on_validation: Callable[[list[ValidationIssue]], None] | None = None,
    object_selector: str | None = None,
) -> Dataset:
    """
    Read a file, apply transformations and optionally write the result.
    """

    input_path = Path(
        input_file
    )
    output_path = Path(
        output_file
    )
    logger = get_logger()

    if not input_path.exists():
        raise ConversionError(
            f"Input file does not exist: {input_file}"
        )

    if output_path.exists() and not overwrite and not dry_run:
        raise ConversionError(
            f"Output exists: {output_file}. Use --overwrite to replace it."
        )

    try:
        reader = get_reader_for_file(input_file)
        writer = get_writer_for_file(output_file)
    except ValueError as exc:
        raise ConversionError(str(exc)) from None
    logger.debug(
        "Transformation backends resolved: reader=%s writer=%s",
        reader.__class__.__name__,
        writer.__class__.__name__,
    )

    logger.debug("Reading transformation input: %s", input_file)
    dataset = read_dataset(
        input_file,
        object_selector=object_selector,
    )
    logger.info(
        "Transformation input read: rows=%s columns=%s",
        dataset.rows,
        len(dataset.columns),
    )
    logger.debug("Applying transformation pipeline")
    transformed = transform_dataset(
        dataset,
        pipeline,
    )
    logger.info(
        "Transformation pipeline completed: rows=%s columns=%s",
        transformed.rows,
        len(transformed.columns),
    )

    if validate or strict_validation:
        logger.debug("Validating transformed dataset before write")
        issues = validate_for_write(
            transformed,
            target_format=output_path.suffix.lower() or None,
            strict=strict_validation,
        )
        if on_validation is not None:
            on_validation(issues)
        logger.info(
            "Transformation validation completed: issues=%s errors=%s warnings=%s",
            len(issues),
            sum(issue.severity == "error" for issue in issues),
            sum(issue.severity == "warning" for issue in issues),
        )
        if validation_should_fail(issues, strict=strict_validation):
            raise ValidationFailedError(issues)

    if not dry_run:
        logger.debug("Writing transformed dataset: %s", output_file)
        writer.write(
            transformed,
            output_file,
        )
        logger.info("Transformation output written: output_file=%s", output_file)
    else:
        logger.info("Transformation dry run completed without writing output")

    return transformed
