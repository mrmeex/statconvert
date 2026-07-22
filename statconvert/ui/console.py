from rich.console import Console

from statconvert.context import context


console = Console(
    no_color=not context.use_color
)


def encoding_supports_unicode(encoding: str | None) -> bool:
    """Return whether an output encoding can represent the UI status symbols."""

    if not encoding:
        return False
    try:
        "✓⚠⠋".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def console_supports_unicode() -> bool:
    """Return whether the active shared console can render Unicode status symbols."""

    return encoding_supports_unicode(getattr(console.file, "encoding", None))
