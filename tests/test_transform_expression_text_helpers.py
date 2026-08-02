from __future__ import annotations

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
from statconvert.transformations.expressions.evaluator import (
    MAX_REGEX_INPUT_LENGTH,
    MAX_REGEX_PATTERN_LENGTH,
)


@pytest.fixture
def dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "text": ["banana", None, "café"],
            "code": ["AB-12-12", "plain", None],
            "number": pd.Series([1212, 5, pd.NA], dtype="Int64"),
            "old": ["a", "x", "é"],
            "new": ["X", "Y", "e"],
            "pattern": ["a", "b", "c"],
        }
    )


def test_replace_is_literal_global_and_supports_row_values(dataframe):
    literal = evaluate_expression("replace(text, 'a', 'X')", dataframe)
    dynamic = evaluate_expression("replace(text, old, new)", dataframe)
    numeric = evaluate_expression("replace(number, '1', 'x')", dataframe)

    assert literal.iloc[0] == "bXnXnX"
    assert pd.isna(literal.iloc[1])
    assert literal.iloc[2] == "cXfé"
    assert dynamic.iloc[0] == "bXnXnX"
    assert pd.isna(dynamic.iloc[1])
    assert dynamic.iloc[2] == "cafe"
    assert numeric.iloc[:2].tolist() == ["x2x2", "5"]
    assert pd.isna(numeric.iloc[2])


def test_replace_handles_no_match_empty_search_and_missing_operands(dataframe):
    no_match = evaluate_expression("replace(text, 'z', 'x')", dataframe)
    empty_search = evaluate_expression("replace('ab', '', '-')", dataframe)
    missing_old = evaluate_expression("replace(text, null, 'x')", dataframe)
    missing_new = evaluate_expression("replace(text, 'a', null)", dataframe)

    assert no_match.tolist() == ["banana", pd.NA, "café"]
    assert empty_search == "-a-b-"
    assert missing_old.isna().all()
    assert missing_new.isna().all()


def test_regex_match_searches_converted_values_and_missing_is_false(dataframe):
    text = evaluate_expression("regex_match(text, '^ba')", dataframe)
    numeric = evaluate_expression("regex_match(number, '^12')", dataframe)

    assert text.tolist() == [True, False, False]
    assert numeric.tolist() == [True, False, False]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("regex_match(text, '[')", "expression_invalid_regex"),
        ("regex_match(text, null)", "expression_null_control"),
        ("regex_match(text, pattern)", "expression_non_scalar_control"),
    ],
)
def test_regex_match_rejects_invalid_or_non_scalar_patterns(
    dataframe,
    expression,
    code,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    issue = exc_info.value.issue
    assert issue.code == code
    assert issue.function == "regex_match"
    assert expression[issue.source_span.start : issue.source_span.end]


def test_regex_limits_raise_structured_errors(dataframe):
    pattern = "a" * (MAX_REGEX_PATTERN_LENGTH + 1)
    with pytest.raises(ExpressionEvaluationError) as pattern_error:
        evaluate_expression(f"regex_match(text, '{pattern}')", dataframe)

    long_values = pd.DataFrame({"value": ["a" * (MAX_REGEX_INPUT_LENGTH + 1)]})
    with pytest.raises(ExpressionEvaluationError) as input_error:
        evaluate_expression("regex_match(value, 'a')", long_values)

    assert pattern_error.value.issue.code == "expression_regex_pattern_too_long"
    assert input_error.value.issue.code == "expression_regex_input_too_long"


def test_regex_replace_is_global_and_supports_converted_values(dataframe):
    replaced = evaluate_expression(
        "regex_replace(code, '[0-9]+', '#')",
        dataframe,
    )
    numeric = evaluate_expression(
        "regex_replace(number, '1', 9)",
        dataframe,
    )

    assert replaced.tolist() == ["AB-#-#", "plain", pd.NA]
    assert numeric.tolist() == ["9292", "5", pd.NA]


def test_regex_replace_missing_values_and_replacement_return_missing(dataframe):
    missing_replacement = evaluate_expression(
        "regex_replace(text, 'a', null)",
        dataframe,
    )

    assert missing_replacement.isna().all()


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("regex_replace(text, null, 'x')", "expression_null_control"),
        ("regex_replace(text, '[', 'x')", "expression_invalid_regex"),
        (
            r"regex_replace(text, '(a)', '\\2')",
            "expression_invalid_regex_replacement",
        ),
    ],
)
def test_regex_replace_reports_pattern_and_replacement_errors(
    dataframe,
    expression,
    code,
):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == code
    assert exc_info.value.issue.function == "regex_replace"


