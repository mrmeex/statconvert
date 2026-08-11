from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any, Mapping


class TransformStepType(StrEnum):
    """Step kinds planned for ordered 0.10.0 transform recipes."""

    SELECT = "select"
    DROP = "drop"
    RENAME = "rename"
    CONVERT_TYPE = "convert_type"
    DERIVE = "derive"
    FILTER = "filter"
    RECODE = "recode"
    SORT = "sort"
    DISTINCT = "distinct"
    ROW_NUMBER = "row_number"


@dataclass(frozen=True)
class _StepSchema:
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()


_STEP_SCHEMAS: Mapping[TransformStepType, _StepSchema] = MappingProxyType(
    {
        TransformStepType.SELECT: _StepSchema(
            required=("columns",),
            optional=("ignore_missing",),
        ),
        TransformStepType.DROP: _StepSchema(
            required=("columns",),
            optional=("ignore_missing",),
        ),
        TransformStepType.RENAME: _StepSchema(
            required=(),
            optional=("from", "to", "map", "ignore_missing"),
        ),
        TransformStepType.CONVERT_TYPE: _StepSchema(
            required=("column", "data_type"),
            optional=("errors", "datetime_format"),
        ),
        TransformStepType.DERIVE: _StepSchema(
            required=("column", "expression"),
        ),
        TransformStepType.FILTER: _StepSchema(
            required=(),
            optional=("expression", "conditions", "mode", "reset_index"),
        ),
        TransformStepType.RECODE: _StepSchema(
            required=("column", "map"),
            optional=("default", "update_value_labels"),
        ),
        TransformStepType.SORT: _StepSchema(required=("keys",)),
        TransformStepType.DISTINCT: _StepSchema(
            required=("columns", "keep"),
        ),
        TransformStepType.ROW_NUMBER: _StepSchema(
            required=("column",),
            optional=("start", "step"),
        ),
    }
)

_STRING_FIELDS = {
    "column",
    "data_type",
    "datetime_format",
    "expression",
    "from",
    "mode",
}
_BOOLEAN_FIELDS = {
    "ignore_missing",
    "reset_index",
    "update_value_labels",
}


@dataclass(frozen=True)
class TransformStep:
    """One validated, non-executing step in an ordered transform recipe."""

    step_type: TransformStepType
    parameters: Mapping[str, Any] = field(default_factory=dict)
    step_id: str | None = None

    def __post_init__(self) -> None:
        try:
            normalized_type = TransformStepType(self.step_type)
        except ValueError as exc:
            supported = ", ".join(item.value for item in TransformStepType)
            raise ValueError(
                f"Unsupported transform step type '{self.step_type}'. "
                f"Use one of: {supported}."
            ) from exc

        normalized_parameters = {
            name: _freeze_json_value(value)
            for name, value in self.parameters.items()
        }
        _validate_step_parameters(normalized_type, normalized_parameters)
        if self.step_id is not None and (
            not isinstance(self.step_id, str) or not self.step_id.strip()
        ):
            raise ValueError("Transform step_id must be a non-blank string.")
        object.__setattr__(self, "step_type", normalized_type)
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(normalized_parameters),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-safe representation."""

        schema = _STEP_SCHEMAS[self.step_type]
        ordered_names = schema.required + schema.optional
        result = {
            "type": self.step_type.value,
        }
        if self.step_id is not None:
            result["id"] = self.step_id
        result.update(
            {
                name: _copy_json_value(self.parameters[name])
                for name in ordered_names
                if name in self.parameters
            }
        )
        return result


@dataclass(frozen=True)
class TransformRecipe:
    """Portable ordered transform recipe metadata without execution behavior."""

    input_file: str
    output_file: str
    steps: tuple[TransformStep, ...]
    overwrite: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.input_file, str) or not self.input_file.strip():
            raise ValueError("Transform recipe input_file must be a non-blank string.")
        if not isinstance(self.output_file, str) or not self.output_file.strip():
            raise ValueError("Transform recipe output_file must be a non-blank string.")
        if not isinstance(self.overwrite, bool):
            raise TypeError("Transform recipe overwrite must be a boolean.")

        normalized_steps = tuple(self.steps)
        if not all(isinstance(step, TransformStep) for step in normalized_steps):
            raise TypeError("Transform recipe steps must contain TransformStep values.")
        object.__setattr__(self, "steps", normalized_steps)

    def to_dict(self) -> dict[str, Any]:
        """Return the proposed TOML-shaped, JSON-safe representation."""

        return {
            "command": "transform",
            "input": self.input_file,
            "output": self.output_file,
            "overwrite": self.overwrite,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class TransformStepMetadata:
    """Backend-neutral metadata intended for validation and future previews."""

    step_index: int
    step_type: TransformStepType
    input_columns: tuple[str, ...] = ()
    output_columns: tuple[str, ...] = ()
    row_local: bool = True
    previewable: bool = True

    def __post_init__(self) -> None:
        if self.step_index < 0:
            raise ValueError("Transform step_index must be at least zero.")
        object.__setattr__(self, "step_type", TransformStepType(self.step_type))
        object.__setattr__(self, "input_columns", tuple(self.input_columns))
        object.__setattr__(self, "output_columns", tuple(self.output_columns))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe metadata with stable field ordering."""

        return {
            "step_index": self.step_index,
            "step_type": self.step_type.value,
            "input_columns": list(self.input_columns),
            "output_columns": list(self.output_columns),
            "row_local": self.row_local,
            "previewable": self.previewable,
        }


