from __future__ import annotations

from collections.abc import Iterable
from difflib import get_close_matches


def suggest_value(
    value: str,
    choices: Iterable[str],
    *,
    cutoff: float = 0.72,
) -> str | None:
    """Return one deterministic close match without guessing at weak matches."""

    normalized = value.strip().casefold()
    choice_lookup = {
        choice.strip().casefold(): choice
        for choice in choices
        if choice.strip()
    }
    matches = get_close_matches(
        normalized,
        sorted(choice_lookup),
        n=1,
        cutoff=cutoff,
    )
    return choice_lookup[matches[0]] if matches else None


def did_you_mean(
    value: str,
    choices: Iterable[str],
    *,
    cutoff: float = 0.72,
) -> str | None:
    """Format a concise close-match suggestion when one is credible."""

    match = suggest_value(value, choices, cutoff=cutoff)
    return f"Did you mean '{match}'?" if match is not None else None


def format_cli_path(value: object) -> str:
    """Quote a command-line path only when whitespace requires it."""

    text = str(value)
    return f'"{text}"' if any(character.isspace() for character in text) else text
