from dataclasses import asdict
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.reporting import (
    DatasetReport,
    ReportIssue,
    ReportMetric,
    ReportSection,
    ReportTable,
    build_dataset_report,
    build_describe_section,
    build_frequencies_section,
    build_labels_section,
    build_metadata_section,
    build_missing_section,
    build_schema_section,
    build_summary_section,
    build_validation_section,
    write_dataset_report_csv,
    write_dataset_report_html,
    write_dataset_report_json,
)


def test_full_report_model_is_asdict_friendly_and_counts_section_issues():
    section_issue = ReportIssue("warning", "section", "Section warning")
    top_issue = ReportIssue("error", "top", "Top error")
    section = ReportSection(
        "summary",
        "Summary",
        metrics=[ReportMetric("rows", 1)],
        tables=[ReportTable("values", ["column"], [{"column": "a"}])],
        issues=[section_issue],
    )
    report = DatasetReport(
        "Report",
        generated_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        sections=[section],
        issues=[top_issue],
    )
    payload = asdict(report)
    assert report.section_count == 1
    assert report.issue_count == 2
    assert report.has_errors and report.has_warnings
    assert report.get_section("summary") is section
    assert report.get_section("absent") is None
    assert payload["sections"][0]["tables"][0]["rows"][0] == {"column": "a"}


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(),
        pd.DataFrame({"only": [1]}),
        pd.DataFrame({"empty": pd.Series(dtype="float64")}),
        pd.DataFrame({"all_missing": [None, None]}),
        pd.DataFrame({"constant": [1, 1, 1]}),
        pd.DataFrame({"boolean": [True, False, None]}),
        pd.DataFrame({"when": pd.to_datetime(["2026-01-01", None])}),
        pd.DataFrame({"mixed": [1, "two", True, None]}),
        pd.DataFrame({"<script> column": ["<script>alert(1)</script>"]}),
        pd.DataFrame({f"column_{index}": [index] for index in range(150)}),
    ],
)
def test_all_section_builders_handle_normal_odd_datasets(frame):
    dataset = Dataset(frame)
    assert build_summary_section(dataset).key == "summary"
    assert build_schema_section(dataset).key == "schema"
    assert build_metadata_section(dataset).key == "metadata"
    assert build_labels_section(dataset).key == "labels"
    assert build_missing_section(dataset).key == "missing"
    assert build_describe_section(dataset).key == "describe"
    assert build_frequencies_section(dataset).key == "frequencies"
    assert build_validation_section(dataset).key == "validation"
    assert build_dataset_report(dataset).section_count == 7


def test_unhashable_object_cells_are_profiled_and_counted_defensively():
    dataset = Dataset(
        pd.DataFrame({"objects": [[1], {"answer": 42}, [1], None]})
    )
    summary = build_summary_section(dataset)
    describe = build_describe_section(dataset)
    frequencies = build_frequencies_section(
        dataset,
        columns=["objects"],
        include_missing=True,
    )
    assert next(metric.value for metric in summary.metrics if metric.name == "duplicate_rows") == 1
    assert describe.tables[0].rows[0]["unique"] == 2
    assert [row["count"] for row in frequencies.tables[0].rows] == [2, 1, 1]


def test_all_missing_column_profiles_and_frequencies_are_stable():
    dataset = Dataset(pd.DataFrame({"missing": [None, None]}))
    missing = build_missing_section(dataset).tables[0].rows[0]
    describe = build_describe_section(dataset).tables[0].rows[0]
    frequencies = build_frequencies_section(
        dataset,
        columns=["missing"],
        include_missing=True,
    ).tables[0].rows
    assert missing["missing_count"] == 2
    assert missing["missing_percent"] == 100.0
    assert describe["non_missing"] == 0
    assert frequencies[0]["count"] == 2


def _scalar_report() -> DatasetReport:
    return DatasetReport(
        "Special <Report>",
        source_file="data & source.csv",
        generated_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        sections=[
            ReportSection(
                "values",
                "Values",
                metrics=[
                    ReportMetric("nan", float("nan")),
                    ReportMetric("infinity", float("inf")),
                    ReportMetric("nat", pd.NaT),
                    ReportMetric("pandas_na", pd.NA),
                    ReportMetric("numpy_integer", np.int64(7)),
                    ReportMetric("timestamp", pd.Timestamp("2026-07-12")),
                ],
                tables=[ReportTable("empty", ["column"], [])],
            )
        ],
    )


def test_json_serializes_missing_nonfinite_and_numpy_scalars_strictly(tmp_path):
    output = tmp_path / "nested folder" / "special report.json"
    write_dataset_report_json(_scalar_report(), output)
    text = output.read_text(encoding="utf-8")
    payload = json.loads(text, parse_constant=lambda value: pytest.fail(value))
    metrics = payload["report"]["sections"][0]["metrics"]
    values = {metric["name"]: metric["value"] for metric in metrics}
    assert values["nan"] is None
    assert values["infinity"] is None
    assert values["nat"] is None
    assert values["pandas_na"] is None
    assert values["numpy_integer"] == 7
    assert values["timestamp"] == "2026-07-12T00:00:00"
    assert payload["title"] == "Special <Report>"


def test_csv_and_html_render_missing_scalars_and_special_characters_safely(tmp_path):
    csv_output = tmp_path / "csv folder" / "special report.csv"
    html_output = tmp_path / "html folder" / "special report.htm"
    write_dataset_report_csv(_scalar_report(), csv_output)
    write_dataset_report_html(_scalar_report(), html_output)
    csv_text = csv_output.read_text(encoding="utf-8")
    html = html_output.read_text(encoding="utf-8")
    assert "nan,nan" not in csv_text.lower()
    assert "nat,nat" not in csv_text.lower()
    assert "<NA>" not in csv_text
    assert "numpy_integer,7" in csv_text
    assert "Special &lt;Report&gt;" in html
    assert "data &amp; source.csv" in html
    assert "No rows." in html


@pytest.mark.parametrize(
    ("writer", "suffix"),
    [
        (write_dataset_report_json, ".json"),
        (write_dataset_report_csv, ".csv"),
        (write_dataset_report_html, ".html"),
    ],
)
def test_direct_writers_wrap_file_failures(writer, suffix, tmp_path):
    output = tmp_path / f"directory{suffix}"
    output.mkdir()
    from statconvert.reporting import ReportError

    with pytest.raises(ReportError, match="Unable to write dataset report"):
        writer(_scalar_report(), output)
