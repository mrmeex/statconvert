from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.transformations.planning import plan_transform_recipe
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)


runner = CliRunner()


def _recipe(*steps: TransformStep) -> TransformRecipe:
    return TransformRecipe("input.csv", "output.csv", steps)


def _source(path: Path) -> None:
    pd.DataFrame(
        {
            "status": [" a ", "i", "x"],
            "keep": [True, False, True],
        }
    ).to_csv(path, index=False)


def test_recode_plan_reports_conservative_execution_metadata():
    step = TransformStep(
        TransformStepType.RECODE,
        {
            "column": "status",
            "map": {"A": "Active", "I": "Inactive"},
            "default": "Unknown",
            "update_value_labels": False,
        },
    )

    planned = plan_transform_recipe(_recipe(step), ["status"]).steps[0]
    payload = planned.to_dict()

    assert planned.referenced_columns == ("status",)
    assert planned.recode_map_keys == ("A", "I")
    assert planned.recode_map_count == 2
    assert planned.recode_uses_default is True
    assert planned.recode_default == "Unknown"
    assert planned.recode_updates_value_labels is False
    assert planned.recode_affects_missing_values is False
    assert planned.row_local is True
    assert planned.previewable is True
    assert payload["recode_map_keys"] == ["A", "I"]


def test_recode_plan_without_default_reports_preserve_unmapped_behavior():
    step = TransformStep(
        TransformStepType.RECODE,
        {"column": "status", "map": {"A": "Active"}},
    )

    planned = plan_transform_recipe(_recipe(step), ["status"]).steps[0]

    assert planned.recode_uses_default is False
    assert planned.recode_default is None
    assert planned.recode_updates_value_labels is True


def test_recode_after_drop_fails_with_structured_unknown_column():
    recipe = _recipe(
        TransformStep(TransformStepType.DROP, {"columns": ["status"]}),
        TransformStep(
            TransformStepType.RECODE,
            {"column": "status", "map": {"A": "Active"}},
        ),
    )

    plan = plan_transform_recipe(recipe, ["status", "keep"])

    assert plan.valid is False
    assert plan.steps[1].errors[0].code == "transform_unknown_column"
    assert plan.steps[1].errors[0].referenced_column == "status"


def test_cli_recode_runs_after_derive_and_reports_recoded_column(tmp_path):
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
            "status_code=normalize_code(status)",
            "--recode",
            "status_code:A=Active,I=Inactive",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["status_code"].tolist() == [
        "Active",
        "Inactive",
        "X",
    ]
    assert "Recoded columns" in result.output
    assert "Derived columns" in result.output


def test_cli_recode_runs_after_expression_filter(tmp_path):
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
            "keep",
            "--recode",
            "status:a=Active,x=Other",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output)["status"].tolist() == [" a ", "Other"]
