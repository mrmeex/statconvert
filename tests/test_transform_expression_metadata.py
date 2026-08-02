import json

import pytest

from statconvert.transformations.expressions import parse_expression


def test_metadata_discovers_columns_and_functions_in_first_seen_order():
    analysis = parse_expression(
        "lower(strip(email)) == upper(country) or email == backup"
    )

    assert analysis.valid is True
    assert analysis.referenced_columns == ("email", "country", "backup")
    assert analysis.functions == ("lower", "strip", "upper")
    assert analysis.row_local is True
    assert analysis.previewable is True


def test_bracketed_column_metadata_uses_decoded_name_and_span():
    expression = 'lower(strip(["Email Address"]))'
    analysis = parse_expression(expression)
    column = (
        analysis.ast.to_dict()["root"]["arguments"][0]["arguments"][0]
    )

    assert analysis.referenced_columns == ("Email Address",)
    assert column["span"] == {"start": 12, "end": 29}
    assert expression[12:29] == '["Email Address"]'


@pytest.mark.parametrize(
    ("expression", "result_kind"),
    [
        ("'text'", "string"),
        ("42", "number"),
        ("true", "boolean"),
        ("null", "null"),
        ("email", "unknown"),
        ("lower(email)", "string"),
        ("contains(email, '@')", "boolean"),
        ("abs(-2)", "number"),
        ("round(10 / 3, 2)", "number"),
        ("age >= 18 and active", "boolean"),
        ("coalesce(null, 'unknown')", "string"),
        ("coalesce(email, 'unknown')", "unknown"),
        ("normalize_whitespace(email)", "string"),
        ("normalize_code(country)", "string"),
        ("null_if(email, '')", "unknown"),
        ("null_if_empty(email)", "string"),
        ("default_if_missing(null, 0)", "number"),
        ("default_if_missing(email, 'unknown')", "unknown"),
        ("if_else(active, 'yes', 'no')", "string"),
        ("if_else(active, 'yes', 0)", "unknown"),
        ("replace(code, '-', '')", "string"),
        ("regex_match(code, '^[A-Z]+$')", "boolean"),
        ("regex_replace(code, '[^A-Z]', '')", "string"),
        ("length(code)", "number"),
        ("substring(code, 0, 2)", "string"),
        ("concat(code, '-', email)", "string"),
        ("remove_accents(code)", "string"),
        ("to_string(code)", "string"),
        ("to_number(code)", "number"),
        ("to_integer(code)", "number"),
        ("to_float(code)", "number"),
        ("to_boolean(code)", "boolean"),
        ("parse_date(code, '%Y-%m-%d')", "date"),
        ("format_date(code, '%Y-%m-%d')", "string"),
        ("year(code)", "number"),
        ("month(code)", "number"),
        ("day(code)", "number"),
        ("weekday(code)", "number"),
        ("date_diff(code, email)", "number"),
        ("add_days(code, 1)", "date"),
        ("between(code, 'A', 'Z')", "boolean"),
        ("is_in(code, 'A', 'B')", "boolean"),
        ("not_in(code, 'A', 'B')", "boolean"),
        ("is_number(code)", "boolean"),
        ("is_date(code, '%Y-%m-%d')", "boolean"),
        ("is_email(email)", "boolean"),
        ("amount + 1", "unknown"),
    ],
)
def test_result_kind_inference_is_conservative(expression, result_kind):
    analysis = parse_expression(expression)

    assert analysis.valid is True
    assert analysis.result_kind == result_kind


def test_valid_analysis_and_ast_are_json_safe():
    analysis = parse_expression("lower(strip(email))")
    payload = analysis.to_dict()

    assert json.loads(json.dumps(payload)) == payload
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert payload["span"] == {"start": 0, "end": 19}


def test_invalid_analysis_is_deterministic_and_json_safe():
    first = parse_expression("unknown(email)")
    second = parse_expression("unknown(email)")

    assert first.to_dict() == second.to_dict()
    assert first.valid is False
    assert first.ast is None
    assert first.referenced_columns == ()
    assert first.functions == ()
    assert first.row_local is False
    assert first.previewable is False
    assert first.result_kind == "unknown"
    assert json.loads(json.dumps(first.to_dict())) == first.to_dict()


def test_function_call_and_operator_spans_are_available_for_ui_highlighting():
    expression = "lower(email) == 'x'"
    analysis = parse_expression(expression)
    root = analysis.ast.to_dict()["root"]

    assert root["operator_span"] == {"start": 13, "end": 15}
    assert root["left"]["name_span"] == {"start": 0, "end": 5}
    assert root["left"]["span"] == {"start": 0, "end": 12}


def test_non_string_input_returns_safe_error():
    analysis = parse_expression(None)

    assert analysis.valid is False
    assert analysis.errors[0].code == "invalid_expression_type"
    assert analysis.to_dict()["expression"] == ""
