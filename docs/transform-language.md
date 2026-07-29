# Transform recipe and expression language design

Status: **0.10.0 ordered recipe release baseline**

This document defines the intended StatConvert 0.10.0 transform recipe system. It is a
design contract for the parser, recipe engine, configuration, preview, and future UI
work. The 0.10.0d slice added closed expression evaluation, derived columns, conditional
values, and expression filters. The 0.10.0e slice activated a focused normalization and
missing-value helper set and enriched recode planning metadata. The 0.10.0f slice added
canonical ordered config import/export, exact-order compilation to the existing
transformations, and a bounded internal preview API.

## Current internal implementation

`statconvert/transformations/expressions/` now contains:

- a closed tokenizer with deterministic half-open character spans;
- immutable literal, column, function-call, unary, binary, group, and expression AST
  nodes;
- a recursive-descent parser with explicit precedence;
- core/deferred/excluded function validation;
- conservative result-kind inference;
- a non-throwing `parse_expression()` analysis helper with JSON-safe issues;
- a closed vectorized evaluator for the core functions/operators; and
- structured evaluation issues without raw pandas tracebacks.

The single-file `transform` command now exposes repeatable `--derive COLUMN=EXPRESSION`
and `--filter-expression EXPRESSION`. Existing structured `--filter` syntax is unchanged.
`transform --write-config` exports canonical ordered `[[steps]]`, and `config validate`
and `config run` validate and execute that order. Existing top-level transform fields
remain accepted for backward compatibility.

`statconvert/transformations/planning.py` now projects recipes against an ordered input
column list. Each planned step records its status, input/output columns, referenced and
removed columns, renames, intended type conversions, expression analysis, UI flags,
warnings, and structured errors. The recipe plan reports initial/final columns and
aggregates issues in step order. Planning modes (`full`, `preview`, and `compatibility`)
label the intended consumer. Execution and preview compile a valid plan to the existing
transformation classes rather than implementing another engine.

`statconvert/transformations/compatibility.py` translates existing transform options into
the established fixed order without replacing the live CLI path. Simultaneous legacy
rename maps remain one compatibility step, and legacy structured filters retain their
conditions/mode/reset-index settings instead of being rewritten into potentially
different expressions.

## Goals

The 0.10.0 transform system provides:

- safe, row-local transform expressions;
- portable, explicitly ordered recipe steps;
- reusable TOML configurations;
- compatibility with existing CLI operations;
- enough structured metadata for future UI creation, editing, validation, preview,
  import, and export;
- deterministic validation, execution, serialization, and result ordering; and
- clear errors tied to the recipe step and field that caused them.

A recipe is a backend-neutral description. File reads and writes continue through the
backend registry, and execution continues to accept and return `Dataset`.

## Non-goals

The 0.10.0 language does not provide:

- arbitrary Python or `eval`;
- imports or user-defined functions;
- filesystem, network, environment, or process access;
- a SQL engine;
- joins;
- group-by or aggregate transforms;
- window functions;
- streaming transform execution; or
- a GUI implementation.

The full GUI remains future 1.0.0 work launched with `statconvert ui`. The 0.10.0
structures are designed so that GUI controls can create and edit recipes later; they do
not claim that such a GUI currently exists.

## Current behavior and migration boundary

The current CLI builds an ordered `TransformationPipeline` in this fixed order:

1. select;
2. drop;
3. rename;
4. type conversion;
5. derive, in supplied order;
6. legacy structured filter;
7. expression filter, in supplied order; and
8. recode.

Legacy transform TOML may still store operations in top-level `select`, `drop`, `rename`,
`type`, `derive`, `filter`, `filter_expression`, and `recode` fields. `config run`
continues to translate them into the fixed order above. New `transform --write-config`
exports `[[steps]]` instead. A transform config cannot combine legacy operation fields
with `[[steps]]`; mixed formats fail before execution because their ordering is
ambiguous.

## Ordered recipe model

Steps are applied exactly in file order. This is required because each step observes the
columns and values produced by earlier steps. For example:

```text
derive email_clean from email
drop email
```

is valid when `email` exists initially. Reversing those steps:

```text
drop email
derive email_clean from email
```

must fail at the derive step because its input dependency no longer exists.

Ordering also controls rename dependencies, type conversion before comparison, repeated
derived-column replacement policy, and filter/recode interactions. The engine must never
silently regroup steps by type.

The planner uses deterministic best-effort state: a valid step updates projected columns;
an invalid step does not change them. Later steps are still planned against the most
recent valid state, so one error does not hide independent downstream diagnostics.

## Canonical TOML shape

The canonical 0.10.0 representation uses an array of tables:

