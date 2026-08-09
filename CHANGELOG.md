# Changelog

## 1.1.1 - 2026-08-09

### Improved

- Audited the complete 18-extension format surface across registry capabilities,
  read/write paths, objects, metadata, sidecars, shared workflows, documentation, and
  browser Reference data.
- Added actionable writable alternatives to read-only format errors and caveats: SAV for
  ZSAV/POR input and XPT for SAS7BDAT input.
- Made object listing for single-dataset files identify the extension and explain that
  there are no selectable objects, with focused API, CLI, registry, and Reference tests.
- Added a compact supported-format and metadata-mode guide, practical read-only,
  object-container, JSON Lines, and sidecar examples, and clearer warnings that suggested
  writable alternatives are explicit conversions rather than automatic or lossless
  replacements.
- Refined registry-driven Reference caveats for spreadsheet presentation loss, partial
  statistical metadata writes, JSON flattening limits, and Arrow sidecar precedence.
- Added no new format family, database support, or runtime dependency.

## 1.1.0 - 2026-08-09

### Improved

- Made extension-level capabilities report streaming support for CSV, JSONL, and NDJSON
  while continuing to report normal JSON arrays as non-streaming.
- Added NDJSON beside JSONL in browser Convert, Batch Convert, Validate, and Transform
  target selectors; both retain friendly labels and alphabetical display sorting.
- Made normal and streaming malformed-input errors distinguish JSON Lines from NDJSON.
- Added parity coverage for normal JSONL/NDJSON sidecars, line-oriented writes, batch and
  config conversion, shared inspection/compare/validate/report workflows, CLI/reference
  capabilities, and browser selector presence.
- Reconciled the 18-extension registry, CLI format table, browser Reference, centralized
  target selectors, and public format guidance. Reference now exposes friendly-sorted
  metadata modes and caveats; target selectors include every normally writable extension
  and no longer offer read-only SAS7BDAT.
- Added no new format family, database support, or runtime dependency.

## 1.0.1 - UI polish and Compare correctness

### Improved

- Retained the compact confirmed-starting-folder path picker and its existing local-only
  containment behavior. A drive/common-location starting view remains deferred.
- Centralized friendly, alphabetically sorted browser format labels while retaining the
  existing extension values in plans, commands, and API payloads.
- Standardized job badges so queued and unknown states are neutral, running is blue,
  successful states are green, failures are red, and cancellation states are orange.
- Increased table header, striped-row, hover, and border contrast through shared light
  and dark theme variables.
- Removed development-slice and build labels from the application header, Home, and
  workflow pages. Runtime version information remains available in About, the version
  API, and `statconvert --version`.
- Defaulted the browser Report workflow to HTML and applied `.html`, `.json`, or `.csv`
  to extensionless report paths while preserving explicit mismatched extensions with a
  visible warning.
- Simplified Configs by removing prominent implementation-status wording and keeping
  its CLI command in the Settings-controlled command panel instead of duplicating it in
  the result summary. The original payload remains available under collapsed Raw details.

### Investigated

- Reproduced SAV-to-RDS and SAV-to-RData comparison failures for logical date columns.
  The current R writer serializes Python `date` values as ISO strings, while sidecar
  metadata restores the logical `date` declaration without coercing those strings on
  read. No comparison, conversion, or backend behavior changed in this investigation.

### Fixed

- Compare now treats semantically date-only values as equal when the same calendar date
  is represented by a Python date, a naive midnight datetime/Timestamp, supported NumPy
  date-like scalar, or canonical `YYYY-MM-DD` string. Detection requires date metadata
  on at least one side; arbitrary strings and epoch integers are not normalized. Backend
  conversion behavior is unchanged, and schema/metadata warnings remain independent.

## 1.0.0 - Local browser UI

### Added

- Added the lazy `statconvert ui` command with loopback-only host validation, browser
  launch control, clear missing-extra guidance, and a FastAPI/Uvicorn `ui` optional
  extra that leaves base runtime dependencies unchanged.
- Added the `statconvert.webui` application factory, packaged static serving, and
  health, version, and environment endpoints.
