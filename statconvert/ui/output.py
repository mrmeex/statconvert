from __future__ import annotations

import sys
from typing import Any

import typer

from statconvert.serialization import to_json_text


def emit_json(data: Any) -> None:
    """Write JSON directly to stdout without Rich markup processing."""

    _configure_stdout_for_unicode()
    typer.echo(to_json_text(data))


def _configure_stdout_for_unicode() -> None:
    encoding = getattr(sys.stdout, "encoding", None)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if (
        encoding
        and encoding.lower().replace("-", "") != "utf8"
        and callable(reconfigure)
    ):
        reconfigure(encoding="utf-8")
