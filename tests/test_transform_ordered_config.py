from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config, validate_config
from statconvert.exceptions import ConfigError


runner = CliRunner()


def _write_ordered_config(
    path: Path,
    source: Path,
    output: Path,
    steps: str,
) -> None:
    path.write_text(
        "\n".join(
            (
                'command = "transform"',
                f'input = "{source.as_posix()}"',
                f'output = "{output.as_posix()}"',
                "overwrite = true",
                "",
                steps.strip(),
                "",
            )
        ),
        encoding="utf-8",
    )


def test_ordered_config_import_preserves_all_step_types(tmp_path):
    path = tmp_path / "recipe.toml"
    _write_ordered_config(
        path,
        tmp_path / "input.csv",
        tmp_path / "output.csv",
        """
[[steps]]
type = "select"
columns = ["id", "old", "unused", "status"]

[[steps]]
type = "drop"
columns = ["unused"]

[[steps]]
type = "rename"
[steps.map]
old = "value"

[[steps]]
type = "convert_type"
column = "value"
data_type = "integer"

[[steps]]
type = "derive"
column = "value_plus_one"
expression = "value + 1"

[[steps]]
type = "filter"
expression = "value_plus_one >= 2"

[[steps]]
type = "recode"
column = "status"
default = "Unknown"
update_value_labels = false
[steps.map]
A = "Active"

[[steps]]
type = "sort"
keys = [{ column = "value", order = "descending", nulls = "last" }]

[[steps]]
type = "distinct"
columns = ["status"]
keep = "last"

[[steps]]
type = "row_number"
column = "row_id"
start = 10
step = 2
""",
    )

    config = load_config(path)

    assert [step["type"] for step in config.options["steps"]] == [
        "select",
        "drop",
        "rename",
        "convert_type",
        "derive",
        "filter",
        "recode",
        "sort",
        "distinct",
        "row_number",
    ]
    assert config.options["steps"][2]["map"] == {"old": "value"}
    assert config.options["steps"][6]["map"] == {"A": "Active"}
    assert config.options["steps"][7]["keys"] == [
        {"column": "value", "order": "descending", "nulls": "last"}
    ]
    assert config.options["steps"][8]["keep"] == "last"
    assert config.options["steps"][9]["start"] == 10


def test_ordered_config_executes_existing_transformations_in_exact_order(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config = tmp_path / "recipe.toml"
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "old_age": ["17", "18", "25"],
            "country": ["nl", " nl ", "be"],
            "status": ["A", "I", "X"],
            "unused": ["x", "y", "z"],
        }
    ).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        """
[[steps]]
type = "select"
columns = ["id", "old_age", "country", "status", "unused"]

[[steps]]
type = "drop"
columns = ["unused"]

[[steps]]
type = "rename"
[steps.map]
old_age = "age"

[[steps]]
type = "convert_type"
column = "age"
data_type = "integer"

[[steps]]
type = "derive"
column = "country_clean"
expression = "normalize_code(country)"

[[steps]]
type = "filter"
expression = "age >= 18 and country_clean == 'NL'"

[[steps]]
type = "recode"
column = "status"
[steps.map]
I = "Inactive"
""",
    )

    validate_result = runner.invoke(app, ["config", "validate", str(config)])
    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    assert "Ordered recipe" in run_result.output
    assert pd.read_csv(output).to_dict("list") == {
        "id": [2],
        "age": [18],
        "country": [" nl "],
        "status": ["Inactive"],
        "country_clean": ["NL"],
    }


def test_derive_then_drop_source_works_but_drop_then_derive_fails(tmp_path):
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [10, 20], "value": [1, 2]}).to_csv(source, index=False)

    works_output = tmp_path / "works.csv"
    works = tmp_path / "works.toml"
    _write_ordered_config(
        works,
        source,
        works_output,
        """
[[steps]]
type = "derive"
column = "next"
expression = "value + 1"

[[steps]]
type = "drop"
columns = ["value"]
""",
    )
    works_result = runner.invoke(app, ["config", "run", str(works)])

    fails_output = tmp_path / "fails.csv"
    fails = tmp_path / "fails.toml"
    _write_ordered_config(
        fails,
        source,
        fails_output,
        """
[[steps]]
type = "drop"
columns = ["value"]

[[steps]]
type = "derive"
column = "next"
expression = "value + 1"
""",
    )
    fails_result = runner.invoke(app, ["config", "run", str(fails)])
    fails_validate = runner.invoke(app, ["config", "validate", str(fails)])

    assert works_result.exit_code == 0, works_result.output
    assert pd.read_csv(works_output).to_dict("list") == {
        "id": [10, 20],
        "next": [2, 3],
    }
    assert fails_result.exit_code == 1
    assert fails_validate.exit_code == 1
    assert "step 1 (derive)" in " ".join(fails_result.output.split())
    assert "transform_unknown_referenced_column" in fails_validate.output
    assert "value" in fails_result.output
    assert not fails_output.exists()


def test_ordered_config_executes_new_text_helpers(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config = tmp_path / "text-helpers.toml"
    pd.DataFrame(
        {
            "name": ["José", "Alice"],
            "code": ["AB-1", "xx"],
        }
    ).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        """
[[steps]]
type = "derive"
column = "label"
expression = "concat(remove_accents(name), ':', replace(code, '-', ''))"

[[steps]]
type = "filter"
expression = "regex_match(code, '^AB-')"
""",
    )

    validate_result = runner.invoke(app, ["config", "validate", str(config)])
    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    assert pd.read_csv(output)["label"].tolist() == ["Jose:AB1"]


