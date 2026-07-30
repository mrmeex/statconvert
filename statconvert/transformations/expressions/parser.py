from __future__ import annotations

from statconvert.error_suggestions import did_you_mean
from statconvert.transformations.language import (
    CORE_EXPRESSION_FUNCTIONS,
    DEFERRED_EXPRESSION_FUNCTIONS,
    EXCLUDED_NON_ROW_LOCAL_FUNCTIONS,
    ExpressionFunctionSpec,
)

from .ast import (
    BinaryOpNode,
    ColumnReferenceNode,
    Expression,
    ExpressionNode,
    FunctionCallNode,
    GroupNode,
    LiteralNode,
    SourceSpan,
    UnaryOpNode,
)
from .errors import ExpressionIssue, ExpressionParseError
from .tokens import Token, TokenKind, tokenize_expression


_CORE_FUNCTIONS = {spec.name: spec for spec in CORE_EXPRESSION_FUNCTIONS}
_DEFERRED_FUNCTIONS = {
    spec.name: spec for spec in DEFERRED_EXPRESSION_FUNCTIONS
}
_COMPARISON_KINDS = {
    TokenKind.EQUAL,
    TokenKind.NOT_EQUAL,
    TokenKind.LESS,
    TokenKind.LESS_EQUAL,
    TokenKind.GREATER,
    TokenKind.GREATER_EQUAL,
}


def parse_expression_ast(expression: str) -> Expression:
    """Parse and validate one expression or raise a structured internal error."""

    tokens = tokenize_expression(expression)
    return _Parser(tokens, len(expression)).parse()


