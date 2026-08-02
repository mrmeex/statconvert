from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config


runner = CliRunner()


def _source(path: Path):
    pd.DataFrame(
        {
            "email": [" Alice@EXAMPLE.COM ", None, "bob@example.com"],
            "country": ["nl", "NL", "be"],
            "age": [17, 18, 21],
            "status": ["A", "I", "A"],
        }
    ).to_csv(path, index=False)


def test_transform_cli_derives_one_column(tmp_path):
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
            "email_clean=lower(strip(email))",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written.columns.tolist()[-1] == "email_clean"
    assert written["email_clean"].iloc[0] == "alice@example.com"
    assert pd.isna(written["email_clean"].iloc[1])


def test_transform_cli_multiple_derives_use_supplied_order(tmp_path):
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
            "country_clean=upper(strip(country))",
            "--derive",
            "is_nl=country_clean == 'NL'",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written.columns.tolist()[-2:] == ["country_clean", "is_nl"]
    assert written["is_nl"].tolist() == [True, True, False]


def test_transform_cli_if_else_derives_conditional_values(tmp_path):
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
            "age_group=if_else(age >= 18, 'adult', 'minor')",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["age_group"].tolist() == [
        "minor",
        "adult",
        "adult",
    ]


def test_transform_cli_text_helper_derive_and_regex_filter(tmp_path):
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
            "label=concat(remove_accents(country), ':', substring(status, 0, 1))",
            "--filter-expression",
            "regex_match(label, '^nl:')",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["label"].tolist() == ["nl:A"]


def test_transform_cli_conversion_helper_derive_and_filter(tmp_path):
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
            "age_text=to_string(age)",
            "--derive",
            "age_number=to_number(age_text)",
            "--filter-expression",
            "to_boolean(status == 'I') and age_number >= 18",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written["age_text"].tolist() == [18]
    assert written["age_number"].tolist() == [18]


def test_transform_cli_date_helpers_derive_and_filter(tmp_path):
    source = tmp_path / "dates.csv"
    output = tmp_path / "dates-output.csv"
    pd.DataFrame(
        {
            "opened": ["2026-07-27", "2026-08-02", "bad"],
            "closed": ["2026-08-01", "2026-08-12", "2026-08-10"],
        }
    ).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--derive",
            "opened_date=parse_date(opened, '%Y-%m-%d')",
            "--derive",
            "closed_date=parse_date(closed, '%Y-%m-%d')",
            "--derive",
            "elapsed=date_diff(opened_date, closed_date)",
            "--derive",
            "due=add_days(opened_date, 5)",
            "--derive",
            "due_text=format_date(due, '%Y/%m/%d')",
            "--filter-expression",
            "year(opened_date) == 2026 and month(opened_date) == 7",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written["elapsed"].tolist() == [5]
    assert written["due_text"].tolist() == ["2026/08/01"]


def test_transform_cli_validation_helpers_derive_and_filter(tmp_path):
    source = tmp_path / "validation.csv"
    output = tmp_path / "validation-output.csv"
    pd.DataFrame(
        {
            "score": ["10", "bad", "101", "50"],
            "status": ["A", "A", "X", "B"],
            "email": [
                "a@example.com",
                "bad",
                "x@example.com",
                "b@example.com",
            ],
            "raw_date": ["2026-07-30", "bad", "2026-08-01", "2024-02-29"],
        }
    ).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--derive",
            "email_valid=is_email(email)",
            "--derive",
            "score_valid=is_number(score)",
            "--filter-expression",
            (
                "email_valid and score_valid "
                "and between(to_number(score), 0, 100) "
                "and is_in(status, 'A', 'B') "
                "and not_in(status, 'X') "
                "and is_date(raw_date, '%Y-%m-%d')"
            ),
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written["score"].tolist() == [10, 50]
    assert written["email_valid"].tolist() == [True, True]
    assert written["score_valid"].tolist() == [True, True]


def test_transform_cli_reports_unknown_invalid_and_colliding_derives(tmp_path):
    source = tmp_path / "input.csv"
    _source(source)

    cases = [
        ("clean=lower(missing)", "Unknown column 'missing'"),
        ("bad=open('file')", "Unknown expression function 'open'"),
        ("email=lower(email)", "Choose a new derived-column name."),
    ]
    for index, (derive, message) in enumerate(cases):
        output = tmp_path / f"output-{index}.csv"
        result = runner.invoke(
            app,
            [
                "transform",
                str(source),
                str(output),
                "--derive",
                derive,
            ],
        )
        assert result.exit_code == 1
        assert message in " ".join(result.output.split())
        assert not output.exists()


def test_transform_cli_derive_and_filter_expression_write_config_and_run(
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config = tmp_path / "transform.toml"
    _source(source)

    write_result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--derive",
            "country_clean=upper(strip(country))",
            "--filter-expression",
            "age >= 18 and country_clean == 'NL'",
            "--write-config",
            str(config),
        ],
    )

    assert write_result.exit_code == 0, write_result.output
    assert not output.exists()
    model = load_config(config)
    assert model.options["steps"] == [
        {
            "type": "derive",
            "column": "country_clean",
            "expression": "upper(strip(country))",
        },
        {
            "type": "filter",
            "expression": "age >= 18 and country_clean == 'NL'",
            "reset_index": True,
        },
    ]

    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert run_result.exit_code == 0, run_result.output
    written = pd.read_csv(output)
    assert written["age"].tolist() == [18]
    assert written["country_clean"].tolist() == ["NL"]
