from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetReadOptions:
    """Backend-neutral options for reading a dataset file."""

    encoding: str | None = None
    csv_delimiter: str | None = None
    csv_decimal: str | None = None

    def __post_init__(self) -> None:
        _validate_csv_separators(self.csv_delimiter, self.csv_decimal)

    def csv_kwargs(self) -> dict[str, str]:
        """Return explicitly selected pandas CSV reader arguments."""

        return _csv_kwargs(self.csv_delimiter, self.csv_decimal)


@dataclass(frozen=True)
class DatasetWriteOptions:
    """Backend-neutral options for writing a dataset file."""

    encoding: str | None = None
    csv_delimiter: str | None = None
    csv_decimal: str | None = None

    def __post_init__(self) -> None:
        _validate_csv_separators(self.csv_delimiter, self.csv_decimal)

    def csv_kwargs(self) -> dict[str, str]:
        """Return explicitly selected pandas CSV writer arguments."""

        return _csv_kwargs(self.csv_delimiter, self.csv_decimal)


def _csv_kwargs(
    delimiter: str | None,
    decimal: str | None,
) -> dict[str, str]:
    options = {
        "sep": delimiter,
        "decimal": decimal,
    }
    return {name: value for name, value in options.items() if value is not None}


def _validate_csv_separators(
    delimiter: str | None,
    decimal: str | None,
) -> None:
    _validate_single_character(
        delimiter,
        "Invalid CSV delimiter: delimiter must be exactly one character.",
    )
    _validate_single_character(
        decimal,
        (
            "Invalid CSV decimal separator: decimal separator must be exactly one "
            "character."
        ),
    )
    if delimiter is not None and decimal is not None and delimiter == decimal:
        raise ValueError(
            "CSV delimiter and decimal separator cannot be the same character."
        )


def _validate_single_character(value: str | None, message: str) -> None:
    if value is not None and len(value) != 1:
        raise ValueError(message)
