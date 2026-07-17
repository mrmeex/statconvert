from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from statconvert.backends.objects import (
    DatasetObjectInfo,
    NamedDataset,
    resolve_object_selector,
)
from statconvert.batch.exceptions import BatchError
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.exceptions import ConversionError, ObjectSelectionError
from statconvert.inspection import (
    ValidationFailedError,
    ValidationIssue,
    validate_for_write,
    validation_should_fail,
)
from statconvert.object_manifest import ObjectManifestRow, read_object_manifest
from statconvert.output_paths import validate_output_file_path
from statconvert.registry import (
    can_read_format,
    format_supports_multi_object_write,
    format_supports_objects,
    list_dataset_objects,
    read_dataset,
    supported_extensions,
    validate_dataset_object_names,
    write_dataset_objects,
)


class CollectionError(ConversionError):
    """An object collection could not be planned or completed."""


@dataclass(frozen=True)
class CollectionPlanItem:
    """One included manifest row resolved for collection."""

    row_number: int
    input_file: Path
    input_object: str | None
    output_object: str
    source_object: DatasetObjectInfo | None = None


@dataclass(frozen=True)
class CollectionPlan:
    """Validated manifest collection plan in output object order."""

    manifest_file: Path
    output_file: Path
    base_dir: Path
    items: tuple[CollectionPlanItem, ...]
    overwrite: bool = False
    create_dirs: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class CollectionResult:
    """Completed collection and its loaded named datasets."""

    plan: CollectionPlan
    objects: tuple[NamedDataset, ...]

    @property
    def rows(self) -> int:
        return sum(item.dataset.rows for item in self.objects)


CollectionValidationCallback = Callable[
    [CollectionPlanItem, list[ValidationIssue]],
    None,
]


def build_collection_plan(
    manifest_file: str | Path,
    output_file: str | Path,
    *,
    base_dir: str | Path | None = None,
    overwrite: bool = False,
    create_dirs: bool = False,
    dry_run: bool = False,
) -> CollectionPlan:
    """Parse and validate a manifest without reading full datasets."""

    try:
        manifest = read_object_manifest(
            manifest_file,
            error_label="Object collection manifest",
            validate_output_names=False,
        )
    except BatchError as exc:
        raise CollectionError(str(exc)) from None

    included_rows = manifest.included_rows
    if not included_rows:
        raise CollectionError(
            "Object collection manifest contains no included rows."
        )

    output_path = Path(output_file)
    if not format_supports_multi_object_write(output_path.suffix):
        raise CollectionError(
            "collect requires a multi-object output format such as xlsx or ods."
        )
    validate_output_file_path(
        output_path,
        overwrite=overwrite,
        create_dirs=create_dirs,
        dry_run=dry_run,
    )

    input_base = _collection_base_dir(manifest.path, base_dir)
    items = tuple(
        _build_collection_item(row, input_base=input_base)
        for row in included_rows
    )
    validate_dataset_object_names(
        [item.output_object for item in items],
        output_path,
    )

    return CollectionPlan(
        manifest_file=manifest.path,
        output_file=output_path,
        base_dir=input_base,
        items=items,
        overwrite=overwrite,
        create_dirs=create_dirs,
        dry_run=dry_run,
    )


