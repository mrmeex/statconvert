from __future__ import annotations

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.transformations import (
    compile_transform_recipe,
    parse_portable_recipe_text,
)
from statconvert.transformations.planning import plan_transform_recipe


def _apply(text: str, dataframe: pd.DataFrame) -> Dataset:
    portable = parse_portable_recipe_text(text)
    recipe = portable.bind(input_file="input.csv", output_file="output.csv")
    pipeline = compile_transform_recipe(recipe, list(dataframe.columns))
    return pipeline.apply(Dataset(dataframe=dataframe))


def test_sort_distinct_row_number_interleave_executes_in_file_order() -> None:
    result = _apply(
        """version = 1
[[steps]]
type = "sort"
keys = [{ column = "group", order = "ascending", nulls = "last" }, { column = "score", order = "descending", nulls = "last" }]
[[steps]]
type = "distinct"
columns = ["group"]
keep = "first"
[[steps]]
type = "row_number"
column = "row_id"
start = 10
step = 5
""",
        pd.DataFrame(
            {"group": ["B", "A", "A", "B"], "score": [1, 2, 3, 4]}
        ),
    )

    assert result.dataframe.to_dict("records") == [
        {"group": "A", "score": 3, "row_id": 10},
        {"group": "B", "score": 4, "row_id": 15},
    ]


def test_rename_then_sort_filter_then_row_number_and_recode_then_sort() -> None:
    result = _apply(
        """version = 1
[[steps]]
type = "rename"
from = "old"
to = "score"
[[steps]]
type = "filter"
expression = "keep"
[[steps]]
type = "row_number"
column = "row_id"
[[steps]]
type = "recode"
column = "group"
mappings = [{ from = "b", to = "B" }, { from = "a", to = "A" }]
[[steps]]
type = "sort"
keys = [{ column = "group", order = "ascending", nulls = "last" }, { column = "score", order = "descending", nulls = "last" }]
""",
        pd.DataFrame(
            {
                "old": [1, 3, 2],
                "group": ["b", "a", "a"],
                "keep": [True, True, False],
            }
        ),
    )

    assert result.dataframe.to_dict("records") == [
        {"score": 3, "group": "A", "keep": True, "row_id": 2},
        {"score": 1, "group": "B", "keep": True, "row_id": 1},
    ]


def test_planner_projects_new_column_and_rejects_missing_keys() -> None:
    portable = parse_portable_recipe_text(
        """version = 1
[[steps]]
type = "sort"
keys = [{ column = "missing", order = "ascending", nulls = "last" }]
[[steps]]
type = "row_number"
column = "row_id"
"""
    )
    plan = plan_transform_recipe(
        portable.bind(input_file="input.csv", output_file="output.csv"),
        ["value"],
    )

    assert plan.valid is False
    assert plan.errors[0].step_index == 0
    assert plan.errors[0].field == "keys"
    assert plan.steps[1].output_columns == ("value", "row_id")
