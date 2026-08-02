import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.inspection import FrequencyItem, FrequencyTable
from statconvert.ui.inspection import console, show_frequency_tables


runner = CliRunner()


def test_show_frequency_tables_handles_one_table():

    table = FrequencyTable(
        column="school",
        label="Wizard School",
        total_count=3,
        missing_count=0,
        items=[
            FrequencyItem(
                value="alchemy",
                count=2,
                percent=66.666,
            ),
        ],
    )

    with console.capture() as capture:
        show_frequency_tables(
            [
                table,
            ]
        )

    output = capture.get()

    assert "Frequencies: school - Wizard School" in output
    assert "alchemy" in output
    assert "2" in output
    assert "66.7%" in output


def test_show_frequency_tables_handles_multiple_tables():

    tables = [
        FrequencyTable(
            column="school",
            total_count=2,
            missing_count=0,
            items=[
                FrequencyItem(
                    value="alchemy",
                    count=1,
                    percent=50.0,
                ),
            ],
        ),
        FrequencyTable(
            column="rank",
            total_count=2,
            missing_count=0,
            items=[
                FrequencyItem(
                    value="adept",
                    count=1,
                    percent=50.0,
                ),
            ],
        ),
    ]

    with console.capture() as capture:
        show_frequency_tables(
            tables
        )

    output = capture.get()

    assert "Frequencies: school" in output
    assert "Frequencies: rank" in output


def test_show_frequency_tables_handles_value_labels():

    table = FrequencyTable(
        column="school",
        total_count=2,
        missing_count=0,
        items=[
            FrequencyItem(
                value=1,
                label="Alchemy",
                count=2,
                percent=100.0,
            ),
        ],
    )

    with console.capture() as capture:
        show_frequency_tables(
            [
                table,
            ]
        )

    assert "Alchemy" in capture.get()


def test_show_frequency_tables_handles_missing_values_display():

    table = FrequencyTable(
        column="school",
        total_count=2,
        missing_count=1,
        items=[
            FrequencyItem(
                value=pd.NA,
                count=1,
                percent=50.0,
            ),
        ],
    )

    with console.capture() as capture:
        show_frequency_tables(
            [
                table,
            ]
        )

    assert "<missing>" in capture.get()


def test_show_frequency_tables_handles_empty_table_list():

    with console.capture() as capture:
        show_frequency_tables(
            []
        )

    assert "No frequency tables available" in capture.get()


def test_show_frequency_tables_handles_empty_items():

    table = FrequencyTable(
        column="school",
        total_count=0,
        missing_count=0,
        items=[],
    )

    with console.capture() as capture:
        show_frequency_tables(
            [
                table,
            ]
        )

    assert "Frequencies: school" in capture.get()


def test_frequencies_command_reads_csv_successfully(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 0
    assert "Frequencies: school" in result.output


def test_frequencies_command_output_includes_categorical_column(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
        ],
    )

    assert "school" in result.output
    assert "alchemy" in result.output


def test_frequencies_command_respects_columns(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--columns",
            "rank",
        ],
    )

    assert result.exit_code == 0
    assert "Frequencies: rank" in result.output
    assert "Frequencies: school" not in result.output


def test_frequencies_command_respects_top(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--columns",
            "school",
            "--top",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "alchemy" in result.output
    assert "runes" not in result.output


def test_frequencies_command_respects_include_missing(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--columns",
            "school",
            "--include-missing",
        ],
    )

    assert result.exit_code == 0
    assert "<missing>" in result.output


def test_frequencies_command_handles_missing_requested_column(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--columns",
            "missing",
        ],
    )

    assert result.exit_code == 1
    assert "Column not found: missing" in result.output


def test_frequencies_command_rejects_top_zero(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--top",
            "0",
        ],
    )

    assert result.exit_code == 1
    assert "--top must be greater than 0" in result.output


def test_frequencies_command_rejects_negative_max_unique(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--max-unique",
            "-1",
        ],
    )

    assert result.exit_code == 1
    assert "--max-unique must be greater than 0" in result.output


def test_frequencies_command_outputs_json(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(
                input_file
            ),
            "--columns",
            "school",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )

    assert data[0]["column"] == "school"
    assert data[0]["items"][0]["value"] == "alchemy"


def _write_csv(
    tmp_path
):
    input_file = tmp_path / "frequencies.csv"
    pd.DataFrame(
        {
            "school": [
                "alchemy",
                "alchemy",
                "runes",
                None,
            ],
            "rank": [
                "adept",
                "master",
                "adept",
                "novice",
            ],
            "score": [
                10,
                20,
                30,
                40,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    return input_file