def _validate_step_parameters(
    step_type: TransformStepType,
    parameters: dict[str, Any],
) -> None:
    schema = _STEP_SCHEMAS[step_type]
    allowed = set(schema.required + schema.optional)
    unknown = sorted(set(parameters) - allowed)
    if unknown:
        raise ValueError(
            f"Transform step '{step_type.value}' has unknown field(s): "
            f"{', '.join(unknown)}."
        )

    missing = [name for name in schema.required if name not in parameters]
    if missing:
        raise ValueError(
            f"Transform step '{step_type.value}' is missing required field(s): "
            f"{', '.join(missing)}."
        )

    if step_type == TransformStepType.RENAME:
        has_pair = "from" in parameters or "to" in parameters
        has_map = "map" in parameters
        if has_pair and has_map:
            raise ValueError(
                "Transform step 'rename' cannot combine 'from'/'to' with 'map'."
            )
        if has_pair and not {"from", "to"} <= set(parameters):
            raise ValueError(
                "Transform step 'rename' requires both 'from' and 'to'."
            )
        if not has_pair and not has_map:
            raise ValueError(
                "Transform step 'rename' requires 'from'/'to' or 'map'."
            )

    if step_type == TransformStepType.FILTER:
        has_expression = "expression" in parameters
        has_conditions = "conditions" in parameters
        if has_expression == has_conditions:
            raise ValueError(
                "Transform step 'filter' requires exactly one of "
                "'expression' or compatibility 'conditions'."
            )

    if step_type == TransformStepType.SORT:
        keys = parameters.get("keys")
        if not isinstance(keys, (list, tuple)) or not keys:
            raise ValueError("Transform step 'sort' requires a non-empty key list.")
        key_columns: list[str] = []
        for index, key in enumerate(keys):
            if not isinstance(key, Mapping) or set(key) != {
                "column", "order", "nulls"
            }:
                raise ValueError(
                    f"Transform step 'sort' key {index} must contain exactly "
                    "'column', 'order', and 'nulls'."
                )
            column = key["column"]
            if not isinstance(column, str) or not column.strip():
                raise ValueError("Transform sort key column must be non-blank text.")
            if key["order"] not in {"ascending", "descending"}:
                raise ValueError(
                    "Transform sort key order must be 'ascending' or 'descending'."
                )
            if key["nulls"] not in {"first", "last"}:
                raise ValueError("Transform sort key nulls must be 'first' or 'last'.")
            key_columns.append(column)
        duplicates = _duplicate_values(key_columns)
        if duplicates:
            raise ValueError(
                "Transform sort key columns must be unique: "
                + ", ".join(duplicates)
                + "."
            )

    if step_type == TransformStepType.DISTINCT:
        distinct_columns = parameters.get("columns")
        if distinct_columns is not None:
            duplicates = _duplicate_values(list(distinct_columns))
            if duplicates:
                raise ValueError(
                    "Transform distinct columns must be unique: "
                    + ", ".join(duplicates)
                    + "."
                )
        if parameters.get("keep") not in {"first", "last"}:
            raise ValueError("Transform distinct keep must be 'first' or 'last'.")

    if step_type == TransformStepType.ROW_NUMBER:
        start = parameters.get("start", 1)
        increment = parameters.get("step", 1)
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("Transform row_number start must be an integer.")
        if (
            isinstance(increment, bool)
            or not isinstance(increment, int)
            or increment <= 0
        ):
            raise ValueError("Transform row_number step must be a positive integer.")

    for name, value in parameters.items():
        _validate_json_value(value, field_name=name)
        if name in _STRING_FIELDS and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ValueError(
                f"Transform step field '{name}' must be a non-blank string."
            )
        if name in _BOOLEAN_FIELDS and not isinstance(value, bool):
            raise TypeError(f"Transform step field '{name}' must be a boolean.")

    columns = parameters.get("columns")
    if columns is not None:
        if (
            not isinstance(columns, (list, tuple))
            or not columns
            or not all(isinstance(column, str) and column.strip() for column in columns)
        ):
            raise ValueError(
                "Transform step field 'columns' must be a non-empty list of "
                "non-blank strings."
            )
    recode_map = parameters.get("map")
    if recode_map is not None and not isinstance(recode_map, Mapping):
        raise ValueError("Transform step field 'map' must be a mapping.")


def _validate_json_value(value: Any, *, field_name: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"Transform step field '{field_name}' contains a non-finite number."
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(item, field_name=field_name)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if field_name == "map":
                if not isinstance(key, (str, int, float, bool)):
                    raise TypeError(
                        "Transform step field 'map' contains an unsupported key."
                    )
                if isinstance(key, float) and not math.isfinite(key):
                    raise ValueError(
                        "Transform step field 'map' contains a non-finite key."
                    )
            elif not isinstance(key, str):
                raise TypeError(
                    f"Transform step field '{field_name}' contains a non-string key."
                )
            _validate_json_value(item, field_name=field_name)
        return
    raise TypeError(
        f"Transform step field '{field_name}' contains a non-JSON-safe "
        f"{type(value).__name__} value."
    )


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_json_value(item)
                for key, item in value.items()
            }
        )
    return value


def _copy_json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_copy_json_value(item) for item in value]
    if isinstance(value, list):
        return [_copy_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            key: _copy_json_value(item)
            for key, item in value.items()
        }
    return value


def _duplicate_values(values: list[Any]) -> list[str]:
    seen: list[Any] = []
    duplicates: list[str] = []
    for value in values:
        if value in seen and str(value) not in duplicates:
            duplicates.append(str(value))
        seen.append(value)
    return duplicates
