from rich.panel import Panel
from rich.text import Text

from statconvert.context import context
from statconvert.exceptions import StatConvertError
from statconvert.logging import log_user_error

from .console import console, console_supports_unicode


def show_error(message: str, suggestion: str | None = None) -> None:
    body = Text(message, style="red", overflow="fold")
    if suggestion is not None:
        body.append("\nSuggestion: ", style="bold yellow")
        body.append(suggestion, style="yellow")
    console.print(
        Panel(
            body,
            title="Error",
            border_style="red",
            expand=True,
        ),
        crop=False,
    )


def show_success(message: str) -> None:
    marker = "✓" if console_supports_unicode() else "OK:"
    console.print(f"[green]{marker} {message}[/green]")


def show_warning(message: str) -> None:
    marker = "⚠" if console_supports_unicode() else "Warning:"
    console.print(f"[yellow]{marker} {message}[/yellow]")


def handle_exception(exc: Exception) -> None:
    """
    Display an exception.

    Shows a traceback only in debug mode.
    """

    log_user_error(str(exc), exc)

    if context.debug:
        console.print_exception()

    else:
        if isinstance(exc, StatConvertError):
            show_error(exc.message, exc.suggestion)
        else:
            show_error(str(exc))
