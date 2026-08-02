import json

from statconvert.transformations.compatibility import (
    recipe_from_transform_options,
)
from statconvert.transformations.planning import (
    TransformPlanMode,
    plan_transform_recipe,
)
from statconvert.transformations.recipes import TransformStepType


def test_no_existing_options_produce_zero_step_recipe():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
    )

    assert recipe.steps == ()


def test_existing_options_translate_in_fixed_pipeline_order():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        select_columns=["id", "age", "status"],
        drop_columns=["status"],
        rename_items=["age=years"],
        type_items=["years=int"],
        filter_items=["years,gte,18"],
        recode_items=["years:18=adult"],
    )

    assert [step.step_type for step in recipe.steps] == [
        TransformStepType.SELECT,
        TransformStepType.DROP,
        TransformStepType.RENAME,
        TransformStepType.CONVERT_TYPE,
        TransformStepType.FILTER,
        TransformStepType.RECODE,
    ]


def test_select_drop_and_rename_translation_preserves_values():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        select_columns=["id", "old", "unused"],
        drop_columns=["unused"],
        rename_items=["old=new"],
        ignore_missing_columns=True,
    )

    assert recipe.steps[0].to_dict() == {
        "type": "select",
        "columns": ["id", "old", "unused"],
        "ignore_missing": True,
    }
    assert recipe.steps[1].to_dict()["columns"] == ["unused"]
    assert recipe.steps[2].to_dict()["map"] == {"old": "new"}


def test_multiple_rename_pairs_remain_one_simultaneous_step():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        rename_items=["a=b", "b=a"],
    )
    plan = plan_transform_recipe(
        recipe,
        ["a", "b"],
        mode=TransformPlanMode.COMPATIBILITY,
    )

    assert len(recipe.steps) == 1
    assert plan.valid is True
    assert plan.final_columns == ("b", "a")


def test_type_translation_expands_to_ordered_single_column_steps():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        type_items=["age=int", "score=float"],
        type_errors="coerce",
        datetime_format="%Y-%m-%d",
    )

    assert [step.parameters["column"] for step in recipe.steps] == [
        "age",
        "score",
    ]
    assert all(step.parameters["errors"] == "coerce" for step in recipe.steps)
    assert all(
        step.parameters["datetime_format"] == "%Y-%m-%d"
        for step in recipe.steps
    )


def test_derive_and_expression_filter_translate_in_execution_order():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        derive_items=[
            "country_clean=upper(country)",
            "adult=age >= 18",
        ],
        filter_items=["age,gte,18"],
        filter_expression_items=["adult and country_clean == 'NL'"],
    )

    assert [step.step_type for step in recipe.steps] == [
        TransformStepType.DERIVE,
        TransformStepType.DERIVE,
        TransformStepType.FILTER,
        TransformStepType.FILTER,
    ]
    assert recipe.steps[-1].parameters["expression"] == (
        "adult and country_clean == 'NL'"
    )


def test_legacy_filter_translation_preserves_conditions_mode_and_reset_policy():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        filter_items=["age,gte,18", "status,in,A|B"],
        filter_mode="or",
        reset_index=False,
    )
    step = recipe.steps[0]

    assert step.step_type == TransformStepType.FILTER
    assert step.parameters["mode"] == "or"
    assert step.parameters["reset_index"] is False
    assert step.to_dict()["conditions"] == [
        {"column": "age", "operator": "gte", "value": 18},
        {"column": "status", "operator": "in", "value": ["A", "B"]},
    ]


def test_legacy_filter_plan_tracks_referenced_columns_without_expression():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        filter_items=["age,gte,18", "active,eq,true"],
    )

    plan = plan_transform_recipe(
        recipe,
        ["age", "active"],
        mode=TransformPlanMode.COMPATIBILITY,
    )

    assert plan.valid is True
    assert plan.steps[0].referenced_columns == ("age", "active")
    assert plan.steps[0].expression is None
    assert plan.steps[0].expression_metadata is None


def test_recode_translation_preserves_mapping_default_and_metadata_policy():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        recode_items=["status:A=Active,I=Inactive"],
        recode_default="Unknown",
        update_value_labels=False,
    )

    assert recipe.steps[0].to_dict() == {
        "type": "recode",
        "column": "status",
        "map": {"A": "Active", "I": "Inactive"},
        "default": "Unknown",
        "update_value_labels": False,
    }


def test_translated_recipe_plan_matches_current_fixed_order_column_projection():
    recipe = recipe_from_transform_options(
        input_file="input.csv",
        output_file="output.csv",
        select_columns=["id", "value", "status"],
        drop_columns=["status"],
        rename_items=["value=amount"],
        type_items=["amount=float"],
        filter_items=["amount,gte,0"],
        recode_items=["amount:0=zero"],
    )

    plan = plan_transform_recipe(
        recipe,
        ["id", "value", "status", "unused"],
        mode=TransformPlanMode.COMPATIBILITY,
    )

    assert plan.valid is True
    assert plan.final_columns == ("id", "amount")
    assert json.loads(json.dumps(plan.to_dict())) == plan.to_dict()
