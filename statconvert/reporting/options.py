from __future__ import annotations

from dataclasses import dataclass

from statconvert.reporting.exceptions import ReportError


SECTION_NAMES = (
    "summary",
    "schema",
    "metadata",
    "labels",
    "missing",
    "describe",
    "frequencies",
    "validation",
)

PRESETS: dict[str, set[str]] = {
    "quick": {"summary", "schema", "missing", "validation"},
    "full": set(SECTION_NAMES),
    "validation": {"summary", "schema", "validation"},
    "metadata": {"summary", "schema", "metadata", "labels"},
}

DEFAULT_SECTIONS = {
    "summary",
    "schema",
    "metadata",
    "labels",
    "missing",
    "describe",
    "validation",
}


@dataclass(frozen=True)
class ReportBuildOptions:
    include_summary: bool
    include_schema: bool
    include_metadata: bool
    include_labels: bool
    include_missing: bool
    include_describe: bool
    include_frequencies: bool
    include_validation: bool
    preset: str = "default"
    max_table_rows: int = 1000
    max_preview_values: int = 5


def resolve_report_options(
    preset: str | None = None,
    sections: list[str] | None = None,
    no_summary: bool = False,
    no_schema: bool = False,
    no_metadata: bool = False,
    no_labels: bool = False,
    no_missing: bool = False,
    no_describe: bool = False,
    frequencies: bool = False,
    no_validation: bool = False,
    max_table_rows: int = 1000,
    max_preview_values: int = 5,
) -> ReportBuildOptions:
    """Resolve report presets, targeted sections and explicit CLI overrides."""

    _validate_size("--max-table-rows", max_table_rows)
    _validate_size("--max-preview-values", max_preview_values)

    normalized_preset = (preset or "default").lower()
    if normalized_preset != "default" and normalized_preset not in PRESETS:
        supported = ", ".join(PRESETS)
        raise ReportError(
            f"Unknown report preset: {preset}. Use one of: {supported}."
        )

    selected = set(
        DEFAULT_SECTIONS
        if normalized_preset == "default"
        else PRESETS[normalized_preset]
    )
    display_preset = normalized_preset

    if sections:
        selected = _normalize_sections(sections)
        display_preset = "custom"

    exclusions = {
        "summary": no_summary,
        "schema": no_schema,
        "metadata": no_metadata,
        "labels": no_labels,
        "missing": no_missing,
        "describe": no_describe,
        "validation": no_validation,
    }
    selected.difference_update(
        name for name, excluded in exclusions.items() if excluded
    )
    if frequencies:
        selected.add("frequencies")

    return ReportBuildOptions(
        include_summary="summary" in selected,
        include_schema="schema" in selected,
        include_metadata="metadata" in selected,
        include_labels="labels" in selected,
        include_missing="missing" in selected,
        include_describe="describe" in selected,
        include_frequencies="frequencies" in selected,
        include_validation="validation" in selected,
        preset=display_preset,
        max_table_rows=max_table_rows,
        max_preview_values=max_preview_values,
    )


def _normalize_sections(sections: list[str]) -> set[str]:
    normalized = {section.lower() for section in sections}
    unknown = sorted(normalized - set(SECTION_NAMES))
    if unknown:
        supported = ", ".join(SECTION_NAMES)
        raise ReportError(
            f"Unknown report section: {unknown[0]}. Use one of: {supported}."
        )
    return normalized


def _validate_size(option_name: str, value: int) -> None:
    if value < 1:
        raise ReportError(f"{option_name} must be at least 1.")
