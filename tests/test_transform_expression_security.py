import pytest

from statconvert.transformations.expressions import parse_expression


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "open('file')",
        "globals()",
        "eval('1+1')",
    ],
)
def test_dangerous_python_function_names_are_rejected(expression):
    analysis = parse_expression(expression)

    assert analysis.valid is False
    assert analysis.errors[0].code == "unknown_function"


@pytest.mark.parametrize(
    "expression",
    [
        "os.system('x')",
        "email.__class__",
        "email[0]",
        "age = 18",
        "age; open('file')",
        "age # comment",
        "{'a': 1}",
        "[1, 2]",
        "lambda value: value",
        "[value for value in items]",
        'f"{email}"',
    ],
)
def test_code_execution_and_container_syntax_are_rejected(expression):
    analysis = parse_expression(expression)

    assert analysis.valid is False
    assert analysis.errors
    assert 0 <= analysis.errors[0].start <= analysis.errors[0].end <= len(
        expression
    )


def test_indexing_is_rejected_even_when_index_looks_like_column_syntax():
    analysis = parse_expression('email["domain"]')

    assert analysis.valid is False
    assert analysis.errors[0].code == "unexpected_token"


def test_no_analysis_error_exposes_traceback_or_python_execution_details():
    payload = parse_expression("__import__('os')").to_dict()
    serialized = str(payload).casefold()

    assert "traceback" not in serialized
    assert "exec(" not in serialized
