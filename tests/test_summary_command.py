import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.inspection import DatasetSummary
from statconvert.ui.inspection import console, show_dataset_summary


runner = CliRunner()


def test_show_dataset_summary_handles_normal_summary():

    summary = DatasetSummary(
        row_count=1000,
        column_count=12,
        numeric_columns=5,
        text_columns=4,
        boolean_columns=1,
        datetime_columns=2,
        categorical_columns=0,
        other_columns=0,
        columns_with_variable_labels=8,
        columns_with_value_labels=3,
        total_missing_cells=47,
        duplicate_rows=0,
        memory_usage_bytes=1_250_000,
    )

    with console.capture() as capture:
        show_dataset_summary(
            summary
        )

    output = capture.get()

    assert "Dataset Summary" in output
    assert "Rows" in output
    assert "1,000" in output
    assert "Memory usage" in output
    assert "1.2 MB" in output


def test_show_dataset_summary_handles_zero_rows():

    summary = DatasetSummary(
        row_count=0,
        column_count=0,
        numeric_columns=0,
        text_columns=0,
        boolean_columns=0,
        datetime_columns=0,
        categorical_columns=0,
        other_columns=0,
        columns_with_variable_labels=0,
        columns_with_value_labels=0,
        total_missing_cells=0,
        duplicate_rows=0,
        memory_usage_bytes=0,
    )

    with console.capture() as capture:
        show_dataset_summary(
            summary
        )

    output = capture.get()

    assert "Rows" in output
    assert "0 B" in output


def test_show_dataset_summary_handles_unknown_memory():

    summary = DatasetSummary(
        row_count=1,
        column_count=1,
        numeric_columns=1,
        text_columns=0,
        boolean_columns=0,
        datetime_columns=0,
        categorical_columns=0,
        other_columns=0,
        columns_with_variable_labels=0,
        columns_with_value_labels=0,
        total_missing_cells=0,
        duplicate_rows=0,
        memory_usage_bytes=None,
    )

    with console.capture() as capture:
        show_dataset_summary(
            summary
        )

    assert "unknown" in capture.get()


def test_summary_command_reads_csv_and_outputs_counts(tmp_path):

    input_file = tmp_path / "summary.csv"
    pd.DataFrame(
        {
            "age": [
                10,
                20,
                None,
            ],
            "name": [
                "Alice",
                "Bob",
                "Bob",
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    result = runner.invoke(
        app,
        [
            "summary",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 0
    assert "Dataset Summary" in result.output
    assert "Rows" in result.output
    assert "3" in result.output
    assert "Columns" in result.output
    assert "Total missing cells" in result.output


def test_summary_command_outputs_json(tmp_path):

    input_file = tmp_path / "summary.csv"
    pd.DataFrame(
        {
            "age": [
                10,
                20,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    result = runner.invoke(
        app,
        [
            "summary",
            str(
                input_file
            ),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"row_count": 2' in result.output
    assert '"column_count": 1' in result.output


def test_summary_command_handles_unsupported_extension_gracefully(tmp_path):

    input_file = tmp_path / "summary.unsupported"
    input_file.write_text(
        "x",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "summary",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported file format" in result.output