def test_ordered_config_executes_conversion_helpers(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config = tmp_path / "conversion-helpers.toml"
    pd.DataFrame(
        {
            "amount": ["10", "bad", "20.5"],
            "active": ["yes", "true", "no"],
        }
    ).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        """
[[steps]]
type = "derive"
column = "amount_number"
expression = "to_number(amount)"

[[steps]]
type = "filter"
expression = "to_boolean(active) and amount_number >= 10"
""",
    )

    validate_result = runner.invoke(app, ["config", "validate", str(config)])
    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    written = pd.read_csv(output)
    assert written["amount"].tolist() == [10]
    assert written["amount_number"].tolist() == [10]


def test_ordered_config_executes_date_helpers(tmp_path):
    source = tmp_path / "dates.csv"
    output = tmp_path / "dates-output.csv"
    config = tmp_path / "date-helpers.toml"
    pd.DataFrame(
        {
            "opened": ["2026-07-27", "2026-08-02", "bad"],
        }
    ).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        """
[[steps]]
type = "derive"
column = "opened_date"
expression = "parse_date(opened, '%Y-%m-%d')"

[[steps]]
type = "derive"
column = "due_date"
expression = "add_days(opened_date, 5)"

[[steps]]
type = "derive"
column = "due_text"
expression = "format_date(due_date, '%Y/%m/%d')"

[[steps]]
type = "filter"
expression = "weekday(opened_date) <= 5"
""",
    )

    validate_result = runner.invoke(app, ["config", "validate", str(config)])
    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    written = pd.read_csv(output)
    assert written["opened"].tolist() == ["2026-07-27"]
    assert written["due_text"].tolist() == ["2026/08/01"]


def test_ordered_config_executes_validation_helpers(tmp_path):
    source = tmp_path / "validation.csv"
    output = tmp_path / "validation-output.csv"
    config = tmp_path / "validation-helpers.toml"
    pd.DataFrame(
        {
            "score": ["10", "bad", "101", "50"],
            "status": ["A", "A", "X", "B"],
            "raw_date": ["2026-07-30", "bad", "2026-08-01", "2024-02-29"],
        }
    ).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        """
[[steps]]
type = "derive"
column = "score_valid"
expression = "is_number(score)"

[[steps]]
type = "filter"
expression = "score_valid and between(to_number(score), 0, 100) and is_in(status, 'A', 'B') and not_in(status, 'X') and is_date(raw_date, '%Y-%m-%d')"
""",
    )

    validate_result = runner.invoke(app, ["config", "validate", str(config)])
    run_result = runner.invoke(app, ["config", "run", str(config)])

    assert validate_result.exit_code == 0, validate_result.output
    assert run_result.exit_code == 0, run_result.output
    written = pd.read_csv(output)
    assert written["score"].tolist() == [10, 50]
    assert written["score_valid"].tolist() == [True, True]


@pytest.mark.parametrize(
    ("expression", "expected_exit"),
    [("new + 1", 0), ("old + 1", 1)],
)
def test_rename_then_derive_observes_new_name(
    tmp_path,
    expression,
    expected_exit,
):
    source = tmp_path / "input.csv"
    output = tmp_path / f"output-{expected_exit}.csv"
    config = tmp_path / f"recipe-{expected_exit}.toml"
    pd.DataFrame({"old": [1]}).to_csv(source, index=False)
    _write_ordered_config(
        config,
        source,
        output,
        f"""
[[steps]]
type = "rename"
[steps.map]
old = "new"

[[steps]]
type = "derive"
column = "result"
expression = "{expression}"
""",
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == expected_exit
    assert output.exists() is (expected_exit == 0)


def test_mixed_ordered_and_legacy_transform_fields_are_rejected():
    with pytest.raises(ConfigError, match=r"cannot mix ordered \[\[steps\]\]"):
        validate_config(
            {
                "command": "transform",
                "input": "input.csv",
                "output": "output.csv",
                "derive": ["clean=strip(value)"],
                "steps": [
                    {
                        "type": "derive",
                        "column": "clean",
                        "expression": "strip(value)",
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"type": "unknown"}, "unsupported type"),
        ({"type": "derive", "column": "clean"}, "missing required field"),
        (
            {"type": "derive", "column": "clean", "expression": "open('x')"},
            "unknown_function",
        ),
        (
            {"type": "convert_type", "column": "value", "data_type": "uuid"},
            "transform_unsupported_type",
        ),
        (
            {"type": "recode", "column": "value", "map": {}},
            "transform_invalid_recode_map",
        ),
    ],
)
def test_ordered_config_structural_errors_are_step_scoped(step, message):
    with pytest.raises(ConfigError, match=message):
        validate_config(
            {
                "command": "transform",
                "input": "input.csv",
                "output": "output.csv",
                "steps": [step],
            }
        )


def test_ordered_toml_is_standard_toml(tmp_path):
    config = tmp_path / "recipe.toml"
    _write_ordered_config(
        config,
        tmp_path / "input.csv",
        tmp_path / "output.csv",
        """
[[steps]]
type = "recode"
column = "status"
[steps.map]
"1" = "Active"
""",
    )

    assert tomllib.loads(config.read_text(encoding="utf-8"))["steps"][0][
        "map"
    ] == {"1": "Active"}