```toml
command = "transform"
input = "survey_raw.csv"
output = "survey_clean.csv"
overwrite = true

[[steps]]
type = "derive"
column = "email_clean"
expression = "lower(strip(email))"

[[steps]]
type = "derive"
column = "country_clean"
expression = "upper(strip(country))"

[[steps]]
type = "filter"
expression = "consent == 'yes'"

[[steps]]
type = "recode"
column = "status"
default = "Unknown"

[steps.map]
"1" = "Active"
"2" = "Inactive"
"9" = "Unknown"
```

`[[steps]]` preserves order in TOML and maps directly to a list in JSON. Each step has
one `type` discriminator and only the fields valid for that type. This is easier for a
form editor than overloaded CLI strings and allows repeated step types.

The first ordered schema uses one source/target pair per `rename` step and one column per
`convert_type` or `recode` step. This makes dependencies and UI fields explicit. A CLI
option that names several operations may expand into several adjacent recipe steps.

## Step types

All seven planned step types are deterministic and backend-neutral. “Previewable” means
the step can be applied by a future internal sample-preview service; it does not mean
that a GUI exists.

### `select`

- Required: `columns`, a non-empty ordered list of column names.
- Optional: `ignore_missing` (default `false`).
- Inputs: the named columns.
- Outputs: the named columns, in the requested order.
- Row-local: yes; no values depend on another row.
- Previewable: yes.
- Ordering: always significant because unselected columns become unavailable.
- UI fields: ordered column picker and ignore-missing toggle.
- Errors: unknown/duplicate column, empty selection, or a later dependency on a removed
  column.

### `drop`

- Required: `columns`, a non-empty ordered list of column names.
- Optional: `ignore_missing` (default `false`).
- Inputs: the named columns plus the current schema.
- Outputs: the current schema without the named columns.
- Row-local: yes.
- Previewable: yes.
- Ordering: always significant because dropped columns become unavailable.
- UI fields: ordered multi-column picker and ignore-missing toggle.
- Errors: unknown/duplicate column, attempt to drop every column where disallowed, or a
  later dependency on a dropped column.

### `rename`

- Required: `from` and `to`.
- Optional: `ignore_missing` (default `false`).
- Inputs: `from`.
- Outputs: `to`.
- Row-local: yes.
- Previewable: yes.
- Ordering: always significant; later steps must use the new name.
- UI fields: source-column picker, target-name field, and ignore-missing toggle.
- Errors: unknown source, blank/invalid target, duplicate target, target collision, or a
  later reference to the old name.

Example:

```toml
[[steps]]
type = "rename"
from = "old_name"
to = "new_name"
```

### `convert_type`

- Required: `column` and `data_type`.
- Optional: `errors` (`raise`, `coerce`, or `ignore`) and `datetime_format`.
- Inputs: `column`.
- Outputs: the same column with a new logical/storage value type.
- Row-local: yes.
- Previewable: yes.
- Ordering: significant for later expressions, filters, and recodes.
- UI fields: column picker, supported-type picker, error-mode picker, and optional format.
- Errors: unknown column/type/error mode, incompatible values, invalid date format, or
  conversion loss rejected by policy.

### `derive`

- Required: `column` and `expression`.
- Optional: none in the first version.
- Inputs: columns reported by parsed expression metadata.
- Outputs: `column`.
- Row-local: yes in 0.10.0.
- Previewable: yes.
- Ordering: always significant; later steps may reference the new column.
- UI fields: output-name field, expression editor, column/function pickers, validation
  status, and inferred result kind.
- Errors: duplicate output column, unknown input column, invalid expression, unsupported
  function/operator, wrong argument count, or incompatible types.

The first engine should reject replacing an existing column through `derive`; changing
that policy later requires an explicit option rather than silent replacement.

### `filter`

- Required: `expression`, which must produce boolean or missing values.
- Optional: `reset_index` (default `true` for CLI compatibility).
- Inputs: columns reported by parsed expression metadata.
- Outputs: the same columns and only rows for which the expression is true.
- Row-local: yes.
- Previewable: yes.
- Ordering: significant because it observes prior values and changes later row counts.
- UI fields: expression editor, column/function pickers, reset-index toggle, and match
  count preview.
- Errors: invalid/non-boolean expression, unknown column, unsupported function/operator,
  incompatible comparison, or ambiguous missing-result policy.

The engine must define one missing-condition policy. The recommended first policy is to
treat a missing filter result as false, matching conservative row inclusion.

### `recode`

