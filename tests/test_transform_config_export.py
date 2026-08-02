from __future__ import annotations

import tomllib

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config


runner = CliRunner()


def test_transform_write_config_exports_canonical_deterministic_steps(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    pd.DataFrame(
        {"email": [" A@EXAMPLE.COM "], "age": [18], "status": ["A"]}
    ).to_csv(source, index=False)
    command = [
        "transform",
        str(source),
        str(output),
        "--derive",
        "email_clean=lower(strip(email))",
        "--filter-expression",
        "age >= 18",
        "--recode",
        "status:A=Active",
    ]

    first_result = runner.invoke(app, [*command, "--write-config", str(first)])
    second_result = runner.invoke(app, [*command, "--write-config", str(second)])

    assert first_result.exit_code == 0, first_result.output
    assert second_result.exit_code == 0, second_result.output
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    text = first.read_text(encoding="utf-8")
    assert text.count("[[steps]]") == 3
    assert "derive =" not in text
    assert "filter_expression =" not in text
    assert tomllib.loads(text)["steps"][2]["map"] == {"A": "Active"}

    validate_result = runner.invoke(app, ["config", "validate", str(first)])
    run_result = runner.invoke(app, ["config", "run", str(first)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    assert pd.read_csv(output).to_dict("list") == {
        "email": [" A@EXAMPLE.COM "],
        "age": [18],
        "status": ["Active"],
        "email_clean": ["a@example.com"],
    }


def test_legacy_transform_config_remains_supported(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config = tmp_path / "legacy.toml"
    pd.DataFrame({"value": [1, -1]}).to_csv(source, index=False)
    config.write_text(
        "\n".join(
            (
                'command = "transform"',
                f'input = "{source.as_posix()}"',
                f'output = "{output.as_posix()}"',
                'filter = ["value,gte,0"]',
                "",
            )
        ),
        encoding="utf-8",
    )

    model = load_config(config)
    result = runner.invoke(app, ["config", "run", str(config)])

    assert "steps" not in model.options
    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["value"].tolist() == [1]
