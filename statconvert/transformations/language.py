from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressionArgumentSpec:
    """JSON-safe function argument metadata for future expression editors."""

    name: str
    kind: str
    accepted_types: tuple[str, ...]
    required: bool = True
    variadic: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe argument metadata."""

        return {
            "name": self.name,
            "kind": self.kind,
            "accepted_types": list(self.accepted_types),
            "required": self.required,
            "variadic": self.variadic,
        }


@dataclass(frozen=True)
class ExpressionFunctionSpec:
    """Non-executing metadata for one safe expression function."""

    name: str
    category: str
    minimum_arguments: int
    maximum_arguments: int | None
    result_kind: str
    row_local: bool = True
    previewable: bool = True
    deferred: bool = False
    signature: str | None = None
    description: str | None = None
    arguments: tuple[ExpressionArgumentSpec, ...] = ()
    examples: tuple[str, ...] = ()
    derive_allowed: bool = True
    filter_suitability: str = "composable"
    null_behavior: str | None = None
    error_behavior: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe function metadata."""

        arity: object
        if (
            self.maximum_arguments is not None
            and self.minimum_arguments == self.maximum_arguments
        ):
            arity = self.minimum_arguments
        else:
            arity = {
                "minimum": self.minimum_arguments,
                "maximum": self.maximum_arguments,
            }
        return {
            "name": self.name,
            "category": self.category,
            "arity": arity,
            "minimum_arguments": self.minimum_arguments,
            "maximum_arguments": self.maximum_arguments,
            "row_local": self.row_local,
            "previewable": self.previewable,
            "result_kind": self.result_kind,
            "return_type": self.result_kind,
            "deferred": self.deferred,
            "signature": self.signature,
            "description": self.description,
            "arguments": [argument.to_dict() for argument in self.arguments],
            "examples": list(self.examples),
            "derive_allowed": self.derive_allowed,
            "filter_suitability": self.filter_suitability,
            "null_behavior": self.null_behavior,
            "error_behavior": self.error_behavior,
        }


