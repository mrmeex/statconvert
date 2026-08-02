import csv
import json

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

import statconvert.compare.reporting as compare_reporting
from statconvert.cli import app
from statconvert.compare import (
    CompareError,
    CompareOptions,
    compare_datasets,
    infer_compare_report_format,
    write_compare_report,
)
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


runner = CliRunner()


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [("csv", "csv"), ("json", "json"), ("html", "html")],
)
def test_infer_compare_report_format(suffix, expected):
    assert infer_compare_report_format(f"comparison.{suffix}") == expected


def test_infer_compare_report_format_rejects_unsupported_extension():
    with pytest.raises(CompareError, match="Unsupported compare report format"):
        infer_compare_report_format("comparison.xlsx")


def test_write_compare_json_report_contains_full_structure(tmp_path):
    report = tmp_path / "nested" / "comparison.json"

    write_compare_report(_changed_comparison(), report)
    payload = json.loads(report.read_text(encoding="utf-8"))

    assert payload["type"] == "comparison"
    assert payload["summary"]["left_source"] == "before<&.sav"
    assert payload["summary"]["errors"] == 1
    assert payload["comparison"]["shape"]["rows_match"] is True
    assert payload["comparison"]["schema"]["storage_type_changes"]["age"] == [
        "int32",
        "float64",
    ]


