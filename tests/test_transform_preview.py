from __future__ import annotations

import json

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.transformations import (
    preview_transform_recipe,
    recipe_from_ordered_steps,
)


def _dataset() -> Dataset:
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "email": [
                    " A@EXAMPLE.COM ",
                    None,
                    "b@example.com",
                    "c@example.com",
                ],
                "age": [17, 18, 21, 30],
            }
        )
    )


def _recipe():
    return recipe_from_ordered_steps(
        input_file="input.csv",
        output_file="output.csv",
        steps=[
            {
                "type": "derive",
                "column": "email_clean",
                "expression": "lower(strip(email))",
            },
            {
                "type": "filter",
                "expression": "age >= 18",
            },
        ],
    )


def test_preview_is_bounded_json_safe_and_does_not_mutate_dataset():
    dataset = _dataset()
    original = dataset.dataframe.copy(deep=True)

    preview = preview_transform_recipe(dataset, _recipe(), limit=3)
    payload = preview.to_dict()

    assert preview.valid is True
    assert preview.rows_before == 4
    assert preview.sampled_rows == 3
    assert preview.preview_rows == 2
    assert preview.columns_before == ("email", "age")
    assert preview.columns_after == ("email", "age", "email_clean")
    assert [step.status for step in preview.steps] == ["applied", "applied"]
    assert preview.steps[0].created_columns == ("email_clean",)
    assert preview.steps[0].expression_metadata["functions"] == [
        "lower",
        "strip",
    ]
    assert len(preview.sample_output_rows) == 2
    assert json.loads(json.dumps(payload)) == payload
    pd.testing.assert_frame_equal(dataset.dataframe, original)


def test_preview_reports_planner_errors_without_mutating_or_writing():
    dataset = _dataset()
    recipe = recipe_from_ordered_steps(
        input_file="missing.csv",
        output_file="must-not-exist.csv",
        steps=[
            {"type": "drop", "columns": ["email"]},
            {
                "type": "derive",
                "column": "clean",
                "expression": "lower(email)",
            },
        ],
    )

    preview = preview_transform_recipe(dataset, recipe, limit=2)

    assert preview.valid is False
    assert preview.steps[1].status == "invalid"
    assert preview.errors[0]["step_index"] == 1
    assert preview.errors[0]["code"] == "transform_unknown_referenced_column"
    assert preview.columns_after == ("email", "age")


def test_preview_applies_text_helpers_and_keeps_json_safe_metadata():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "name": ["José", "Alice"],
                "code": ["AB-1", "xx"],
            }
        )
    )
    recipe = recipe_from_ordered_steps(
        input_file="input.csv",
        output_file="output.csv",
        steps=[
            {
                "type": "derive",
                "column": "label",
                "expression": "concat(remove_accents(name), ':', replace(code, '-', ''))",
            },
            {
                "type": "filter",
                "expression": "regex_match(code, '^AB-')",
            },
        ],
    )

    preview = preview_transform_recipe(dataset, recipe)
    payload = preview.to_dict()

    assert preview.valid is True
    assert preview.preview_rows == 1
    assert preview.sample_output_rows[0]["label"] == "Jose:AB1"
    assert preview.steps[0].expression_metadata["functions"] == [
        "concat",
        "remove_accents",
        "replace",
    ]
    assert json.loads(json.dumps(payload)) == payload


def test_preview_applies_conversion_helpers_and_keeps_json_safe_metadata():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "amount": ["10", "bad", "20.5"],
                "active": ["yes", "true", "no"],
            }
        )
    )
    recipe = recipe_from_ordered_steps(
        input_file="input.csv",
        output_file="output.csv",
        steps=[
            {
                "type": "derive",
                "column": "amount_number",
                "expression": "to_number(amount)",
            },
            {
                "type": "filter",
                "expression": "to_boolean(active) and amount_number >= 0",
            },
        ],
    )

    preview = preview_transform_recipe(dataset, recipe)
    payload = preview.to_dict()

    assert preview.valid is True
    assert preview.preview_rows == 1
    assert preview.sample_output_rows[0]["amount_number"] == 10
    assert preview.steps[0].expression_metadata["functions"] == ["to_number"]
    assert preview.steps[1].expression_metadata["functions"] == ["to_boolean"]
    assert json.loads(json.dumps(payload)) == payload


def test_preview_applies_date_helpers_and_serializes_dates_as_iso_text():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "opened": ["2026-07-27", "2026-08-02", "bad"],
            }
        )
    )
    recipe = recipe_from_ordered_steps(
        input_file="input.csv",
        output_file="output.csv",
        steps=[
            {
                "type": "derive",
                "column": "opened_date",
                "expression": "parse_date(opened, '%Y-%m-%d')",
            },
            {
                "type": "derive",
                "column": "due_date",
                "expression": "add_days(opened_date, 5)",
            },
            {
                "type": "filter",
                "expression": "weekday(opened_date) <= 5",
            },
        ],
    )

    preview = preview_transform_recipe(dataset, recipe)
    payload = preview.to_dict()

    assert preview.valid is True
    assert preview.preview_rows == 1
    assert preview.sample_output_rows[0]["opened_date"] == "2026-07-27"
    assert preview.sample_output_rows[0]["due_date"] == "2026-08-01"
    assert preview.steps[0].expression_metadata["functions"] == ["parse_date"]
    assert preview.steps[1].expression_metadata["functions"] == ["add_days"]
    assert preview.steps[2].expression_metadata["functions"] == ["weekday"]
    assert json.loads(json.dumps(payload)) == payload


def test_preview_applies_validation_helpers_and_keeps_json_safe_metadata():
    dataset = Dataset(
        dataframe=pd.DataFrame(
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
        )
    )
    recipe = recipe_from_ordered_steps(
        input_file="input.csv",
        output_file="output.csv",
        steps=[
            {
                "type": "derive",
                "column": "email_valid",
                "expression": "is_email(email)",
            },
            {
                "type": "filter",
                "expression": (
                    "email_valid and is_number(score) "
                    "and between(to_number(score), 0, 100) "
                    "and is_in(status, 'A', 'B') "
                    "and is_date(raw_date, '%Y-%m-%d')"
                ),
            },
        ],
    )

    preview = preview_transform_recipe(dataset, recipe)
    payload = preview.to_dict()

    assert preview.valid is True
    assert preview.preview_rows == 2
    assert [row["score"] for row in preview.sample_output_rows] == ["10", "50"]
    assert preview.steps[0].expression_metadata["functions"] == ["is_email"]
    assert preview.steps[1].expression_metadata["functions"] == [
        "is_number",
        "between",
        "to_number",
        "is_in",
        "is_date",
    ]
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.parametrize("limit", [0, -1, True])
def test_preview_limit_must_be_positive_integer(limit):
    with pytest.raises(ValueError, match="positive integer"):
        preview_transform_recipe(_dataset(), _recipe(), limit=limit)