CORE_EXPRESSION_FUNCTIONS: tuple[ExpressionFunctionSpec, ...] = (
    ExpressionFunctionSpec("strip", "text", 1, 1, "string"),
    ExpressionFunctionSpec("lower", "text", 1, 1, "string"),
    ExpressionFunctionSpec("upper", "text", 1, 1, "string"),
    ExpressionFunctionSpec("contains", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("starts_with", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("ends_with", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("abs", "numeric", 1, 1, "number"),
    ExpressionFunctionSpec("round", "numeric", 2, 2, "number"),
    ExpressionFunctionSpec("is_null", "missing", 1, 1, "boolean"),
    ExpressionFunctionSpec("not_null", "missing", 1, 1, "boolean"),
    ExpressionFunctionSpec("coalesce", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("normalize_whitespace", "text", 1, 1, "string"),
    ExpressionFunctionSpec("null_if", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("null_if_empty", "missing", 1, 1, "string"),
    ExpressionFunctionSpec("default_if_missing", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("normalize_code", "normalization", 1, 1, "string"),
    ExpressionFunctionSpec("if_else", "conditional", 3, 3, "dynamic"),
    ExpressionFunctionSpec(
        name="replace",
        category="text",
        minimum_arguments=3,
        maximum_arguments=3,
        result_kind="string",
        signature="replace(value, old, new)",
        description="Replace all literal occurrences after deterministic text conversion.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "old",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "new",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("replace(code, '-', '')",),
        null_behavior="Missing value, old, or new returns missing.",
        error_behavior="Unsupported non-missing values return missing.",
    ),
    ExpressionFunctionSpec(
        name="regex_match",
        category="text",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="boolean",
        signature="regex_match(value, pattern)",
        description="Search deterministically converted text with a bounded scalar regex.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "pattern",
                "scalar_control",
                ("string",),
            ),
        ),
        examples=("regex_match(code, '^[A-Z]{2}$')",),
        filter_suitability="direct",
        null_behavior="Missing value returns false; pattern must not be missing.",
        error_behavior=(
            "Non-scalar, null, invalid, or oversized patterns and oversized inputs "
            "produce structured expression errors."
        ),
    ),
    ExpressionFunctionSpec(
        name="regex_replace",
        category="text",
        minimum_arguments=3,
        maximum_arguments=3,
        result_kind="string",
        signature="regex_replace(value, pattern, replacement)",
        description="Replace every scalar-regex match in deterministically converted text.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "pattern",
                "scalar_control",
                ("string",),
            ),
            ExpressionArgumentSpec(
                "replacement",
                "scalar_control",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("regex_replace(phone, '[^0-9]', '')",),
        null_behavior=(
            "Missing value or replacement returns missing; pattern must not be missing."
        ),
        error_behavior=(
            "Non-scalar, null, invalid, or oversized patterns, invalid replacement "
            "syntax, and oversized inputs produce structured expression errors."
        ),
    ),
    ExpressionFunctionSpec(
        name="length",
        category="text",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="length(value)",
        description="Return the character length after deterministic text conversion.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("length(strip(name))",),
        null_behavior="Missing value returns missing.",
        error_behavior="Unsupported non-missing values return missing.",
    ),
    ExpressionFunctionSpec(
        name="substring",
        category="text",
        minimum_arguments=3,
        maximum_arguments=3,
        result_kind="string",
        signature="substring(value, start, end)",
        description="Return a zero-based substring with an exclusive end index.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "start",
                "scalar_control",
                ("integer", "integer-convertible"),
            ),
            ExpressionArgumentSpec(
                "end",
                "scalar_control",
                ("integer", "integer-convertible"),
            ),
        ),
        examples=("substring(code, 0, 2)",),
        null_behavior="Missing value or invalid indexes return missing.",
        error_behavior="Negative, fractional, or non-convertible indexes return missing.",
    ),
    ExpressionFunctionSpec(
        name="concat",
        category="text",
        minimum_arguments=1,
        maximum_arguments=None,
        result_kind="string",
        signature="concat(value1, value2, ...)",
        description="Concatenate one or more deterministically converted values.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
                variadic=True,
            ),
        ),
        examples=("concat(first, ' ', last)",),
        null_behavior="Each missing value contributes an empty string.",
        error_behavior="Unsupported non-missing values make the row missing.",
    ),
    ExpressionFunctionSpec(
        name="remove_accents",
        category="text",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="string",
        signature="remove_accents(value)",
        description="Remove Unicode combining marks using standard-library normalization.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("remove_accents(city)",),
        null_behavior="Missing value returns missing.",
        error_behavior="Unsupported non-missing values return missing.",
    ),
    ExpressionFunctionSpec(
        name="to_string",
        category="conversion",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="string",
        signature="to_string(value)",
        description="Convert supported scalar values to deterministic text.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("to_string(record_id)",),
        null_behavior="Missing values remain missing.",
        error_behavior="Unsupported and non-finite values return missing.",
    ),
    ExpressionFunctionSpec(
        name="to_number",
        category="conversion",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="number",
        signature="to_number(value)",
        description="Convert locale-independent numeric values or text to a number.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("number", "string", "missing"),
            ),
        ),
        examples=("to_number(amount_text)",),
        null_behavior="Missing values remain missing.",
        error_behavior=(
            "Booleans, malformed or empty text, non-finite values, and unsupported "
            "values return missing."
        ),
    ),
    ExpressionFunctionSpec(
        name="to_integer",
        category="conversion",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="to_integer(value)",
        description="Convert exactly integral numeric values or text to an integer.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("number", "string", "missing"),
            ),
        ),
        examples=("to_integer(age_text)",),
        null_behavior="Missing values remain missing.",
        error_behavior=(
            "Booleans, fractional or non-finite numbers, malformed text, and "
            "unsupported values return missing."
        ),
    ),
    ExpressionFunctionSpec(
        name="to_float",
        category="conversion",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="float",
        signature="to_float(value)",
        description="Convert locale-independent finite numeric values or text to float.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("number", "string", "missing"),
            ),
        ),
        examples=("to_float(rate_text)",),
        null_behavior="Missing values remain missing.",
        error_behavior=(
            "Booleans, malformed or empty text, non-finite values, overflow, and "
            "unsupported values return missing."
        ),
    ),
    ExpressionFunctionSpec(
        name="to_boolean",
        category="conversion",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="boolean",
        signature="to_boolean(value)",
        description="Convert explicit boolean tokens or numeric one and zero.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("boolean", "number", "string", "missing"),
            ),
        ),
        examples=("to_boolean(active_text)",),
        filter_suitability="direct",
        null_behavior="Missing values remain missing.",
        error_behavior=(
            "Unrecognized text, numbers other than one or zero, and unsupported "
            "values return missing."
        ),
    ),
    ExpressionFunctionSpec(
        name="parse_date",
        category="date_time",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="date",
        signature="parse_date(value, format)",
        description="Parse text as a calendar date using a portable scalar format.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "format",
                "scalar_control",
                ("string",),
            ),
        ),
        examples=("parse_date(raw_date, '%Y-%m-%d')",),
        null_behavior="Missing row values remain missing; format must not be missing.",
        error_behavior=(
            "Invalid row values return missing; non-scalar, null, malformed, or "
            "unsupported formats produce structured expression errors."
        ),
    ),
    ExpressionFunctionSpec(
        name="format_date",
        category="date_time",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="string",
        signature="format_date(value, format)",
        description="Format a calendar date using a portable scalar format.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
            ExpressionArgumentSpec(
                "format",
                "scalar_control",
                ("string",),
            ),
        ),
        examples=("format_date(order_date, '%Y/%m/%d')",),
        null_behavior="Missing row values remain missing; format must not be missing.",
        error_behavior=(
            "Invalid row values return missing; non-scalar, null, malformed, or "
            "unsupported formats produce structured expression errors."
        ),
    ),
    ExpressionFunctionSpec(
        name="year",
        category="date_time",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="year(value)",
        description="Return the calendar year from a date-like value.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
        ),
        examples=("year(order_date)",),
        null_behavior="Missing and invalid row values return missing.",
        error_behavior="Text must be parsed explicitly with parse_date first.",
    ),
    ExpressionFunctionSpec(
        name="month",
        category="date_time",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="month(value)",
        description="Return the calendar month from a date-like value.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
        ),
        examples=("month(order_date)",),
        null_behavior="Missing and invalid row values return missing.",
        error_behavior="Text must be parsed explicitly with parse_date first.",
    ),
    ExpressionFunctionSpec(
        name="day",
        category="date_time",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="day(value)",
        description="Return the calendar day of month from a date-like value.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
        ),
        examples=("day(order_date)",),
        null_behavior="Missing and invalid row values return missing.",
        error_behavior="Text must be parsed explicitly with parse_date first.",
    ),
    ExpressionFunctionSpec(
        name="weekday",
        category="date_time",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="integer",
        signature="weekday(value)",
        description="Return ISO weekday Monday 1 through Sunday 7.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
        ),
        examples=("weekday(order_date)",),
        filter_suitability="composable",
        null_behavior="Missing and invalid row values return missing.",
        error_behavior="Text must be parsed explicitly with parse_date first.",
    ),
    ExpressionFunctionSpec(
        name="date_diff",
        category="date_time",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="integer",
        signature="date_diff(start, end)",
        description="Return calendar-day difference as end minus start.",
        arguments=(
            ExpressionArgumentSpec(
                "start",
                "value_expression",
                ("date", "missing"),
            ),
            ExpressionArgumentSpec(
                "end",
                "value_expression",
                ("date", "missing"),
            ),
        ),
        examples=("date_diff(opened, closed)",),
        null_behavior="Missing or invalid start or end returns missing.",
        error_behavior="Text must be parsed explicitly with parse_date first.",
    ),
    ExpressionFunctionSpec(
        name="add_days",
        category="date_time",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="date",
        signature="add_days(value, days)",
        description="Advance a calendar date by an exactly integral number of days.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("date", "missing"),
            ),
            ExpressionArgumentSpec(
                "days",
                "value_expression",
                ("integer", "integer-convertible", "missing"),
            ),
        ),
        examples=("add_days(start_date, 30)",),
        null_behavior="Missing or invalid date or days returns missing.",
        error_behavior=(
            "Fractional, non-finite, non-convertible, and overflowing day offsets "
            "return missing."
        ),
    ),
    ExpressionFunctionSpec(
        name="between",
        category="validation_list",
        minimum_arguments=3,
        maximum_arguments=3,
        result_kind="boolean",
        signature="between(value, minimum, maximum)",
        description="Test an inclusive range within one compatible value family.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("number", "string", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "minimum",
                "value_expression",
                ("number", "string", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "maximum",
                "value_expression",
                ("number", "string", "date", "missing"),
            ),
        ),
        examples=("between(score, 0, 100)",),
        filter_suitability="direct",
        null_behavior="Missing value or either bound returns false.",
        error_behavior=(
            "Incompatible or unsupported non-missing comparison families produce "
            "a structured expression error."
        ),
    ),
    ExpressionFunctionSpec(
        name="is_in",
        category="validation_list",
        minimum_arguments=2,
        maximum_arguments=None,
        result_kind="boolean",
        signature="is_in(value, option1, option2, ...)",
        description="Test equality against one or more row-local options.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("dynamic", "missing"),
            ),
            ExpressionArgumentSpec(
                "option",
                "value_expression",
                ("dynamic", "missing"),
                variadic=True,
            ),
        ),
        examples=("is_in(status, 'A', 'B', 'C')",),
        filter_suitability="direct",
        null_behavior=(
            "Missing value returns false; missing options never match."
        ),
        error_behavior="Equality-incompatible values produce a structured error.",
    ),
    ExpressionFunctionSpec(
        name="not_in",
        category="validation_list",
        minimum_arguments=2,
        maximum_arguments=None,
        result_kind="boolean",
        signature="not_in(value, option1, option2, ...)",
        description="Return the exact boolean inverse of is_in.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("dynamic", "missing"),
            ),
            ExpressionArgumentSpec(
                "option",
                "value_expression",
                ("dynamic", "missing"),
                variadic=True,
            ),
        ),
        examples=("not_in(status, 'deleted', 'blocked')",),
        filter_suitability="direct",
        null_behavior=(
            "Missing value returns true; missing options never match."
        ),
        error_behavior="Equality-incompatible values produce a structured error.",
    ),
    ExpressionFunctionSpec(
        name="is_number",
        category="validation_list",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="boolean",
        signature="is_number(value)",
        description="Test whether to_number would produce a finite number.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("number", "string", "missing"),
            ),
        ),
        examples=("is_number(amount_text)",),
        filter_suitability="direct",
        null_behavior="Missing values return false.",
        error_behavior="Invalid, boolean, non-finite, and unsupported values return false.",
    ),
    ExpressionFunctionSpec(
        name="is_date",
        category="validation_list",
        minimum_arguments=2,
        maximum_arguments=2,
        result_kind="boolean",
        signature="is_date(value, format)",
        description="Test whether parse_date would produce a calendar date.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "date", "missing"),
            ),
            ExpressionArgumentSpec(
                "format",
                "scalar_control",
                ("string",),
            ),
        ),
        examples=("is_date(raw_date, '%Y-%m-%d')",),
        filter_suitability="direct",
        null_behavior="Missing row values return false; format must not be missing.",
        error_behavior=(
            "Invalid row values return false; non-scalar, null, malformed, or "
            "unsupported formats produce structured expression errors."
        ),
    ),
    ExpressionFunctionSpec(
        name="is_email",
        category="validation_list",
        minimum_arguments=1,
        maximum_arguments=1,
        result_kind="boolean",
        signature="is_email(value)",
        description="Apply a deterministic pragmatic email-address check.",
        arguments=(
            ExpressionArgumentSpec(
                "value",
                "value_expression",
                ("string", "number", "boolean", "date", "missing"),
            ),
        ),
        examples=("is_email(strip(email))",),
        filter_suitability="direct",
        null_behavior="Missing values return false.",
        error_behavior=(
            "Unsupported values and text outside the documented pragmatic rule "
            "return false."
        ),
    ),
)

DEFERRED_EXPRESSION_FUNCTIONS: tuple[ExpressionFunctionSpec, ...] = ()

EXCLUDED_NON_ROW_LOCAL_FUNCTIONS: frozenset[str] = frozenset(
    {
        "sum",
        "mean",
        "median",
        "count",
        "rank",
        "lag",
        "lead",
        "group_by",
        "join",
        "window",
    }
)


def expression_function_specs(
    *,
    include_deferred: bool = False,
) -> tuple[ExpressionFunctionSpec, ...]:
    """Return function metadata without providing parser or execution behavior."""

    if include_deferred:
        return CORE_EXPRESSION_FUNCTIONS + DEFERRED_EXPRESSION_FUNCTIONS
    return CORE_EXPRESSION_FUNCTIONS