- Added a responsive React/Vite/TypeScript/Mantine shell with navigation placeholders
  for every planned UI area, a deterministic pnpm lockfile, and production assets built
  directly into the Python package.
- Added functional Inspect tabs for overview, preview, schema, labels, metadata,
  summary, describe, frequencies, missing values, and object discovery, with bounded
  JSON-safe responses and equivalent CLI command previews.
- Added non-writing planners and functional Convert, Batch Convert, and Validate
  screens that call existing Python business layers directly and preserve overwrite,
  directory, streaming, target-capability, and schema-contract safeguards.
- Added a bounded process-local background job registry with status, server-sent
  progress events, structured failures, and best-effort cancellation for write and
  potentially long-running validation workflows.
- Added explicit batch container-object choices, recursive `.xls`/`.xlsx` all-object
  planning, plan warnings, advanced-option tiers, and live per-file status tables.
- Added a loopback-only, user-rooted local path browser, automatic cached Inspect tabs,
  dedicated label and frequency tables, centralized theme colors, and Tabler icons.
- Added functional Configs, Compare, Report, Collect, and Reference screens backed by
  existing config execution, comparison, reporting, collection, and registry services.
- Added typed config init/load/validate/export/run APIs, planned and background
  compare/report/collect APIs, truthful command previews, and live format/backend/
  capability reference tables.
- Added platform-native local UI preference storage, functional Settings and About
  screens, malformed-settings recovery, remembered path-picker directories, and runtime,
  dependency, license, network, and privacy diagnostics.
- Added existing `--log` and `--log-level` preference propagation for executable browser
  jobs with per-job log filenames, plus the loopback-only `statconvert.localhost` default
  browser URL and graceful `127.0.0.1` fallback.
- Added Inspect > Metadata helper-script export through the existing R (`.R`), SPSS
  (`.sps`), and Stata (`.do`) exporter with explicit local output paths and truthful
  `metadata --export-script` command previews.
- Added active Batch job lookup and an atomic one-active-UI-batch guard, while keeping
  CLI Batch concurrency unchanged.
- Added structured browser comparison results, current-schema Collect manifest help and
  safe starter generation, and a public-safe browser UI guide for every workflow.

### Improved

- Corrected the default browser-visible URL to prefer `statconvert.localhost` after IPv4
  readiness, with `127.0.0.1` fallback when browser opening fails.
- Made the shared command-preview preference hide panels completely, added quiet
  30-second local health polling with reconnecting/disconnected states, simplified homepage copy,
  and cleared and ignored remembered folders when remembering is disabled.
- Improved Inspect with file/folder discovery controls, Overview columns, a metadata
  summary, human-readable memory, CLI-style Describe sections, per-variable frequency
  tables, and reordered missing-value fields; validation job results now render their
  structured issues or an explicit no-issues state.
- Reduced repeated workflow chrome and compacted inspection controls while retaining
  manual refresh and existing bounded API behavior.
- Defaulted Convert, Batch Convert, and Transform browser targets to Parquet; added
  shared extensionless-output handling for Convert and Transform; exposed optional
  positive Batch workers; replaced running Batch plans with progress; restored active
  Batch progress after navigation; and cleared stale Convert/Transform results on run.
- Added the functional Transform page with all seven canonical ordered step types,
  projected column state, per-step planning errors, bounded before/after preview, direct
  background execution, and canonical `[[steps]]` TOML.
- Added registry-driven discovery for all 43 active expression helpers, debounced pure
  expression validation with half-open source spans, contextual column insertion, and
  function call insertion without adding expression semantics.
- Kept comparison details and report tables bounded, preserved Report and Collect output
  collision rules, and retained the established rejection of mixed legacy transform
  fields with ordered `[[steps]]`.
- Replaced accepted Compare, Report, and Collect plans with live jobs, cleared competing
  Config validation/run results, and made raw comparison JSON secondary to Summary,
  Inputs, Shape, Columns, Schema, Metadata, and Values sections.
- Standardized collapsed **Raw details** below user-facing plan and result summaries,
  added workflow-specific Convert, Transform, Report, Collect, and Config result fields,
  replaced accepted Convert and Validate plans with live progress, and renamed the
  connection indicator to **StatConvert backend**.

### Design

