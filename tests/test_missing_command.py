import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.inspection import MissingProfile
from statconvert.ui.inspection import console, show_missing_profiles


runner = CliRunner()


def test_show_missing_profiles_handles_one_profile():

    profile = MissingProfile(
        column="ritual_score",
        label="Ritual Score",
        missing_count=4,
        missing_percent=40.0,
        metadata_missing_values=[
            999,
        ],
    )

    with console.capture() as capture:
        show_missing_profiles(
            [
                profile,
            ]
        )

    output = capture.get()

    assert "Missing Values" in output
    assert "ritual_score" in output
    assert "Ritual Score" in output
    assert "999" in output


def test_show_missing_profiles_handles_multiple_profiles():

    profiles = [
        MissingProfile(
            column="mana_level",
            missing_count=1,
            missing_percent=25.0,
        ),
        MissingProfile(
            column="familiar_name",
            missing_count=2,
            missing_percent=50.0,
        ),
    ]

    with console.capture() as capture:
        show_missing_profiles(
            profiles
        )

    output = capture.get()

    assert "mana_level" in output
    assert "familiar_name" in output


def test_show_missing_profiles_displays_metadata_missing_values():

    profile = MissingProfile(
        column="ritual_score",
        missing_count=0,
        missing_percent=0.0,
        metadata_missing_values=[
            999,
            998,
        ],
    )

    with console.capture() as capture:
        show_missing_profiles(
            [
                profile,
            ]
        )

    output = capture.get()

    assert "999, 998" in output


def test_show_missing_profiles_handles_empty_profile_list():

    with console.capture() as capture:
        show_missing_profiles(
            []
        )

    assert "No missing values found" in capture.get()


def test_show_missing_profiles_handles_no_metadata_missing_values():

    profile = MissingProfile(
        column="school",
        missing_count=0,
        missing_percent=0.0,
    )

    with console.capture() as capture:
        show_missing_profiles(
            [
                profile,
            ]
        )

    assert "-" in capture.get()


def test_missing_command_reads_csv_successfully(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 0
    assert "Missing Values" in result.output


def test_missing_command_output_includes_column_with_missing_values(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
        ],
    )

    assert "age" in result.output
    assert "familiar_name" in result.output


def test_missing_command_respects_columns(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--columns",
            "familiar_name",
            "age",
        ],
    )

    assert result.exit_code == 0
    assert result.output.find(
        "familiar_name"
    ) < result.output.find(
        "age"
    )
    assert "school" not in result.output


def test_missing_command_respects_only_missing(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--only-missing",
        ],
    )

    assert result.exit_code == 0
    assert "age" in result.output
    assert "school" not in result.output


def test_missing_command_respects_threshold(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--threshold",
            "50",
        ],
    )

    assert result.exit_code == 0
    assert "all_missing" in result.output
    assert "age" not in result.output


def test_missing_command_handles_missing_requested_column(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--columns",
            "missing",
        ],
    )

    assert result.exit_code == 1
    assert "Column not found: missing" in result.output


def test_missing_command_rejects_threshold_below_zero(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--threshold",
            "-1",
        ],
    )

    assert result.exit_code == 1
    assert "--threshold must be between 0 and 100" in result.output


def test_missing_command_rejects_threshold_above_one_hundred(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--threshold",
            "101",
        ],
    )

    assert result.exit_code == 1
    assert "--threshold must be between 0 and 100" in result.output


def test_missing_command_outputs_json(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "missing",
            str(
                input_file
            ),
            "--columns",
            "age",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )

    assert data[0]["column"] == "age"
    assert data[0]["missing_count"] == 1


def _write_csv(
    tmp_path
):
    input_file = tmp_path / "missing.csv"
    pd.DataFrame(
        {
            "age": [
                10,
                None,
                30,
                40,
            ],
            "familiar_name": [
                "Nyx",
                None,
                "Puck",
                "Mira",
            ],
            "school": [
                "alchemy",
                "runes",
                "alchemy",
                "runes",
            ],
            "all_missing": [
                None,
                None,
                None,
                None,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    return input_file
