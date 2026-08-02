import pytest

from statconvert.transformations.expressions import (
    ExpressionParseError,
    TokenKind,
    tokenize_expression,
)


def _tokens(expression):
    return tokenize_expression(expression)[:-1]


def test_tokenizer_emits_identifiers_keywords_literals_and_spans():
    expression = "age >= 18 and active == true or value != null"

    tokens = _tokens(expression)

    assert [token.kind for token in tokens] == [
        TokenKind.IDENTIFIER,
        TokenKind.GREATER_EQUAL,
        TokenKind.NUMBER,
        TokenKind.AND,
        TokenKind.IDENTIFIER,
        TokenKind.EQUAL,
        TokenKind.BOOLEAN,
        TokenKind.OR,
        TokenKind.IDENTIFIER,
        TokenKind.NOT_EQUAL,
        TokenKind.NULL,
    ]
    assert tokens[0].value == "age"
    assert (tokens[0].start, tokens[0].end) == (0, 3)
    assert expression[tokens[1].start : tokens[1].end] == ">="
    assert tokens[6].value is True
    assert tokens[-1].value is None


def test_tokenizer_supports_all_arithmetic_comparison_and_punctuation_tokens():
    tokens = _tokens("(a + 1) * 2 / 3 - 4 < 5 <= 6 > 0 >= -1, false")

    assert [token.kind for token in tokens] == [
        TokenKind.LEFT_PAREN,
        TokenKind.IDENTIFIER,
        TokenKind.PLUS,
        TokenKind.NUMBER,
        TokenKind.RIGHT_PAREN,
        TokenKind.STAR,
        TokenKind.NUMBER,
        TokenKind.SLASH,
        TokenKind.NUMBER,
        TokenKind.MINUS,
        TokenKind.NUMBER,
        TokenKind.LESS,
        TokenKind.NUMBER,
        TokenKind.LESS_EQUAL,
        TokenKind.NUMBER,
        TokenKind.GREATER,
        TokenKind.NUMBER,
        TokenKind.GREATER_EQUAL,
        TokenKind.MINUS,
        TokenKind.NUMBER,
        TokenKind.COMMA,
        TokenKind.BOOLEAN,
    ]


def test_tokenizer_supports_single_and_double_quoted_strings():
    tokens = _tokens(r"""'NL' "line\nvalue" 'it\'s'""")

    assert [token.value for token in tokens] == ["NL", "line\nvalue", "it's"]
    assert all(token.kind == TokenKind.STRING for token in tokens)


def test_tokenizer_supports_bracketed_json_column_reference():
    expression = 'lower(["Email Address"])'

    tokens = _tokens(expression)
    column = tokens[2]

    assert column.kind == TokenKind.COLUMN
    assert column.value == "Email Address"
    assert expression[column.start : column.end] == '["Email Address"]'


def test_tokenizer_decodes_json_escapes_in_bracketed_column_reference():
    token = _tokens(r'["country\u002dcode"]')[0]

    assert token.value == "country-code"


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("'unterminated", "unterminated_string"),
        (r"'bad\q'", "invalid_escape"),
        ('["unterminated"', "malformed_column_reference"),
        ("['single quotes']", "malformed_column_reference"),
        ('[""]', "empty_column_reference"),
        ('["name"', "malformed_column_reference"),
        ("[name]", "malformed_column_reference"),
        ("age = 18", "invalid_character"),
        ("age # comment", "invalid_character"),
        ("age; open('x')", "invalid_character"),
        ("import", "disallowed_keyword"),
    ],
)
def test_tokenizer_returns_precise_errors(expression, code):
    with pytest.raises(ExpressionParseError) as exc_info:
        tokenize_expression(expression)

    issue = exc_info.value.issue
    assert issue.code == code
    assert 0 <= issue.start <= issue.end <= len(expression)


def test_tokenizer_emits_end_marker_at_source_end():
    token = tokenize_expression(" email ")[-1]

    assert token.kind == TokenKind.END
    assert (token.start, token.end) == (7, 7)
