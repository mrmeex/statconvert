from __future__ import annotations

import pandas as pd
import pytest

from statconvert.transformations.expressions import (
    ExpressionEvaluationError,
    evaluate_expression,
    parse_expression,
)


@pytest.fixture
def dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["  New\t York\n City  ", None, "Already clean"],
            "code": ["  ab\t12 ", pd.NA, "Cd"],
            "note": ["", " \t\n ", None],
            "value": ["missing", "kept", None],
            "match_value": ["missing", "other", None],
            "fallback": ["first", "second", "third"],
            "amount": [1, 2, 3],
        }
    )


def test_helper_parser_metadata_and_result_kinds_are_deterministic():
    analysis = parse_expression(
        "normalize_code(normalize_whitespace(code)) == "
        "default_if_missing(null_if_empty(note), 'x')"
    )

    assert analysis.valid is True
    assert analysis.functions == (
        "normalize_code",
        "normalize_whitespace",
        "default_if_missing",
        "null_if_empty",
    )
    assert analysis.row_local is True
    assert analysis.previewable is True
    assert analysis.result_kind == "boolean"

    expected_kinds = {
        "normalize_whitespace(name)": "string",
        "normalize_code(code)": "string",
        "null_if(value, 'missing')": "unknown",
        "null_if_empty(note)": "string",
        "default_if_missing(amount, 0)": "unknown",
        "default_if_missing(null, 0)": "number",
    }
    for expression, result_kind in expected_kinds.items():
        parsed = parse_expression(expression)
        assert parsed.valid is True
        assert parsed.result_kind == result_kind


@pytest.mark.parametrize(
    "expression",
    [
        "normalize_whitespace()",
        "normalize_whitespace(name, code)",
        "null_if(value)",
        "null_if(value, match_value, 'extra')",
        "null_if_empty()",
        "default_if_missing(value)",
        "normalize_code()",
    ],
)
def test_helper_wrong_arity_is_rejected(expression):
    analysis = parse_expression(expression)

    assert analysis.valid is False
    assert analysis.errors[0].code == "wrong_arity"


def test_normalize_whitespace_trims_collapses_and_preserves_missing(dataframe):
    result = evaluate_expression("normalize_whitespace(name)", dataframe)

    assert result.iloc[0] == "New York City"
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == "Already clean"


def test_normalize_code_normalizes_text_and_preserves_missing(dataframe):
    result = evaluate_expression("normalize_code(code)", dataframe)

    assert result.iloc[0] == "AB 12"
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == "CD"


@pytest.mark.parametrize(
    "expression",
    ["normalize_whitespace(amount)", "normalize_code(amount)"],
)
def test_normalization_helpers_reject_non_string_values(dataframe, expression):
    with pytest.raises(ExpressionEvaluationError) as exc_info:
        evaluate_expression(expression, dataframe)

    assert exc_info.value.issue.code == "expression_incompatible_type"


def test_null_if_handles_scalar_and_series_matches(dataframe):
    literal = evaluate_expression("null_if(value, 'missing')", dataframe)
    series = evaluate_expression("null_if(value, match_value)", dataframe)

    assert pd.isna(literal.iloc[0])
    assert literal.iloc[1] == "kept"
    assert pd.isna(literal.iloc[2])
    assert pd.isna(series.iloc[0])
    assert series.iloc[1] == "kept"
    assert pd.isna(series.iloc[2])


def test_null_if_with_missing_match_preserves_non_missing_values(dataframe):
    result = evaluate_expression("null_if(value, null)", dataframe)

    assert result.iloc[0] == "missing"
    assert result.iloc[1] == "kept"
    assert pd.isna(result.iloc[2])


def test_null_if_empty_detects_trimmed_empty_but_preserves_original_non_empty():
    dataframe = pd.DataFrame({"note": ["", " \t ", "  keep me  ", None]})

    result = evaluate_expression("null_if_empty(note)", dataframe)

    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == "  keep me  "
    assert pd.isna(result.iloc[3])


def test_default_if_missing_aligns_fallback_and_preserves_existing(dataframe):
    scalar = evaluate_expression("default_if_missing(value, 'default')", dataframe)
    series = evaluate_expression("default_if_missing(value, fallback)", dataframe)

    assert scalar.tolist() == ["missing", "kept", "default"]
    assert series.tolist() == ["missing", "kept", "third"]


def test_helpers_work_in_nested_expressions(dataframe):
    result = evaluate_expression(
        "normalize_code(default_if_missing(null_if_empty(code), 'unknown'))",
        dataframe,
    )

    assert result.tolist() == ["AB 12", "UNKNOWN", "CD"]