def test_json_report_serializes_comparison_dataclass_once(tmp_path, monkeypatch):
    report = tmp_path / "comparison.json"
    original = compare_reporting.asdict
    calls = 0

    def tracked_asdict(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(compare_reporting, "asdict", tracked_asdict)

    write_compare_report(_changed_comparison(), report)

    assert calls == 1
    assert json.loads(report.read_text(encoding="utf-8"))["type"] == "comparison"


def test_write_compare_csv_report_has_stable_sections(tmp_path):
    report = tmp_path / "comparison.csv"

    write_compare_report(_changed_comparison(), report)
    with report.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == [
        "section",
        "severity",
        "code",
        "column",
        "metric",
        "left",
        "right",
        "message",
    ]
    assert _has_row(rows, "shape", "rows")
    assert _has_row(rows, "schema", "storage_type")
    assert _has_row(rows, "metadata", "variable_label")
    assert _has_row(rows, "values", "differing_cells")
    assert any(row["section"] == "issue" and row["code"] == "values_changed" for row in rows)


def test_compare_reports_include_display_format_and_measurement_level_changes(tmp_path):
    comparison = _schema_changed_comparison()
    csv_report = tmp_path / "comparison.csv"
    json_report = tmp_path / "comparison.json"
    html_report = tmp_path / "comparison.html"

    write_compare_report(comparison, csv_report)
    write_compare_report(comparison, json_report)
    write_compare_report(comparison, html_report)

    csv_rows = list(csv.DictReader(csv_report.open(encoding="utf-8", newline="")))
    schema_metrics = [
        row["metric"] for row in csv_rows if row["section"] == "schema"
    ]
    json_payload = json.loads(json_report.read_text(encoding="utf-8"))
    html = html_report.read_text(encoding="utf-8")

    assert schema_metrics == ["display_format", "measurement_level"]
    assert json_payload["comparison"]["schema"]["display_format_changes"] == {
        "age": ["<F8.0>", "F9.2"]
    }
    assert json_payload["comparison"]["schema"]["measurement_level_changes"] == {
        "age": ["scale", "ordinal"]
    }
    assert "Display format" in html
    assert "Measurement level" in html
    assert "&lt;F8.0&gt;" in html
    assert "<F8.0>" not in html


def test_compare_reports_include_applied_core_options(tmp_path):
    left = _dataset({"id": [1.0], "generated": ["left"]})
    right = _dataset({"id": [1.00005], "generated": ["right"]})
    comparison = compare_datasets(
        left,
        right,
        options=CompareOptions(
            ignore_columns=("generated",),
            numeric_tolerance=0.0001,
        ),
    )
    csv_report = tmp_path / "comparison.csv"
    json_report = tmp_path / "comparison.json"
    html_report = tmp_path / "comparison.html"

    write_compare_report(comparison, csv_report)
    write_compare_report(comparison, json_report)
    write_compare_report(comparison, html_report)

    csv_rows = list(csv.DictReader(csv_report.open(encoding="utf-8", newline="")))
    summary = {
        row["metric"]: row["left"]
        for row in csv_rows
        if row["section"] == "summary"
    }
    json_payload = json.loads(json_report.read_text(encoding="utf-8"))
    html = html_report.read_text(encoding="utf-8")

    assert summary["ignored_columns"] == '["generated"]'
    assert summary["columns_compared"] == '["id"]'
    assert summary["numeric_tolerance"] == "0.0001"
    assert json_payload["summary"]["ignored_columns"] == ["generated"]
    assert json_payload["summary"]["columns_compared"] == ["id"]
    assert json_payload["summary"]["numeric_tolerance"] == 0.0001
    assert "Comparison Options" in html
    assert "generated" in html
    assert "0.0001" in html


def test_compare_reports_include_key_matching_summary(tmp_path):
    comparison = compare_datasets(
        _dataset({"id": [1, 2], "value": [10, 20]}),
        _dataset({"id": [2, 3], "value": [20, 30]}),
        options=CompareOptions(key_columns=("id",)),
    )
    csv_report = tmp_path / "comparison.csv"
    json_report = tmp_path / "comparison.json"
    html_report = tmp_path / "comparison.html"

    write_compare_report(comparison, csv_report)
    write_compare_report(comparison, json_report)
    write_compare_report(comparison, html_report)

    csv_rows = list(csv.DictReader(csv_report.open(encoding="utf-8", newline="")))
    summary = {
        row["metric"]: row["left"]
        for row in csv_rows
        if row["section"] == "summary"
    }
    json_payload = json.loads(json_report.read_text(encoding="utf-8"))
    html = html_report.read_text(encoding="utf-8")

    assert summary["row_matching_mode"] == "key"
    assert summary["key_columns"] == '["id"]'
    assert summary["matched_rows"] == "1"
    assert summary["rows_only_left"] == "1"
    assert summary["rows_only_right"] == "1"
    assert json_payload["summary"]["row_matching_mode"] == "key"
    assert json_payload["summary"]["key_columns"] == ["id"]
    assert json_payload["summary"]["matched_rows"] == 1
    assert "Rows only in left" in html
    assert "Rows only in right" in html


def test_compare_reports_include_bounded_first_differences(tmp_path):
    comparison = compare_datasets(
        _dataset({"value": [np.int64(1), np.nan, 3]}),
        _dataset({"value": [np.int64(2), 0.0, 4]}),
        options=CompareOptions(max_differences=2),
    )
    csv_report = tmp_path / "comparison.csv"
    json_report = tmp_path / "comparison.json"
    html_report = tmp_path / "comparison.html"

    write_compare_report(comparison, csv_report)
    write_compare_report(comparison, json_report)
    write_compare_report(comparison, html_report)

    csv_rows = list(csv.DictReader(csv_report.open(encoding="utf-8", newline="")))
    detail_rows = [row for row in csv_rows if row["section"] == "difference"]
    summary = {
        row["metric"]: row["left"]
        for row in csv_rows
        if row["section"] == "summary"
    }
    json_payload = json.loads(json_report.read_text(encoding="utf-8"))
    html = html_report.read_text(encoding="utf-8")

    assert len(detail_rows) == 2
    assert summary["max_differences"] == "2"
    assert summary["cells_different"] == "3"
    assert summary["detailed_differences_shown"] == "2"
    assert summary["detailed_differences_truncated"] == "True"
    assert len(json_payload["differences"]) == 2
    assert json_payload["differences"][0]["left"] == 1.0
    assert json_payload["differences"][1]["left"] is None
    assert json_payload["summary"]["cells_different"] == 3
    assert json_payload["summary"]["detailed_differences_total"] == 3
    assert "First Differences" in html
    assert "Showing first 2 of 3 detailed differences" in html


def test_compare_json_report_normalizes_numpy_value_label_keys(tmp_path):
    left = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", value_labels={np.int64(1): "One"}),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", value_labels={np.int64(1): "First"}),
    )
    report = tmp_path / "comparison.json"

    write_compare_report(compare_datasets(left, right), report)
    payload = json.loads(report.read_text(encoding="utf-8"))

    changes = payload["comparison"]["metadata"]["value_label_changes"]["age"]
    assert changes == [{"1": "One"}, {"1": "First"}]


