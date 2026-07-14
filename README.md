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

Dataset comparison is provided by `statconvert compare`. There is currently no separate
`statconvert diff` alias.

## Installation

StatConvert requires Python 3.11 or newer and is distributed as a wheel attached to a
GitHub Release.

1. Open the StatConvert GitHub Releases page and download the latest
   `statconvert-<version>-py3-none-any.whl` file.
2. Open PowerShell in the download folder.
3. Install the downloaded wheel:

```powershell
python -m pip install .\statconvert-<version>-py3-none-any.whl
```

4. Verify the installation:

```powershell
python -m statconvert --help
python -m statconvert formats
```

If the `statconvert` command is not found, continue using `python -m statconvert` or add
the selected Python environment's `Scripts` directory to `PATH`. The wheel installation
includes dependencies for every supported format. See the
[Administrator Guide](docs/admin-guide.md) for detailed wheel deployment, updates, and
Windows `PATH` guidance.

## Quick start

```bash
statconvert formats
statconvert objects workbook.xlsx
statconvert peek input.sav
statconvert convert input.sav output.xlsx
statconvert convert workbook.xlsx output.csv --object Data
statconvert validate input.sav --to parquet
statconvert compare before.sav after.parquet
statconvert report input.sav --output report.html
statconvert batch input-folder output-folder --to parquet
```

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
