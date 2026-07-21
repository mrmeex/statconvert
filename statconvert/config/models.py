from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias


CommandName: TypeAlias = Literal[
    "convert",
    "transform",
    "batch",
    "compare",
    "report",
    "collect",
]
ConfigScalar: TypeAlias = str | int | float | bool
ConfigValue: TypeAlias = (
    ConfigScalar | list[ConfigScalar] | dict[str, ConfigScalar] | None
)

SUPPORTED_COMMANDS: tuple[CommandName, ...] = (
    "convert",
    "transform",
    "batch",
    "compare",
    "report",
    "collect",
)


@dataclass(frozen=True)
class WorkflowConfig:
    """A validated, single-command StatConvert configuration."""

    command: CommandName
    options: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the public TOML-shaped representation."""

        return {"command": self.command, **self.options}
