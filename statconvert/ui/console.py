from rich.console import Console

from statconvert.context import context


console = Console(
    no_color=not context.use_color
)