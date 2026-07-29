# Roadmap

StatConvert 0.10.1 is a documentation and licensing patch for the 0.10.0 behavior
baseline. It adds `AGPL-3.0-or-later` licensing, corrects and refreshes documentation,
and changes no runtime, command, or supported-format behavior.

## Planned releases

### 0.11.0 — Release automation and quality gates

Strengthen repeatable release checks, documentation validation, artifact inspection, and
quality gates.

### 0.12.0 — Pre-UI transform function expansion

Add only deliberately specified row-local transform helpers with parser, evaluator,
preview, metadata, documentation, and security coverage. Regex, date/time, broad
conversion, aggregate, window, group, join, and arbitrary-code behavior remain excluded
until separately designed and implemented.

### 1.0.0 — Full GUI

Provide a full GUI covering commands and options, launched with future
`statconvert ui`. No GUI is included in 0.10.1.

## Current boundaries

- Streaming remains opt-in and limited to supported CSV, JSONL, and NDJSON conversion,
  plain batch, and schema-contract validation workflows.
- Transform, report, compare, collect, JSON-array, object-selection, and other-format
  workflows are not streamed.
- The transform expression evaluator remains closed and row-local; it does not execute
  arbitrary Python.
