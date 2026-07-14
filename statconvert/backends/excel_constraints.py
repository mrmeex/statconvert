from __future__ import annotations


XLS_MAX_WORKSHEET_ROWS = 65_536
XLS_HEADER_ROWS = 1
XLS_MAX_DATA_ROWS = XLS_MAX_WORKSHEET_ROWS - XLS_HEADER_ROWS
XLS_MAX_COLUMNS = 256


def validate_excel_sheet_name(name: str) -> str:
    """Return a valid Excel sheet name or raise a friendly value error."""

    if not name:
        raise ValueError("Excel sheet names cannot be empty.")
    if len(name) > 31:
        raise ValueError("Excel sheet names are limited to 31 characters.")

    invalid_characters = [character for character in r":\/?*[]" if character in name]
    if invalid_characters:
        invalid = " ".join(invalid_characters)
        raise ValueError(
            "Excel sheet names cannot contain these characters: "
            f": \\ / ? * [ ]. Found: {invalid}."
        )
    return name
