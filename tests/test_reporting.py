from datetime import datetime

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.reporting import (
    DatasetReport, ReportIssue, ReportSection, build_dataset_report,
    build_describe_section, build_frequencies_section, build_labels_section,
    build_metadata_section, build_missing_section, build_schema_section,
    build_summary_section, build_validation_section,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        dataset_label="Study dataset",
        notes=["Reviewed"],
    )
    metadata.add_variable(VariableMetadata(name="score", label="Test score", missing_values=[-99], storage_type="F8.2", display_format="F8.2", measure="scale"))
    metadata.add_variable(VariableMetadata(name="group", label="Study group", value_labels={1: "Control", 2: "Treatment", 3: "Waitlist", 4: "Other", 5: "Unknown", 6: "Unused"}, storage_type="F1.0", measure="nominal"))
    metadata.add_variable(VariableMetadata(name="when", storage_type="DATETIME"))
    return Dataset(
        pd.DataFrame({"score": [1.0, None, 3.0], "group": [1, 1, 2], "when": pd.to_datetime(["2026-01-01", None, "2026-01-03"])}),
        source_format="sav",
        source_file="survey.sav",
        normalized_metadata=metadata,
        metadata_provenance={
            "dataset": "automatic_sidecar",
            "columns": {
                "score": "automatic_sidecar",
                "group": "automatic_sidecar",
                "when": "primary_file",
            },
        },
    )


def _metric(section: ReportSection, name: str):
    return next(metric.value for metric in section.metrics if metric.name == name)


def test_report_model_properties_and_independent_section_defaults():
    error = ReportIssue("error", "broken", "Broken")
    warning = ReportIssue("warning", "careful", "Careful")
    first = ReportSection("one", "One", issues=[warning])
    second = ReportSection("two", "Two")
    first.metrics.append(object())
    report = DatasetReport("Report", sections=[first, second], issues=[error])
    assert (report.section_count, report.issue_count) == (2, 2)
    assert report.has_errors and report.has_warnings
    assert report.get_section("two") is second
    assert report.get_section("missing") is None
    assert second.metrics == []


def test_summary_and_schema_include_core_values_and_metadata():
    summary = build_summary_section(_dataset())
    schema = build_schema_section(_dataset())
    assert summary.key == "summary"
    assert (_metric(summary, "rows"), _metric(summary, "columns")) == (3, 3)
    assert [row["column"] for row in schema.tables[0].rows] == ["score", "group", "when"]
    assert schema.tables[0].rows[0]["dtype"] == "float64"
    assert schema.tables[0].rows[0]["variable_label"] == "Test score"
    assert schema.tables[0].rows[0]["storage_type"] == "F8.2"


def test_metadata_and_labels_are_compact_and_defensive():
    empty = build_metadata_section(Dataset(pd.DataFrame({"plain": [1]})))
    metadata = build_metadata_section(_dataset())
    labels = build_labels_section(_dataset())
    assert _metric(empty, "variable_labels") == 0
    assert _metric(metadata, "variable_labels") == 2
    assert _metric(metadata, "value_label_variables") == 1
    assert _metric(metadata, "dataset_label") == "Study dataset"
    assert _metric(metadata, "dataset_notes") == ["Reviewed"]
    assert _metric(metadata, "metadata_source") == "automatic_sidecar"
    assert _metric(metadata, "column_metadata_sources")["when"] == "primary_file"
    assert labels.tables[0].rows[0] == {"column": "score", "label": "Test score"}
    value_row = labels.tables[1].rows[0]
    assert value_row["value_count"] == 6
    assert value_row["values_preview"].count("=") == 5
    assert "Unused" not in value_row["values_preview"]


