import pytest

from statconvert.transformations.expressions import (
    BinaryOpNode,
    ColumnReferenceNode,
    FunctionCallNode,
    GroupNode,
    LiteralNode,
    UnaryOpNode,
    parse_expression,
    parse_expression_ast,
)


def test_parser_parses_plain_and_bracketed_column_references():
    plain = parse_expression_ast("email").root
    bracketed = parse_expression_ast('["Email Address"]').root

    assert plain == ColumnReferenceNode(
        name="email",
        bracketed=False,
        span=plain.span,
    )
    assert bracketed.name == "Email Address"
    assert bracketed.bracketed is True


@pytest.mark.parametrize(
    ("expression", "kind", "value"),
    [
        ("'NL'", "string", "NL"),
        ("123", "number", 123),
        ("123.45", "number", 123.45),
        ("true", "boolean", True),
        ("false", "boolean", False),
        ("null", "null", None),
    ],
)
def test_parser_parses_literals(expression, kind, value):
    node = parse_expression_ast(expression).root

    assert isinstance(node, LiteralNode)
    assert node.literal_kind == kind
    assert node.value == value


def test_parser_parses_nested_function_calls():
    node = parse_expression_ast("lower(strip(email))").root

    assert isinstance(node, FunctionCallNode)
    assert node.name == "lower"
    assert isinstance(node.arguments[0], FunctionCallNode)
    assert node.arguments[0].name == "strip"
    assert node.name_span.to_dict() == {"start": 0, "end": 5}


def test_parser_parses_if_else_with_comparison():
    node = parse_expression_ast(
        "if_else(age >= 18, 'adult', 'minor')"
    ).root

    assert isinstance(node, FunctionCallNode)
    assert node.name == "if_else"
    assert isinstance(node.arguments[0], BinaryOpNode)
    assert node.arguments[0].operator == ">="


def test_parser_applies_arithmetic_precedence():
    node = parse_expression_ast("1 + 2 * 3").root

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "+"
    assert isinstance(node.right, BinaryOpNode)
    assert node.right.operator == "*"


def test_parser_preserves_group_span_and_overrides_precedence():
    node = parse_expression_ast("(1 + 2) * 3").root

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "*"
    assert isinstance(node.left, GroupNode)
    assert node.left.span.to_dict() == {"start": 0, "end": 7}


def test_parser_applies_boolean_precedence_and_predicate_not():
    node = parse_expression_ast(
        "not age >= 18 or active and consent"
    ).root

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "or"
    assert isinstance(node.left, UnaryOpNode)
    assert node.left.operator == "not"
    assert isinstance(node.left.operand, BinaryOpNode)
    assert node.left.operand.operator == ">="
    assert isinstance(node.right, BinaryOpNode)
    assert node.right.operator == "and"


def test_parser_parses_recursive_unary_minus():
    node = parse_expression_ast("--amount").root

    assert isinstance(node, UnaryOpNode)
    assert isinstance(node.operand, UnaryOpNode)


@pytest.mark.parametrize(
    "expression",
    [
        "strip(value)",
        "lower(value)",
        "upper(value)",
        "contains(value, 'x')",
        "starts_with(value, 'x')",
        "ends_with(value, 'x')",
        "abs(value)",
        "round(value, 2)",
        "is_null(value)",
        "not_null(value)",
        "coalesce(value, 'fallback')",
        "if_else(active, 'yes', 'no')",
        "replace(value, 'x', 'y')",
        "regex_match(value, '^x')",
        "regex_replace(value, 'x', 'y')",
        "length(value)",
        "substring(value, 0, 2)",
        "concat(value)",
        "concat(value, '-', other, 3)",
        "remove_accents(value)",
        "to_string(value)",
        "to_number(value)",
        "to_integer(value)",
        "to_float(value)",
        "to_boolean(value)",
        "parse_date(value, '%Y-%m-%d')",
        "format_date(value, '%Y-%m-%d')",
        "year(value)",
        "month(value)",
        "day(value)",
        "weekday(value)",
        "date_diff(value, other)",
        "add_days(value, 1)",
        "between(value, 0, 10)",
        "is_in(value, 1)",
        "is_in(value, 1, 2, 3)",
        "not_in(value, 1)",
        "not_in(value, 1, 2, 3)",
        "is_number(value)",
        "is_date(value, '%Y-%m-%d')",
        "is_email(value)",
    ],
)
def test_parser_accepts_every_core_function_with_valid_arity(expression):
    assert parse_expression(expression).valid is True


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("lower()", "wrong_arity"),
        ("round(value)", "wrong_arity"),
        ("if_else(active, 1)", "wrong_arity"),
        ("LOWER(value)", "unknown_function"),
        ("mystery(value)", "unknown_function"),
        ("replace(value, 'x')", "wrong_arity"),
        ("substring(value, 0)", "wrong_arity"),
        ("concat()", "wrong_arity"),
        ("parse_date(value)", "wrong_arity"),
        ("date_diff(value, other, 1)", "wrong_arity"),
        ("between(value, 0)", "wrong_arity"),
        ("is_in(value)", "wrong_arity"),
        ("not_in(value)", "wrong_arity"),
        ("is_date(value)", "wrong_arity"),
        ("to_date(value)", "unknown_function"),
        ("sum(value)", "non_row_local_function"),
        ("lag(value)", "non_row_local_function"),
        ("group_by(value)", "non_row_local_function"),
        ("1 < age < 100", "chained_comparison"),
        ("contains(value,)", "missing_argument"),
        ("(age + 1", "unexpected_token"),
        ("age +", "unexpected_token"),
    ],
)
def test_parser_rejects_invalid_functions_and_syntax(expression, code):
    analysis = parse_expression(expression)

    assert analysis.valid is False
    assert analysis.errors[0].code == code
    assert 0 <= analysis.errors[0].start <= analysis.errors[0].end <= len(
        expression
    )


def test_unknown_function_error_highlights_function_name():
    analysis = parse_expression("mystery(email)")

    assert analysis.errors[0].to_dict() == {
        "code": "unknown_function",
        "message": "Unknown expression function 'mystery'.",
        "start": 0,
        "end": 7,
    }


def test_wrong_arity_error_highlights_function_name():
    analysis = parse_expression("lower(email, country)")

    assert analysis.errors[0].code == "wrong_arity"
    assert (analysis.errors[0].start, analysis.errors[0].end) == (0, 5)
    assert analysis.errors[0].suggestion is not None
