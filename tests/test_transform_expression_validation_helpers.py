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
from statconvert.transformations.expressions import (
    ExpressionEvaluationError,
    evaluate_expression,
    parse_expression,
)


@pytest.fixture
def dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "number": [5, 0, 10, -1, 11, None],
            "lower": [0, 0, 0, 0, 0, 0],
            "upper": [10, 10, 10, 10, 10, None],
            "status": ["A", "B", "C", None, "A", "B"],
            "other": ["X", "B", None, "A", "C", "D"],
            "raw_date": [
                "2026-07-30",
                "2024-02-29",
                "bad",
                "2023-02-29",
                None,
                "2020-01-01",
            ],
            "format": ["%Y-%m-%d"] * 6,
        }
    )


def test_between_is_inclusive_for_numbers_and_missing_is_false(dataframe):
    result = evaluate_expression("between(number, lower, upper)", dataframe)

    assert result.tolist() == [True, True, True, False, False, False]


def test_between_supports_strings_with_exact_lexical_order():
    values = pd.DataFrame({"value": ["b", "a", "c", "B", None]})

    result = evaluate_expression("between(value, 'a', 'c')", values)

    assert result.tolist() == [True, True, True, False, False]


def test_between_supports_date_like_values_and_nested_parse_date(dataframe):
    parsed = evaluate_expression(
        (
            "between(parse_date(raw_date, '%Y-%m-%d'), "
            "parse_date('2024-01-01', '%Y-%m-%d'), "
            "parse_date('2026-12-31', '%Y-%m-%d'))"
        ),
        dataframe,
    )
    existing = pd.DataFrame(
        {
            "value": [date(2026, 7, 30), date(2023, 12, 31), None],
        }
    )

    assert parsed.tolist() == [True, True, False, False, False, False]
    assert evaluate_expression(
        "between(value, value, value)",
        existing,
    ).tolist() == [True, True, False]


@pytest.mark.parametrize(
    "expression",
    [
        "between(number, '0', '10')",
        "between('5', 0, 10)",
        "between(number, true, false)",
    ],
)
def test_between_mixed_or_unsupported_families_are_structured_errors(
    dataframe,
    expression,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == "expression_incompatible_type"
    assert exc_info.value.issue.function == "between"


def test_is_in_matches_first_later_and_row_local_options(dataframe):
    literals = evaluate_expression("is_in(status, 'A', 'B')", dataframe)
    row_options = evaluate_expression("is_in(status, other, 'C')", dataframe)

    assert literals.tolist() == [True, True, False, False, True, True]
    assert row_options.tolist() == [False, True, True, False, False, False]


def test_is_in_missing_values_and_options_never_match(dataframe):
    result = evaluate_expression("is_in(status, null, 'A')", dataframe)

    assert result.tolist() == [True, False, False, False, True, False]
    assert evaluate_expression("is_in(null, null, 'A')", dataframe) is False


def test_is_in_uses_existing_equality_without_string_numeric_coercion(dataframe):
    assert evaluate_expression("is_in(1, '1', 2)", dataframe) is False
    assert evaluate_expression("is_in(1, 1.0)", dataframe) is True
    assert evaluate_expression("is_in(true, 1)", dataframe) is True
    assert evaluate_expression("is_in('A', 'a', 'A')", dataframe) is True


def test_is_in_supports_date_like_values(dataframe):
    result = evaluate_expression(
        (
            "is_in(parse_date(raw_date, '%Y-%m-%d'), "
            "parse_date('2026-07-30', '%Y-%m-%d'), "
            "parse_date('2020-01-01', '%Y-%m-%d'))"
        ),
        dataframe,
    )

    assert result.tolist() == [True, False, False, False, False, True]


def test_not_in_is_exact_inverse_including_missing_values(dataframe):
    included = evaluate_expression("is_in(status, 'A', 'B')", dataframe)
    excluded = evaluate_expression("not_in(status, 'A', 'B')", dataframe)

    assert excluded.tolist() == [not item for item in included.tolist()]
    assert excluded.iloc[3] is True or bool(excluded.iloc[3]) is True
    assert evaluate_expression("not_in(null, null, 'A')", dataframe) is True


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("is_number(12)", True),
        ("is_number(12.5)", True),
        ("is_number('12')", True),
        ("is_number(' 12.5 ')", True),
        ("is_number('1e2')", True),
        ("is_number('')", False),
        ("is_number('bad')", False),
        ("is_number('1,000')", False),
        ("is_number('1_000')", False),
        ("is_number(true)", False),
        ("is_number(null)", False),
    ],
)
def test_is_number_matches_to_number_acceptance(expression, expected, dataframe):
    assert evaluate_expression(expression, dataframe) is expected


