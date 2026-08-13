# StatConvert

StatConvert is a Python 3.11 command-line toolkit and optional local browser interface for converting, transforming,
inspecting, validating, batch-processing, comparing, reporting, and logging statistical
datasets. It uses a backend registry and a common `Dataset` model so format-specific code
stays out of conversion and analysis workflows.

Version 1.3.1 stabilizes the 1.3.0 transform workflow. Empty browser transform plans no
longer validate, full-impact preview remains available when an output or sidecar collision
blocks execution, and extensionless recipe-save paths consistently receive `.toml`. The
release adds no operations, formats, ORC or database support, or runtime dependencies. The
local browser UI remains bound to the local machine and is installed through the optional
`statconvert[ui]` extra; the CLI keeps its 11 base runtime dependencies.

## Implemented features

- Conversion between registered statistical, spreadsheet, JSON, Arrow, and R formats
- Normalized schema, variable-label, value-label, missing-value, and metadata access
- Versioned metadata sidecars, Arrow-embedded StatConvert metadata, resolved-metadata
  export/apply, human-readable data dictionaries, and external-tool helper scripts
- Read-only metadata diagnostics, diagnostic sidecar validation, metadata-only diff, and
  richer metadata coverage in reports
- Preview-first, sidecar-only metadata editing for dataset labels/notes, variable and typed
  value labels, and measurement levels
- Ordered transformations: select, drop, rename, type conversion, derived columns,
  expression and structured filtering, and recoding
- Path-independent version-1 transform recipes with deterministic TOML, typed recode
  mappings, atomic save/load, syntax or input-bound validation, and full-impact preview
- Canonical ordered workflow-config `[[steps]]` with exact-order execution and legacy
  transform-config compatibility
- Closed row-local expression functions for text, numeric, missing-value, conditional,
  normalization, conversion, date/time, validation, and list-membership workflows
- Dataset summary, descriptive profiles, frequencies, and missing-value analysis
- Dataset-quality and target-format validation, versioned schema contracts, and named
  allowed-value, range, regex, uniqueness, row-count, not-null, and length rules
- Deterministic batch planning, parallel execution, shared transformation pipelines,
  validation, progress, workload summaries, worker-memory guidance, and CSV/JSON reports
- Dataset comparison with positional or unique-key row matching, ignored columns,
  absolute numeric tolerance, bounded details, and terminal/JSON/CSV/HTML output
- File and folder dataset-object discovery with manifest-ready CSV/JSON reports, plus
  selection for Excel/ODS sheets and RData objects
- Whole-container conversion from XLSX/ODS/RData/RDA/XLS inputs to multi-sheet XLSX or
  ODS outputs
- Manifest-controlled collection from multiple input files and selected objects into one
  XLSX or ODS output container
- Single-dataset reports in HTML, JSON, and CSV
- Opt-in file diagnostics across every public command
- Plain-text installed version, Python version, and runtime dependency status
- TOML starter generation and validation for repeatable single-command workflows
- Opt-in streaming conversion and batch conversion for all nine ordered pairs among CSV,
  JSONL, and NDJSON, plus contract-only streaming validation for those inputs
- Optional local browser UI for Inspect, Convert, Batch Convert, Validate, Transform,
  Configs, Compare, Report, Collect, Reference, Settings, and About

Dataset comparison is provided by `statconvert compare`. There is currently no separate
`statconvert diff` alias.

Portable recipes contain ordered steps only: no input/output paths, selectors, execution
policy, or executable code. `transform --preview --json` applies the full recipe to a
copied dataset and writes nothing. Recipes support the seven existing transformations plus
stable multi-key sort, order-preserving distinct, and deterministic row number. Batch
recipe loading, ORC, and database support are not part of the current implementation.

## Installation

StatConvert requires Python 3.11 or newer. Public releases are distributed as wheel
files attached to the GitHub Releases page. Download
`statconvert-<version>-py3-none-any.whl`, open PowerShell in the download folder, and
install that exact file:

```powershell
python -m pip install .\statconvert-<version>-py3-none-any.whl
python -m statconvert --version
python -m statconvert --help
python -m statconvert formats
```

