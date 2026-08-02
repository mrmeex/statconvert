import pytest

from statconvert.reporting import ReportError, resolve_report_options


def _included(options):
    return {
        name.removeprefix("include_")
        for name, value in vars(options).items()
        if name.startswith("include_") and value
    }


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("quick", {"summary", "schema", "missing", "validation"}),
        ("full", {"summary", "schema", "metadata", "labels", "missing", "describe", "frequencies", "validation"}),
        ("validation", {"summary", "schema", "validation"}),
        ("metadata", {"summary", "schema", "metadata", "labels"}),
    ],
)
def test_report_presets_include_expected_sections(preset, expected):
    assert _included(resolve_report_options(preset=preset)) == expected


def test_explicit_flags_override_presets():
    quick = resolve_report_options(preset="quick", frequencies=True)
    full = resolve_report_options(preset="full", no_labels=True)
    assert quick.include_frequencies
    assert not full.include_labels


def test_targeted_sections_are_case_insensitive_and_custom():
    options = resolve_report_options(
        preset="full",
        sections=["SUMMARY", "Validation"],
    )
    assert _included(options) == {"summary", "validation"}
    assert options.preset == "custom"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"preset": "huge"}, "Unknown report preset"),
        ({"sections": ["unknown"]}, "Unknown report section"),
        ({"max_table_rows": 0}, "--max-table-rows must be at least 1"),
        ({"max_preview_values": 0}, "--max-preview-values must be at least 1"),
    ],
)
def test_report_option_errors_are_friendly(kwargs, message):
    with pytest.raises(ReportError, match=message):
        resolve_report_options(**kwargs)
