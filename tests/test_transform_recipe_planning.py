import json

import pytest

from statconvert.transformations.planning import (
    TransformPlanMode,
    plan_transform_recipe,
)
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)


def _recipe(*steps):
    return TransformRecipe(
        input_file="input.csv",
        output_file="output.csv",
        steps=steps,
    )


def _step(step_type, **parameters):
    return TransformStep(step_type, parameters)


def test_empty_recipe_produces_valid_unchanged_plan():
    plan = plan_transform_recipe(_recipe(), ["id", "email"])

    assert plan.valid is True
    assert plan.initial_columns == ("id", "email")
    assert plan.final_columns == ("id", "email")
    assert plan.steps == ()
    assert plan.errors == ()


def test_ordered_steps_project_select_drop_rename_and_derive():
    recipe = _recipe(
        _step(TransformStepType.SELECT, columns=["id", "email", "status"]),
        _step(TransformStepType.DROP, columns=["status"]),
        _step(TransformStepType.RENAME, **{"from": "email", "to": "source_email"}),
        _step(
            TransformStepType.DERIVE,
            column="email_clean",
            expression="lower(strip(source_email))",
        ),
    )

    plan = plan_transform_recipe(recipe, ["id", "email", "status", "unused"])

    assert plan.valid is True
    assert [step.step_type for step in plan.steps] == [
        TransformStepType.SELECT,
        TransformStepType.DROP,
        TransformStepType.RENAME,
        TransformStepType.DERIVE,
    ]
    assert plan.final_columns == ("id", "source_email", "email_clean")
    assert plan.steps[0].removed_columns == ("unused",)
    assert plan.steps[1].removed_columns == ("status",)
    assert plan.steps[2].renamed_columns == (("email", "source_email"),)


def test_convert_filter_and_recode_preserve_columns_and_record_intent():
    recipe = _recipe(
        _step(
            TransformStepType.CONVERT_TYPE,
            column="age",
            data_type="int",
        ),
        _step(
            TransformStepType.FILTER,
            expression="age >= 18 and active",
        ),
        _step(
            TransformStepType.RECODE,
            column="active",
            map={"yes": True, "no": False},
        ),
    )

    plan = plan_transform_recipe(recipe, ["age", "active"])

    assert plan.valid is True
    assert plan.final_columns == ("age", "active")
    assert plan.steps[0].intended_types == (("age", "integer"),)
    assert plan.steps[1].referenced_columns == ("age", "active")
    assert plan.steps[1].expression_metadata.result_kind == "boolean"
    assert plan.steps[2].recode_map_keys == ("yes", "no")
    assert plan.steps[2].recode_map_count == 2
    assert plan.steps[2].recode_uses_default is False
    assert plan.steps[2].recode_updates_value_labels is True
    assert plan.steps[2].recode_affects_missing_values is False


@pytest.mark.parametrize(
    ("step", "columns", "code"),
    [
        (
            _step(TransformStepType.SELECT, columns=["missing"]),
            ["id"],
            "transform_unknown_column",
        ),
        (
            _step(TransformStepType.SELECT, columns=["id", "id"]),
            ["id"],
            "transform_duplicate_column",
        ),
        (
            _step(TransformStepType.DROP, columns=["missing"]),
            ["id"],
            "transform_unknown_column",
        ),
        (
            _step(TransformStepType.DROP, columns=["id", "id"]),
            ["id", "value"],
            "transform_duplicate_column",
        ),
        (
            _step(TransformStepType.RENAME, **{"from": "missing", "to": "new"}),
            ["id"],
            "transform_unknown_column",
        ),
        (
            _step(
                TransformStepType.RENAME,
                map={"first": "same", "second": "same"},
            ),
            ["first", "second"],
            "transform_duplicate_column",
        ),
        (
            _step(TransformStepType.RENAME, **{"from": "old", "to": "existing"}),
            ["old", "existing"],
            "transform_column_collision",
        ),
        (
            _step(TransformStepType.RENAME, map={"old": ""}),
            ["old"],
            "transform_invalid_step",
        ),
        (
            _step(TransformStepType.RENAME, map={}),
            ["old"],
            "transform_invalid_step",
        ),
        (
            _step(
                TransformStepType.CONVERT_TYPE,
                column="missing",
                data_type="integer",
            ),
            ["id"],
            "transform_unknown_column",
        ),
        (
            _step(
                TransformStepType.CONVERT_TYPE,
                column="id",
                data_type="uuid",
            ),
            ["id"],
            "transform_unsupported_type",
        ),
        (
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(",
            ),
            ["email"],
            "transform_invalid_expression",
        ),
        (
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(missing)",
            ),
            ["email"],
            "transform_unknown_referenced_column",
        ),
        (
            _step(
                TransformStepType.DERIVE,
                column="email",
                expression="lower(email)",
            ),
            ["email"],
            "transform_column_collision",
        ),
        (
            _step(
                TransformStepType.FILTER,
                expression="age >=",
            ),
            ["age"],
            "transform_invalid_expression",
        ),
        (
            _step(
                TransformStepType.FILTER,
                expression="missing >= 18",
            ),
            ["age"],
            "transform_unknown_referenced_column",
        ),
        (
            _step(
                TransformStepType.RECODE,
                column="missing",
                map={"a": "b"},
            ),
            ["status"],
            "transform_unknown_column",
        ),
        (
            _step(
                TransformStepType.RECODE,
                column="status",
                map={},
            ),
            ["status"],
            "transform_invalid_recode_map",
        ),
    ],
)
def test_planner_reports_structured_step_errors(step, columns, code):
    plan = plan_transform_recipe(_recipe(step), columns)

    assert plan.valid is False
    assert plan.steps[0].status == "invalid"
    assert code in {error.code for error in plan.steps[0].errors}
    assert plan.errors == plan.steps[0].errors
    assert plan.final_columns == tuple(columns)