The wheel install includes dependencies for every supported format. See the
[Administrator Guide](docs/admin-guide.md) for wheel deployment, verification, updates,
and Windows `PATH` guidance. If the `statconvert` console command is not found, continue
using `python -m statconvert` or add the active Python environment's Scripts directory
to `PATH`.

`python -m statconvert --version` reports the installed StatConvert and Python versions
plus each important runtime dependency. Missing dependencies are shown as
`not installed`. The equivalent `statconvert --version` form works when the console
command is on `PATH`.

Install the optional local browser interface after downloading the wheel:

```powershell
python -m pip install ".\statconvert-<version>-py3-none-any.whl[ui]"
statconvert ui
```

The browser opens at `http://statconvert.localhost:<port>` when available while the
server remains bound to `127.0.0.1`. The UI has no accounts, cloud processing,
telemetry, or remote-server mode.

## Quick start

Start with `statconvert formats` before choosing a destination. ZSAV, POR, and SAS7BDAT
are read-only inputs; SAV is the suggested writable SPSS alternative and XPT the suggested
SAS interchange alternative when those target models fit. These are explicit conversions,
not automatic substitutions. The [Format Guide](docs/formats.md) explains streaming,
container objects, metadata modes, and fidelity limits.

```bash
statconvert formats
statconvert objects workbook.xlsx
statconvert objects incoming --recursive --output objects.csv
statconvert batch incoming converted --to csv --object-manifest objects.csv --create-dirs
statconvert batch incoming converted --to csv --all-objects
statconvert batch incoming converted --to parquet --transform --select id --select name
statconvert peek input.sav
statconvert metadata input.sav --export-sidecar
statconvert metadata input.sav --export-dictionary dictionary.xlsx
statconvert metadata input.sav --export-script labels.R
statconvert metadata input.sav --diagnose
statconvert metadata input.csv --validate-sidecar --json
statconvert metadata-diff before.sav after.csv --report metadata-diff.html
statconvert metadata input.csv --patch metadata.toml --sidecar-output edited.json --dry-run
statconvert metadata input.csv --patch metadata.toml --sidecar-output edited.json
statconvert convert input.sav output.xlsx
statconvert convert input.csv output.jsonl --stream --chunk-size 50000
statconvert convert input.sav new-output/output.xlsx --create-dirs
statconvert convert workbook.xlsx output.csv --object Data
statconvert convert workbook.xlsx combined.ods --all-objects
statconvert collect objects.csv combined.xlsx --base-dir incoming
statconvert validate input.sav --to parquet
statconvert ui
statconvert schema input.sav --export-contract schema.toml
statconvert validate input.sav --schema-contract schema.toml
statconvert validate input.csv --schema-contract schema.toml --stream
statconvert report input.sav --output quality.html --schema-contract schema.toml
statconvert compare before.sav after.parquet
statconvert compare before.csv after.csv --ignore-columns exported_at --numeric-tolerance 0.001
statconvert compare before.csv after.csv --key id --max-differences 10
statconvert transform input.csv output.csv --derive "email_clean=lower(strip(email))"
statconvert transform input.csv output.csv --filter-expression "age >= 18"
statconvert report input.sav --output report.html
statconvert batch input-folder output-folder --to parquet
statconvert batch incoming-csv output-jsonl --to jsonl --stream --chunk-size 50000
statconvert batch input-folder output-folder --to parquet --workers 2 --dry-run
statconvert config init batch --output batch.toml
statconvert config validate batch.toml
statconvert config run batch.toml
statconvert convert input.csv output.parquet --write-config convert.toml
statconvert transform input.csv output.parquet --select id --write-config transform.toml
statconvert config validate transform.toml
statconvert config run transform.toml
statconvert batch incoming converted --to parquet --workers 1 --write-config batch.toml
statconvert compare old.csv new.csv --key id --write-config compare.toml
statconvert validate input.csv --schema-contract schema.toml --write-config validate.toml
statconvert report input.csv --output report.html --preset quick --write-config report.toml
statconvert collect manifest.csv workbook.xlsx --write-config collect.toml
```