class _Parser:
    def __init__(self, tokens: tuple[Token, ...], expression_length: int) -> None:
        self._tokens = tokens
        self._position = 0
        self._expression_length = expression_length

    def parse(self) -> Expression:
        if self._current.kind == TokenKind.END:
            self._raise(
                "empty_expression",
                "Expression must not be empty.",
                self._current,
                "Enter a column, literal, function call, or operation.",
            )
        root = self._parse_or()
        if self._current.kind != TokenKind.END:
            self._raise_unexpected(self._current)
        return Expression(root=root, span=SourceSpan(0, self._expression_length))

    @property
    def _current(self) -> Token:
        return self._tokens[self._position]

    def _advance(self) -> Token:
        token = self._current
        if token.kind != TokenKind.END:
            self._position += 1
        return token

    def _match(self, *kinds: TokenKind) -> Token | None:
        if self._current.kind not in kinds:
            return None
        return self._advance()

    def _expect(
        self,
        kind: TokenKind,
        *,
        message: str,
        suggestion: str | None = None,
    ) -> Token:
        if self._current.kind == kind:
            return self._advance()
        self._raise(
            "unexpected_token",
            message,
            self._current,
            suggestion,
        )

    def _parse_or(self) -> ExpressionNode:
        node = self._parse_and()
        while (operator := self._match(TokenKind.OR)) is not None:
            right = self._parse_and()
            node = self._binary(node, operator, right)
        return node

    def _parse_and(self) -> ExpressionNode:
        node = self._parse_not()
        while (operator := self._match(TokenKind.AND)) is not None:
            right = self._parse_not()
            node = self._binary(node, operator, right)
        return node

    def _parse_not(self) -> ExpressionNode:
        operator = self._match(TokenKind.NOT)
        if operator is None:
            return self._parse_comparison()
        operand = self._parse_not()
        return UnaryOpNode(
            operator="not",
            operand=operand,
            operator_span=_token_span(operator),
            span=SourceSpan(operator.start, operand.span.end),
        )

    def _parse_comparison(self) -> ExpressionNode:
        node = self._parse_additive()
        operator = self._match(*_COMPARISON_KINDS)
        if operator is None:
            return node
        right = self._parse_additive()
        node = self._binary(node, operator, right)
        if self._current.kind in _COMPARISON_KINDS:
            self._raise(
                "chained_comparison",
                "Chained comparisons are not supported.",
                self._current,
                "Join explicit comparisons with 'and'.",
            )
        return node

    def _parse_additive(self) -> ExpressionNode:
        node = self._parse_multiplicative()
        while (
            operator := self._match(TokenKind.PLUS, TokenKind.MINUS)
        ) is not None:
            right = self._parse_multiplicative()
            node = self._binary(node, operator, right)
        return node

    def _parse_multiplicative(self) -> ExpressionNode:
        node = self._parse_unary_minus()
        while (
            operator := self._match(TokenKind.STAR, TokenKind.SLASH)
        ) is not None:
            right = self._parse_unary_minus()
            node = self._binary(node, operator, right)
        return node

    def _parse_unary_minus(self) -> ExpressionNode:
        operator = self._match(TokenKind.MINUS)
        if operator is None:
            return self._parse_primary()
        operand = self._parse_unary_minus()
        return UnaryOpNode(
            operator="-",
            operand=operand,
            operator_span=_token_span(operator),
            span=SourceSpan(operator.start, operand.span.end),
        )

    def _parse_primary(self) -> ExpressionNode:
        token = self._current
        if token.kind == TokenKind.NUMBER:
            self._advance()
            return LiteralNode(token.value, "number", _token_span(token))
        if token.kind == TokenKind.STRING:
            self._advance()
            return LiteralNode(token.value, "string", _token_span(token))
        if token.kind == TokenKind.BOOLEAN:
            self._advance()
            return LiteralNode(token.value, "boolean", _token_span(token))
        if token.kind == TokenKind.NULL:
            self._advance()
            return LiteralNode(None, "null", _token_span(token))
        if token.kind == TokenKind.COLUMN:
            self._advance()
            return ColumnReferenceNode(
                name=token.value,
                bracketed=True,
                span=_token_span(token),
            )
        if token.kind == TokenKind.IDENTIFIER:
            return self._parse_identifier()
        if token.kind == TokenKind.LEFT_PAREN:
            left = self._advance()
            expression = self._parse_or()
            right = self._expect(
                TokenKind.RIGHT_PAREN,
                message="Expected ')' to close the grouped expression.",
                suggestion="Add a closing parenthesis.",
            )
            return GroupNode(
                expression=expression,
                span=SourceSpan(left.start, right.end),
            )
        self._raise_unexpected(token)

    def _parse_identifier(self) -> ExpressionNode:
        name_token = self._advance()
        if self._match(TokenKind.LEFT_PAREN) is None:
            return ColumnReferenceNode(
                name=name_token.value,
                bracketed=False,
                span=_token_span(name_token),
            )

        arguments: list[ExpressionNode] = []
        if self._current.kind != TokenKind.RIGHT_PAREN:
            while True:
                arguments.append(self._parse_or())
                if self._match(TokenKind.COMMA) is None:
                    break
                if self._current.kind == TokenKind.RIGHT_PAREN:
                    self._raise(
                        "missing_argument",
                        "Function call has a trailing comma without an argument.",
                        self._current,
                        "Remove the comma or add the missing argument.",
                    )
        right = self._expect(
            TokenKind.RIGHT_PAREN,
            message=f"Expected ')' to close function '{name_token.value}'.",
            suggestion="Add a closing parenthesis.",
        )
        spec = self._validate_function(name_token, len(arguments))
        return FunctionCallNode(
            name=spec.name,
            arguments=tuple(arguments),
            name_span=_token_span(name_token),
            span=SourceSpan(name_token.start, right.end),
        )

    def _validate_function(
        self,
        token: Token,
        argument_count: int,
    ) -> ExpressionFunctionSpec:
        name = token.value
        spec = _CORE_FUNCTIONS.get(name)
        if spec is None:
            if name in _DEFERRED_FUNCTIONS:
                self._raise(
                    "deferred_function",
                    f"Function '{name}' is planned but is not implemented yet.",
                    token,
                    "Use a currently supported core function.",
                )
            if name in EXCLUDED_NON_ROW_LOCAL_FUNCTIONS:
                self._raise(
                    "non_row_local_function",
                    f"Function '{name}' is not supported by the row-local "
                    "expression language.",
                    token,
                    "Use a row-local expression; aggregate and window operations "
                    "require separate design.",
                )
            suggestion = did_you_mean(name, _CORE_FUNCTIONS)
            self._raise(
                "unknown_function",
                f"Unknown expression function '{name}'.",
                token,
                suggestion,
            )

        maximum_valid = (
            spec.maximum_arguments is None
            or argument_count <= spec.maximum_arguments
        )
        if argument_count < spec.minimum_arguments or not maximum_valid:
            expected = _format_arity(spec)
            self._raise(
                "wrong_arity",
                f"Function '{name}' expects {expected}; received {argument_count}.",
                token,
                f"Call '{name}' with {expected}.",
            )
        return spec

    def _binary(
        self,
        left: ExpressionNode,
        operator: Token,
        right: ExpressionNode,
    ) -> BinaryOpNode:
        return BinaryOpNode(
            left=left,
            operator=operator.kind.value,
            right=right,
            operator_span=_token_span(operator),
            span=SourceSpan(left.span.start, right.span.end),
        )

    def _raise_unexpected(self, token: Token) -> None:
        if token.kind == TokenKind.END:
            message = "Expression ended before another value was provided."
            suggestion = "Add the missing value or remove the incomplete operator."
        else:
            message = f"Unexpected token {token.kind.value!r}."
            suggestion = "Check expression operators, commas, and parentheses."
        self._raise("unexpected_token", message, token, suggestion)

    def _raise(
        self,
        code: str,
        message: str,
        token: Token,
        suggestion: str | None = None,
    ) -> None:
        raise ExpressionParseError(
            ExpressionIssue(
                code=code,
                message=message,
                start=token.start,
                end=token.end,
                suggestion=suggestion,
            )
        )


def _token_span(token: Token) -> SourceSpan:
    return SourceSpan(token.start, token.end)


def _format_arity(spec: ExpressionFunctionSpec) -> str:
    if spec.maximum_arguments is None:
        count = spec.minimum_arguments
        noun = "argument" if count == 1 else "arguments"
        return f"at least {count} {noun}"
    if spec.minimum_arguments == spec.maximum_arguments:
        count = spec.minimum_arguments
        noun = "argument" if count == 1 else "arguments"
        return f"{count} {noun}"
    return (
        f"{spec.minimum_arguments} to {spec.maximum_arguments} arguments"
    )
