# Changelog

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

- Added batch workload summaries with planned item/file counts, input sizes, worker count,
  target/structure settings, transform and validation state, and object mode.
- Added multi-worker memory guidance for CSV-to-Parquet and CSV-to-JSON workloads.

### Changed

- JSON, JSONL, and NDJSON record writes now serialize bounded row chunks while preserving
  their existing output structures.
- Compare paths avoid unnecessary full Python mask materialization and repeated JSON
  dataclass serialization without changing comparison semantics.
- Feather writing avoids an unnecessary index copy for the default `RangeIndex` path.
- Documentation now includes safer large-file, dry-run, and batch-worker guidance.

### Notes

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
