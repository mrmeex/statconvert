from __future__ import annotations

import re


def sanitize_output_name(value: str, *, fallback: str) -> str:
    """Return a conservative filesystem-safe output base name."""

    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return normalized or fallback
