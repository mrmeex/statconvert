from __future__ import annotations

import csv
from datetime import datetime, timezone
import json

import pytest

from statconvert.reporting import (
    DatasetReport,
    ReportError,
    ReportIssue,
    ReportMetric,
    ReportSection,
    ReportTable,
    infer_report_output_format,
    write_dataset_report,
    write_dataset_report_csv,
    write_dataset_report_html,
    write_dataset_report_json,
)
from statconvert.reporting.output import REPORT_COLUMNS


def _report() -> DatasetReport:
    issue = ReportIssue(
        severity="warning",
        code="unsafe_<code>",
        column="age",
        message="Value contains <script>alert('x')</script>.",
    )
    section = ReportSection(
        key="summary",
        title="Dataset <Summary>",
        text="Profile <text>",
        metrics=[
            ReportMetric("rows", 2, label="Row <count>"),
            ReportMetric("optional", None, description="May be empty"),
            ReportMetric("details", {"levels": [1, 2]}),
        ],
        tables=[
            ReportTable(
                name="schema <table>",
                columns=["column", "value", "notes"],
                rows=[
                    {"column": "age", "value": [1, 2], "notes": None},
                    {"column": "name", "value": "<Alice>", "notes": {"safe": True}},
                ],
            )
        ],
        issues=[issue],
    )
    return DatasetReport(
        title="Report <script>",
        source_file="input<&>.sav",
        source_format="sav",
        generated_at=datetime(2026, 7, 12, 12, 30, tzinfo=timezone.utc),
        sections=[section],
        issues=[issue],
    )


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.json", "json"),
        ("report.csv", "csv"),
        ("report.html", "html"),
        ("report.HTM", "html"),
    ],
)
def test_infer_report_output_format(filename, expected):
    assert infer_report_output_format(filename) == expected


def test_infer_report_output_format_rejects_unknown_extension():
    with pytest.raises(ReportError, match="Unsupported dataset report format"):
        infer_report_output_format("report.txt")


def test_json_writer_preserves_hierarchy_and_datetime(tmp_path):
    output = tmp_path / "nested" / "report.json"
    write_dataset_report_json(_report(), output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["type"] == "dataset_report"
    assert payload["title"] == "Report <script>"
    assert payload["summary"] == {
        "sections": 1,
        "issues": 1,
        "has_errors": False,
        "has_warnings": True,
    }
    assert payload["generated_at"] == "2026-07-12T12:30:00+00:00"
    assert payload["report"]["sections"][0]["tables"][0]["rows"]


def test_csv_writer_has_stable_rows_and_serializes_nested_values(tmp_path):
    output = tmp_path / "report.csv"
    write_dataset_report_csv(_report(), output)
    with output.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == REPORT_COLUMNS
    assert any(row["section"] == "report" and row["metric"] == "source_file" for row in rows)
    assert any(row["item_type"] == "metric" and row["metric"] == "rows" for row in rows)
    table_rows = [row for row in rows if row["item_type"] == "table"]
    assert table_rows[0]["column"] == "age"
    assert json.loads(table_rows[0]["value"])["value"] == [1, 2]
    assert json.loads(table_rows[0]["value"])["notes"] == ""
    assert any(row["item_type"] == "issue" and row["code"] == "unsafe_<code>" for row in rows)
    optional = next(row for row in rows if row["metric"] == "optional")
    assert optional["value"] == ""
    details = next(row for row in rows if row["metric"] == "details")
    assert details["value"] == '{"levels":[1,2]}'


def test_html_writer_renders_sections_and_escapes_all_data(tmp_path):
    output = tmp_path / "report.html"
    write_dataset_report_html(_report(), output)
    html = output.read_text(encoding="utf-8")
    assert "Report &lt;script&gt;" in html
    assert "input&lt;&amp;&gt;.sav" in html
    assert "Dataset &lt;Summary&gt;" in html
    assert "Row &lt;count&gt;" in html
    assert "schema &lt;table&gt;" in html
    assert "&lt;Alice&gt;" in html
    assert "unsafe_&lt;code&gt;" in html
    assert "Report Issues" in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html
    assert "<script>alert" not in html
    assert 'href="#section-1"' in html


@pytest.mark.parametrize(
    ("filename", "marker"),
    [
        ("report.json", '"type": "dataset_report"'),
        ("report.csv", "section,section_title,item_type"),
        ("report.html", "<!doctype html>"),
    ],
)
def test_dispatch_infers_format_and_creates_parent(tmp_path, filename, marker):
    output = tmp_path / "new" / filename
    write_dataset_report(_report(), output, create_dirs=True)
    assert marker in output.read_text(encoding="utf-8")


def test_dispatch_explicit_format_is_case_insensitive(tmp_path):
    output = tmp_path / "report.data"
    write_dataset_report(_report(), output, output_format="JSON")
    assert json.loads(output.read_text(encoding="utf-8"))["type"] == "dataset_report"


def test_dispatch_rejects_explicit_unknown_format(tmp_path):
    with pytest.raises(ReportError, match="Unsupported dataset report format"):
        write_dataset_report(_report(), tmp_path / "report.data", output_format="xml")


def test_dispatch_wraps_write_failures(tmp_path):
    output = tmp_path / "directory.json"
    output.mkdir()
    with pytest.raises(ReportError, match="Unable to write dataset report"):
        write_dataset_report(_report(), output, overwrite=True)


def test_csv_table_limit_adds_deterministic_truncation_note(tmp_path):
    report = _report()
    report.sections[0].tables[0].rows.append(
        {"column": "third", "value": 3, "notes": "last"}
    )
    output = tmp_path / "limited.csv"
    write_dataset_report_csv(report, output, max_table_rows=2)
    with output.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    table_rows = [row for row in rows if row["item_type"] == "table"]
    notes = [row for row in rows if row["item_type"] == "note"]
    assert len(table_rows) == 2
    assert notes[0]["message"] == (
        "Table 'schema <table>' truncated to 2 rows from 3 rows."
    )


def test_html_table_limit_and_empty_messages_are_clear(tmp_path):
    report = _report()
    report.issues = []
    report.sections[0].issues = []
    report.sections[0].tables[0].rows.append(
        {"column": "third-marker", "value": 3, "notes": None}
    )
    report.sections[0].tables.append(ReportTable("empty", ["column"], []))
    output = tmp_path / "limited.html"
    write_dataset_report_html(report, output, max_table_rows=2)
    html = output.read_text(encoding="utf-8")
    assert "third-marker" not in html
    assert "truncated to 2 rows from 3 rows" in html
    assert "Table of Contents" in html
    assert "status-ok" in html
    assert "No issues." in html
    assert "No rows." in html
    assert "table-wrap" in html


def test_json_dispatch_keeps_full_tables_when_limit_is_set(tmp_path):
    report = _report()
    report.sections[0].tables[0].rows.append(
        {"column": "third", "value": 3, "notes": None}
    )
    output = tmp_path / "full.json"
    write_dataset_report(report, output, max_table_rows=1)
    rows = json.loads(output.read_text(encoding="utf-8"))["report"]["sections"][0]["tables"][0]["rows"]
    assert len(rows) == 3


@pytest.mark.parametrize("writer", [write_dataset_report_csv, write_dataset_report_html])
def test_direct_writers_reject_invalid_table_limit(writer, tmp_path):
    with pytest.raises(ReportError, match="max_table_rows must be at least 1"):
        writer(_report(), tmp_path / "report.out", max_table_rows=0)
