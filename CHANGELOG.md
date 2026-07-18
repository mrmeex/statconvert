# Changelog

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
- Public distribution remains a wheel attached to the GitHub Release; StatConvert is not
  published to PyPI.

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
- Public distribution remains a wheel attached to the GitHub Release; StatConvert is not
  published to PyPI.

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
- XLS and RData/RDA multi-object output remain deferred; current multi-object output
  targets are XLSX and ODS.
- Public distribution remains a wheel attached to the GitHub Release; StatConvert is not
  published to PyPI.

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