- Required: `column` and non-empty `map`.
- Optional: `default` and `update_value_labels` (default `true`).
- Inputs: `column`.
- Outputs: the same column with mapped values.
- Row-local: yes.
- Previewable: yes.
- Ordering: significant because it observes values created by earlier steps.
- UI fields: column picker, editable mapping rows, optional default, and value-label
  toggle.
- Errors: unknown column, empty/invalid map, duplicate source key after type
  normalization, incompatible mapped/default values, or metadata update conflict.

Omitting `default` preserves unmapped values. Supplying `default` replaces unmapped
non-missing values. TOML has no null scalar, so omission and an explicit future missing
sentinel must not be conflated. Recode runs after derive and both filter forms, so it can
target a derived column and observes only rows retained by filters. Planning metadata
records the target, mapping keys/count, whether a default is present, its JSON-safe
value, the value-label policy, and that compatibility recodes do not alter missing input
values. Normal execution summaries report the number of recoded columns.

## Expression language

The parser accepts only a closed grammar and registered functions. Function names are
case-sensitive lowercase identifiers. No attribute access, general indexing,
comprehensions, assignment, lambda, comments, semicolon statements, or function
definition syntax is permitted. The implementation does not call Python `ast`, `eval`,
or `exec`.

### Supported functions

Text:

- `strip(value)`
- `lower(value)`
- `upper(value)`
- `contains(value, text)`
- `starts_with(value, text)`
- `ends_with(value, text)`
- `normalize_whitespace(value)`
- `normalize_code(value)`

Numeric:

- `abs(value)`
- `round(value, digits)`

Missing values:

- `is_null(value)`
- `not_null(value)`
- `coalesce(value, fallback)`
- `null_if(value, match)`
- `null_if_empty(value)`
- `default_if_missing(value, fallback)`

Conditional:

- `if_else(condition, true_value, false_value)`

These functions are the complete supported 0.10.0 registry. They are row-local and
previewable. Null propagation and accepted input/result kinds are explicit in the
parser/type rules and do not rely on arbitrary Python behavior.

### Operators

The grammar supports:

- comparisons: `==`, `!=`, `<`, `<=`, `>`, and `>=`;
- boolean operators: `and`, `or`, and `not`; and
- arithmetic: `+`, `-`, `*`, and `/` only where operand types and divide-by-zero behavior
  are safe and defined.

The implemented precedence, highest to lowest, is:

1. calls, literals, column references, and parentheses;
2. unary `-`;
3. `*` and `/`;
4. `+` and `-`;
5. comparisons;
6. predicate `not`;
7. `and`; and
8. `or`.

Placing `not` below comparisons gives `not age >= 18` the useful meaning
`not (age >= 18)`. Parentheses may override precedence. Chained comparisons are rejected;
write explicit comparisons joined with `and`.

### Literals

The grammar supports:

- quoted strings with controlled escapes;
- finite integers and floating-point numbers;
- `true` and `false`; and
- `null` as the missing-value literal.

Non-finite numeric literals and implicit names such as `None`, `True`, or `False` are not
part of the language.

## Evaluation policies

The 0.10.0d evaluator walks the immutable AST directly. It never uses Python `ast`,
`eval`, `exec`, `compile`, dynamic imports, attribute lookup, or arbitrary callables.
Normal column operations use pandas vectorization.

Missing values:

- `is_null` and `not_null` use pandas missing-value detection;
- `coalesce(value, fallback)` replaces missing values and aligns Series by index;
- `default_if_missing(value, fallback)` follows the same aligned fill policy under a
  cleaning-oriented name;
- `null_if(value, match)` replaces literal equality matches with missing, preserves
  existing missing values, and with a missing `match` leaves non-missing values intact;
- `null_if_empty(value)` detects emptiness after trimming but returns the original
  non-empty string unchanged;
- `strip`, `lower`, and `upper` preserve missing values rather than producing `"nan"`;
- `normalize_whitespace` trims and collapses spaces, tabs, and newlines without changing
  case or other characters;
- `normalize_code` applies the same whitespace normalization and uppercases the result
  without removing accents or applying locale-specific conversion;
- `contains`, `starts_with`, and `ends_with` return false for missing inputs; and
- boolean operations, `if_else` conditions, and filter masks treat missing conditions as
  false.

Types:

- text and normalization functions require strings or missing values; numeric codes are
  rejected by `normalize_code` rather than silently converted;
- text predicates use literal, case-sensitive matching and never regular expressions;
- numeric functions and `+`, `-`, `*`, `/`, and unary `-` require numeric-compatible
  values;
- `+` does not perform implicit string concatenation;
- `round` requires an integer literal/scalar for `digits`; and
- ambiguous mixed object operations fail with `expression_incompatible_type`.

