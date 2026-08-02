import json

import pytest

from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepMetadata,
    TransformStepType,
)


def test_recipe_preserves_ordered_steps_and_serializes_json_safely():
    recipe = TransformRecipe(
        input_file="survey_raw.csv",
        output_file="survey_clean.csv",
        overwrite=True,
        steps=(
            TransformStep(
                TransformStepType.DERIVE,
                {
                    "column": "email_clean",
                    "expression": "lower(strip(email))",
                },
            ),
            TransformStep(
                TransformStepType.DROP,
                {"columns": ["email"]},
            ),
        ),
    )

    payload = recipe.to_dict()

    assert [step["type"] for step in payload["steps"]] == ["derive", "drop"]
    assert json.loads(json.dumps(payload)) == payload


def test_step_serialization_uses_schema_order_not_input_mapping_order():
    step = TransformStep(
        TransformStepType.RECODE,
        {
            "default": "Unknown",
            "map": {"2": "Inactive", "1": "Active"},
            "column": "status",
        },
    )

    assert list(step.to_dict()) == ["type", "column", "map", "default"]


def test_step_defensively_freezes_nested_parameters():
    columns = ["email"]
    step = TransformStep(TransformStepType.DROP, {"columns": columns})

    columns.append("status")

    assert step.to_dict()["columns"] == ["email"]


@pytest.mark.parametrize(
        ("step_type", "parameters"),
    [
        (TransformStepType.SELECT, {}),
        (TransformStepType.DERIVE, {"column": "new"}),
        (TransformStepType.RECODE, {"column": "status"}),
    ],
)
def test_step_rejects_missing_required_fields(step_type, parameters):
    with pytest.raises(ValueError, match="missing required field"):
        TransformStep(step_type, parameters)


def test_rename_step_requires_complete_pair_or_mapping():
    with pytest.raises(ValueError, match="requires both"):
        TransformStep(TransformStepType.RENAME, {"from": "old"})


def test_filter_step_requires_expression_or_compatibility_conditions():
    with pytest.raises(ValueError, match="exactly one"):
        TransformStep(TransformStepType.FILTER, {})


def test_step_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown field"):
        TransformStep(
            TransformStepType.FILTER,
            {"expression": "active == true", "python": "forbidden"},
        )


def test_step_metadata_is_json_safe():
    metadata = TransformStepMetadata(
        step_index=0,
        step_type=TransformStepType.DERIVE,
        input_columns=("email",),
        output_columns=("email_clean",),
    )

    assert metadata.to_dict() == {
        "step_index": 0,
        "step_type": "derive",
        "input_columns": ["email"],
        "output_columns": ["email_clean"],
        "row_local": True,
        "previewable": True,
    }
