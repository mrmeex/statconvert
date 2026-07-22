# StatConvert

StatConvert is a Python 3.11 command-line toolkit for converting, transforming,
inspecting, validating, batch-processing, comparing, reporting, and logging statistical
datasets. It uses a backend registry and a common `Dataset` model so format-specific code
stays out of conversion and analysis workflows.

Version 0.6.0 improves operator experience with clearer batch workload and live worker
status, planning-only dry-run messaging, concise completion summaries, and consistent
friendly errors with deterministic suggestions. Direct and config-driven workflows share
the same behavior, and JSON output remains machine-readable. No new commands or required
dependencies are introduced.

## Implemented features

- Conversion between registered statistical, spreadsheet, JSON, Arrow, and R formats
- Normalized schema, variable-label, value-label, missing-value, and metadata access
- Ordered transformations: select, drop, rename, type conversion, filtering, and recoding
- Dataset summary, descriptive profiles, frequencies, and missing-value analysis
- Dataset-quality and target-format validation
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
- Reproducible private benchmark data generation, subprocess measurement, optional
  `psutil` peak-RSS sampling, and Markdown/CSV result summaries

Dataset comparison is provided by `statconvert compare`. There is currently no separate
`statconvert diff` alias.

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

Repository source and editable installations are maintainer workflows, not public
installation methods.

## Quick start

```bash
statconvert formats
statconvert objects workbook.xlsx
statconvert objects incoming --recursive --output objects.csv
statconvert batch incoming converted --to csv --object-manifest objects.csv --create-dirs
statconvert batch incoming converted --to csv --all-objects
statconvert batch incoming converted --to parquet --transform --select id --select name
statconvert peek input.sav
statconvert convert input.sav output.xlsx
statconvert convert input.sav new-output/output.xlsx --create-dirs
statconvert convert workbook.xlsx output.csv --object Data
statconvert convert workbook.xlsx combined.ods --all-objects
statconvert collect objects.csv combined.xlsx --base-dir incoming
statconvert validate input.sav --to parquet
statconvert compare before.sav after.parquet
statconvert compare before.csv after.csv --ignore-columns exported_at --numeric-tolerance 0.001
statconvert compare before.csv after.csv --key id --max-differences 10
statconvert report input.sav --output report.html
statconvert batch input-folder output-folder --to parquet
statconvert batch input-folder output-folder --to parquet --workers 2 --dry-run
statconvert config init batch --output batch.toml
statconvert config validate batch.toml
statconvert config run batch.toml
statconvert convert input.csv output.parquet --write-config convert.toml
statconvert transform input.csv output.parquet --select id --write-config transform.toml
statconvert batch incoming converted --to parquet --workers 1 --write-config batch.toml
statconvert compare old.csv new.csv --key id --write-config compare.toml
statconvert report input.csv --output report.html --preset quick --write-config report.toml
statconvert collect manifest.csv workbook.xlsx --write-config collect.toml
```

`config run` executes `convert`, `transform`, `batch`, `compare`, `report`, and `collect`
workflows. Each matching command accepts `--write-config FILE`, which writes validated
TOML and does not run the workflow; use `--overwrite-config` to replace an existing
config. Config loading uses Python 3.11's standard-library `tomllib` and adds no required
dependency.

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

Use `statconvert capabilities FORMAT` for detailed runtime capabilities. Important output
restrictions include:

- Legacy `.xls` reading uses `xlrd` and genuine BIFF writing uses `xlwt`; both are included
  by the normal installation. Use `.xlsx` beyond the legacy row/column limits.
- `.zsav`, `.por`, and `.sas7bdat` are readable but not writable.
- Statistical metadata preservation depends on the destination. Metadata-poor formats use
  a `*.statconvert-metadata.json` sidecar when written by StatConvert.

See [Examples and Recipes](docs/examples.md) for copyable workflows, the
[Format Guide](docs/formats.md) for the complete extension matrix, and the
[CLI Reference](docs/cli.md) for command options and exit behavior.

## Documentation

- [User Guide](docs/user-guide.md) - practical end-user manual for everyday workflows
- [Administrator Guide](docs/admin-guide.md) - installation, managed deployment, and support
- [Examples and Recipes](docs/examples.md) - copyable workflows for common tasks
- [CLI Reference](docs/cli.md) - commands, options, output, and exit behavior
- [Format Guide](docs/formats.md) - format-specific usage, capabilities, metadata, and caveats

## License

License to be determined.
