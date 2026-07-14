from rich.panel import Panel

from statconvert.context import context
from statconvert.logging import log_user_error

from .console import console


def show_error(message: str) -> None:
    console.print(
        Panel.fit(
            f"[red]{message}[/red]",
            title="Error",
            border_style="red",
        )
    )


def show_success(message: str) -> None:
    console.print(f"[green]✓ {message}[/green]")


def show_warning(message: str) -> None:
    console.print(f"[yellow]⚠ {message}[/yellow]")


def handle_exception(exc: Exception) -> None:
    """
    Display an exception.

    Shows a traceback only in debug mode.
    """

    log_user_error(str(exc), exc)

    if context.debug:
        console.print_exception()

    else:
        show_error(str(exc))
