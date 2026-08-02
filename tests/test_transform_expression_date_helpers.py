from __future__ import annotations

from datetime import date, datetime

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
            "raw": ["2026-07-30", "2024-02-29", "bad", "2023-02-29", None],
            "slash": ["30/07/2026", "29/02/2024", "x", None, "01/01/2020"],
            "format": ["%Y-%m-%d"] * 5,
        }
    )


def test_parse_date_accepts_exact_portable_formats(dataframe):
    iso = evaluate_expression("parse_date(raw, '%Y-%m-%d')", dataframe)
    slash = evaluate_expression("parse_date(slash, '%d/%m/%Y')", dataframe)

    assert iso.tolist() == [
        date(2026, 7, 30),
        date(2024, 2, 29),
        pd.NA,
        pd.NA,
        pd.NA,
    ]
    assert slash.tolist() == [
        date(2026, 7, 30),
        date(2024, 2, 29),
        pd.NA,
        pd.NA,
        date(2020, 1, 1),
    ]


def test_parse_date_requires_exact_field_width_and_preserves_date_like_values():
    values = pd.DataFrame(
        {
            "value": [
                "2026-7-03",
                date(2026, 7, 3),
                datetime(2026, 7, 4, 23, 59),
                pd.Timestamp("2026-07-05"),
            ]
        }
    )

    result = evaluate_expression("parse_date(value, '%Y-%m-%d')", values)

    assert result.tolist() == [
        pd.NA,
        date(2026, 7, 3),
        date(2026, 7, 4),
        date(2026, 7, 5),
    ]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("parse_date(raw, null)", "expression_null_control"),
        ("parse_date(raw, 1)", "expression_incompatible_type"),
        ("parse_date(raw, format)", "expression_non_scalar_control"),
        ("parse_date(raw, '%Y-%b-%d')", "expression_invalid_date_format"),
        ("parse_date(raw, '%Y-%m')", "expression_invalid_date_format"),
        ("parse_date(raw, '%Y-%Y-%m-%d')", "expression_invalid_date_format"),
        ("parse_date(raw, '%Y-%m-%d%')", "expression_invalid_date_format"),
        ("parse_date(raw, '%Y-%m-%d %H')", "expression_invalid_date_format"),
        ("parse_date(raw, '%Y-%m-%d %z')", "expression_invalid_date_format"),
    ],
)
def test_parse_date_format_errors_are_structured(
    dataframe,
    expression,
    code,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    issue = exc_info.value.issue
    assert issue.code == code
    assert issue.function == "parse_date"
    assert expression[issue.source_span.start : issue.source_span.end]


def test_format_date_accepts_parsed_and_existing_date_values(dataframe):
    parsed = evaluate_expression(
        "format_date(parse_date(raw, '%Y-%m-%d'), '%d.%m.%Y')",
        dataframe,
    )
    existing = pd.DataFrame(
        {
            "value": [
                date(2026, 7, 30),
                datetime(2024, 2, 29, 12, 30),
                pd.Timestamp("2020-01-02"),
                "2026-07-30",
                None,
            ]
        }
    )
    formatted = evaluate_expression("format_date(value, '%Y/%m/%d')", existing)

    assert parsed.tolist() == [
        "30.07.2026",
        "29.02.2024",
        pd.NA,
        pd.NA,
        pd.NA,
    ]
    assert formatted.tolist() == [
        "2026/07/30",
        "2024/02/29",
        "2020/01/02",
        pd.NA,
        pd.NA,
    ]


def test_format_date_supports_subset_fields_and_literal_percent():
    values = pd.DataFrame({"value": [date(2026, 7, 30)]})

    result = evaluate_expression("format_date(value, '%Y-%m %%')", values)

    assert result.tolist() == ["2026-07 %"]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("format_date(value, null)", "expression_null_control"),
        ("format_date(value, '')", "expression_invalid_date_format"),
        ("format_date(value, '%B %d')", "expression_invalid_date_format"),
        ("format_date(value, '%Y-%m-%d %H')", "expression_invalid_date_format"),
    ],
)
def test_format_date_control_errors_are_structured(expression, code):
    values = pd.DataFrame({"value": [date(2026, 7, 30)]})

    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, values)

    assert exc_info.value.issue.code == code
    assert exc_info.value.issue.function == "format_date"


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        ("year", [2026, 2024, pd.NA, pd.NA, pd.NA]),
        ("month", [7, 2, pd.NA, pd.NA, pd.NA]),
        ("day", [30, 29, pd.NA, pd.NA, pd.NA]),
        ("weekday", [4, 4, pd.NA, pd.NA, pd.NA]),
    ],
)
def test_date_parts_use_parsed_dates(dataframe, function, expected):
    result = evaluate_expression(
        f"{function}(parse_date(raw, '%Y-%m-%d'))",
        dataframe,
    )

    assert result.tolist() == expected
    assert str(result.dtype) == "Int64"