def execute_collection_plan(
    plan: CollectionPlan,
    *,
    validate: bool = False,
    strict_validation: bool = False,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_option_warning: Callable[[str], None] | None = None,
    on_validation: CollectionValidationCallback | None = None,
) -> CollectionResult:
    """Read every planned dataset, then write one output container."""

    if plan.dry_run:
        raise CollectionError("A dry-run collection plan cannot be executed.")

    named_datasets: list[NamedDataset] = []
    for item in plan.items:
        dataset = read_dataset(
            item.input_file,
            object_selector=item.input_object,
            options=read_options,
            on_option_warning=on_option_warning,
        )

        if validate or strict_validation:
            issues = validate_for_write(
                dataset,
                target_format=plan.output_file.suffix.lower() or None,
                strict=strict_validation,
            )
            if on_validation is not None:
                on_validation(item, issues)
            if validation_should_fail(issues, strict=strict_validation):
                raise ValidationFailedError(issues)

        source_object = item.source_object
        named_datasets.append(
            NamedDataset(
                name=item.output_object,
                dataset=dataset,
                source_object_index=(
                    None if source_object is None else source_object.index
                ),
                source_object_name=(
                    item.input_object
                    if source_object is None
                    else source_object.name or item.input_object
                ),
                source_file=str(item.input_file),
            )
        )

    write_dataset_objects(
        named_datasets,
        plan.output_file,
        options=write_options,
        on_option_warning=on_option_warning,
    )
    return CollectionResult(plan=plan, objects=tuple(named_datasets))


def _collection_base_dir(
    manifest_file: Path,
    base_dir: str | Path | None,
) -> Path:
    if base_dir is None:
        return manifest_file.parent

    input_base = Path(base_dir)
    if not input_base.exists():
        raise CollectionError(
            f"Object collection base directory does not exist: {input_base}"
        )
    if not input_base.is_dir():
        raise CollectionError(
            f"Object collection base path is not a directory: {input_base}"
        )
    return input_base


def _build_collection_item(
    row: ObjectManifestRow,
    *,
    input_base: Path,
) -> CollectionPlanItem:
    manifest_input = Path(row.input_file)
    input_file = (
        manifest_input
        if manifest_input.is_absolute()
        else input_base / manifest_input
    )
    if not input_file.exists():
        raise CollectionError(
            f"Object collection manifest row {row.row_number} points to a "
            f"missing file: {input_file}"
        )
    if not input_file.is_file():
        raise CollectionError(
            f"Object collection manifest row {row.row_number} input path is "
            f"not a file: {input_file}"
        )

    extension = input_file.suffix.lower()
    if extension not in supported_extensions():
        raise CollectionError(
            f"Object collection manifest row {row.row_number} has an "
            f"unsupported input format: {extension or '<none>'}"
        )
    if not can_read_format(extension):
        raise CollectionError(
            f"Object collection manifest row {row.row_number} input format "
            f"is not readable: {extension}"
        )

    source_object = _resolve_source_object(
        input_file,
        row.input_object,
        row_number=row.row_number,
    )
    output_object = _collection_output_object(row, input_file)
    return CollectionPlanItem(
        row_number=row.row_number,
        input_file=input_file,
        input_object=row.input_object,
        output_object=output_object,
        source_object=source_object,
    )


def _resolve_source_object(
    input_file: Path,
    input_object: str | None,
    *,
    row_number: int,
) -> DatasetObjectInfo | None:
    if not format_supports_objects(input_file.suffix):
        if input_object is not None:
            raise CollectionError(
                f"Object collection manifest row {row_number}:\n"
                f"Object selection is not supported for "
                f"{input_file.suffix.lower()} files."
            )
        return None

    try:
        selected = resolve_object_selector(
            list_dataset_objects(input_file),
            input_object,
            path=input_file,
        )
    except (ValueError, ObjectSelectionError, ConversionError) as exc:
        raise CollectionError(
            f"Object collection manifest row {row_number}:\n{exc}"
        ) from None

    if not selected.supported:
        detail = f": {selected.message}" if selected.message else "."
        raise CollectionError(
            f"Object collection manifest row {row_number} selected an "
            f"unsupported object{detail}"
        )
    return selected


def _collection_output_object(
    row: ObjectManifestRow,
    input_file: Path,
) -> str:
    output_object = _optional_text(row.raw.get("output_object"))
    name = (
        output_object
        or row.output_name
        or row.input_object
        or input_file.stem
    )
    if not name:
        raise CollectionError(
            f"Object collection manifest row {row.row_number} has no usable "
            "output object name."
        )
    return name


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
