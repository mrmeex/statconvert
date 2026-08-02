import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.inspection import (
    CategoricalProfile,
    ColumnProfile,
    NumericProfile,
)
from statconvert.ui.inspection import console, show_column_profiles


runner = CliRunner()


def test_show_column_profiles_handles_numeric_profiles():

    profiles = [
        ColumnProfile(
            name="age",
            storage_type="float64",
            label="Age",
            non_missing_count=3,
            missing_count=1,
            missing_percent=25.0,
            unique_count=3,
            profile_type="numeric",
            numeric=NumericProfile(
                count=3,
                mean=20.0,
                std=10.0,
                min=10.0,
                q1=15.0,
                median=20.0,
                q3=25.0,
                max=30.0,
            ),
        ),
    ]

    with console.capture() as capture:
        show_column_profiles(
            profiles
        )

    output = capture.get()

    assert "Column Profiles" in output
    assert "Numeric Statistics" in output
    assert "age" in output
    assert "20.00" in output


def test_show_column_profiles_handles_categorical_profiles():

    profiles = [
        ColumnProfile(
            name="school",
            storage_type="object",
            label="School",
            non_missing_count=10,
            missing_count=0,
            missing_percent=0.0,
            unique_count=2,
            profile_type="categorical",
            categorical=CategoricalProfile(
                count=10,
                unique_count=2,
                top_value="alchemy",
                top_label="Alchemy",
                top_count=7,
                top_percent=70.0,
            ),
        ),
    ]

    with console.capture() as capture:
        show_column_profiles(
            profiles
        )

    output = capture.get()

    assert "Categorical Statistics" in output
    assert "school" in output
    assert "Alchemy" in output
    assert "70.0%" in output


def test_show_column_profiles_handles_datetime_and_other_profiles():

    profiles = [
        ColumnProfile(
            name="created_at",
            storage_type="datetime64[ns]",
            profile_type="datetime",
        ),
        ColumnProfile(
            name="payload",
            storage_type="object",
            profile_type="other",
        ),
    ]

    with console.capture() as capture:
        show_column_profiles(
            profiles
        )

    output = capture.get()

    assert "created_at" in output
    assert "datetime" in output
    assert "payload" in output


def test_show_column_profiles_handles_empty_profile_list():

    with console.capture() as capture:
        show_column_profiles(
            []
        )

    assert "No column profiles to display" in capture.get()


def test_show_column_profiles_handles_missing_subprofiles():

    profiles = [
        ColumnProfile(
            name="age",
            storage_type="float64",
            profile_type="numeric",
            numeric=None,
        ),
        ColumnProfile(
            name="school",
            storage_type="object",
            profile_type="categorical",
            categorical=None,
        ),
    ]

    with console.capture() as capture:
        show_column_profiles(
            profiles
        )

    output = capture.get()

    assert "age" in output
    assert "school" in output


def test_describe_command_reads_csv_successfully(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 0
    assert "Column Profiles" in result.output


def test_describe_command_output_includes_numeric_and_categorical_columns(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
        ],
    )

    assert "age" in result.output
    assert "school" in result.output
    assert "Numeric Statistics" in result.output
    assert "Categorical Statistics" in result.output


def test_describe_command_respects_columns_option(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
            "--columns",
            "school",
            "age",
        ],
    )

    assert result.exit_code == 0
    assert result.output.find(
        "school"
    ) < result.output.find(
        "age"
    )


def test_describe_command_handles_missing_requested_column(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
            "--columns",
            "missing",
        ],
    )

    assert result.exit_code == 1
    assert "Column not found: missing" in result.output


def test_describe_command_outputs_json(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )

    assert data[0]["name"] == "age"
    assert data[0]["profile_type"] == "numeric"


def test_describe_command_only_filters_profile_types(tmp_path):

    input_file = _write_csv(
        tmp_path
    )

    result = runner.invoke(
        app,
        [
            "describe",
            str(
                input_file
            ),
            "--only",
            "numeric",
        ],
    )

    assert result.exit_code == 0
    assert "age" in result.output
    assert "school" not in result.output


def _write_csv(
    tmp_path
):
    input_file = tmp_path / "describe.csv"
    pd.DataFrame(
        {
            "age": [
                10,
                20,
                None,
            ],
            "school": [
                "alchemy",
                "runes",
                "alchemy",
            ],
            "created_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-02",
                    "2020-01-03",
                ]
            ),
        }
    ).to_csv(
        input_file,
        index=False,
    )

    return input_file