def test_rename_mapping_is_simultaneous_and_supports_swaps():
    plan = plan_transform_recipe(
        _recipe(_step(TransformStepType.RENAME, map={"a": "b", "b": "a"})),
        ["a", "b"],
    )

    assert plan.valid is True
    assert plan.final_columns == ("b", "a")


def test_derive_then_drop_source_is_valid():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="email_clean",
                expression="lower(email)",
            ),
            _step(TransformStepType.DROP, columns=["email"]),
        ),
        ["email"],
    )

    assert plan.valid is True
    assert plan.final_columns == ("email_clean",)


def test_drop_then_derive_from_source_reports_dependency_error():
    plan = plan_transform_recipe(
        _recipe(
            _step(TransformStepType.DROP, columns=["email"]),
            _step(
                TransformStepType.DERIVE,
                column="email_clean",
                expression="lower(email)",
            ),
        ),
        ["email", "id"],
    )

    assert plan.valid is False
    assert plan.steps[0].status == "planned"
    assert plan.steps[1].errors[0].code == "transform_unknown_referenced_column"
    assert plan.final_columns == ("id",)


def test_rename_then_derive_must_use_new_name():
    valid = plan_transform_recipe(
        _recipe(
            _step(TransformStepType.RENAME, **{"from": "email", "to": "address"}),
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(address)",
            ),
        ),
        ["email"],
    )
    invalid = plan_transform_recipe(
        _recipe(
            _step(TransformStepType.RENAME, **{"from": "email", "to": "address"}),
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(email)",
            ),
        ),
        ["email"],
    )

    assert valid.valid is True
    assert invalid.errors[0].referenced_column == "email"


def test_invalid_step_does_not_mutate_best_effort_column_state():
    plan = plan_transform_recipe(
        _recipe(
            _step(TransformStepType.DROP, columns=["missing"]),
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(email)",
            ),
        ),
        ["email"],
    )

    assert plan.valid is False
    assert plan.steps[0].output_columns == ("email",)
    assert plan.steps[1].status == "planned"
    assert plan.final_columns == ("email", "clean")


def test_select_removes_columns_from_later_dependency_state():
    plan = plan_transform_recipe(
        _recipe(
            _step(TransformStepType.SELECT, columns=["id"]),
            _step(
                TransformStepType.FILTER,
                expression="status == 'active'",
            ),
        ),
        ["id", "status"],
    )

    assert plan.errors[0].code == "transform_unknown_referenced_column"
    assert plan.errors[0].step_index == 1


def test_derive_metadata_includes_functions_columns_and_ui_flags():
    plan = plan_transform_recipe(
        _recipe(
            TransformStep(
                TransformStepType.DERIVE,
                {
                    "column": "email_clean",
                    "expression": 'lower(strip(["Email Address"]))',
                },
                step_id="clean-email",
            )
        ),
        ["Email Address"],
        mode=TransformPlanMode.PREVIEW,
    )
    step = plan.steps[0]

    assert plan.mode == TransformPlanMode.PREVIEW
    assert step.step_id == "clean-email"
    assert step.referenced_columns == ("Email Address",)
    assert step.expression_metadata.functions == ("lower", "strip")
    assert step.row_local is True
    assert step.previewable is True


def test_text_helper_metadata_flows_through_derive_and_filter_planning():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="label",
                expression="concat(remove_accents(name), '-', substring(code, 0, 2))",
            ),
            _step(
                TransformStepType.FILTER,
                expression="regex_match(label, '^Jose-')",
            ),
        ),
        ["name", "code"],
        mode=TransformPlanMode.PREVIEW,
    )

    assert plan.valid is True
    assert plan.steps[0].expression_metadata.functions == (
        "concat",
        "remove_accents",
        "substring",
    )
    assert plan.steps[0].expression_metadata.result_kind == "string"
    assert plan.steps[1].expression_metadata.functions == ("regex_match",)
    assert plan.steps[1].expression_metadata.result_kind == "boolean"