`config run` executes `convert`, `transform`, `batch`, `compare`, `validate`, `report`,
and `collect` workflows. Each matching command accepts `--write-config FILE`, which
writes validated TOML and does not run the workflow; use `--overwrite-config` to replace
an existing config. Config loading uses Python 3.11's standard-library `tomllib` and adds
no required dependency.

New transform configs use canonical ordered `[[steps]]`. Steps execute in file order and
support select, drop, rename, type conversion, derive, expression filter, and recode.
Existing top-level transform configs remain supported, but cannot be mixed with
`[[steps]]`.

Human batch runs show planned workload settings before execution, stable active-worker
slots while work is running, and complete success, failure, skipped, and blocked counts
afterward. Dry-run is explicitly planning-only. Human errors distinguish `--overwrite`,
`--overwrite-config`, and `--create-dirs`; JSON modes bypass Rich progress and error
rendering so stdout stays parseable.

Commands that write files refuse to replace an existing output unless `--overwrite` is
used. `convert`, `collect`, `transform`, `batch`, `report`, and `objects --output` accept
`--create-dirs` for a missing
user-specified output directory; dry-run does not create directories or write files.

Batch conversion, including `batch --all-objects` and `batch --transform`, processes each
planned item independently. Dry-run reports planned workload size and worker settings;
each active worker may hold one dataset in memory, so use `--workers 1` for huge or
memory-constrained runs. By contrast, `convert --all-objects` and `collect` must hold
their selected datasets in memory before writing one final XLSX or ODS container. For very
large inputs, prefer separate Parquet/Feather batch outputs over JSON/Excel/ODS where
practical. Object listing is metadata-oriented, although
RData/RDA discovery may load workspace data because of backend-library limitations.

Streaming is explicitly enabled with `--stream` and is limited to CSV, JSONL, and NDJSON.
All nine source/target pairs are available for `convert` and plain `batch`; streaming
validation accepts those three inputs and requires `--schema-contract`. Exact uniqueness
validation retains observed keys in memory. Streaming conversion writes its metadata
sidecar only after the data file commits successfully. Transforms, reports, compare,
collect, object modes, JSON arrays, and other formats are not streamed.

Use `statconvert capabilities FORMAT` for detailed runtime capabilities. Important output
restrictions include:

- Legacy `.xls` reading uses `xlrd` and genuine BIFF writing uses `xlwt`; both are included
  by the normal installation. Use `.xlsx` beyond the legacy row/column limits.
- `.zsav`, `.por`, and `.sas7bdat` are readable but not writable.
- Statistical metadata preservation depends on the destination. Metadata-poor formats use
  a `*.statconvert-metadata.json` sidecar when written by StatConvert.

The runtime registry contains 18 extensions across CSV, spreadsheet, statistical,
JSON-record, Arrow-columnar, and R format families. The local browser **Reference** page
reads that same registry and shows read/write, streaming, metadata mode, object support,
and important caveats. StatConvert does not currently support database files, ORC, Avro,
HDF5, MATLAB MAT, XML tables, HTML tables as datasets, or DDI/codebook import/export.

See [Examples and Recipes](docs/examples.md) for copyable workflows, the
[Format Guide](docs/formats.md) for the complete extension matrix, and the
[CLI Reference](docs/cli.md) for command options, ordered recipes, safe expressions,
and exit behavior.

## Documentation

- [User Guide](docs/user-guide.md) - practical end-user manual for everyday workflows
- [Browser UI Guide](docs/ui.md) - local UI installation, workflows, settings, and troubleshooting
- [Administrator Guide](docs/admin-guide.md) - installation, managed deployment, and support
- [Examples and Recipes](docs/examples.md) - copyable workflows for common tasks
- [CLI Reference](docs/cli.md) - commands, options, output, and exit behavior
- [Format Guide](docs/formats.md) - format-specific usage, capabilities, metadata, and caveats
- [License](LICENSE) - GNU Affero General Public License v3.0 or later

## License

StatConvert is licensed under the GNU Affero General Public License v3.0 or later
(`AGPL-3.0-or-later`). See [LICENSE](LICENSE) for details.