Division by a scalar zero or any zero in a divisor Series fails with
`expression_division_by_zero`. It does not silently produce infinity. `if_else` accepts
scalar or Series branches, aligns them to the input index, and chooses the false branch
when its condition is missing.

Evaluator issues include a stable code, message, original expression, half-open source
span, and optional column/function/suggestion fields.

### Column references

Plain identifiers refer to columns when unambiguous:

```text
lower(email)
amount >= 0
```

Awkward names use a dedicated bracketed, JSON-quoted column form:

```text
lower(["Email Address"])
["2025 amount"] >= 0
```

This bracket form is column-reference syntax only. It does not enable general indexing,
lists, or computed lookup. The parser should normalize both forms into the same column
reference node and preserve the original expression separately for display.

## Deferred function library

The following row-local functions are candidates for pre-UI expansion after the initial
parser and engine are stable:

- text: `replace`, `regex_match`, `regex_replace`, `length`, `substring`, `concat`,
  `remove_accents`;
- dates: `parse_date`, `format_date`, `year`, `month`, `day`, `weekday`, `date_diff`,
  `add_days`;
- conversion: `to_string`, `to_number`, `to_integer`, `to_float`, `to_boolean`,
  `to_date`;
- comparison/validation: `between`, `is_in`, `not_in`, `is_number`, `is_date`,
  `is_email`.

These names are design reservations, not initial parser support. The parser recognizes
them and returns a specific `deferred_function` error explaining that they are planned
but not implemented. Later slices must add each function deliberately with arity, type,
null, error, preview, and test coverage.

## Intentionally excluded operations

The expression registry intentionally excludes `sum`, `mean`, `median`, `count`, `rank`,
`lag`, `lead`, `group_by`, joins, and window functions.

These operations depend on multiple rows, datasets, grouping state, or row ordering. They
are not simple row-local preview operations and need separate design for recipe ordering,
memory limits, streaming behavior, validation, and UI semantics. The parser reports them
with `non_row_local_function` rather than treating them as an accidental unknown name.

## Expression metadata

The internal `parse_expression()` helper produces a JSON-safe metadata object
independently of execution:

```json
{
  "expression": "lower(strip(email))",
  "valid": true,
  "referenced_columns": ["email"],
  "functions": ["lower", "strip"],
  "row_local": true,
  "previewable": true,
  "result_kind": "string"
}
```

References and functions use deterministic first-appearance order without duplicates.
Invalid input returns `valid: false`, no partial AST, and a structured error containing
`code`, `message`, `start`, `end`, and an optional `suggestion`. Token, AST-node,
function-name, column-reference, operator, and error spans use zero-based half-open
offsets suitable for future editor highlighting.

Result-kind inference is deliberately conservative: literals, boolean/comparison
operations, numeric literal arithmetic, and fixed-result core functions are inferred;
columns remain `unknown` without a schema; incompatible conditional branches and
uncertain arithmetic remain `unknown`. Unknown kinds are not validation failures.

This metadata enables a future UI to provide:

- column and function pickers;
- expression validation before execution;
- before/after preview cards;
- per-step warnings and inferred result information;
- step dependency checks; and
- editable recipe import/export rather than an apply-only config loader.

For example, `derive email_clean = lower(strip(email))` becomes a derive-step form with
the output column, expression text, referenced `email` input, `lower`/`strip` functions,
and row-local/previewable status available separately.

## Preview foundation

A later internal preview service should accept a validated ordered recipe plus a limited
`Dataset` or deterministic sample. It should return:

- rows before and after the recipe;
- columns before and after the recipe;
- bounded before/after row data;
- per-step status and row/column changes;
- expression metadata for expression-bearing steps;
- warnings; and
- errors tied to a zero-based step index.

`preview_transform_recipe(dataset, recipe, limit=50)` applies the same compiled
transformations to a deterministic `head(limit)` copy. It never reads or writes files and
does not mutate the source `Dataset`. Its JSON-safe result includes total/source sample
row counts, before/after columns, per-step statuses and row counts, expression metadata,
diagnostics, and bounded sample output rows. Preview results are sample observations, not
full-dataset guarantees.

## CLI mapping

Existing options remain compatibility inputs. Config export maps each option to one or
more recipe steps:

```text
--select a,b,c
```

maps to:

```toml
[[steps]]
type = "select"
columns = ["a", "b", "c"]
```

```text
--derive email_clean="lower(strip(email))"
```

maps to:

```toml
[[steps]]
type = "derive"
column = "email_clean"
expression = "lower(strip(email))"
```

```text
--filter-expression "consent == 'yes'"
```

maps to:

