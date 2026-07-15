# StatConvert

StatConvert is a Python 3.11 command-line toolkit for converting, transforming,
inspecting, validating, batch-processing, comparing, reporting, and logging statistical
datasets. It uses a backend registry and a common `Dataset` model so format-specific code
stays out of conversion and analysis workflows.

## Implemented features

- Conversion between registered statistical, spreadsheet, JSON, Arrow, and R formats
- Normalized schema, variable-label, value-label, missing-value, and metadata access
- Ordered transformations: select, drop, rename, type conversion, filtering, and recoding
- Dataset summary, descriptive profiles, frequencies, and missing-value analysis
- Dataset-quality and target-format validation
- Deterministic batch planning, parallel execution, validation, progress, and CSV/JSON reports
- Dataset comparison with terminal, JSON, CSV, and HTML output
- Generic dataset-object discovery and selection for Excel/ODS sheets and RData objects
- Single-dataset reports in HTML, JSON, and CSV
- Opt-in file diagnostics across every public command
- Plain-text installed version, Python version, and runtime dependency status

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

## Quick start

```bash
statconvert formats
statconvert objects workbook.xlsx
statconvert peek input.sav
statconvert convert input.sav output.xlsx
statconvert convert input.sav new-output/output.xlsx --create-dirs
statconvert convert workbook.xlsx output.csv --object Data
statconvert validate input.sav --to parquet
statconvert compare before.sav after.parquet
statconvert report input.sav --output report.html
statconvert batch input-folder output-folder --to parquet
```

Commands that write files refuse to replace an existing output unless `--overwrite` is
used. `convert`, `transform`, `batch`, and `report` accept `--create-dirs` for a missing
user-specified output directory; dry-run does not create directories or write files.

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
