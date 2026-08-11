from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from statconvert.exceptions import OutputPathError
from statconvert.metadata.sidecar import sidecar_path
from statconvert.output_paths import validate_output_file_path
from statconvert.registry import FORMAT_INFO


@dataclass(frozen=True)
class TransformOutputPreflight:
    """Non-secret output and metadata-target facts for planning and preview."""

    input_path: Path
    output_path: Path
    output_format: str
    metadata_mode: str
    sidecar_path: Path | None
    output_exists: bool
    sidecar_exists: bool
    overwrite_required: bool
    parent_exists: bool
    would_write: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.output_path),
            "format": self.output_format,
            "would_write": self.would_write,
            "overwrite_required": self.overwrite_required,
            "parent_exists": self.parent_exists,
            "metadata_mode": self.metadata_mode,
            "sidecar_behavior": {
                "target": str(self.sidecar_path) if self.sidecar_path else None,
                "would_write": self.sidecar_path is not None and self.would_write,
                "exists": self.sidecar_exists,
            },
        }


def validate_distinct_transform_paths(
    input_path: str | Path,
    output_path: str | Path,
) -> tuple[Path, Path]:
    """Reject normalized, case-folded, symlink, or hard-link path identity."""

    source = Path(input_path)
    target = Path(output_path)
    source_resolved = source.resolve(strict=False)
    target_resolved = target.resolve(strict=False)
    normalized_source = os.path.normcase(os.path.abspath(source_resolved))
    normalized_target = os.path.normcase(os.path.abspath(target_resolved))
    same = normalized_source == normalized_target
    if not same and source.exists() and target.exists():
        try:
            same = os.path.samefile(source, target)
        except OSError:
            same = False
    if same:
        raise OutputPathError(
            f"Transform output must differ from the input file: {target}",
            suggestion="Choose a separate output path; --overwrite cannot replace input.",
        )
    return source_resolved, target_resolved


def preflight_transform_output(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool,
    create_dirs: bool,
    write: bool,
) -> TransformOutputPreflight:
    """Validate transform targets and report automatic sidecar behavior."""

    source, target = validate_distinct_transform_paths(input_path, output_path)
    extension = target.suffix.lower()
    info = FORMAT_INFO.get(extension, {})
    metadata_mode = str(info.get("metadata_mode", "unknown"))
    automatic_sidecar = sidecar_path(target) if "sidecar" in metadata_mode else None
    output_exists = target.exists()
    sidecar_exists = bool(automatic_sidecar and automatic_sidecar.exists())
    parent_exists = target.parent.exists()
    overwrite_required = output_exists or sidecar_exists

    if write:
        validate_output_file_path(
            target,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )
        if sidecar_exists and not overwrite:
            raise OutputPathError(
                f"Metadata sidecar already exists: {automatic_sidecar}",
                suggestion=(
                    "Use --overwrite to replace the output and its sidecar, or choose "
                    "a different output path."
                ),
            )

    return TransformOutputPreflight(
        input_path=source,
        output_path=target,
        output_format=extension.lstrip("."),
        metadata_mode=metadata_mode,
        sidecar_path=automatic_sidecar,
        output_exists=output_exists,
        sidecar_exists=sidecar_exists,
        overwrite_required=overwrite_required,
        parent_exists=parent_exists,
        would_write=write,
    )
