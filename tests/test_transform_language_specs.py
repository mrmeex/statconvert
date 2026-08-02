import json

from statconvert.transformations.expressions import parse_expression
from statconvert.transformations.language import (
    CORE_EXPRESSION_FUNCTIONS,
    DEFERRED_EXPRESSION_FUNCTIONS,
    EXCLUDED_NON_ROW_LOCAL_FUNCTIONS,
    expression_function_specs,
)


def test_core_function_registry_contains_exact_initial_function_set():
    assert {spec.name for spec in CORE_EXPRESSION_FUNCTIONS} == {
        "strip",
        "lower",
        "upper",
        "contains",
        "starts_with",
        "ends_with",
        "abs",
        "round",
        "is_null",
        "not_null",
        "coalesce",
        "normalize_whitespace",
        "null_if",
        "null_if_empty",
        "default_if_missing",
        "normalize_code",
        "if_else",
        "replace",
        "regex_match",
        "regex_replace",
        "length",
        "substring",
        "concat",
        "remove_accents",
        "to_string",
        "to_number",
        "to_integer",
        "to_float",
        "to_boolean",
        "parse_date",
        "format_date",
        "year",
        "month",
        "day",
        "weekday",
        "date_diff",
        "add_days",
        "between",
        "is_in",
        "not_in",
        "is_number",
        "is_date",
        "is_email",
    }


def test_core_functions_are_row_local_previewable_and_not_deferred():
    assert len(CORE_EXPRESSION_FUNCTIONS) == 43
    assert len(DEFERRED_EXPRESSION_FUNCTIONS) == 0
    assert all(spec.row_local for spec in CORE_EXPRESSION_FUNCTIONS)
    assert all(spec.previewable for spec in CORE_EXPRESSION_FUNCTIONS)
    assert not any(spec.deferred for spec in CORE_EXPRESSION_FUNCTIONS)


def test_deferred_functions_are_separate_and_marked_deferred():
    core_names = {spec.name for spec in CORE_EXPRESSION_FUNCTIONS}
    deferred_names = {spec.name for spec in DEFERRED_EXPRESSION_FUNCTIONS}

    assert "replace" in core_names
    assert "replace" not in deferred_names
    assert "parse_date" in core_names
    assert "parse_date" not in deferred_names
    assert "to_date" not in core_names | deferred_names
    assert "to_number" in core_names
    assert "to_number" not in deferred_names
    assert "normalize_code" in core_names
    assert "normalize_code" not in deferred_names
    assert {
        "between",
        "is_in",
        "not_in",
        "is_number",
        "is_date",
        "is_email",
    } <= core_names
    assert core_names.isdisjoint(deferred_names)
    assert DEFERRED_EXPRESSION_FUNCTIONS == ()
    assert all(spec.deferred for spec in DEFERRED_EXPRESSION_FUNCTIONS)
    assert expression_function_specs() == CORE_EXPRESSION_FUNCTIONS


def test_aggregate_and_window_functions_are_not_registered():
    registered_names = {
        spec.name for spec in expression_function_specs(include_deferred=True)
    }

    assert EXCLUDED_NON_ROW_LOCAL_FUNCTIONS.isdisjoint(registered_names)
    assert {"sum", "mean", "rank", "lag", "lead"} <= (
        EXCLUDED_NON_ROW_LOCAL_FUNCTIONS
    )


def test_function_specs_serialize_to_json_safe_metadata():
    payload = [spec.to_dict() for spec in expression_function_specs()]

    assert json.loads(json.dumps(payload)) == payload


def test_every_registered_metadata_example_is_valid_expression_syntax():
    failures = {
        spec.name: example
        for spec in CORE_EXPRESSION_FUNCTIONS
        for example in spec.examples
        if not parse_expression(example).valid
    }

    assert failures == {}


def test_text_function_specs_include_ui_picker_metadata():
    specs = {spec.name: spec.to_dict() for spec in CORE_EXPRESSION_FUNCTIONS}
    concat = specs["concat"]
    regex_match = specs["regex_match"]

    assert concat["signature"] == "concat(value1, value2, ...)"
    assert concat["arity"] == {"minimum": 1, "maximum": None}
    assert concat["maximum_arguments"] is None
    assert concat["arguments"][0]["variadic"] is True
    assert concat["return_type"] == "string"
    assert concat["derive_allowed"] is True
    assert concat["filter_suitability"] == "composable"
    assert concat["examples"]
    assert concat["null_behavior"]
    assert concat["error_behavior"]
    assert regex_match["filter_suitability"] == "direct"
    assert regex_match["arguments"][1]["kind"] == "scalar_control"


def test_conversion_function_specs_include_ui_picker_metadata():
    specs = {spec.name: spec.to_dict() for spec in CORE_EXPRESSION_FUNCTIONS}

    for name in (
        "to_string",
        "to_number",
        "to_integer",
        "to_float",
        "to_boolean",
    ):
        spec = specs[name]
        assert spec["category"] == "conversion"
        assert spec["signature"] == f"{name}(value)"
        assert spec["arity"] == 1
        assert spec["minimum_arguments"] == 1
        assert spec["maximum_arguments"] == 1
        assert spec["arguments"][0]["kind"] == "value_expression"
        assert spec["examples"]
        assert spec["derive_allowed"] is True
        assert spec["null_behavior"]
        assert spec["error_behavior"]

    assert specs["to_boolean"]["filter_suitability"] == "direct"


def test_date_function_specs_include_ui_picker_metadata():
    specs = {spec.name: spec.to_dict() for spec in CORE_EXPRESSION_FUNCTIONS}
    expected_arity = {
        "parse_date": 2,
        "format_date": 2,
        "year": 1,
        "month": 1,
        "day": 1,
        "weekday": 1,
        "date_diff": 2,
        "add_days": 2,
    }

    for name, arity in expected_arity.items():
        spec = specs[name]
        assert spec["category"] == "date_time"
        assert spec["arity"] == arity
        assert spec["minimum_arguments"] == arity
        assert spec["maximum_arguments"] == arity
        assert spec["signature"]
        assert spec["arguments"]
        assert spec["examples"]
        assert spec["derive_allowed"] is True
        assert spec["filter_suitability"] == "composable"
        assert spec["null_behavior"]
        assert spec["error_behavior"]

    assert specs["parse_date"]["arguments"][1]["kind"] == "scalar_control"
    assert specs["format_date"]["arguments"][1]["kind"] == "scalar_control"


def test_validation_function_specs_include_ui_picker_metadata():
    specs = {spec.name: spec.to_dict() for spec in CORE_EXPRESSION_FUNCTIONS}

    for name in (
        "between",
        "is_in",
        "not_in",
        "is_number",
        "is_date",
        "is_email",
    ):
        spec = specs[name]
        assert spec["category"] == "validation_list"
        assert spec["return_type"] == "boolean"
        assert spec["signature"]
        assert spec["arguments"]
        assert spec["examples"]
        assert spec["derive_allowed"] is True
        assert spec["filter_suitability"] == "direct"
        assert spec["null_behavior"]
        assert spec["error_behavior"]

    for name in ("is_in", "not_in"):
        assert specs[name]["arity"] == {"minimum": 2, "maximum": None}
        assert specs[name]["arguments"][1]["variadic"] is True
    assert specs["between"]["arity"] == 3
    assert specs["is_date"]["arguments"][1]["kind"] == "scalar_control"
