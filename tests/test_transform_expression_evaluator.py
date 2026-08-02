import json

import pandas as pd
import pytest

from statconvert.transformations.expressions import (
    ExpressionEvaluationError,
    evaluate_expression,
    parse_expression,
)


@pytest.fixture
def dataframe():
    return pd.DataFrame(
        {
            "email": [" Alice@EXAMPLE.COM ", None, "bob@example.com"],
            "country": ["nl", "BE", None],
            "age": [17, 18, 21],
            "score": [-1.234, 2.345, None],
            "active": pd.Series([True, False, pd.NA], dtype="boolean"),
            "fallback": ["first", "second", "third"],
            "mixed": ["one", 2, None],
            "zero": [1, 0, 2],
        }
    )


def test_nested_text_functions_preserve_missing_values(dataframe):
    result = evaluate_expression("lower(strip(email))", dataframe)

    assert result.iloc[0] == "alice@example.com"
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == "bob@example.com"


def test_upper_and_bracketed_column_reference(dataframe):
    renamed = dataframe.rename(columns={"country": "Country Code"})

    result = evaluate_expression('upper(["Country Code"])', renamed)

    assert result.tolist()[:2] == ["NL", "BE"]
    assert pd.isna(result.iloc[2])


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("contains(email, '@example')", [False, False, True]),
        ("starts_with(strip(email), 'Alice')", [True, False, False]),
        ("ends_with(email, '.com')", [False, False, True]),
    ],
)
def test_string_predicates_are_literal_case_sensitive_and_missing_false(
    dataframe,
    expression,
    expected,
):
    result = evaluate_expression(expression, dataframe)

    assert result.tolist() == expected


def test_numeric_functions_arithmetic_and_unary_minus(dataframe):
    absolute = evaluate_expression("abs(score)", dataframe)
    rounded = evaluate_expression("round(abs(score), 2)", dataframe)
    arithmetic = evaluate_expression("(-age + 20) * 2", dataframe)

    assert absolute.iloc[:2].tolist() == [1.234, 2.345]
    assert rounded.iloc[:2].tolist() == [1.23, 2.35]
    assert arithmetic.tolist() == [6, 4, -2]


def test_missing_helpers_and_series_fallback(dataframe):
    is_null = evaluate_expression("is_null(email)", dataframe)
    not_null = evaluate_expression("not_null(email)", dataframe)
    coalesced = evaluate_expression("coalesce(email, fallback)", dataframe)

    assert is_null.tolist() == [False, True, False]
    assert not_null.tolist() == [True, False, True]
    assert coalesced.tolist() == [
        " Alice@EXAMPLE.COM ",
        "second",
        "bob@example.com",
    ]


def test_if_else_aligns_literals_columns_and_nested_functions(dataframe):
    groups = evaluate_expression(
        "if_else(age >= 18, 'adult', 'minor')",
        dataframe,
    )
    emails = evaluate_expression(
        "if_else(not_null(email), lower(strip(email)), fallback)",
        dataframe,
    )

    assert groups.tolist() == ["minor", "adult", "adult"]
    assert emails.tolist() == ["alice@example.com", "second", "bob@example.com"]


def test_missing_boolean_values_are_false_for_boolean_operations(dataframe):
    result = evaluate_expression("active or age >= 21", dataframe)
    inverted = evaluate_expression("not active", dataframe)

    assert result.tolist() == [True, False, True]
    assert inverted.tolist() == [False, True, True]


def test_comparisons_return_vectorized_boolean_result(dataframe):
    result = evaluate_expression("age >= 18 and country == 'BE'", dataframe)

    assert result.tolist() == [False, True, False]


def test_division_by_zero_fails_deterministically(dataframe):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression("age / zero", dataframe)

    assert exc_info.value.issue.code == "expression_division_by_zero"
    assert exc_info.value.issue.source_span.to_dict() == {"start": 6, "end": 10}


@pytest.mark.parametrize(
    "expression",
    [
        "lower(age)",
        "abs(email)",
        "age + email",
        "round(score, 1.5)",
        "contains(email, age)",
    ],
)
def test_incompatible_function_and_operator_types_fail_safely(
    dataframe,
    expression,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == "expression_incompatible_type"


def test_unknown_column_error_is_structured_and_json_safe(dataframe):
    analysis = parse_expression("lower(missing)")

    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(analysis, dataframe)

    issue = exc_info.value.issue
    assert issue.code == "expression_unknown_column"
    assert issue.referenced_column == "missing"
    assert issue.source_span.to_dict() == {"start": 6, "end": 13}
    assert json.loads(json.dumps(issue.to_dict())) == issue.to_dict()


def test_parser_rejects_non_row_local_or_dangerous_function_before_evaluation(
    dataframe,
):
    for expression in ("sum(age)", "open('file')", "__import__('os')"):
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluate_expression(expression, dataframe)
        assert exc_info.value.issue.code == "expression_invalid"
