from contextlib import contextmanager

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)


@contextmanager
def progress(description: str):
    """
    Generic progress bar context manager.
    """

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
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