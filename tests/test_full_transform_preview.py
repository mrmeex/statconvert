from __future__ import annotations

from pathlib import Path

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.transformations import (
    parse_portable_recipe_text,
    preflight_transform_output,
    preview_full_transform,
)


def test_full_preview_reports_exact_impact_without_mutating_source(tmp_path: Path) -> None:
    dataframe = pd.DataFrame(
        {
            "old": ["1", "bad", "3"],
            "group": [1, 2, 9],
            "keep": [True, False, True],
            "unused": [4, 5, 6],
        }
    )
    dataset = Dataset(dataframe=dataframe.copy(deep=True))
    recipe = parse_portable_recipe_text(
        """version = 1
name = "Preview"
[[steps]]
type = "drop"
columns = ["unused"]
[[steps]]
type = "rename"
from = "old"
to = "value"
[[steps]]
type = "convert_type"
column = "value"
data_type = "float"
errors = "coerce"
[[steps]]
type = "derive"
column = "double"
expression = "value * 2"
[[steps]]
type = "filter"
expression = "keep"
[[steps]]
type = "recode"
column = "group"
mappings = [{ from = 1, to = "A" }, { from = 2, to = "B" }]
default = "Other"
"""
    )
    output = tmp_path / "missing" / "output.csv"
    preflight = preflight_transform_output(
        tmp_path / "input.csv",
        output,
        overwrite=False,
        create_dirs=True,
        write=False,
    )

    payload = preview_full_transform(
        dataset,
        recipe.bind(input_file="input.csv", output_file=str(output)),
        input_path=tmp_path / "input.csv",
        output_preflight=preflight,
        portable_recipe=recipe,
        sample_limit=1,
    ).to_dict()

    assert payload["valid"] is True
    assert payload["mode"] == "full_preview"
    assert payload["summary"]["rows_removed"] == 1
    assert payload["summary"]["columns_added"] == ["double"]
    assert payload["summary"]["columns_removed"] == ["unused"]
    assert payload["summary"]["columns_renamed"] == {"old": "value"}
    assert payload["steps"][2]["coercion_count"] == 1
    assert payload["steps"][5]["recode_mapped_count"] == 1
    assert payload["steps"][5]["recode_unmapped_count"] == 1
    assert payload["steps"][5]["recode_defaulted_count"] == 1
    assert payload["truncation"] == {
        "sample_limit": 1,
        "before_truncated": True,
        "after_truncated": True,
    }
    assert not output.parent.exists()
    pd.testing.assert_frame_equal(dataset.dataframe, dataframe)


def test_sidecar_preflight_reports_collision_without_writing(tmp_path: Path) -> None:
    output = tmp_path / "output.csv"
    sidecar = Path(f"{output}.statconvert-metadata.json")
    sidecar.write_text("unrelated", encoding="utf-8")

    result = preflight_transform_output(
        tmp_path / "input.csv",
        output,
        overwrite=False,
        create_dirs=False,
        write=False,
    ).to_dict()

    assert result["metadata_mode"] == "sidecar"
    assert result["overwrite_required"] is True
    assert result["sidecar_behavior"]["exists"] is True
    assert result["would_write"] is False
    assert sidecar.read_text(encoding="utf-8") == "unrelated"


def test_full_preview_reports_row_operation_impacts(tmp_path: Path) -> None:
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {"group": ["b", "a", "a", "b"], "value": [2, 1, 1, 1]}
        )
    )
    recipe = parse_portable_recipe_text(
        """version = 1
[[steps]]
type = "sort"
keys = [{ column = "group", order = "ascending", nulls = "last" }, { column = "value", order = "descending", nulls = "last" }]
[[steps]]
type = "distinct"
columns = ["group", "value"]
keep = "first"
[[steps]]
type = "row_number"
column = "row_id"
start = 10
step = 5
"""
    )

    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    preflight = preflight_transform_output(
        input_path,
        output_path,
        overwrite=False,
        create_dirs=False,
        write=False,
    )
    payload = preview_full_transform(
        dataset,
        recipe.bind(input_file=str(input_path), output_file=str(output_path)),
        input_path=input_path,
        output_preflight=preflight,
    ).to_dict()

    assert payload["summary"]["rows_removed"] == 1
    assert payload["summary"]["columns_added"] == ["row_id"]
    assert payload["steps"][0]["row_order_changed"] is True
    assert payload["steps"][0]["sort_keys"] == [
        {"column": "group", "order": "ascending", "nulls": "last"},
        {"column": "value", "order": "descending", "nulls": "last"},
    ]
    assert payload["steps"][1]["rows_removed"] == 1
    assert payload["steps"][1]["distinct_columns"] == ["group", "value"]
    assert payload["steps"][1]["distinct_keep"] == "first"
    assert payload["steps"][2]["row_number_column"] == "row_id"
    assert payload["steps"][2]["row_number_start"] == 10
    assert payload["steps"][2]["row_number_step"] == 5
    assert payload["sample"]["after"] == [
        {"group": "a", "value": 1, "row_id": 10},
        {"group": "b", "value": 2, "row_id": 15},
        {"group": "b", "value": 1, "row_id": 20},
    ]