- Defined the 1.0.0 local browser UI architecture using FastAPI, Uvicorn, React, Vite,
  TypeScript, and Mantine, with built frontend assets bundled into the future wheel.
- Assigned every existing command to the 1.0.0b-f implementation slices and specified
  the local launcher, loopback security boundary, API routes, page map, command/config
  previews, background jobs, progress, and packaging strategy.
- Designed the ordered transform recipe builder and function picker around existing
  recipe planning, bounded preview, safe expression evaluation, and all 43 active
  function metadata specifications.
- Kept `statconvert/ui` as the Rich terminal layer and reserved the separate
  `statconvert/webui` package for browser-server code.
- Finalized the 1.0.0 package metadata, bundled frontend assets, public-safe browser
  documentation, wheel-only packaging, and release verification.

## 0.12.0 - Transform helper expansion

### Design

- Audited the closed transform-expression parser, evaluator, registry, metadata,
  planner, recipe/config integration, preview/JSON paths, tests, and private
  documentation for the 0.12.0 expansion.
- Approved exact semantics, null/error behavior, UI function-picker metadata, safety
  boundaries, and implementation gates for 26 row-local text, type-conversion,
  date/time, and validation/list helpers.
- Split implementation into focused 0.12.0b text, 0.12.0c conversion, 0.12.0d
  date/time, 0.12.0e validation/list, and 0.12.0f release slices.

### Added

- Added the closed expression helpers `replace`, `regex_match`, `regex_replace`,
  `length`, `substring`, `concat`, and `remove_accents` for derive and expression-filter
  workflows.
- Added structured function signatures, argument metadata, examples, return types, null
  and error behavior, filter suitability, and unbounded maximum arity serialization for
  UI and preview consumers.
- Added bounded regular-expression handling with scalar patterns, a 256-character pattern
  limit, a 10,000-character per-value input limit, and structured errors for invalid
  patterns and replacements.
- Added parser, evaluator, metadata, planner, preview, direct CLI, and ordered-config
  coverage for the new helpers.
- Added the closed expression helpers `to_string`, `to_number`, `to_integer`, `to_float`,
  and `to_boolean` with deterministic, locale-independent, missing-on-invalid behavior.
- Added exact conversion-helper function-picker metadata and shared evaluator, planner,
  preview/JSON, direct CLI, and ordered-config coverage.
- Removed the unapproved deferred `to_date` reservation; it now reports an unknown
  function and remains unimplemented.
- Added `parse_date`, `format_date`, `year`, `month`, `day`, `weekday`, `date_diff`, and
  `add_days` as closed date-level expression helpers.
- Added portable `%Y`/`%m`/`%d`/`%%` format validation, structured control errors,
  missing-on-invalid row behavior, ISO weekday numbering, calendar-day differences,
  exact signed day offsets, and JSON-safe preview coverage.
- Added date/time function-picker metadata and evaluator, planner, preview, direct CLI,
  and ordered-config integration coverage.
- Added inclusive `between`, variadic `is_in` and `not_in`, `is_number`, `is_date`, and
  pragmatic `is_email` as the final approved 0.12.0 expression helpers.
- Added compatible-family range validation, exact inverse membership semantics,
  numeric/date parser reuse, deterministic email checks, complete helper metadata, and
  shared evaluator, planner, preview/JSON, direct CLI, and ordered-config coverage.

### Notes

- All 26 approved expansion helpers are implemented, with no extra helper added; no
  conversion backend or runtime dependency behavior changed.
- Existing transform behavior remains compatible, no runtime dependencies were added,
  and no supported format behavior changed.
- No GUI implementation is included. The GUI remains future 1.0.0 work via
  `statconvert ui`.

## 0.11.0 - 2026-07-29

### Added

- Added a documented Codex-driven release process with explicit private, public,
  artifact, GitHub Release, Pages, and post-release quality gates.
- Added safeguards for the current package version, AGPL package metadata, official
  `LICENSE` text, and the documentation dependency group required by GitHub Pages.
- Added a machine-reviewable public documentation allowlist, conditional set, denylist,
  content boundary, required navigation, and next-sync removal list.

### Documentation

- Documented the curated public-sync boundary and the required removal of private-only
  roadmap and transform-language design pages from public documentation.