def test_is_number_rejects_non_finite_series_values():
    values = pd.DataFrame({"value": [math.inf, -math.inf, math.nan, 1.5]})

    assert evaluate_expression("is_number(value)", values).tolist() == [
        False,
        False,
        False,
        True,
    ]


def test_is_date_matches_parse_date_success(dataframe):
    result = evaluate_expression("is_date(raw_date, '%Y-%m-%d')", dataframe)

    assert result.tolist() == [True, True, False, False, False, True]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("is_date(raw_date, null)", "expression_null_control"),
        ("is_date(raw_date, '%Y-%b-%d')", "expression_invalid_date_format"),
        ("is_date(raw_date, format)", "expression_non_scalar_control"),
    ],
)
def test_is_date_reuses_structured_format_validation(
    dataframe,
    expression,
    code,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == code
    assert exc_info.value.issue.function == "is_date"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("alice@example.com", True),
        ("alice+tag@mail.example.com", True),
        ("missing-at.example.com", False),
        ("a@@example.com", False),
        ("@example.com", False),
        ("alice@", False),
        ("alice@localhost", False),
        ("alice @example.com", False),
        (".alice@example.com", False),
        ("alice.@example.com", False),
        ("alice@.example.com", False),
        ("alice@example.com.", False),
        ("alice@example..com", False),
        ("", False),
    ],
)
def test_is_email_uses_documented_pragmatic_rule(dataframe, value, expected):
    expression = f"is_email('{value}')"

    assert evaluate_expression(expression, dataframe) is expected


def test_is_email_converts_supported_non_string_values_and_missing_is_false(dataframe):
    values = pd.DataFrame(
        {
            "value": [
                None,
                123,
                True,
                date(2026, 7, 30),
                "alice@example.com",
            ]
        }
    )

    assert evaluate_expression("is_email(value)", values).tolist() == [
        False,
        False,
        False,
        False,
        True,
    ]


def test_is_email_enforces_total_length_limit(dataframe):
    valid = ("a" * 242) + "@example.com"
    oversized = ("a" * 243) + "@example.com"

    assert len(valid) == 254
    assert evaluate_expression(f"is_email('{valid}')", dataframe) is True
    assert evaluate_expression(f"is_email('{oversized}')", dataframe) is False


def test_validation_helpers_work_in_derive_and_filter_transformations():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "score": ["10", "bad", "101", "50"],
                "status": ["A", "A", "X", "B"],
                "email": [
                    "a@example.com",
                    "bad",
                    "x@example.com",
                    "b@example.com",
                ],
                "raw_date": ["2026-07-30", "bad", "2026-08-01", "2024-02-29"],
            }
        )
    )

    derived = DeriveColumnTransformation(
        "email_valid",
        "is_email(email)",
    ).apply(dataset)
    derived = DeriveColumnTransformation(
        "score_valid",
        "is_number(score)",
    ).apply(derived)
    filtered = ExpressionFilterTransformation(
        (
            "score_valid and between(to_number(score), 0, 100) "
            "and is_in(status, 'A', 'B') "
            "and not_in(status, 'X') "
            "and is_date(raw_date, '%Y-%m-%d')"
        ),
    ).apply(derived)

    assert derived.dataframe["email_valid"].tolist() == [True, False, True, True]
    assert derived.dataframe["score_valid"].tolist() == [True, False, True, True]
    assert filtered.dataframe["score"].tolist() == ["10", "50"]


@pytest.mark.parametrize(
    ("name", "minimum"),
    [
        ("between", 3),
        ("is_in", 2),
        ("not_in", 2),
        ("is_number", 1),
        ("is_date", 2),
        ("is_email", 1),
    ],
)
def test_validation_helpers_enforce_minimum_or_exact_arity(name, minimum):
    arguments = ", ".join("value" for _ in range(minimum))
    too_few = ", ".join("value" for _ in range(minimum - 1))

    assert parse_expression(f"{name}({arguments})").valid is True
    assert parse_expression(f"{name}({too_few})").errors[0].code == "wrong_arity"


def test_membership_helpers_accept_more_than_two_arguments():
    assert parse_expression("is_in(value, 1, 2, 3, 4)").valid is True
    assert parse_expression("not_in(value, 1, 2, 3, 4)").valid is True