def test_write_compare_csv_report_handles_values_none(tmp_path):
    report = tmp_path / "comparison.csv"
    comparison = compare_datasets(
        _dataset({"age": [1]}),
        _dataset({"age": [2]}),
        compare_values=False,
    )

    write_compare_report(comparison, report)
    rows = list(csv.DictReader(report.open(encoding="utf-8", newline="")))

    skipped = next(row for row in rows if row["section"] == "values")
    assert skipped["message"] == "Value comparison skipped."


def test_write_compare_html_report_escapes_sources_and_shows_issues(tmp_path):
    report = tmp_path / "comparison.html"

    write_compare_report(_changed_comparison(), report)
    output = report.read_text(encoding="utf-8")

    assert "StatConvert Comparison Report" in output
    assert "before&lt;&amp;.sav" in output
    assert "Errors found" in output
    assert "values_changed" in output
    assert "<table>" in output


def test_write_compare_html_report_handles_no_issues(tmp_path):
    report = tmp_path / "comparison.html"
    comparison = compare_datasets(_dataset({"age": [1]}), _dataset({"age": [1]}))

    write_compare_report(comparison, report)

    assert "No comparison issues found." in report.read_text(encoding="utf-8")


def test_write_compare_report_supports_explicit_format(tmp_path):
    report = tmp_path / "comparison.data"

    write_compare_report(_changed_comparison(), report, report_format="json")

    assert json.loads(report.read_text(encoding="utf-8"))["type"] == "comparison"


@pytest.mark.parametrize("suffix", ["csv", "json", "html"])
def test_compare_command_writes_each_report_format(tmp_path, suffix):
    left, right = _write_csv_pair(tmp_path, [1, 2], [1, 2])
    report = tmp_path / "reports" / f"comparison.{suffix}"

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--report", str(report)],
    )

    assert result.exit_code == 0
    assert report.exists()
    assert "Report written" in result.output


def test_compare_json_stdout_and_csv_report_are_independent(tmp_path):
    left, right = _write_csv_pair(tmp_path, [1], [1])
    report = tmp_path / "comparison.csv"

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--json",
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["shape"]["rows_match"] is True
    assert report.exists()


def test_compare_report_unsupported_extension_is_friendly(tmp_path):
    left, right = _write_csv_pair(tmp_path, [1], [1])

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--report", str(tmp_path / "bad.ext")],
    )

    assert result.exit_code == 1
    assert "Unsupported compare report format" in result.output


def test_compare_differences_write_report_before_nonzero_exit(tmp_path):
    left, right = _write_csv_pair(tmp_path, [1], [2])
    report = tmp_path / "difference.json"

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--report", str(report)],
    )

    assert result.exit_code == 1
    assert report.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["summary"]["errors"] == 1


def _changed_comparison():
    left = _dataset(
        {"age": [1]},
        VariableMetadata(
            name="age",
            label="Age",
            value_labels={1: "One"},
            missing_values=[-1],
            storage_type="int32",
        ),
        source="before<&.sav",
    )
    right = _dataset(
        {"age": [2]},
        VariableMetadata(
            name="age",
            label="Age in years",
            value_labels={2: "Two"},
            missing_values=[-9],
            storage_type="float64",
        ),
        source="after>.parquet",
    )
    return compare_datasets(left, right)


def _schema_changed_comparison():
    left = _dataset(
        {"age": [1]},
        VariableMetadata(
            name="age",
            display_format="<F8.0>",
            measure="scale",
        ),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(
            name="age",
            display_format="F9.2",
            measure="ordinal",
        ),
    )
    return compare_datasets(left, right)


def _dataset(data, variable=None, source=None):
    metadata = DatasetMetadata()
    if variable is not None:
        metadata.add_variable(variable)
    return Dataset(
        dataframe=pd.DataFrame(data),
        normalized_metadata=metadata,
        source_file=source,
    )


def _write_csv_pair(tmp_path, left_values, right_values):
    left = tmp_path / "before.csv"
    right = tmp_path / "after.csv"
    pd.DataFrame({"age": left_values}).to_csv(left, index=False)
    pd.DataFrame({"age": right_values}).to_csv(right, index=False)
    return left, right


def _has_row(rows, section, metric):
    return any(row["section"] == section and row["metric"] == metric for row in rows)