- Documented strict MkDocs verification, public navigation requirements, and the
  documentation-only Pages hotfix procedure.
- Kept Codex as the automation layer without adding an internal release framework or
  user-facing release command.

### Notes

- No data-conversion, command, supported-format, or runtime dependency behavior changed.
- The GUI remains future 1.0.0 work via `statconvert ui`.

## 0.10.1 - 2026-07-29

### Added

- Licensed StatConvert under the GNU Affero General Public License v3.0 or later using
  the SPDX expression `AGPL-3.0-or-later`, the official license text, and explicit
  package license-file metadata.

### Documentation

- Audited the 0.10.0 command surface, formats, streaming boundaries, transform language,
  configuration workflows, roadmap, and release-facing documentation against live CLI
  output and implementation metadata.
- Corrected localized stale version, recipe-status, roadmap, and capability wording
  without changing command or package behavior.
- Refreshed task-oriented examples for basic conversion, selective streaming, schema
  contracts, safe derived/filter expressions, canonical ordered recipes, metadata
  precedence, and current fixed transform order.
- Improved links among the README, User Guide, examples, transform-language reference,
  and AGPL license so public-facing material can be curated without private maintainer
  documentation.

### Notes

- The package version remains `0.10.0` during the 0.10.1 documentation and licensing
  implementation slices.

## 0.10.0 - 2026-07-29

### Added

- Completed the 0.10.0a transform recipe and UI-ready language design, including an
  explicitly ordered `[[steps]]` TOML model, seven planned step types, CLI compatibility
  mapping, structured per-step errors, JSON-safe result metadata, and an internal preview
  contract.
- Defined the closed initial row-local expression function set, operators, literals,
  awkward-column syntax, expression metadata, deferred pre-UI function library, and
  intentionally excluded aggregate/window operations.
- Added non-executing transform recipe, step, step-metadata, and expression-function
  specification scaffolding with deterministic JSON-safe serialization and focused
  validation tests.
- Added the 0.10.0b internal closed expression tokenizer, immutable AST,
  recursive-descent parser, lowercase core-function and arity validation, explicit
  deferred/non-row-local function errors, and a non-throwing analysis API.
- Added deterministic first-seen column/function metadata, conservative result-kind
  inference, and zero-based half-open spans for tokens, AST nodes, function and column
  references, operators, and JSON-safe errors.
- Added security regression coverage rejecting Python execution helpers, imports,
  attributes, general indexing, assignment, statements, comments, containers, lambdas,
  comprehensions, and formatted-string syntax.
- Added the 0.10.0c internal ordered recipe planner for select, drop, simultaneous rename,
  type conversion, derive, filter, and recode steps, including projected input/output
  columns, dependencies, intended types, expression analysis, UI flags, and deterministic
  best-effort state.
- Added stable JSON-safe planning issues for unknown/duplicate/colliding columns, invalid
  steps/expressions/recodes, unsupported target types, and missing expression
  dependencies, preserving expression source spans.
- Added internal compatibility translation from existing transform options into the
  current fixed select, drop, rename, type, filter, and recode order, retaining legacy
  structured filter and simultaneous rename semantics without changing live execution.
- Added the 0.10.0d closed vectorized AST evaluator for the core text, numeric, missing,
  conditional, comparison, boolean, and arithmetic operations with structured safe
  evaluation errors.
- Added repeatable `transform --derive COLUMN=EXPRESSION` and
  `--filter-expression EXPRESSION`, conditional `if_else`, planner-backed dependency
  validation, and fixed select/drop/rename/type/derive/structured-filter/expression-filter/
  recode ordering.
- Added explicit policies for preserved text missing values, false missing masks,
  literal case-sensitive matching, numeric-only arithmetic, aligned conditional branches,
  and clear division-by-zero failure.
- Added conservative derived-column metadata synchronization plus fixed-order
  compatibility config fields for derive/expression-filter commands; canonical ordered
  `[[steps]]` execution remains deferred.
- Activated the focused row-local `normalize_whitespace`, `normalize_code`, `null_if`,
  `null_if_empty`, and `default_if_missing` expression helpers with deterministic
  string, equality, missing-value, and index-alignment policies.
