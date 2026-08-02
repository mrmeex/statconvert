from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def _source(path: Path):
    pd.DataFrame(
        {
            "age": [17, 18, 21, 30],
            "country": ["NL", "NL", "BE", "NL"],
            "active": [True, False, True, None],
        }
    ).to_csv(path, index=False)


def test_filter_expression_cli_keeps_expected_rows(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    _source(source)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--filter-expression",
            "age >= 18 and country == 'NL'",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["age"].tolist() == [18, 30]


def test_filter_expression_can_reference_derived_column(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    _source(source)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--derive",
            "country_clean=lower(country)",
            "--filter-expression",
            "country_clean == 'nl' and age >= 18",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["age"].tolist() == [18, 30]


def test_filter_expression_missing_mask_values_are_false(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    _source(source)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--filter-expression",
            "active",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["age"].tolist() == [17, 21]


def test_filter_expression_rejects_invalid_and_non_boolean_expressions(tmp_path):
    source = tmp_path / "input.csv"
    _source(source)

    for index, (expression, message) in enumerate(
        [
            ("open('x')", "Unknown expression function 'open'"),
            ("lower(country)", "boolean"),
        ]
    ):
        output = tmp_path / f"output-{index}.csv"
        result = runner.invoke(
            app,
            [
                "transform",
                str(source),
                str(output),
                "--filter-expression",
                expression,
            ],
        )
        assert result.exit_code == 1
        assert message in result.output
        assert not output.exists()


def test_legacy_filter_syntax_remains_unchanged_with_expression_support(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    _source(source)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--filter",
            "age,gte,18",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["age"].tolist() == [18, 21, 30]


def test_full_transform_order_places_derive_before_both_filter_forms_and_recode(
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    pd.DataFrame(
        {
            "old_age": ["17", "18", "21"],
            "status": ["A", "I", "A"],
            "remove": [1, 2, 3],
        }
    ).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--select",
            "old_age",
            "--select",
            "status",
            "--select",
            "remove",
            "--drop",
            "remove",
            "--rename",
            "old_age=age",
            "--type",
            "age=int",
            "--derive",
            "age_group=if_else(age >= 18, 'adult', 'minor')",
            "--filter",
            "age,gte,18",
            "--filter-expression",
            "age_group == 'adult'",
            "--recode",
            "status:A=Active,I=Inactive",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written.columns.tolist() == ["age", "status", "age_group"]
    assert written.to_dict("list") == {
        "age": [18, 21],
        "status": ["Inactive", "Active"],
        "age_group": ["adult", "adult"],
    }
