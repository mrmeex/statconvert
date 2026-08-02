from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config


runner = CliRunner()


def _source(path: Path) -> None:
    pd.DataFrame(
        {
            "name": ["  New\t York  ", "Clean", None],
            "code": [" a ", "i", None],
            "note": ["", "keep", " \t "],
            "income": [None, 10, 20],
            "email": ["first@example.com", " \t ", None],
            "keep": [True, True, False],
        }
    ).to_csv(path, index=False)


def test_transform_cli_derive_helpers_and_filter_expression(tmp_path):
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
            "name_clean=normalize_whitespace(name)",
            "--derive",
            "code_clean=normalize_code(code)",
            "--derive",
            "note_clean=null_if_empty(note)",
            "--derive",
            "income_clean=default_if_missing(income, 0)",
            "--filter-expression",
            "not_null(null_if_empty(email))",
        ],
    )

    assert result.exit_code == 0, result.output
    written = pd.read_csv(output)
    assert written["name_clean"].tolist() == ["New York"]
    assert written["code_clean"].tolist() == ["A"]
    assert pd.isna(written["note_clean"].iloc[0])
    assert written["income_clean"].tolist() == [0.0]


def test_transform_cli_helpers_work_through_compatibility_config(tmp_path):
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
            "code_clean=normalize_code(code)",
            "--filter-expression",
            "not_null(null_if_empty(email))",
            "--write-config",
            str(config),
        ],
    )

    assert write_result.exit_code == 0, write_result.output
    model = load_config(config)
    assert [step["type"] for step in model.options["steps"]] == [
        "derive",
        "filter",
    ]
    assert model.options["steps"][0]["expression"] == "normalize_code(code)"

    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert run_result.exit_code == 0, run_result.output
    assert pd.read_csv(output)["code_clean"].tolist() == ["A"]


def test_transform_cli_invalid_helper_fails_without_output(tmp_path):
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
            "bad=normalize_code(income)",
        ],
    )

    assert result.exit_code == 1
    assert "string-like values" in " ".join(result.output.split())
    assert not output.exists()