- Added recode planner metadata for target mappings, map count/keys, default behavior,
  value-label updates, and missing-value behavior; transform summaries now report
  recoded-column counts.
- Verified that fixed-order recode remains last, can target derived columns, observes
  filtered rows, and retains the existing CLI/config and metadata synchronization
  behavior.
- Added canonical ordered `[[steps]]` transform config import, deterministic export from
  `transform --write-config`, exact file-order execution through existing transformation
  classes, and schema-aware `config validate`.
- Preserved legacy top-level transform configs and added explicit rejection of ambiguous
  configs that mix those fields with `[[steps]]`.
- Added a bounded, non-mutating, JSON-safe internal transform preview API with per-step
  statuses, row/column changes, expression metadata, diagnostics, and sample output rows.
- Added concise ordered-recipe and recipe-step counts to config-run transform summaries.

### Notes

- Existing commands without expression options retain their prior behavior. Structured
  `--filter COLUMN,OPERATOR,VALUE` remains unchanged; expression filtering uses the
  separate `--filter-expression` option.
- Safe expression execution is limited to the documented core row-local language.
  Regex, date/time, explicit conversion, replacement/substring/concatenation, aggregate,
  grouping, and window helpers remain deferred. Streaming transform execution is not
  included, and the GUI remains future 1.0.0 work.

## 0.9.0 - 2026-07-27

### Added

- Added the 0.9.0a private streaming feasibility audit with backend/format and workflow
  matrices, architecture invariants, failure-cleanup policy, and an exact 0.9.0b gate.
- Added immutable internal format feasibility records for all registered extensions,
  JSON-safe capability serialization, positive chunk-size option validation, and a pure
  source/target planning gate.
- Added focused tests that keep feasibility declarations synchronized with the registry
  and prevent planned dependency support from being reported as implemented streaming.
- Added backend-owned CSV and JSONL/NDJSON chunk readers, transactional chunk writers,
  stable ordered-schema validation, backend-neutral chunk/progress/result models, and an
  internal executor for all nine approved source/target pairs.
- Added one-time source-sidecar loading, final-sidecar commit after data commit,
  overwrite/create-directory enforcement, malformed-input and schema-drift cleanup, and
  deterministic empty/header-only behavior.
- Added opt-in `convert --stream` and `--chunk-size ROWS` for all nine CSV/JSONL/NDJSON
  pairs, with a 100,000-row default, CSV option mapping, compact completion summaries, and
  friendly unsupported-pair and option-conflict errors.
- Added opt-in `batch --stream` and shared `--chunk-size ROWS` handling for the same nine
  pairs, preserving deterministic ordering, workers, continue/fail-fast semantics, output
  safety, and per-item sidecars.
- Added batch streaming state and row/chunk metrics to human summaries, machine JSON, and
  CSV/JSON reports, including aggregate streamed totals.
- Added opt-in, contract-only `validate --stream` and shared `--chunk-size ROWS` support
  for CSV, JSONL, and NDJSON, with deterministic chunk/row/rule/column totals.
- Added bounded aggregation for schema and chunk-local contract findings plus exact
  retained-key state for single/composite uniqueness, preserving existing issue codes,
  severities, source rules, samples, JSON contract structure, and exit policy.
- Verified semantic equivalence for every ordered CSV/JSONL/NDJSON conversion pair,
  deterministic streaming validation parity, multi-chunk large-file workflows, and
  transactional cleanup before release.

### Notes

- Streaming remains opt-in on convert, plain batch conversion, and contract validation.
  Normal paths stay in-memory, and JSON arrays plus every non-CSV/JSONL/NDJSON format
  remain non-streaming.
- Batch streaming does not yet support transforms, validation, object modes, or workflow
  config serialization; existing batch configs remain unchanged.
- Streaming validation requires `--schema-contract`; no-contract validation,
  destination-readiness checks, object selection, reports, and config serialization
  remain non-streaming. Exact uniqueness memory grows with distinct complete keys.
- Existing `Dataset`, backend, registry, converter, metadata, configuration, and
  non-streaming behavior remains unchanged outside the explicit streaming options.

## 0.8.0 - 2026-07-27

