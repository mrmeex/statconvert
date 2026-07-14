"""Data models used by the StatConvert logging layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class LogLevel(str, Enum):
    """Supported logging levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class LoggingOptions:
    """Options controlling StatConvert's dedicated file logger."""

    enabled: bool = False
    log_file: Path | None = None
    level: str = "info"
    developer: bool = False
    include_tracebacks: bool = True
    append: bool = False


@dataclass
class CommandLogContext:
    """Mutable lifecycle information for one command invocation."""

    command: str
    parameters: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    success: bool | None = None
    input_file: str | None = None
    output_file: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
