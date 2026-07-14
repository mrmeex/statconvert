from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any


def make_json_safe(value: Any) -> Any:
    """Recursively normalize values and mapping keys for standards-safe JSON."""

    if is_dataclass(value) and not isinstance(value, type):
        return make_json_safe(asdict(value))
    if _is_missing_scalar(value):
        return None
    if isinstance(value, dict):
        return {
            _json_key(key): make_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [
            make_json_safe(item)
            for item in sorted(value, key=lambda item: str(item))
        ]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return make_json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def to_json_text(data: Any, *, indent: int | None = 2) -> str:
    """Serialize data as readable, UTF-8-friendly, standards-compliant JSON."""

    return json.dumps(
        make_json_safe(data),
        indent=indent,
        ensure_ascii=False,
        allow_nan=False,
    )


def _json_key(value: Any) -> str:
    normalized = make_json_safe(value)
    if normalized is None:
        return "null"
    if isinstance(normalized, (str, int, float, bool)):
        return str(normalized)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (dict, list, tuple, set, frozenset, str, bytes)):
        return False
    value_type = type(value)
    if value_type.__name__ == "NAType" and value_type.__module__.startswith("pandas"):
        return True
    try:
        unequal = value != value
        return bool(unequal)
    except (TypeError, ValueError):
        return False
