from statconvert.context import context
from .console import console


def show_verbose(message: str):
    """
    Print a message only in verbose mode.
    """
    if context.verbose:
        console.print(f"[dim]{message}[/dim]")