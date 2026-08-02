from __future__ import annotations

import csv
import json

from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.cli import app
from statconvert.reporting import DatasetReport


runner = CliRunner()


def _write_csv(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("age,sex,income\n10,F,100\n20,M,200\n20,M,\n", encoding="utf-8")
    return path


def _invoke(tmp_path, suffix, *options):
    input_file = _write_csv(tmp_path)
    output_file = tmp_path / f"report{suffix}"
    result = runner.invoke(
        app,
        ["report", str(input_file), "--output", str(output_file), *options],
    )
    return result, output_file


def test_report_command_writes_html_json_and_csv(tmp_path):
    html_result, html_file = _invoke(tmp_path, ".html")
    json_result, json_file = _invoke(tmp_path, ".json")
    csv_result, csv_file = _invoke(tmp_path, ".csv")

    assert html_result.exit_code == 0
    assert "Dataset report written" in html_result.output
    assert "<!doctype html>" in html_file.read_text(encoding="utf-8")
    assert json.loads(json_file.read_text(encoding="utf-8"))["type"] == "dataset_report"
    with csv_file.open(encoding="utf-8", newline="") as source:
        assert next(csv.reader(source))[:3] == ["section", "section_title", "item_type"]
    assert json_result.exit_code == 0
    assert csv_result.exit_code == 0


def test_report_explicit_format_works_with_unusual_extension(tmp_path):
    result, output = _invoke(tmp_path, ".data", "--format", "JSON")
    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["type"] == "dataset_report"


def test_report_rejects_unsupported_output_and_input(tmp_path):
    output_result, _ = _invoke(tmp_path, ".txt")
    unsupported = tmp_path / "input.unknown"
    unsupported.write_text("age\n1\n", encoding="utf-8")
    input_result = runner.invoke(
        app,
        ["report", str(unsupported), "--output", str(tmp_path / "report.html")],
    )
    assert output_result.exit_code == 1
    assert "Unsupported dataset report format" in output_result.output
    assert input_result.exit_code == 1
    assert "Unsupported file format" in input_result.output


def test_report_frequency_toggle_changes_serialized_sections(tmp_path):
    default_result, default_file = _invoke(tmp_path, ".json")
    frequency_result, frequency_file = _invoke(
        tmp_path, ".with-frequencies.json", "--frequencies", "--frequency-top", "1"
    )
    default_keys = [
        section["key"]
        for section in json.loads(default_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    frequency_payload = json.loads(frequency_file.read_text(encoding="utf-8"))
    frequency_keys = [section["key"] for section in frequency_payload["report"]["sections"]]
    assert default_result.exit_code == 0 and "frequencies" not in default_keys
    assert frequency_result.exit_code == 0 and "frequencies" in frequency_keys
    frequency_section = next(
        section for section in frequency_payload["report"]["sections"]
        if section["key"] == "frequencies"
    )
    assert all(
        sum(row["column"] == column for row in frequency_section["tables"][0]["rows"]) <= 1
        for column in {row["column"] for row in frequency_section["tables"][0]["rows"]}
    )


def test_report_section_toggles_omit_labels_and_validation(tmp_path):
    result, output = _invoke(tmp_path, ".json", "--no-labels", "--no-validation")
    keys = [
        section["key"]
        for section in json.loads(output.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    assert result.exit_code == 0
    assert "labels" not in keys
    assert "validation" not in keys


def test_report_columns_restrict_describe_and_frequencies(tmp_path):
    result, output = _invoke(
        tmp_path,
        ".json",
        "--frequencies",
        "--columns",
        "sex",
        "income",
    )
    sections = {
        section["key"]: section
        for section in json.loads(output.read_text(encoding="utf-8"))["report"]["sections"]
    }
    assert result.exit_code == 0
    assert [row["column"] for row in sections["describe"]["tables"][0]["rows"]] == [
        "sex", "income"
    ]
    assert {row["column"] for row in sections["frequencies"]["tables"][0]["rows"]} == {
        "sex", "income"
    }


def test_report_rejects_non_positive_frequency_options(tmp_path):
    top_result, _ = _invoke(tmp_path, ".html", "--frequency-top", "0")
    unique_result, _ = _invoke(tmp_path, ".html", "--frequency-max-unique", "0")
    assert top_result.exit_code == 1
    assert "--frequency-top must be greater than 0" in top_result.output
    assert unique_result.exit_code == 1
    assert "--frequency-max-unique must be greater than 0" in unique_result.output


def test_report_json_stdout_is_valid_and_quiet_suppresses_rich(tmp_path):
    json_result, output = _invoke(tmp_path, ".html", "--json")
    summary = json.loads(json_result.output)
    quiet_result, quiet_output = _invoke(tmp_path, ".quiet.html", "--quiet")
    assert json_result.exit_code == 0 and output.exists()
    assert summary["format"] == "html"
    assert summary["sections"] == 7
    assert "Dataset report written" not in json_result.output
    assert quiet_result.exit_code == 0 and quiet_output.exists()
    assert quiet_result.output == ""


def test_report_passes_builder_and_writer_options(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path)
    output_file = tmp_path / "report.custom"
    captured = {}
    fake_report = DatasetReport("Fake")

    def fake_builder(dataset, **options):
        captured["dataset"] = dataset
        captured["builder"] = options
        return fake_report

    def fake_writer(
        report,
        output_file,
        output_format=None,
        max_table_rows=None,
        overwrite=False,
        create_dirs=False,
    ):
        captured["writer"] = (
            report,
            output_file,
            output_format,
            max_table_rows,
            overwrite,
            create_dirs,
        )

    monkeypatch.setattr(cli_module, "build_dataset_report", fake_builder)
    monkeypatch.setattr(cli_module, "write_dataset_report", fake_writer)
    result = runner.invoke(
        app,
        [
            "report", str(input_file), "-o", str(output_file), "--format", "json",
            "--frequencies", "--frequency-include-missing", "--frequency-max-unique", "8",
            "--target-format", "dta", "--strict-validation", "--no-summary", "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert captured["builder"]["include_summary"] is False
    assert captured["builder"]["include_frequencies"] is True
    assert captured["builder"]["frequency_include_missing"] is True
    assert captured["builder"]["frequency_max_unique"] == 8
    assert captured["builder"]["validation_target_format"] == "dta"
    assert captured["builder"]["strict_validation"] is True
    assert captured["builder"]["label_preview_values"] == 5
    assert captured["writer"] == (
        fake_report,
        str(output_file),
        "json",
        1000,
        False,
        False,
    )


def test_report_cli_presets_and_explicit_overrides(tmp_path):
    quick_result, quick_file = _invoke(tmp_path, ".quick.json", "--preset", "quick")
    full_result, full_file = _invoke(
        tmp_path, ".full.json", "--preset", "full", "--no-labels"
    )
    quick_frequency_result, quick_frequency_file = _invoke(
        tmp_path, ".quick-frequency.json", "--preset", "quick", "--frequencies"
    )
    quick_keys = [
        section["key"]
        for section in json.loads(quick_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    full_keys = [
        section["key"]
        for section in json.loads(full_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    quick_frequency_keys = [
        section["key"]
        for section in json.loads(quick_frequency_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    assert quick_result.exit_code == 0
    assert quick_keys == ["summary", "schema", "missing", "validation"]
    assert full_result.exit_code == 0
    assert "frequencies" in full_keys and "labels" not in full_keys
    assert quick_frequency_result.exit_code == 0
    assert "frequencies" in quick_frequency_keys


def test_report_cli_validation_and_metadata_presets(tmp_path):
    validation_result, validation_file = _invoke(
        tmp_path, ".validation.json", "--preset", "validation"
    )
    metadata_result, metadata_file = _invoke(
        tmp_path, ".metadata.json", "--preset", "metadata"
    )
    validation_keys = [
        section["key"]
        for section in json.loads(validation_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    metadata_keys = [
        section["key"]
        for section in json.loads(metadata_file.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    assert validation_result.exit_code == 0
    assert validation_keys == ["summary", "schema", "validation"]
    assert metadata_result.exit_code == 0
    assert metadata_keys == ["summary", "schema", "metadata", "labels"]


def test_report_cli_targeted_sections_are_repeatable_and_case_insensitive(tmp_path):
    result, output = _invoke(
        tmp_path,
        ".sections.json",
        "--section",
        "SUMMARY",
        "--section",
        "validation",
    )
    keys = [
        section["key"]
        for section in json.loads(output.read_text(encoding="utf-8"))["report"]["sections"]
    ]
    assert result.exit_code == 0
    assert keys == ["summary", "validation"]


def test_report_cli_rejects_invalid_preset_section_and_sizes(tmp_path):
    invalid_preset, _ = _invoke(tmp_path, ".html", "--preset", "huge")
    invalid_section, _ = _invoke(tmp_path, ".html", "--section", "unknown")
    invalid_rows, _ = _invoke(tmp_path, ".html", "--max-table-rows", "0")
    invalid_preview, _ = _invoke(tmp_path, ".html", "--max-preview-values", "0")
    assert invalid_preset.exit_code == 1 and "Unknown report preset" in invalid_preset.output
    assert invalid_section.exit_code == 1 and "Unknown report section" in invalid_section.output
    assert invalid_rows.exit_code == 1 and "--max-table-rows must be at least 1" in invalid_rows.output
    assert invalid_preview.exit_code == 1 and "--max-preview-values must be at least 1" in invalid_preview.output


def test_report_json_summary_includes_polish_options(tmp_path):
    result, output = _invoke(
        tmp_path,
        ".html",
        "--preset",
        "quick",
        "--max-table-rows",
        "2",
        "--max-preview-values",
        "3",
        "--json",
    )
    summary = json.loads(result.output)
    assert result.exit_code == 0 and output.exists()
    assert summary["preset"] == "quick"
    assert summary["section_keys"] == ["summary", "schema", "missing", "validation"]
    assert summary["max_table_rows"] == 2
    assert summary["max_preview_values"] == 3


def test_report_terminal_summary_includes_preset(tmp_path):
    result, _ = _invoke(tmp_path, ".html", "--preset", "quick")
    assert result.exit_code == 0
    assert "Preset" in result.output
    assert "quick" in result.output


def test_report_handles_spaces_uppercase_html_and_htm_paths(tmp_path):
    input_file = tmp_path / "input data.csv"
    input_file.write_text("name,value\nAlice,1\n", encoding="utf-8")
    uppercase = tmp_path / "new reports" / "REPORT.HTML"
    htm = tmp_path / "new reports" / "report with spaces.htm"
    uppercase_result = runner.invoke(
        app,
        [
            "report", str(input_file), "--output", str(uppercase),
            "--create-dirs", "--quiet",
        ],
    )
    htm_result = runner.invoke(
        app,
        [
            "report", str(input_file), "--output", str(htm),
            "--create-dirs", "--quiet",
        ],
    )
    assert uppercase_result.exit_code == 0 and uppercase.exists()
    assert htm_result.exit_code == 0 and htm.exists()


def test_report_target_and_strict_validation_are_observational(tmp_path):
    result, output = _invoke(
        tmp_path,
        ".json",
        "--target-format",
        "dta",
        "--strict-validation",
    )
    assert result.exit_code == 0 and output.exists()
