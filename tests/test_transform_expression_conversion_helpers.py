from __future__ import annotations

from datetime import date
import math

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.transformations.expression_steps import (
    DeriveColumnTransformation,
    ExpressionFilterTransformation,
)
from statconvert.transformations.expressions import evaluate_expression, parse_expression


@pytest.fixture
def dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "value": ["12", " 12.5 ", "bad", "", None],
            "integer": [12, 12.0, 12.5, float("inf"), None],
            "boolean": ["YES", " 0 ", "on", "", None],
        }
    )


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("to_string('text')", "text"),
        ("to_string(12)", "12"),
        ("to_string(12.5)", "12.5"),
        ("to_string(true)", "true"),
    ],
)
def test_to_string_uses_deterministic_text_conversion(
    dataframe,
    expression,
    expected,
):
    assert evaluate_expression(expression, dataframe) == expected


def test_to_string_supports_dates_and_propagates_invalid_values(dataframe):
    date_values = pd.DataFrame(
        {"value": [date(2026, 7, 30), math.inf, None]}
    )

    result = evaluate_expression("to_string(value)", date_values)

    assert result.tolist() == ["2026-07-30", pd.NA, pd.NA]
    assert pd.isna(evaluate_expression("to_string(null)", dataframe))


@pytest.mark.parametrize(
    ("expression", "expected", "expected_type"),
    [
        ("to_number(12)", 12, int),
        ("to_number(12.5)", 12.5, float),
        ("to_number('12')", 12, int),
        ("to_number(' 12 ')", 12, int),
        ("to_number('12.0')", 12.0, float),
        ("to_number('1e2')", 100.0, float),
        ("to_number(1000000000000000000000000000000)", 10**30, int),
    ],
)
def test_to_number_preserves_numeric_kind_and_uses_text_syntax(
    dataframe,
    expression,
    expected,
    expected_type,
):
    result = evaluate_expression(expression, dataframe)

    assert result == expected
    assert type(result) is expected_type


@pytest.mark.parametrize(
    "expression",
    [
        "to_number('')",
        "to_number('bad')",
        "to_number('1,000')",
        "to_number('1_000')",
        "to_number(true)",
        "to_number(null)",
    ],
)
def test_to_number_invalid_values_return_missing(dataframe, expression):
    assert pd.isna(evaluate_expression(expression, dataframe))


def test_to_number_series_retains_int_float_and_missing_values(dataframe):
    result = evaluate_expression("to_number(value)", dataframe)

    assert result.iloc[0] == 12
    assert type(result.iloc[0]) is int
    assert result.iloc[1] == 12.5
    assert type(result.iloc[1]) is float
    assert result.iloc[2:].isna().all()
    assert result.dtype == object


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("to_integer(12)", 12),
        ("to_integer(12.0)", 12),
        ("to_integer('12')", 12),
        ("to_integer(' 12.0 ')", 12),
        ("to_integer('1.2e2')", 120),
    ],
)
def test_to_integer_accepts_only_exact_integral_values(
    dataframe,
    expression,
    expected,
):
    assert evaluate_expression(expression, dataframe) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "to_integer(12.5)",
        "to_integer('12.5')",
        "to_integer('bad')",
        "to_integer(true)",
        "to_integer(null)",
        "to_integer('9223372036854775808')",
    ],
)
def test_to_integer_rejects_fractional_invalid_boolean_and_overflow(
    dataframe,
    expression,
):
    assert pd.isna(evaluate_expression(expression, dataframe))


def test_to_integer_series_uses_nullable_integer_dtype(dataframe):
    result = evaluate_expression("to_integer(integer)", dataframe)

    assert result.tolist() == [12, 12, pd.NA, pd.NA, pd.NA]
    assert str(result.dtype) == "Int64"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("to_float(12)", 12.0),
        ("to_float(12.5)", 12.5),
        ("to_float('12')", 12.0),
        ("to_float(' 12.5 ')", 12.5),
        ("to_float('1e2')", 100.0),
    ],
)
def test_to_float_returns_finite_float(dataframe, expression, expected):
    result = evaluate_expression(expression, dataframe)

    assert result == expected
    assert type(result) is float


@pytest.mark.parametrize(
    "expression",
    [
        "to_float('')",
        "to_float('bad')",
        "to_float('1,5')",
        "to_float('1e9999')",
        "to_float(true)",
        "to_float(null)",
    ],
)
def test_to_float_invalid_values_return_missing(dataframe, expression):
    assert pd.isna(evaluate_expression(expression, dataframe))


@pytest.mark.parametrize("token", ["true", "yes", "y", "t", "1"])
def test_to_boolean_accepts_every_true_token(dataframe, token):
    expression = f"to_boolean('  {token.upper()}  ')"

    assert evaluate_expression(expression, dataframe) is True


@pytest.mark.parametrize("token", ["false", "no", "n", "f", "0"])
def test_to_boolean_accepts_every_false_token(dataframe, token):
    expression = f"to_boolean('  {token.upper()}  ')"

    assert evaluate_expression(expression, dataframe) is False


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("to_boolean(true)", True),
        ("to_boolean(false)", False),
        ("to_boolean(1)", True),
        ("to_boolean(1.0)", True),
        ("to_boolean(0)", False),
        ("to_boolean(0.0)", False),
    ],
)
def test_to_boolean_accepts_booleans_and_numeric_one_or_zero(
    dataframe,
    expression,
    expected,
):
    assert evaluate_expression(expression, dataframe) is expected


@pytest.mark.parametrize(
    "expression",
    [
        "to_boolean(2)",
        "to_boolean('on')",
        "to_boolean('')",
        "to_boolean(null)",
    ],
)
def test_to_boolean_invalid_values_return_missing(dataframe, expression):
    assert pd.isna(evaluate_expression(expression, dataframe))


def test_to_boolean_series_uses_nullable_boolean_dtype(dataframe):
    result = evaluate_expression("to_boolean(boolean)", dataframe)

    assert result.tolist() == [True, False, pd.NA, pd.NA, pd.NA]
    assert str(result.dtype) == "boolean"


def test_conversion_helpers_work_in_derive_and_filter_transformations():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "amount": ["10", "bad", "20.5"],
                "active": ["yes", "true", "no"],
            }
        )
    )

    derived = DeriveColumnTransformation(
        "amount_number",
        "to_number(amount)",
    ).apply(dataset)
    filtered = ExpressionFilterTransformation(
        "to_boolean(active) and amount_number >= 10",
    ).apply(derived)

    assert derived.dataframe["amount_number"].tolist() == [10, pd.NA, 20.5]
    assert filtered.dataframe["amount"].tolist() == ["10"]


@pytest.mark.parametrize(
    "name",
    ["to_string", "to_number", "to_integer", "to_float", "to_boolean"],
)
def test_conversion_helpers_require_exactly_one_argument(name):
    missing = parse_expression(f"{name}()")
    extra = parse_expression(f"{name}(1, 2)")

    assert missing.valid is False
    assert missing.errors[0].code == "wrong_arity"
    assert extra.valid is False
    assert extra.errors[0].code == "wrong_arity"