### Added

- Added the internal version 1 TOML schema-contract model and strict parser.
- Added backend-neutral contract validation results with stable issue codes, expected and
  actual values, affected-row counts, sample values, and source-rule context.
- Added in-memory contract validation for required and unexpected columns, column order,
  resolved storage/logical types, nullability, uniqueness, allowed values, numeric ranges,
  and string regular expressions.
- Added `schema --export-contract` for deterministic, overwrite-protected TOML starter
  contracts built from resolved dataset schema and metadata.
- Added additive `validate --schema-contract` checks with readable terminal findings,
  detailed machine-readable results, existing validation exit semantics, object
  selection, and resolved sidecar/embedded metadata support.
- Extended version 1 contracts with strict named `[[rules]]` for allowed values, numeric
  ranges, regex patterns, single/composite uniqueness, row counts, not-null values, and
  string lengths, including configurable severities and source-rule provenance.
- Added `report --schema-contract` for observational JSON, CSV, and HTML contract
  validation sections with status/count summaries, detailed named-rule findings, and
  bounded samples, reusing the existing evaluated contract result.
- Added `validate` workflow configs and `schema_contract` fields for validate/report
  config validation, execution, starter generation, and deterministic `--write-config`.

### Notes

- Exported starter contracts deliberately omit inferred allowed values, ranges, regular
  expressions, uniqueness, keys, and named quality rules so users can add intentional
  policies without brittle row-derived defaults.
- Schema contract export remains a direct `schema --export-contract` workflow; no
  separate schema workflow-config command was added.
- Contract validation reads an already loaded `Dataset` and does not modify its values or
  metadata.

## 0.7.0 - 2026-07-23

### Added

- Added an internal compatibility matrix covering native and sidecar metadata behavior
  for all 18 registered format extensions.
- Added regression coverage for automatic sidecar reads and writes through inspection,
  conversion, transformation, and batch workflows.
- Added version 3 metadata sidecars with dataset labels, notes, safe normalized raw
  metadata, validation, and minimal source provenance while retaining version 2 reads.
- Added a namespaced StatConvert metadata payload to Parquet and Feather files.
- Added explicit resolved-metadata export through `metadata --export-sidecar`, with
  optional `--sidecar-output` and dedicated `--overwrite-sidecar` protection.
- Added explicit sidecar validation and activation through `metadata --apply-sidecar`,
  with optional `--sidecar-input` and version 3 standardized output.
- Added human-readable CSV/XLSX data dictionary export through
  `metadata --export-dictionary`, with dedicated `--overwrite-dictionary` protection.
- Added deterministic R, Stata, and SPSS metadata helper generation through
  `metadata --export-script`, with dedicated `--overwrite-script` protection.

### Improved

- Pyreadstat metadata normalization now includes dataset labels and notes.
- SAV writing now preserves supported dataset labels, notes, and measurement levels;
  DTA and XPT writing preserve supported dataset labels.
- Sidecar-aware backends now share one parser, serializer, validation, and precedence
  implementation.
- Explicit sidecar apply matches columns by name, rejects missing or duplicate sidecar
  columns, permits extra physical columns, and records minimal explicit-source
  provenance.
- Metadata terminal and report summaries now expose dataset labels, notes, and resolved
  provenance where available.
- Metadata helpers emit conservative target commands and list unsafe names,
  target-incompatible formats, missing definitions, provenance, and other unsupported
  metadata as review comments instead of silently rewriting them.
- Parquet and Feather retain native type/pandas schema metadata, embed a StatConvert
  payload, and continue writing the canonical standardized sidecar.
- Batch input discovery ignores standardized StatConvert metadata sidecars.

### Notes

- The standardized `<data-file>.statconvert-metadata.json` name remains unchanged.
- Existing version 2 sidecars remain readable; new writes use version 3.
- Applying a custom sidecar never changes the primary data file; native SAV, DTA, and XPT
  metadata application remains outside this workflow.
- PyArrow 25 may emit Feather read/write deprecation warnings for the current convenience
  APIs; Feather behavior and the full test suite remain successful.

## 0.6.0 - 2026-07-22

### Added

