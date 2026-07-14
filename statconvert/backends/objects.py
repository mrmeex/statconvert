from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from statconvert.exceptions import AmbiguousObjectError, ObjectNotFoundError


@dataclass(frozen=True)
class DatasetObjectInfo:
    """Describe one dataset-like object inside a container file."""

    name: str
    index: int | None = None
    kind: str = "dataset"
    rows: int | None = None
    columns: int | None = None
    supported: bool = True
    message: str | None = None


def object_selector_matches(
    info: DatasetObjectInfo,
    selector: str,
) -> bool:
    """Return whether an exact name or zero-based index matches an object."""

    return selector == info.name or (
        info.index is not None
        and selector == str(info.index)
    )


def dataset_objects_from_names(
    names: Iterable[str],
    *,
    kind: str,
) -> list[DatasetObjectInfo]:
    """Build indexed dataset-object descriptions from ordered names."""

    return [
        DatasetObjectInfo(
            name=name,
            index=index,
            kind=kind,
        )
        for index, name in enumerate(names)
    ]


def resolve_object_selector(
    objects: list[DatasetObjectInfo],
    selector: str | None,
    *,
    path: str | Path,
    object_label: str = "Object",
) -> DatasetObjectInfo:
    """Resolve an exact object name or index with friendly selection errors."""

    path_name = Path(path).name
    plural_label = f"{object_label.lower()}s"
    available = ", ".join(
        f"{info.index}: {info.name}" if info.index is not None else info.name
        for info in objects
    )

    if not objects:
        raise ObjectNotFoundError(
            f"No {plural_label} were found in {path_name}."
        )

    if selector is None:
        if len(objects) == 1:
            return objects[0]
        raise AmbiguousObjectError(
            f"This file contains multiple {plural_label}. "
            f"Use --object to choose one. Available {plural_label}: {available}."
        )

    matches = [
        info
        for info in objects
        if object_selector_matches(info, selector)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousObjectError(
            f"{object_label} selector '{selector}' is ambiguous in {path_name}. "
            f"Available {plural_label}: {available}."
        )

    if _is_integer_selector(selector):
        raise ObjectNotFoundError(
            f"{object_label} index {selector} is out of range for {path_name}. "
            f"Available {plural_label}: {available}."
        )

    raise ObjectNotFoundError(
        f"{object_label} '{selector}' was not found in {path_name}. "
        f"Available {plural_label}: {available}."
    )


def _is_integer_selector(selector: str) -> bool:
    """Return whether a selector represents an integer index."""

    try:
        int(selector)
    except ValueError:
        return False
    return True