def test_length_counts_converted_unicode_and_missing_values(dataframe):
    text = evaluate_expression("length(text)", dataframe)
    numeric = evaluate_expression("length(number)", dataframe)

    assert text.tolist() == [6, pd.NA, 4]
    assert numeric.tolist() == [4, 1, pd.NA]
    assert evaluate_expression("length('')", dataframe) == 0


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("substring('abcdef', 0, 3)", "abc"),
        ("substring('abcdef', 2, 5)", "cde"),
        ("substring('abcdef', 2, 2)", ""),
        ("substring('abcdef', 4, 2)", ""),
        ("substring(123456, 1, 4)", "234"),
    ],
)
def test_substring_uses_zero_based_exclusive_indexes(
    dataframe,
    expression,
    expected,
):
    assert evaluate_expression(expression, dataframe) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "substring('abcdef', -1, 3)",
        "substring('abcdef', 1.5, 3)",
        "substring('abcdef', null, 3)",
        "substring('abcdef', 1, 'x')",
    ],
)
def test_substring_invalid_indexes_return_missing(dataframe, expression):
    assert pd.isna(evaluate_expression(expression, dataframe))


def test_substring_rejects_series_indexes(dataframe):
    expression = "substring(text, number, 3)"

    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == "expression_non_scalar_control"
    assert exc_info.value.issue.function == "substring"


def test_concat_is_variadic_and_missing_contributes_empty_text(dataframe):
    one = evaluate_expression("concat(text)", dataframe)
    many = evaluate_expression("concat(text, '-', number, '!')", dataframe)

    assert one.tolist() == ["banana", "", "café"]
    assert many.tolist() == ["banana-1212!", "-5!", "café-!"]
    assert evaluate_expression("concat(null)", dataframe) == ""
    assert evaluate_expression("concat(null, null)", dataframe) == ""


def test_remove_accents_uses_unicode_normalization_and_converts_values(dataframe):
    result = evaluate_expression("remove_accents(text)", dataframe)
    numeric = evaluate_expression("remove_accents(number)", dataframe)

    assert result.tolist() == ["banana", pd.NA, "cafe"]
    assert numeric.tolist() == ["1212", "5", pd.NA]
    assert evaluate_expression("remove_accents('naïve—test!')", dataframe) == (
        "naive—test!"
    )


def test_text_helpers_work_in_derive_and_filter_transformations():
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "name": ["José", "Alice", None],
                "code": ["AB-1", "xx", "AB-2"],
            }
        )
    )

    derived = DeriveColumnTransformation(
        "label",
        "concat(remove_accents(name), ':', replace(code, '-', ''))",
    ).apply(dataset)
    filtered = ExpressionFilterTransformation(
        "regex_match(code, '^AB-') and length(code) == 4",
    ).apply(derived)

    assert derived.dataframe["label"].tolist() == [
        "Jose:AB1",
        "Alice:xx",
        ":AB2",
    ]
    assert filtered.dataframe["code"].tolist() == ["AB-1", "AB-2"]


def test_concat_zero_arguments_is_source_spanned_arity_error():
    analysis = parse_expression("concat()")

    assert analysis.valid is False
    assert analysis.errors[0].code == "wrong_arity"
    assert (analysis.errors[0].start, analysis.errors[0].end) == (0, 6)
    assert "at least 1 argument" in analysis.errors[0].message