- Added backend-neutral batch progress events for execution start, real worker item start,
  item finish, and execution finish.
- Added concise human batch workload output and live active worker/file slots.
- Added deterministic close-match suggestions for common format, backend, command, and
  config-field typos.
- Added actionable object-selection, batch no-input, compare-key, and transformation
  error guidance.

### Improved

- Batch completion output now includes output names, requested report paths, and a short
  corrective next step after failures.
- Direct and config-driven batch runs use the same status path, while JSON output continues
  to bypass Rich rendering and remains parseable.
- Worker defaults, scheduling, conversion results, and configuration semantics are
  unchanged.
- Human errors now use a consistent error-and-suggestion layout. Workflow output
  collisions suggest `--overwrite`, config-file collisions suggest
  `--overwrite-config`, and missing output parents suggest `--create-dirs`.
- Config validation errors identify the config file, while JSON command output remains
  separate from Rich rendering and machine-readable.
- Human progress and completion markers fall back to ASCII when the active terminal
  encoding cannot represent their Unicode forms.

### Notes

- No new commands were added; examples remain documentation-only.
- Worker defaults, scheduling, conversion results, and batch execution semantics are
  unchanged.
- No new required dependencies were added.

## 0.5.0 - 2026-07-21

Repeatable workflow configuration release.

### Added

- Added TOML workflow configuration files with deterministic writing through Python
  3.11's standard-library `tomllib` support and no new required dependencies.
- Added `statconvert config init`, `statconvert config validate`, and
  `statconvert config run`.
- Added `config run` execution for `convert`, `transform`, `batch`, `compare`, `report`,
  and `collect` through their existing command and service paths.
- Added `--write-config` to `convert`, `transform`, `batch`, `compare`, `report`, and
  `collect`.
- Added `--overwrite-config` for explicit config-file replacement while preserving
  ordinary `--overwrite` as the saved workflow's output policy.
- Added config validation for required and unknown fields, types, supported formats, and
  command-specific conflicts.

### Notes

- Each config file represents one existing command; 0.5.0 does not introduce a multi-step
  workflow engine.
- `--write-config` writes and validates TOML without executing the workflow.
- Config support adds no required dependency.

## 0.4.0 - 2026-07-18

Performance and large-file hardening release.

### Added

- Added reproducible benchmark tooling under `tools/performance/` with deterministic tiny,
  small, medium, and explicitly enabled large synthetic-data profiles.
- Added subprocess benchmark runs and Markdown/CSV summaries covering elapsed time, output
  size, success/skip state, environment details, and optional `psutil` peak RSS.
- Added batch workload summaries with planned item/file counts, input sizes, worker count,
  target/structure settings, transform and validation state, and object mode.
- Added multi-worker memory guidance and worker-count benchmark comparisons for CSV to
  Parquet and JSON workloads.

### Changed

- JSON, JSONL, and NDJSON record writes now serialize bounded row chunks while preserving
  their existing output structures.
- The measured medium CSV-to-JSON benchmark used about 51% less peak RSS in the 0.4.0b
  before/after run; timings and memory remain machine- and workload-dependent.
- Compare paths avoid unnecessary full Python mask materialization and repeated JSON
  dataclass serialization without changing comparison semantics.
- Feather writing avoids an unnecessary index copy for the default `RangeIndex` path.
- Missing benchmark-profile errors now report required, detected, and missing profiles
  plus an exact data-generation command.
- Documentation now includes safer large-file, dry-run, and batch-worker guidance.

### Notes

- `psutil` remains optional and is used only by benchmark tooling for peak-RSS sampling.
- StatConvert remains DataFrame-based for most operations; JSON can still be memory-heavy,
  and Excel/ODS remain poor choices for very large datasets.
- Prefer Parquet or Feather for large tabular workflows where practical.
- Each active batch worker may hold one dataset in memory. Use `--workers 1` for huge files
  or memory-constrained runs and inspect `batch --dry-run` first.
- 0.4.0 does not add universal streaming/chunking, dynamic worker throttling, or automatic
  memory scheduling. The default batch worker count is unchanged.
- Public distribution remains a wheel attached to the GitHub Release.

## 0.3.0 - 2026-07-18

Compare improvements release.

