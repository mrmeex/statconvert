from __future__ import annotations

import json
from pathlib import Path
import tomllib

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def _source(path: Path) -> None:
    pd.DataFrame({"id": [1, 2, 3], "keep": [True, False, True]}).to_csv(
        path,
        index=False,
    )


def _recipe(path: Path) -> None:
    path.write_text(
        """version = 1
name = "Keep rows"
[[steps]]
type = "filter"
expression = "keep"
""",
        encoding="utf-8",
    )


def test_transform_runs_portable_recipe(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    recipe = tmp_path / "recipe.toml"
    _source(source)
    _recipe(recipe)

    result = runner.invoke(
        app,
        ["transform", str(source), str(output), "--recipe", str(recipe)],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["id"].tolist() == [1, 3]


def test_recipe_rejects_direct_operations(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    recipe = tmp_path / "recipe.toml"
    _source(source)
    _recipe(recipe)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(tmp_path / "output.csv"),
            "--recipe",
            str(recipe),
            "--drop",
            "keep",
        ],
    )

    assert result.exit_code == 1
    assert "cannot be combined" in result.output


def test_save_recipe_writes_only_recipe_and_requires_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "must-not-exist.csv"
    recipe = tmp_path / "saved.toml"
    _source(source)

    args = [
        "transform",
        str(source),
        str(output),
        "--filter-expression",
        "keep",
        "--save-recipe",
        str(recipe),
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    replaced = runner.invoke(app, [*args, "--overwrite-recipe"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 1
    assert "overwrite-recipe" in second.output
    assert replaced.exit_code == 0, replaced.output
    assert recipe.is_file()
    assert not output.exists()
    assert not Path(f"{output}.statconvert-metadata.json").exists()


def test_preview_json_is_parseable_bounded_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "missing" / "output.csv"
    recipe = tmp_path / "recipe.toml"
    _source(source)
    _recipe(recipe)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--recipe",
            str(recipe),
            "--preview",
            "--json",
            "--create-dirs",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["mode"] == "full_preview"
    assert payload["output"]["would_write"] is False
    assert payload["summary"]["rows_removed"] == 1
    assert "[bold" not in result.output
    assert not output.parent.exists()


def test_validate_template_and_identity_safety(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    recipe = tmp_path / "recipe.toml"
    template = tmp_path / "template.toml"
    _source(source)
    _recipe(recipe)

    syntax = runner.invoke(
        app,
        ["transform-recipe", "validate", str(recipe), "--json"],
    )
    bound = runner.invoke(
        app,
        [
            "transform-recipe",
            "validate",
            str(recipe),
            "--input",
            str(source),
            "--json",
        ],
    )
    stdout_template = runner.invoke(app, ["transform-recipe", "template"])
    file_template = runner.invoke(
        app,
        ["transform-recipe", "template", "--output", str(template)],
    )
    identity = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(source),
            "--recipe",
            str(recipe),
            "--overwrite",
        ],
    )

    assert json.loads(syntax.output)["mode"] == "syntax"
    bound_payload = json.loads(bound.output)
    assert bound_payload["mode"] == "input_bound"
    assert bound_payload["valid"] is True
    assert bound_payload["issues"] == []
    assert stdout_template.output.startswith("version = 1\n")
    assert file_template.exit_code == 0
    assert template.is_file()
    assert identity.exit_code == 1
    assert "must differ" in identity.output
    assert pd.read_csv(source)["id"].tolist() == [1, 2, 3]


def test_direct_row_operations_use_fixed_order_and_save_recipe(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    recipe = tmp_path / "saved.toml"
    pd.DataFrame(
        {"group": ["b", "a", "a", "b"], "value": [2, 1, 1, 1]}
    ).to_csv(source, index=False)
    args = [
        "transform",
        str(source),
        str(output),
        "--sort",
        "group:asc",
        "--sort",
        "value:desc",
        "--distinct",
        "group",
        "--distinct",
        "value",
        "--distinct-keep",
        "first",
        "--row-number",
        "row_id",
        "--row-number-start",
        "10",
        "--row-number-step",
        "5",
    ]

    result = runner.invoke(app, args)
    saved = runner.invoke(app, [*args, "--save-recipe", str(recipe)])

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output).to_dict("records") == [
        {"group": "a", "value": 1, "row_id": 10},
        {"group": "b", "value": 2, "row_id": 15},
        {"group": "b", "value": 1, "row_id": 20},
    ]
    assert saved.exit_code == 0, saved.output
    parsed = tomllib.loads(recipe.read_text(encoding="utf-8"))
    assert [step["type"] for step in parsed["steps"]] == [
        "sort",
        "distinct",
        "row_number",
    ]


def test_row_operation_cli_modifiers_require_their_operation(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    _source(source)

    result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(tmp_path / "output.csv"),
            "--row-number-step",
            "2",
        ],
    )

    assert result.exit_code == 1
    assert "--row-number" in result.output
