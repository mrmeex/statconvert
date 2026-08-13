from __future__ import annotations

import math
from pathlib import Path
import tomllib

import pytest

from statconvert.transformations import (
    TransformationError,
    parse_portable_recipe,
    parse_portable_recipe_text,
    portable_recipe_to_toml,
    save_portable_recipe,
)


MINIMAL = """version = 1

[[steps]]
type = "select"
columns = ["id"]
"""


def test_minimal_recipe_normalizes_defaults_and_contains_no_paths() -> None:
    recipe = parse_portable_recipe_text(MINIMAL)

    assert recipe.to_dict() == {
        "version": 1,
        "steps": [
            {"type": "select", "columns": ["id"], "ignore_missing": False}
        ],
    }
    assert "input" not in portable_recipe_to_toml(recipe)
    assert "output" not in portable_recipe_to_toml(recipe)


def test_all_current_operations_parse_in_authored_order() -> None:
    recipe = parse_portable_recipe_text(
        """version = 1
name = "All operations"

[[steps]]
type = "select"
columns = ["id", "old", "status"]

[[steps]]
type = "drop"
columns = ["id"]

[[steps]]
type = "rename"
from = "old"
to = "value"

[[steps]]
type = "convert_type"
column = "value"
data_type = "float"

[[steps]]
type = "derive"
column = "double"
expression = "value * 2"

[[steps]]
type = "filter"
expression = "double >= 2"

[[steps]]
type = "recode"
column = "status"
mappings = [{ from = 1, to = "Control" }, { from = "1", to = "Text" }]
"""
    )

    assert [step["type"] for step in recipe.to_dict()["steps"]] == [
        "select",
        "drop",
        "rename",
        "convert_type",
        "derive",
        "filter",
        "recode",
    ]
    mappings = recipe.to_dict()["steps"][-1]["mappings"]
    assert mappings == [{"from": 1, "to": "Control"}, {"from": "1", "to": "Text"}]


@pytest.mark.parametrize(
    "text, match",
    [
        ("version = 2\n[[steps]]\ntype='select'\ncolumns=['id']\n", "version"),
        ("version = 1\ninput='data.csv'\n[[steps]]\ntype='select'\ncolumns=['id']\n", "unknown top-level"),
        ("version = 1\n", "at least one"),
        ("version = 1\n[[steps]]\ntype='select'\ncolumns=['id']\npython='x'\n", "unknown field"),
        ("version = 1\n[[steps]]\ntype='future'\n", "unsupported type"),
    ],
)
def test_invalid_or_unsupported_recipe_shape_is_rejected(text: str, match: str) -> None:
    with pytest.raises(TransformationError, match=match):
        parse_portable_recipe_text(text)


def test_display_text_is_bounded() -> None:
    text = f"version = 1\nname = {'x' * 201!r}\n[[steps]]\ntype='select'\ncolumns=['id']\n"
    with pytest.raises(TransformationError, match="200"):
        parse_portable_recipe_text(text)


def test_typed_recode_rejects_ambiguous_duplicates() -> None:
    text = """version = 1
[[steps]]
type = "recode"
column = "code"
mappings = [{ from = true, to = "yes" }, { from = 1, to = "one" }]
"""
    with pytest.raises(TransformationError, match="duplicate or ambiguous"):
        parse_portable_recipe_text(text)


def test_typed_recode_rejects_non_finite_values() -> None:
    text = """version = 1
[[steps]]
type = "recode"
column = "code"
mappings = [{ from = inf, to = "bad" }]
"""
    with pytest.raises(TransformationError, match="non-finite"):
        parse_portable_recipe_text(text)


def test_canonical_round_trip_is_deterministic_and_ordered() -> None:
    recipe = parse_portable_recipe_text(
        """description = "Reusable"
version = 1
name = "Survey"
[[steps]]
update_value_labels = false
mappings = [{ to = "B", from = 2 }, { from = 1, to = "A" }]
column = "group"
type = "recode"
"""
    )

    canonical = portable_recipe_to_toml(recipe)
    reparsed = parse_portable_recipe_text(canonical)

    assert reparsed == recipe
    assert portable_recipe_to_toml(reparsed) == canonical
    assert canonical.index("from = 2") < canonical.index("from = 1")
    assert tomllib.loads(canonical)["steps"] == recipe.to_dict()["steps"]


def test_recipe_accepts_new_row_operations_and_normalizes_defaults() -> None:
    recipe = parse_portable_recipe_text(
        """version = 1
[[steps]]
type = "sort"
keys = [
  { column = "group", order = "ascending", nulls = "last" },
  { column = "age", order = "descending", nulls = "first" },
]
[[steps]]
type = "distinct"
columns = ["group", "age"]
keep = "first"
[[steps]]
type = "row_number"
column = "row_id"
"""
    )
    canonical = portable_recipe_to_toml(recipe)

    assert recipe.to_dict()["steps"][-1] == {
        "type": "row_number",
        "column": "row_id",
        "start": 1,
        "step": 1,
    }
    assert parse_portable_recipe_text(canonical) == recipe
    assert portable_recipe_to_toml(parse_portable_recipe_text(canonical)) == canonical


def test_save_is_explicit_atomic_and_requires_recipe_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "recipes" / "clean.toml"
    recipe = parse_portable_recipe_text(MINIMAL)

    with pytest.raises(Exception, match="directory does not exist"):
        save_portable_recipe(recipe, output)
    save_portable_recipe(recipe, output, create_dirs=True)
    assert parse_portable_recipe(output) == recipe
    assert not list(output.parent.glob("*.tmp"))
    with pytest.raises(Exception, match="overwrite-recipe"):
        save_portable_recipe(recipe, output)
    save_portable_recipe(recipe, output, overwrite=True)
    assert math.isfinite(float(parse_portable_recipe(output).version))


def test_save_appends_toml_to_extensionless_path(tmp_path: Path) -> None:
    requested = tmp_path / "portable-recipe"
    recipe = parse_portable_recipe_text(MINIMAL)

    saved = save_portable_recipe(recipe, requested)

    assert saved == requested.with_suffix(".toml")
    assert saved.is_file()
    assert not requested.exists()
    assert parse_portable_recipe(saved) == recipe