def test_weekday_uses_iso_monday_one_sunday_seven():
    values = pd.DataFrame(
        {"value": [date(2026, 7, 27), date(2026, 8, 2), "2026-07-27", None]}
    )

    result = evaluate_expression("weekday(value)", values)

    assert result.tolist() == [1, 7, pd.NA, pd.NA]


def test_date_helpers_reject_timezone_aware_and_unparsed_text_values():
    values = pd.DataFrame(
        {
            "value": [
                pd.Timestamp("2026-07-30", tz="UTC"),
                "2026-07-30",
                None,
            ]
        }
    )

    assert evaluate_expression("year(value)", values).isna().all()
    assert evaluate_expression(
        "format_date(value, '%Y-%m-%d')",
        values,
    ).isna().all()


def test_date_diff_returns_end_minus_start_calendar_days():
    values = pd.DataFrame(
        {
            "start": [
                date(2026, 7, 1),
                date(2026, 7, 10),
                datetime(2026, 7, 1, 23, 59),
                None,
                "2026-07-01",
            ],
            "end": [
                date(2026, 7, 11),
                date(2026, 7, 1),
                datetime(2026, 7, 2, 0, 1),
                date(2026, 7, 2),
                date(2026, 7, 2),
            ],
        }
    )

    result = evaluate_expression("date_diff(start, end)", values)

    assert result.tolist() == [10, -9, 1, pd.NA, pd.NA]


def test_date_diff_supports_nested_parse_date(dataframe):
    result = evaluate_expression(
        (
            "date_diff(parse_date('2026-07-01', '%Y-%m-%d'), "
            "parse_date(raw, '%Y-%m-%d'))"
        ),
        dataframe,
    )

    assert result.tolist() == [29, -853, pd.NA, pd.NA, pd.NA]


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        ("10", date(2026, 8, 9)),
        ("0", date(2026, 7, 30)),
        ("-30", date(2026, 6, 30)),
        ("'2.0'", date(2026, 8, 1)),
    ],
)
def test_add_days_accepts_exact_positive_zero_and_negative_offsets(days, expected):
    values = pd.DataFrame({"value": [date(2026, 7, 30)]})

    result = evaluate_expression(f"add_days(value, {days})", values)

    assert result.tolist() == [expected]


@pytest.mark.parametrize(
    "days",
    ["null", "1.5", "'1.5'", "'bad'", "true", "999999999999999999999"],
)
def test_add_days_invalid_fractional_missing_and_overflow_offsets_return_missing(days):
    values = pd.DataFrame({"value": [date(2026, 7, 30)]})

    result = evaluate_expression(f"add_days(value, {days})", values)

    assert result.isna().all()


def test_add_days_supports_row_aligned_offsets_and_invalid_dates():
    values = pd.DataFrame(
        {
            "value": [date(2026, 7, 30), date(2026, 7, 30), "bad", None],
            "days": [1, -1, 2, 3],
        }
    )

    result = evaluate_expression("add_days(value, days)", values)

    assert result.tolist() == [
        date(2026, 7, 31),
        date(2026, 7, 29),
        pd.NA,
        pd.NA,
    ]


def test_date_helpers_work_in_derive_and_filter_transformations():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "raw": ["2026-07-27", "2026-08-02", "bad"],
                "closed": ["2026-08-01", "2026-08-12", "2026-08-10"],
            }
        )
    )

    parsed = DeriveColumnTransformation(
        "opened_date",
        "parse_date(raw, '%Y-%m-%d')",
    ).apply(dataset)
    derived = DeriveColumnTransformation(
        "due_date",
        "add_days(opened_date, 5)",
    ).apply(parsed)
    derived = DeriveColumnTransformation(
        "label",
        "format_date(due_date, '%Y/%m/%d')",
    ).apply(derived)
    filtered = ExpressionFilterTransformation(
        "weekday(opened_date) <= 5 and year(opened_date) == 2026",
    ).apply(derived)

    assert derived.dataframe["label"].tolist() == [
        "2026/08/01",
        "2026/08/07",
        pd.NA,
    ]
    assert evaluate_expression(
        "date_diff(opened_date, parse_date(closed, '%Y-%m-%d'))",
        derived.dataframe,
    ).tolist() == [5, 10, pd.NA]
    assert filtered.dataframe["raw"].tolist() == ["2026-07-27"]


@pytest.mark.parametrize(
    ("name", "valid_arity"),
    [
        ("parse_date", 2),
        ("format_date", 2),
        ("year", 1),
        ("month", 1),
        ("day", 1),
        ("weekday", 1),
        ("date_diff", 2),
        ("add_days", 2),
    ],
)
def test_date_helpers_enforce_exact_arity(name, valid_arity):
    arguments = ", ".join("value" for _ in range(valid_arity))
    too_many = ", ".join("value" for _ in range(valid_arity + 1))

    assert parse_expression(f"{name}({arguments})").valid is True
    assert parse_expression(f"{name}()").errors[0].code == "wrong_arity"
    assert parse_expression(f"{name}({too_many})").errors[0].code == "wrong_arity"
