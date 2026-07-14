from __future__ import annotations

from collections import defaultdict
from fnmatch import fnmatchcase
from pathlib import Path

from statconvert.batch.exceptions import BatchError
from statconvert.batch.models import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SKIPPED,
    BatchItem,
    BatchPlan,
    BatchPlanningOptions,
)
from statconvert.registry import (
    can_read_format,
    format_write_error,
    resolve_format_info,
    supported_extensions,
)


def normalize_target_extension(
    target: str
) -> str:
    """
    Normalize and validate a target extension.
    """

    extension = target.lower().strip()

    if not extension:
        raise BatchError(
            "Target extension is required."
        )

    if not extension.startswith(
        "."
    ):
        extension = f".{extension}"

    format_info = resolve_format_info(
        extension
    )

    if not format_info:
        raise BatchError(
            f"Unsupported target format: {target}"
        )

    _, info = format_info
    if not info["can_write"]:
        raise BatchError(format_write_error(extension))

    return extension


def discover_input_files(
    input_path: str | Path,
    recursive: bool = False,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """
    Discover input files deterministically.

    Include and exclude patterns are matched against both the file name and the path
    relative to the searched directory.
    """

    path = Path(
        input_path
    )

    if not path.exists():
        raise BatchError(
            f"Input path does not exist: {path}"
        )

    if path.is_file():
        base_path = path.parent
        if not _included_by_patterns(path, base_path, patterns):
            return []
        if _matches_patterns(path, base_path, exclude_patterns):
            return []
        return [path]

    if not path.is_dir():
        raise BatchError(
            f"Input path is not a file or directory: {path}"
        )

    iterator = path.rglob(
        "*"
    ) if recursive else path.glob(
        "*"
    )
    files = [
        candidate
        for candidate in iterator
        if candidate.is_file()
    ]
    filtered = [
        candidate
        for candidate in files
        if _included_by_patterns(
            candidate,
            path,
            patterns,
        )
        and not _matches_patterns(
            candidate,
            path,
            exclude_patterns,
        )
    ]

    return sorted(
        filtered,
        key=lambda item: item.as_posix().lower(),
    )


def _included_by_patterns(
    path: Path,
    base_path: Path,
    patterns: list[str] | None,
) -> bool:
    """
    Return whether a path should be included by optional include patterns.
    """

    if not patterns:
        return True

    return _matches_patterns(
        path,
        base_path,
        patterns,
    )


def build_batch_plan(
    input_path: str | Path,
    output_path: str | Path,
    target_extension: str,
    recursive: bool = False,
    overwrite: bool = False,
    include_unsupported: bool = True,
    preserve_structure: bool = True,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> BatchPlan:
    """
    Build a safe, deterministic batch conversion plan.
    """

    normalized_target = normalize_target_extension(
        target_extension
    )
    input_root = Path(
        input_path
    )
    output_root = Path(
        output_path
    )
    _validate_output_path(
        input_root,
        output_root,
        normalized_target,
    )
    discovered_files = discover_input_files(
        input_root,
        recursive=recursive,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
    )
    discovered_files = _exclude_recursive_output_tree(
        discovered_files,
        input_root,
        output_root,
        recursive,
    )

    if not discovered_files:
        raise BatchError(
            "No input files were discovered."
        )

    options = BatchPlanningOptions(
        input_path=input_root,
        output_path=output_root,
        target_extension=normalized_target,
        recursive=recursive,
        overwrite=overwrite,
        include_unsupported=include_unsupported,
        preserve_structure=preserve_structure,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
    )
    items = []

    for input_file in discovered_files:
        item = _build_item(
            input_file=input_file,
            input_root=input_root,
            output_root=output_root,
            target_extension=normalized_target,
            recursive=recursive,
            overwrite=overwrite,
            include_unsupported=include_unsupported,
            preserve_structure=preserve_structure,
        )

        if item is not None:
            items.append(
                item
            )

    if not items:
        raise BatchError(
            "No supported input files were discovered."
        )

    _mark_output_collisions(
        items
    )

    return BatchPlan(
        options=options,
        items=items,
    )


def _build_item(
    input_file: Path,
    input_root: Path,
    output_root: Path,
    target_extension: str,
    recursive: bool,
    overwrite: bool,
    include_unsupported: bool,
    preserve_structure: bool,
) -> BatchItem | None:
    """
    Build one batch item, or omit unsupported files when configured.
    """

    input_extension = input_file.suffix.lower() or None
    relative_path = _relative_path(
        input_file,
        input_root,
    )

    unsupported_input = input_extension not in supported_extensions()
    unreadable_input = not unsupported_input and not can_read_format(
        input_extension or ""
    )
    if unsupported_input or unreadable_input:
        if not include_unsupported:
            return None

        return BatchItem(
            input_file=input_file,
            output_file=None,
            input_extension=input_extension,
            status=BATCH_STATUS_SKIPPED,
            reason=(
                "Unsupported input format"
                if unsupported_input
                else "Input format is not readable"
            ),
            relative_path=relative_path,
        )

    output_file = _planned_output_file(
        input_file=input_file,
        input_root=input_root,
        output_root=output_root,
        target_extension=target_extension,
        recursive=recursive,
        preserve_structure=preserve_structure,
    )
    status = BATCH_STATUS_PENDING
    reason = None

    if _same_path(
        input_file,
        output_file,
    ):
        status = BATCH_STATUS_BLOCKED
        reason = "Input and output path are the same"

    elif output_file.exists() and not overwrite:
        status = BATCH_STATUS_BLOCKED
        reason = "Output file already exists. Use --overwrite to replace it."

    return BatchItem(
        input_file=input_file,
        output_file=output_file,
        input_extension=input_extension,
        output_extension=output_file.suffix.lower() or target_extension,
        status=status,
        reason=reason,
        relative_path=relative_path,
    )


def _planned_output_file(
    input_file: Path,
    input_root: Path,
    output_root: Path,
    target_extension: str,
    recursive: bool,
    preserve_structure: bool,
) -> Path:
    """
    Return the planned output path for one supported input file.
    """

    if input_root.is_file():
        if output_root.suffix:
            return output_root

        return output_root / f"{input_file.stem}{target_extension}"

    if recursive and preserve_structure:
        relative = input_file.relative_to(
            input_root
        )
        return output_root / relative.with_suffix(
            target_extension
        )

    return output_root / f"{input_file.stem}{target_extension}"


def _validate_output_path(
    input_root: Path,
    output_root: Path,
    target_extension: str,
) -> None:
    """Reject ambiguous file-versus-directory output paths before planning items."""

    if not input_root.exists():
        return

    if input_root.is_file():
        if output_root.suffix and output_root.suffix.lower() != target_extension:
            raise BatchError(
                "Explicit output file extension does not match --to format."
            )
        return

    if input_root.is_dir() and output_root.suffix:
        raise BatchError(
            "When input is a directory, output path must be a directory path"
        )


def _exclude_recursive_output_tree(
    files: list[Path],
    input_root: Path,
    output_root: Path,
    recursive: bool,
) -> list[Path]:
    """Avoid rediscovering generated files when output is nested under input."""

    if not recursive or not input_root.is_dir():
        return files

    input_key = _path_key(input_root)
    output_key = _path_key(output_root)
    if input_key == output_key or not _is_relative_to(output_root, input_root):
        return files

    return [
        path
        for path in files
        if not _is_relative_to(path, output_root)
    ]


def _relative_path(
    input_file: Path,
    input_root: Path,
) -> Path:
    """
    Return a stable relative path for a plan item.
    """

    if input_root.is_file():
        return Path(
            input_file.name
        )

    return input_file.relative_to(
        input_root
    )


def _mark_output_collisions(
    items: list[BatchItem]
) -> None:
    """
    Mark all pending supported items that plan to write the same output path.
    """

    by_output: dict[str, list[BatchItem]] = defaultdict(
        list
    )

    for item in items:
        if item.output_file is None:
            continue

        by_output[
            _path_key(
                item.output_file
            )
        ].append(
            item
        )

    for colliding_items in by_output.values():
        if len(
            colliding_items
        ) <= 1:
            continue

        for item in colliding_items:
            item.status = BATCH_STATUS_BLOCKED
            item.reason = (
                "Output path collision. Use --preserve-structure or choose a different "
                "output folder."
            )


def _matches_patterns(
    path: Path,
    base_path: Path,
    patterns: list[str] | None,
) -> bool:
    """
    Return whether a path matches any filename or relative-path glob pattern.

    Matching is deliberately limited to the basename and the POSIX relative path so
    behavior is independent of the current working directory and platform separators.
    Include filtering calls this first; exclude filtering applies afterward.
    """

    if not patterns:
        return False

    relative_path = path.relative_to(base_path).as_posix()

    return any(
        fnmatchcase(path.name, pattern)
        or fnmatchcase(relative_path, pattern)
        for pattern in patterns
    )


def _same_path(
    left: Path,
    right: Path,
) -> bool:
    """
    Return whether two paths point to the same planned location.
    """

    return _path_key(
        left
    ) == _path_key(
        right
    )


def _path_key(
    path: Path
) -> str:
    """
    Return a deterministic key for path comparison.
    """

    return path.resolve(
        strict=False
    ).as_posix().lower()


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Compare paths after non-strict resolution without requiring either to exist."""

    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True
