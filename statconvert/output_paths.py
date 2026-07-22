from __future__ import annotations

from pathlib import Path

from statconvert.exceptions import OutputPathError


def validate_output_file_path(
    output_path: str | Path,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
    dry_run: bool = False,
    overwrite_option: str = "--overwrite",
    output_label: str = "Output file",
) -> Path:
    """Validate one output file and optionally create its missing parent."""

    path = Path(output_path)
    if dry_run:
        return path

    validate_output_parent_directory(path, create_dirs=create_dirs)
    if path.exists() and not overwrite:
        raise OutputPathError(
            f"{output_label} already exists: {path}",
            suggestion=(
                f"Use {overwrite_option} to replace it, or choose a different path."
            ),
        )
    return path


def validate_output_parent_directory(
    output_path: str | Path,
    *,
    create_dirs: bool = False,
    dry_run: bool = False,
) -> Path:
    """Validate the parent of an output file without checking the file itself."""

    path = Path(output_path)
    parent = path.parent
    if parent == Path("."):
        return path
    if parent.exists():
        if not parent.is_dir():
            raise OutputPathError(
                f"Output directory is not a directory: {parent}",
                suggestion="Choose an output path whose parent is a directory.",
            )
        return path
    if not create_dirs:
        raise OutputPathError(
            f"Output directory does not exist: {parent}",
            suggestion="Use --create-dirs to create missing output directories.",
        )
    if not dry_run:
        parent.mkdir(parents=True, exist_ok=True)
    return path


def validate_output_root_directory(
    output_path: str | Path,
    *,
    create_dirs: bool = False,
    dry_run: bool = False,
) -> Path:
    """Validate a user-selected batch root and optionally create it."""

    path = Path(output_path)
    if path.exists():
        if not path.is_dir():
            raise OutputPathError(
                f"Output directory is not a directory: {path}",
                suggestion="Choose a directory path for the batch output root.",
            )
        return path
    if not create_dirs:
        raise OutputPathError(
            f"Output directory does not exist: {path}",
            suggestion="Use --create-dirs to create it.",
        )
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)
    return path