```toml
[[steps]]
type = "filter"
expression = "consent == 'yes'"
```

Existing `--rename OLD=NEW`, `--type COLUMN=TYPE`, legacy
`--filter COLUMN,OPERATOR,VALUE`, and `--recode` syntax should translate into equivalent
steps. When only legacy grouped options are supplied, their current fixed order remains
unchanged. Configs containing both legacy operation fields and `[[steps]]` are rejected
with a suggestion to retain only one representation.

The internal compatibility translator now performs this mapping for planning. It uses
compatibility-only `map` on rename and `conditions` on filter to preserve current
simultaneous rename and structured-filter semantics. These fields do not change the
canonical expression-based TOML design. Existing legacy configs continue to execute;
new exports use canonical steps.

## Config import and export

The ordered configuration contract is:

- TOML array-of-table order is authoritative and preserved;
- field output follows a stable schema order;
- map output is deterministic;
- the whole recipe is structurally validated while loading;
- `config validate` reads the declared input through the registry and runs planner
  dependency validation against its actual columns;
- `config run` builds and executes the same backend-neutral recipe as direct CLI use;
- `transform --write-config` writes a recipe without running it; and
- the internal preview API consumes the same recipe model for future UI cards.

The first schema defers `enabled = true/false`. Disabled steps complicate dependency
validation, execution summaries, and canonical export. A future addition may introduce
it only with explicit rules stating whether disabled steps participate in validation and
preview. Until then, removing or adding a step is unambiguous.

Legacy top-level transform configs remain readable and executable through the established
fixed-order compatibility path. New `transform --write-config` output is canonical and
deterministic: stable root/step field order, stable step order, sorted map keys, and no
timestamps.

## Error model

Recipe planning errors contain:

- zero-based `step_index`;
- `step_type`;
- the invalid `field`;
- a concise `message`; and
- a `suggestion` when a safe corrective action is known.

Expected error categories include:

- unknown column;
- duplicate output column;
- invalid expression;
- unsupported function;
- wrong number of function arguments;
- incompatible types;
- dependency on a dropped or renamed column;
- invalid recode map; and
- unsupported aggregate or window function.

Example JSON-safe issue:

```json
{
  "step_index": 1,
  "step_type": "derive",
  "field": "expression",
  "message": "Column 'email' is not available at this step.",
  "suggestion": "Move this derive step before the step that drops 'email'."
}
```

Parser syntax errors should include a safe character span when available. Errors must not
expose Python objects, tracebacks, or evaluator internals. Terminal rendering may add
presentation, but business-layer errors remain Rich-free and machine output remains
parseable.

Current stable planning codes include `transform_unknown_column`,
`transform_duplicate_column`, `transform_column_collision`,
`transform_invalid_step`, `transform_invalid_expression`,
`transform_unknown_referenced_column`, `transform_unsupported_type`, and
`transform_invalid_recode_map`. Expression errors and unknown expression-column errors
preserve half-open source spans.

## JSON and result metadata

Transform planning and preview results are backend-neutral and JSON-safe. Preview exposes
the following additive shape:

```json
{
  "valid": true,
  "rows_before": 120,
  "sampled_rows": 50,
  "preview_rows": 37,
  "limit": 50,
  "columns_before": ["email", "consent", "status"],
  "columns_after": ["email", "consent", "status", "email_clean"],
  "steps": [],
  "sample_output_rows": [],
  "warnings": [],
  "errors": []
}
```

Each `steps` entry should identify its index/type, input/output columns, row counts,
expression metadata where applicable, status, warnings, and issues. Paths, missing
values, dates, and scalar types continue through the project’s shared JSON normalization.
Human terminal summaries may be concise views of this model but must not define a
different execution contract.

## Implementation history through 0.10.0

- **0.10.0b:** completed the closed safe-expression tokenizer/parser, immutable AST,
  function validation, expression metadata, source spans, conservative result-kind
  inference, and structured errors; no broad evaluator.
- **0.10.0c:** completed ordered recipe validation/planning, projected column
  dependencies, structured step/recipe metadata, parser-metadata consumption, and
  compatibility mapping from existing fixed-order transform options.
- **0.10.0d:** completed derived columns, expression filters, conditionals, and closed
  expression execution.
- **0.10.0e:** completed recode planning/result integration plus the focused
  normalization and missing-value helper set.
- **0.10.0f:** completed canonical config import/export, exact-order compilation,
  schema-aware validation, mixed-format rejection, bounded internal preview,
  documentation, compatibility finalization, and release preparation.

Every slice must keep the CLI thin, keep Rich out of business layers, use the registry for
file access, preserve `Dataset` behavior, and avoid a second transform engine.