def test_metadata_section_reuses_prepared_summary_counts(monkeypatch):
    dataset = Dataset(pd.DataFrame({"value": [1]}))
    monkeypatch.setattr(
        dataset,
        "metadata_summary",
        lambda: {
            "variables": 1,
            "variable_labels": 2,
            "value_label_sets": 3,
            "missing_value_sets": 4,
            "missing_range_sets": 0,
            "display_formats": 5,
            "measurement_levels": 6,
            "has_metadata": True,
        },
    )
    for accessor in (
        "variable_labels",
        "value_labels",
        "missing_values",
        "display_formats",
        "measurement_levels",
    ):
        monkeypatch.setattr(
            dataset,
            accessor,
            lambda name=accessor: (_ for _ in ()).throw(
                AssertionError(f"{name} was recomputed")
            ),
        )
    monkeypatch.setattr(dataset, "storage_types", lambda: {"value": "int64"})

    section = build_metadata_section(dataset)

    assert _metric(section, "variable_labels") == 2
    assert _metric(section, "value_label_variables") == 3
    assert _metric(section, "missing_value_variables") == 4
    assert _metric(section, "display_format_variables") == 5
    assert _metric(section, "measurement_level_variables") == 6


def test_labels_preview_limit_is_configurable_and_defaults_to_five():
    default = build_labels_section(_dataset()).tables[1].rows[0]["values_preview"]
    limited = build_labels_section(
        _dataset(),
        preview_values=3,
    ).tables[1].rows[0]["values_preview"]
    assert default.count("=") == 5
    assert limited.count("=") == 3


def test_labels_preview_does_not_materialize_values_beyond_limit(monkeypatch):
    class LimitedItems(dict):
        def items(self):
            yield 1, "one"
            yield 2, "two"
            raise AssertionError("preview consumed mappings beyond its limit")

    dataset = _dataset()
    monkeypatch.setattr(
        dataset,
        "value_labels",
        lambda: {"group": LimitedItems({1: "one", 2: "two", 3: "three"})},
    )

    preview = build_labels_section(dataset, preview_values=2).tables[1].rows[0]

    assert preview["value_count"] == 3
    assert preview["values_preview"] == "1=one; 2=two"


def test_missing_and_describe_handle_multiple_types():
    missing = build_missing_section(_dataset())
    describe = build_describe_section(_dataset())
    score_missing = missing.tables[0].rows[0]
    assert score_missing["missing_count"] == 1
    assert score_missing["missing_percent"] > 33
    assert score_missing["metadata_missing_values"] == [-99]
    rows = {row["column"]: row for row in describe.tables[0].rows}
    assert rows["score"]["mean"] == 2.0
    assert rows["group"]["non_missing"] == 3
    assert rows["when"]["missing"] == 1


def test_frequencies_respect_options():
    dataset = Dataset(pd.DataFrame({"kind": ["a", "a", "b", None], "other": ["x", "y", "z", "w"]}))
    selected = build_frequencies_section(dataset, columns=["kind"], top=1)
    with_missing = build_frequencies_section(dataset, columns=["kind"], include_missing=True)
    limited = build_frequencies_section(dataset, max_unique=2)
    assert len(selected.tables[0].rows) == 1
    assert {row["column"] for row in selected.tables[0].rows} == {"kind"}
    assert any(pd.isna(row["value"]) for row in with_missing.tables[0].rows)
    assert {row["column"] for row in limited.tables[0].rows} == {"kind"}


def test_validation_converts_and_counts_issues_and_handles_clean_data():
    section = build_validation_section(Dataset(pd.DataFrame()))
    assert section.issues and len(section.tables[0].rows) == len(section.issues)
    assert _metric(section, "errors") >= 1
    assert _metric(section, "warnings") >= 1
    assert _metric(section, "info") >= 1
    clean = build_validation_section(Dataset(pd.DataFrame({"value": [1, 2]})))
    assert _metric(clean, "errors") == 0
    assert _metric(clean, "warnings") == 0


def test_dataset_report_builder_flags_columns_sources_and_time():
    report = build_dataset_report(_dataset())
    selected = build_dataset_report(_dataset(), include_schema=False, include_frequencies=True, columns=["group"])
    assert report.get_section("frequencies") is None
    assert report.section_count == 7
    assert selected.get_section("schema") is None
    assert selected.get_section("frequencies") is not None
    assert [row["column"] for row in selected.get_section("describe").tables[0].rows] == ["group"]
    assert isinstance(report.generated_at, datetime) and report.generated_at.tzinfo is not None
    assert (report.source_file, report.source_format) == ("survey.sav", "sav")
