from __future__ import annotations

from pathlib import Path

from .console import console


def show_config_created(path: Path, command: str) -> None:
    """Show that a starter workflow config was written."""

    console.print(f"[green]Created {command} config: {path}[/green]")


def show_config_valid(path: Path, command: str) -> None:
    """Show that a workflow config passed validation."""

    console.print(
        f"[green]Config is valid for command '{command}': {path}[/green]"
    )


def show_config_written(path: Path, command: str) -> None:
    """Show that a command was serialized without being executed."""

    no_run_messages = {
        "convert": "No conversion was run.",
        "transform": "No transformation was run.",
        "batch": "No batch conversion was run.",
        "compare": "No comparison was run.",
        "report": "No report was generated.",
        "collect": "No collection was run.",
    }
    console.print(f"[green]Config written: {path}[/green]")
    console.print(no_run_messages[command])
    console.print(f"Run it with: statconvert config run {path}")
