from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .console import console, encoding_supports_unicode


def spinner_name_for_encoding(encoding: str | None) -> str:
    """Use an ASCII spinner when the active output encoding cannot represent Unicode."""

    return "dots" if encoding_supports_unicode(encoding) else "line"


@contextmanager
def progress(description: str):
    """
    Generic progress bar context manager.
    """

    with Progress(
        SpinnerColumn(
            spinner_name=spinner_name_for_encoding(
                getattr(console.file, "encoding", None)
            )
        ),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as p:

        task = p.add_task(
            description,
            total=None,
        )

        try:
            yield p, task
        finally:
            p.update(
                task,
                completed=1,
            )