def test_conversion_helper_metadata_flows_through_planning():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="amount_number",
                expression="to_number(amount)",
            ),
            _step(
                TransformStepType.FILTER,
                expression="to_boolean(active) and amount_number >= 0",
            ),
        ),
        ["amount", "active"],
        mode=TransformPlanMode.PREVIEW,
    )

    assert plan.valid is True
    assert plan.steps[0].expression_metadata.functions == ("to_number",)
    assert plan.steps[0].expression_metadata.result_kind == "number"
    assert plan.steps[1].expression_metadata.functions == ("to_boolean",)
    assert plan.steps[1].expression_metadata.result_kind == "boolean"


def test_date_helper_metadata_flows_through_planning():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="opened_date",
                expression="parse_date(opened, '%Y-%m-%d')",
            ),
            _step(
                TransformStepType.DERIVE,
                column="due_date",
                expression="add_days(opened_date, 30)",
            ),
            _step(
                TransformStepType.FILTER,
                expression="year(due_date) == 2026 and weekday(due_date) <= 5",
            ),
        ),
        ["opened"],
        mode=TransformPlanMode.PREVIEW,
    )

    assert plan.valid is True
    assert plan.steps[0].expression_metadata.functions == ("parse_date",)
    assert plan.steps[0].expression_metadata.result_kind == "date"
    assert plan.steps[1].expression_metadata.functions == ("add_days",)
    assert plan.steps[1].expression_metadata.result_kind == "date"
    assert plan.steps[2].expression_metadata.functions == ("year", "weekday")
    assert plan.steps[2].expression_metadata.result_kind == "boolean"


def test_validation_helper_metadata_flows_through_planning():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="email_valid",
                expression="is_email(email)",
            ),
            _step(
                TransformStepType.DERIVE,
                column="score_valid",
                expression="is_number(score)",
            ),
            _step(
                TransformStepType.FILTER,
                expression=(
                    "email_valid and score_valid "
                    "and between(to_number(score), 0, 100) "
                    "and is_in(status, 'A', 'B') "
                    "and not_in(status, 'X') "
                    "and is_date(raw_date, '%Y-%m-%d')"
                ),
            ),
        ),
        ["email", "score", "status", "raw_date"],
        mode=TransformPlanMode.PREVIEW,
    )

    assert plan.valid is True
    assert plan.steps[0].expression_metadata.functions == ("is_email",)
    assert plan.steps[1].expression_metadata.functions == ("is_number",)
    assert plan.steps[2].expression_metadata.functions == (
        "between",
        "to_number",
        "is_in",
        "not_in",
        "is_date",
    )
    assert plan.steps[2].expression_metadata.result_kind == "boolean"


def test_expression_error_and_unknown_reference_spans_survive_planning():
    invalid = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="mystery(email)",
            )
        ),
        ["email"],
    )
    unknown = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DERIVE,
                column="clean",
                expression="lower(missing)",
            )
        ),
        ["email"],
    )

    assert invalid.errors[0].source_span.to_dict() == {"start": 0, "end": 7}
    assert unknown.errors[0].source_span.to_dict() == {"start": 6, "end": 13}


def test_known_non_boolean_filter_result_is_rejected():
    plan = plan_transform_recipe(
        _recipe(_step(TransformStepType.FILTER, expression="lower(email)")),
        ["email"],
    )

    assert plan.valid is False
    assert plan.errors[0].code == "transform_invalid_expression"
    assert "boolean" in plan.errors[0].message


def test_plan_serialization_is_deterministic_and_json_safe():
    recipe = _recipe(
        _step(
            TransformStepType.DERIVE,
            column="email_clean",
            expression="lower(email)",
        ),
        _step(TransformStepType.DROP, columns=["missing"]),
    )

    first = plan_transform_recipe(recipe, ["email"]).to_dict()
    second = plan_transform_recipe(recipe, ["email"]).to_dict()

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["steps"][0]["expression_metadata"]["valid"] is True
    assert first["steps"][1]["errors"][0]["code"] == "transform_unknown_column"


def test_ignore_missing_compatibility_policy_emits_warning():
    plan = plan_transform_recipe(
        _recipe(
            _step(
                TransformStepType.DROP,
                columns=["missing"],
                ignore_missing=True,
            )
        ),
        ["id"],
    )

    assert plan.valid is True
    assert plan.final_columns == ("id",)
    assert plan.warnings[0].code == "transform_ignored_unknown_column"