### Added

- Added `compare --ignore-columns` for excluding nonessential columns from shape,
  schema, metadata, and value comparison.
- Added `compare --numeric-tolerance` for one absolute numeric tolerance.
- Added `compare --key` for row-order-independent matching by one or more comma-separated
  key columns, with unique-key validation on both datasets.
- Added `compare --max-differences` for bounded detailed output, defaulting to 50 examples.
- Added bounded first-difference details for positional/keyed values, side-only rows and
  columns, and schema changes.
- Added expanded compare summaries for rows, columns, cells, schema, row matching, and
  detail truncation.

### Changed

- Compare console output now shows clearer inputs, options, summary counts, and first
  differences.
- JSON compare output now includes a richer structured summary and bounded details while
  retaining the existing full comparison model.
- CSV and HTML compare reports now include clearer summaries and bounded detail rows.
- The roadmap now moves the next major work to 0.4.0 large-file/performance improvements.

### Notes

- Without `--key`, row comparison remains positional. With `--key`, physical row order
  does not matter, but key values must be unique on both sides and key columns cannot be
  ignored.
- Numeric tolerance is absolute-only. `--max-differences` caps examples, not complete
  counts or comparison status.
- Fuzzy matching, duplicate-key reconciliation, joins, merges, appends, deduplication,
  and data-repair workflows are not included.
- Public distribution remains a wheel attached to the GitHub Release.

## 0.2.0 - 2026-07-17

Batch and object workflow release.

### Added

- Added manifest-ready folder and file object discovery reports with `objects --output`.
- Added manifest-driven object conversion with `batch --object-manifest`.
- Added separate-file expansion for every supported object with `batch --all-objects`.
- Added one-container multi-object conversion with `convert --all-objects`.
- Added `collect` for gathering manifest-selected datasets into one XLSX or ODS container.
- Added batch transformations through the existing transformation pipeline with
  `batch --transform`.
- Added backend-neutral multi-object writing for XLSX and ODS outputs.
- Added performance-boundary regression tests and memory guidance for object workflows.

### Changed

- Batch plans, results, and reports now include object selectors and output names where
  relevant.
- Format capabilities now describe object selection and multi-object output behavior.
- Broad streaming, chunking, memory profiling, and performance-tool refresh are deferred
  to the planned 0.4.0 performance work.

### Notes

- `collect` and `convert --all-objects` retain selected datasets in memory before the one
  final container write. Separate batch outputs provide better per-item isolation for very
  large data.
- Object/container workflows do not append, join, merge, or deduplicate rows.
- Current multi-object output targets are XLSX and ODS.
- Public distribution remains a wheel attached to the GitHub Release.

## 0.1.1 - 2026-07-15

### Added

- Added `statconvert --version` to show the StatConvert version, Python version, and important runtime dependency versions.
- Added `--input-encoding` and `--output-encoding` for supported datafile read/write workflows.
- Added `--csv-delimiter` and `--csv-decimal` controls for supported CSV input/output paths on datafile-writing commands.
- Added `--create-dirs` to `convert`, `transform`, `batch`, and `report`.

### Changed

- Improved output safety for `convert`, `transform`, `batch`, and `report`.
- Made overwrite behavior more consistent across datafile-writing and report-writing commands.
- Batch conversion now validates the root output directory while still creating generated preserve-structure subfolders automatically.
- Batch now treats existing output files as per-item failures unless `--overwrite` is supplied.
- Transform and batch dry-runs do not create directories, write files, or replace files.

### Fixed

- Report output now rejects existing output files unless `--overwrite` is supplied.
- Missing output directories now fail with a clear message unless `--create-dirs` is supplied.
- Unsupported encoding options now produce friendly warnings instead of being silently confusing.

## 0.1.0 - 2026-07-14

Initial public release of StatConvert.

### Added

- Dataset conversion across common statistical and tabular formats.
- Dataset inspection, schema, labels, metadata, summaries, descriptions, frequencies, missing-value analysis, and validation.
- Batch conversion.
- Dataset comparison.
- HTML, JSON, and CSV reports.
- Excel, ODS, RDS, RData/RDA object and sheet selection.
- Genuine legacy `.xls` output support.
