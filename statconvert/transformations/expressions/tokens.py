from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import re
from typing import Any

from .errors import ExpressionIssue, ExpressionParseError


class TokenKind(StrEnum):
    """Closed token kinds accepted by the transform expression language."""

    IDENTIFIER = "identifier"
    COLUMN = "column"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"
    AND = "and"
    OR = "or"
    NOT = "not"
    EQUAL = "=="
    NOT_EQUAL = "!="
    LESS = "<"
    LESS_EQUAL = "<="
    GREATER = ">"
    GREATER_EQUAL = ">="
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    LEFT_PAREN = "("
    RIGHT_PAREN = ")"
    COMMA = ","
    END = "end"


@dataclass(frozen=True)
class Token:
    """One token and its half-open source span."""

    kind: TokenKind
    value: Any
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe token metadata."""

        return {
            "kind": self.kind.value,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
_KEYWORDS = {
    "and": TokenKind.AND,
    "or": TokenKind.OR,
    "not": TokenKind.NOT,
}
_LITERALS: dict[str, tuple[TokenKind, object]] = {
    "true": (TokenKind.BOOLEAN, True),
    "false": (TokenKind.BOOLEAN, False),
    "null": (TokenKind.NULL, None),
}
_DISALLOWED_PYTHON_KEYWORDS = {
    "as",
    "assert",
    "async",
    "await",
    "break",
    "case",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "match",
    "nonlocal",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield",
}
_TWO_CHARACTER_OPERATORS = {
    "==": TokenKind.EQUAL,
    "!=": TokenKind.NOT_EQUAL,
    "<=": TokenKind.LESS_EQUAL,
    ">=": TokenKind.GREATER_EQUAL,
}
_ONE_CHARACTER_TOKENS = {
    "<": TokenKind.LESS,
    ">": TokenKind.GREATER,
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "(": TokenKind.LEFT_PAREN,
    ")": TokenKind.RIGHT_PAREN,
    ",": TokenKind.COMMA,
}
_ESCAPES = {
    "\\": "\\",
    "'": "'",
    '"': '"',
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


def tokenize_expression(expression: str) -> tuple[Token, ...]:
    """Tokenize one expression without invoking Python parsing or evaluation."""

    if not isinstance(expression, str):
        raise TypeError("Expression must be a string.")

    tokens: list[Token] = []
    position = 0
    while position < len(expression):
        character = expression[position]
        if character.isspace():
            position += 1
            continue

        if character == "[":
            token, position = _read_bracketed_column(expression, position)
            tokens.append(token)
            continue

        if character in {"'", '"'}:
            token, position = _read_string(expression, position)
            tokens.append(token)
            continue

        identifier_match = _IDENTIFIER.match(expression, position)
        if identifier_match is not None:
            text = identifier_match.group(0)
            end = identifier_match.end()
            if text in _DISALLOWED_PYTHON_KEYWORDS:
                _raise(
                    "disallowed_keyword",
                    f"Python keyword '{text}' is not allowed in expressions.",
                    position,
                    end,
                    "Use only column names, registered functions, and approved literals.",
                )
            literal = _LITERALS.get(text)
            if literal is not None:
                kind, value = literal
            else:
                kind = _KEYWORDS.get(text, TokenKind.IDENTIFIER)
                value = text
            tokens.append(Token(kind, value, position, end))
            position = end
            continue

        number_match = _NUMBER.match(expression, position)
        if number_match is not None:
            text = number_match.group(0)
            end = number_match.end()
            value: int | float = float(text) if "." in text else int(text)
            tokens.append(Token(TokenKind.NUMBER, value, position, end))
            position = end
            continue

        pair = expression[position : position + 2]
        pair_kind = _TWO_CHARACTER_OPERATORS.get(pair)
        if pair_kind is not None:
            tokens.append(Token(pair_kind, pair, position, position + 2))
            position += 2
            continue

        single_kind = _ONE_CHARACTER_TOKENS.get(character)
        if single_kind is not None:
            tokens.append(Token(single_kind, character, position, position + 1))
            position += 1
            continue

        _raise_invalid_character(expression, position)

    tokens.append(Token(TokenKind.END, None, len(expression), len(expression)))
    return tuple(tokens)


def _read_string(expression: str, start: int) -> tuple[Token, int]:
    quote = expression[start]
    position = start + 1
    characters: list[str] = []
    while position < len(expression):
        character = expression[position]
        if character == quote:
            end = position + 1
            return Token(TokenKind.STRING, "".join(characters), start, end), end
        if character in "\r\n":
            _raise(
                "unterminated_string",
                "String literal is not terminated.",
                start,
                position,
                f"Add a closing {quote} quote.",
            )
        if character != "\\":
            characters.append(character)
            position += 1
            continue

        escape_start = position
        position += 1
        if position >= len(expression):
            _raise(
                "unterminated_string",
                "String literal is not terminated.",
                start,
                len(expression),
                f"Add a closing {quote} quote.",
            )
        escape = expression[position]
        if escape == "u":
            code_end = position + 5
            code = expression[position + 1 : code_end]
            if len(code) != 4 or not all(
                character in "0123456789abcdefABCDEF" for character in code
            ):
                _raise(
                    "invalid_escape",
                    "Unicode escapes must contain exactly four hexadecimal digits.",
                    escape_start,
                    min(code_end, len(expression)),
                )
            characters.append(chr(int(code, 16)))
            position = code_end
            continue
        replacement = _ESCAPES.get(escape)
        if replacement is None:
            _raise(
                "invalid_escape",
                f"Unsupported string escape '\\{escape}'.",
                escape_start,
                position + 1,
                "Use a standard quoted-string escape.",
            )
        characters.append(replacement)
        position += 1

    _raise(
        "unterminated_string",
        "String literal is not terminated.",
        start,
        len(expression),
        f"Add a closing {quote} quote.",
    )


def _read_bracketed_column(expression: str, start: int) -> tuple[Token, int]:
    position = start + 1
    while position < len(expression) and expression[position].isspace():
        position += 1
    if position >= len(expression) or expression[position] != '"':
        _raise(
            "malformed_column_reference",
            "Bracketed column references require a JSON double-quoted name.",
            start,
            min(start + 1, len(expression)),
            'Use syntax such as ["Email Address"].',
        )

    string_start = position
    position += 1
    escaped = False
    while position < len(expression):
        character = expression[position]
        if character in "\r\n":
            break
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            position += 1
            break
        position += 1
    else:
        _raise(
            "malformed_column_reference",
            "Bracketed column reference is not terminated.",
            start,
            len(expression),
            'Add the closing quote and bracket, for example ["Email Address"].',
        )

    if position > len(expression) or expression[position - 1] != '"':
        _raise(
            "malformed_column_reference",
            "Bracketed column reference is not terminated.",
            start,
            min(position, len(expression)),
            'Add the closing quote and bracket, for example ["Email Address"].',
        )

    encoded_name = expression[string_start:position]
    try:
        name = json.loads(encoded_name)
    except json.JSONDecodeError as exc:
        error_start = string_start + max(exc.pos - 1, 0)
        _raise(
            "malformed_column_reference",
            "Bracketed column reference contains invalid JSON string syntax.",
            error_start,
            min(error_start + 1, len(expression)),
            'Use a valid JSON-quoted name, for example ["Email Address"].',
        )
    if not isinstance(name, str) or not name:
        _raise(
            "empty_column_reference",
            "Bracketed column reference must not be empty.",
            string_start,
            position,
            "Provide a non-empty column name.",
        )

    while position < len(expression) and expression[position].isspace():
        position += 1
    if position >= len(expression) or expression[position] != "]":
        _raise(
            "malformed_column_reference",
            "Bracketed column reference requires a closing ']'.",
            start,
            min(position + 1, len(expression)),
            'Use syntax such as ["Email Address"].',
        )
    end = position + 1
    return Token(TokenKind.COLUMN, name, start, end), end


def _raise_invalid_character(expression: str, position: int) -> None:
    character = expression[position]
    messages = {
        "=": (
            "Assignment is not allowed in expressions.",
            "Use '==' for equality comparison.",
        ),
        ".": (
            "Attribute access and indexing are not allowed in expressions.",
            "Use a plain or bracketed column reference.",
        ),
        ";": (
            "Semicolon-separated statements are not allowed in expressions.",
            None,
        ),
        "#": (
            "Comments are not allowed in expressions.",
            None,
        ),
        "{": (
            "Dictionary literals are not allowed in expressions.",
            None,
        ),
        "}": (
            "Dictionary literals are not allowed in expressions.",
            None,
        ),
        "]": (
            "Indexing and unmatched brackets are not allowed in expressions.",
            'Use ["Column Name"] only as a complete column reference.',
        ),
        ":": (
            "Colon syntax is not allowed in expressions.",
            None,
        ),
    }
    message, suggestion = messages.get(
        character,
        (f"Invalid expression character {character!r}.", None),
    )
    _raise(
        "invalid_character",
        message,
        position,
        position + 1,
        suggestion,
    )


def _raise(
    code: str,
    message: str,
    start: int,
    end: int,
    suggestion: str | None = None,
) -> None:
    raise ExpressionParseError(
        ExpressionIssue(
            code=code,
            message=message,
            start=start,
            end=end,
            suggestion=suggestion,
        )
    )
