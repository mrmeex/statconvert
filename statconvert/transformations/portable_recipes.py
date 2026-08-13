from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import tomllib
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from statconvert.output_paths import validate_output_file_path
from statconvert.transformations.exceptions import TransformationError
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)


PORTABLE_RECIPE_VERSION = 1
MAX_RECIPE_NAME_LENGTH = 200
MAX_RECIPE_DESCRIPTION_LENGTH = 2_000
_TOP_LEVEL_FIELDS = frozenset({"version", "name", "description", "steps"})
_RECODE_FIELDS = frozenset(
    {"column", "mappings", "default", "update_value_labels"}
)


@dataclass(frozen=True)
class PortableRecodeMapping:
    """One ordered, typed portable recode mapping."""

    source: str | int | float | bool
    target: str | int | float | bool

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target}


@dataclass(frozen=True)
class PortableTransformStep:
    """One normalized step in a path-independent recipe."""

    step_type: TransformStepType
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_type", TransformStepType(self.step_type))
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(_copy_value(dict(self.parameters))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.step_type.value,
            **_copy_value(dict(self.parameters)),
        }

    def to_transform_step(self) -> TransformStep:
        parameters = _copy_value(dict(self.parameters))
        if self.step_type == TransformStepType.RECODE:
            mappings = parameters.pop("mappings")
            parameters["map"] = {
                item["from"]: item["to"]
                for item in mappings
            }
        return TransformStep(self.step_type, parameters)


@dataclass(frozen=True)
class PortableTransformRecipe:
    """Versioned transform steps without paths or execution policy."""

    steps: tuple[PortableTransformStep, ...]
    name: str | None = None
    description: str | None = None
    version: int = PORTABLE_RECIPE_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version != PORTABLE_RECIPE_VERSION:
            raise TransformationError(
                f"Unsupported transform recipe version: {self.version}. "
                f"Only version {PORTABLE_RECIPE_VERSION} is supported."
            )
        _validate_display_text("name", self.name, MAX_RECIPE_NAME_LENGTH)
        _validate_display_text(
            "description",
            self.description,
            MAX_RECIPE_DESCRIPTION_LENGTH,
        )
        steps = tuple(self.steps)
        if not steps:
            raise TransformationError(
                "Transform recipe must contain at least one [[steps]] table."
            )
        if not all(isinstance(step, PortableTransformStep) for step in steps):
            raise TypeError("Portable recipe steps must be PortableTransformStep values.")
        object.__setattr__(self, "steps", steps)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"version": self.version}
        if self.name is not None:
            result["name"] = self.name
        if self.description is not None:
            result["description"] = self.description
        result["steps"] = [step.to_dict() for step in self.steps]
        return result

    def bind(
        self,
        *,
        input_file: str,
        output_file: str,
        overwrite: bool = False,
    ) -> TransformRecipe:
        return TransformRecipe(
            input_file=input_file,
            output_file=output_file,
            steps=tuple(step.to_transform_step() for step in self.steps),
            overwrite=overwrite,
        )


def parse_portable_recipe(path: str | Path) -> PortableTransformRecipe:
    """Parse one explicitly selected local TOML recipe file."""

    recipe_path = Path(path)
    if not recipe_path.exists():
        raise TransformationError(f"Transform recipe does not exist: {recipe_path}")
    if not recipe_path.is_file():
        raise TransformationError(f"Transform recipe is not a file: {recipe_path}")
    try:
        text = recipe_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TransformationError(
            f"Could not read transform recipe {recipe_path}: {exc}"
        ) from exc
    return parse_portable_recipe_text(text, source=str(recipe_path))


def parse_portable_recipe_text(
    text: str,
    *,
    source: str = "transform recipe",
) -> PortableTransformRecipe:
    """Parse and normalize path-independent recipe TOML without executing it."""

    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TransformationError(f"Invalid TOML in {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TransformationError("Transform recipe root must be a TOML table.")
    unknown = sorted(set(raw) - _TOP_LEVEL_FIELDS)
    if unknown:
        raise TransformationError(
            "Transform recipe has unknown top-level field(s): " + ", ".join(unknown)
        )
    if "version" not in raw:
        raise TransformationError("Transform recipe is missing required field 'version'.")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise TransformationError("Transform recipe field 'version' must be integer 1.")
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise TransformationError(
            "Transform recipe must contain at least one [[steps]] table."
        )
    steps = tuple(
        _parse_portable_step(step, index=index)
        for index, step in enumerate(raw_steps)
    )
    return PortableTransformRecipe(
        version=version,
        name=raw.get("name"),
        description=raw.get("description"),
        steps=steps,
    )


def portable_recipe_from_ordered_steps(
    steps: Sequence[Mapping[str, Any]],
    *,
    name: str | None = None,
    description: str | None = None,
) -> PortableTransformRecipe:
    """Normalize current ordered UI/config steps into portable recipe steps."""

    normalized = tuple(
        _parse_portable_step(_portable_raw_step(step), index=index)
        for index, step in enumerate(steps)
    )
    return PortableTransformRecipe(
        steps=normalized,
        name=name,
        description=description,
    )


def portable_recipe_from_transform_recipe(
    recipe: TransformRecipe,
    *,
    name: str | None = None,
    description: str | None = None,
) -> PortableTransformRecipe:
    """Convert the existing internal recipe to the portable representation."""

    return portable_recipe_from_ordered_steps(
        [step.to_dict() for step in recipe.steps],
        name=name,
        description=description,
    )


def portable_recipe_template() -> PortableTransformRecipe:
    return parse_portable_recipe_text(
        """version = 1
name = "Transform recipe"
description = "Reusable ordered transform steps."

[[steps]]
type = "select"
columns = ["id"]
ignore_missing = false
"""
    )


def portable_recipe_to_toml(recipe: PortableTransformRecipe) -> str:
    """Return deterministic canonical TOML with LF line endings."""

    lines = [f"version = {recipe.version}"]
    if recipe.name is not None:
        lines.append(f"name = {_format_value(recipe.name)}")
    if recipe.description is not None:
        lines.append(f"description = {_format_value(recipe.description)}")
    for step in recipe.steps:
        lines.extend(("", "[[steps]]"))
        for name, value in step.to_dict().items():
            lines.append(f"{_format_key(name)} = {_format_value(value)}")
    return "\n".join(lines) + "\n"


def save_portable_recipe(
    recipe: PortableTransformRecipe,
    path: str | Path,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
) -> Path:
    """Atomically save canonical recipe TOML to one normalized path."""

    requested_path = Path(path)
    if not requested_path.suffix:
        requested_path = requested_path.with_suffix(".toml")
    output_path = validate_output_file_path(
        requested_path,
        overwrite=overwrite,
        create_dirs=create_dirs,
        overwrite_option="--overwrite-recipe",
        output_label="Transform recipe",
    )
    text = portable_recipe_to_toml(recipe)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise TransformationError(
            f"Could not save transform recipe {output_path}: {exc}"
        ) from exc
    return output_path


def _parse_portable_step(raw: Any, *, index: int) -> PortableTransformStep:
    if not isinstance(raw, Mapping):
        raise TransformationError(f"Transform recipe step {index} must be a table.")
    data = dict(raw)
    step_type_value = data.pop("type", None)
    if not isinstance(step_type_value, str):
        raise TransformationError(
            f"Transform recipe step {index} is missing string field 'type'."
        )
    try:
        step_type = TransformStepType(step_type_value)
    except ValueError as exc:
        raise TransformationError(
            f"Transform recipe step {index} has unsupported type "
            f"'{step_type_value}'."
        ) from exc
    if step_type == TransformStepType.RECODE:
        return _parse_portable_recode(data, index=index)
    normalized = _normalize_defaults(step_type, data)
    try:
        validated = TransformStep(step_type, normalized)
    except (TypeError, ValueError) as exc:
        raise TransformationError(
            f"Transform recipe step {index} ({step_type.value}) is invalid: {exc}"
        ) from exc
    validated_parameters = validated.to_dict()
    validated_parameters.pop("type")
    return PortableTransformStep(step_type, validated_parameters)


def _parse_portable_recode(
    data: dict[str, Any],
    *,
    index: int,
) -> PortableTransformStep:
    unknown = sorted(set(data) - _RECODE_FIELDS)
    if unknown:
        raise TransformationError(
            f"Transform recipe step {index} (recode) has unknown field(s): "
            + ", ".join(unknown)
        )
    column = data.get("column")
    if not isinstance(column, str) or not column.strip():
        raise TransformationError(
            f"Transform recipe step {index} (recode) field 'column' must be non-blank."
        )
    raw_mappings = data.get("mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise TransformationError(
            f"Transform recipe step {index} (recode) requires non-empty 'mappings'."
        )
    mappings: list[PortableRecodeMapping] = []
    for mapping_index, raw_mapping in enumerate(raw_mappings):
        if not isinstance(raw_mapping, Mapping) or set(raw_mapping) != {"from", "to"}:
            raise TransformationError(
                f"Transform recipe step {index} recode mapping {mapping_index} "
                "must contain exactly 'from' and 'to'."
            )
        source = _validate_scalar(raw_mapping["from"], field="from")
        target = _validate_scalar(raw_mapping["to"], field="to")
        for existing in mappings:
            if _unsafe_equal(existing.source, source):
                raise TransformationError(
                    f"Transform recipe step {index} has duplicate or ambiguous "
                    f"recode source at mapping {mapping_index}."
                )
        mappings.append(PortableRecodeMapping(source, target))
    parameters: dict[str, Any] = {
        "column": column,
        "mappings": [item.to_dict() for item in mappings],
    }
    if "default" in data:
        parameters["default"] = _validate_scalar(data["default"], field="default")
    update_labels = data.get("update_value_labels", True)
    if not isinstance(update_labels, bool):
        raise TransformationError(
            f"Transform recipe step {index} field 'update_value_labels' "
            "must be a boolean."
        )
    parameters["update_value_labels"] = update_labels
    return PortableTransformStep(TransformStepType.RECODE, parameters)


def _normalize_defaults(
    step_type: TransformStepType,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    result = dict(parameters)
    if step_type in {
        TransformStepType.SELECT,
        TransformStepType.DROP,
        TransformStepType.RENAME,
    }:
        result.setdefault("ignore_missing", False)
    if step_type == TransformStepType.CONVERT_TYPE:
        result.setdefault("errors", "raise")
    if step_type == TransformStepType.FILTER:
        result.setdefault("reset_index", True)
        if "conditions" in result:
            result.setdefault("mode", "and")
    if step_type == TransformStepType.ROW_NUMBER:
        result.setdefault("start", 1)
        result.setdefault("step", 1)
    return result


def _portable_raw_step(step: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(step)
    raw.pop("id", None)
    if raw.get("type") == TransformStepType.RECODE.value and "map" in raw:
        mapping = raw.pop("map")
        if not isinstance(mapping, Mapping):
            raise TransformationError("Legacy recode map must be a mapping.")
        raw["mappings"] = [
            {"from": source, "to": target}
            for source, target in mapping.items()
        ]
    return raw


def _validate_display_text(name: str, value: Any, maximum: int) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise TransformationError(f"Transform recipe field '{name}' must be text.")
    if len(value) > maximum:
        raise TransformationError(
            f"Transform recipe field '{name}' exceeds {maximum} characters."
        )


def _validate_scalar(value: Any, *, field: str) -> str | int | float | bool:
    if isinstance(value, float) and not math.isfinite(value):
        raise TransformationError(
            f"Portable recode field '{field}' must not be a non-finite float."
        )
    if isinstance(value, (str, int, float, bool)):
        return value
    raise TransformationError(
        f"Portable recode field '{field}' has unsupported "
        f"{type(value).__name__} value."
    )


def _unsafe_equal(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except Exception:
        return False


def _copy_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _copy_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_value(item) for item in value]
    return value


def _format_key(value: str) -> str:
    if value.replace("_", "").replace("-", "").isalnum():
        return value
    return json.dumps(value, ensure_ascii=False)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TransformationError("Canonical recipe cannot contain non-finite floats.")
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(
            f"{_format_key(str(key))} = {_format_value(item)}"
            for key, item in value.items()
        ) + " }"
    raise TransformationError(
        f"Canonical recipe cannot serialize {type(value).__name__}."
    )
