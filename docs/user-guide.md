# User Guide

## Who this guide is for

This guide is for people who use StatConvert to convert, inspect, validate, report on,
compare, transform, or batch-convert datasets. It focuses on practical, everyday use.
Exact options and exit codes remain in the [CLI Reference](cli.md), while copyable
workflows and task-oriented recipes remain in [Examples and Recipes](examples.md).

## What StatConvert does

StatConvert is a command-line tool for statistical and tabular data. It reads a dataset
through the backend for its format, represents the data and available metadata in a common
internal model, and then writes, inspects, validates, compares, transforms, or reports on
that dataset.

StatConvert focuses on dataset content: rows, columns, types, labels, missing-value
definitions, and other metadata where the source and destination support them. It is not
a spreadsheet editor. Converting an Excel or ODS workbook does not preserve rich workbook
features such as formatting, formulas, macros, charts, or existing sheets.

## Before you start

StatConvert requires Python 3.11 or newer. Install the downloaded release wheel from the
GitHub Releases page; installation, upgrades, and managed deployment are covered by the
[Administrator Guide](admin-guide.md).

Verify the installed command and list the formats available in the current environment:

```powershell
python -m statconvert --version
python -m statconvert --help
python -m statconvert formats
```

`--version` also reports the Python version and important runtime dependency versions.
Any unavailable dependency is shown as `not installed`. If the `statconvert` console
command is on `PATH`, `statconvert --version` provides the same report.

The examples in this guide use PowerShell-friendly syntax. Quote paths that contain
spaces:

```powershell
statconvert convert "C:\Data\input.sav" "C:\Data\output.xlsx"
```

If the `statconvert` command is not found, try `python -m statconvert --help` and see
[Common problems and fixes](#common-problems-and-fixes).

## Basic workflow

A cautious conversion workflow discovers capabilities, checks the input, validates the
planned destination, converts the file, and reviews the result:

```powershell
statconvert formats
statconvert peek input.sav
statconvert info input.sav
statconvert validate input.sav --to xlsx
statconvert convert input.sav output.xlsx
statconvert report output.xlsx --output report.html
```

`formats` confirms that the input and output are supported. `peek` shows sample rows,
while `info` confirms dimensions and types. Target validation catches known destination
constraints before conversion. The final report provides a convenient review of the
written dataset.

This sequence is a useful default, not a requirement. For a familiar dataset and target,
you can run `convert` directly.

## Checking supported formats

Use `formats` for the installed extension matrix and `capabilities` for one format or
backend:

```powershell
statconvert formats
statconvert capabilities xlsx
statconvert capabilities rdata
```

Read support, write support, and metadata support vary by format. Some formats are
read-only, and container formats can expose sheets or named objects that must be selected.
The [Format Guide](formats.md) contains the complete matrix, metadata behavior, and
format-specific caveats.

## Previewing a dataset

Preview the first five rows with:

```powershell
statconvert peek input.sav
```

Use `--rows` when a different preview size is useful:

```powershell
statconvert peek input.sav --rows 10
```

For a compact overview of the source backend, dimensions, variables, and types, use:

```powershell
statconvert info input.sav
```

Preview commands read the selected dataset but do not create an output file.

## Converting files

The basic conversion command takes an input path and an output path:

```powershell
statconvert convert input.sav output.xlsx
statconvert convert input.dta output.parquet
statconvert convert input.csv output.jsonl
statconvert convert input.csv output.xls
```

The output format is inferred from the output filename extension. A read-only or unknown
target is rejected before writing. If the output already exists, choose another path or
replace it explicitly:

```powershell
statconvert convert input.sav output.xlsx --overwrite
statconvert convert input.sav new-output/output.xlsx --create-dirs
```

StatConvert does not replace an existing output unless `--overwrite` is supplied. If the
output parent directory is missing, the command fails unless `--create-dirs` is supplied.
No directory flag is needed for the current directory or any existing directory.

For CSV dataset output, select an encoding, one-character delimiter, or one-character
decimal separator:

```powershell
statconvert convert input.sav output.xlsx --input-encoding cp1252
statconvert convert input.csv output.xlsx --input-encoding latin1 --csv-delimiter ";"
statconvert convert input.xlsx output.csv --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert legacy.csv clean.csv --input-encoding latin1 --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert input.xlsx output.csv --csv-delimiter ";" --csv-decimal ","
```

These options are available on `convert`, `transform`, and `batch` because those commands
write dataset files. `--input-encoding` applies only to a supporting input reader, while
`--output-encoding` applies only to a supporting output writer. StatConvert warns and
continues when the selected backend cannot apply a directional encoding option. The
CSV-specific delimiter and decimal options apply to CSV input/output paths; both must be
one character and cannot be equal when supplied together. Read-only command support,
sniffing, and dialect presets are not provided.

Legacy `.xls` output is a genuine Excel 97-2003 BIFF file. It is limited to 65,535 data
rows plus one header row and 256 columns. Use `.xlsx` for larger or wider Excel output.
The [Format Guide](formats.md) describes other read/write and metadata restrictions.

## Working with Excel and ODS workbooks

StatConvert calls each selectable sheet or named R workspace item a *dataset object*.
Excel `.xlsx` and `.xls` files and ODS workbooks can contain multiple sheets. List them
before reading a multi-sheet workbook:

```powershell
statconvert objects workbook.xlsx
```

Select a sheet by exact name or zero-based index:

```powershell
statconvert convert workbook.xlsx output.csv --object Data
statconvert peek workbook.xlsx --object 0
```

When exactly one supported sheet exists, StatConvert selects it automatically. When more
than one exists, an explicit `--object` is required; StatConvert never silently selects
the first sheet. The same policy applies to `.xls` and `.ods` workbooks.

Single-dataset formats such as CSV and Parquet do not have selectable objects and reject
`--object` rather than ignoring it. Object selection chooses input content; it does not
preserve or edit an entire workbook.

## Working with RDS, RData and RDA files

An `.rds` file stores one R object. StatConvert can convert it when that object is
supported as tabular data, and `--object` is not used:

```powershell
statconvert convert dataset.rds dataset.csv
```

`.rdata` and `.rda` files are workspaces and may contain multiple named R objects. List
the objects, then select a supported tabular object by exact name or zero-based index:

```powershell
statconvert objects workspace.rdata
statconvert convert workspace.rdata patients.csv --object patients
```

If exactly one supported tabular object exists, it can be selected automatically. If
several exist, `--object` is required. Unsupported objects may appear in `objects` output
with an explanation when the R backend can describe them; object types the backend cannot
expose may not be listed. StatConvert does not promise conversion of arbitrary R objects.

## Inspecting metadata, labels and schema

Use these commands to examine structure and statistical metadata without writing a new
dataset:

```powershell
statconvert schema input.sav
statconvert metadata input.sav
statconvert labels input.sav
```

- `schema` shows column names, normalized storage types, labels, metadata counts, display
  formats, and measurement levels.
- `metadata` summarizes the normalized metadata available for the dataset.
- `labels` displays variable labels and value labels when they exist.

Statistical formats commonly contain richer labels and missing-value definitions than
CSV or spreadsheet data. When StatConvert writes a metadata-poor format, it may create a
sibling `*.statconvert-metadata.json` sidecar. Keep the sidecar beside the data file if you
want a later StatConvert read to restore that metadata. Other tools may ignore the
sidecar.

## Summaries, profiles, frequencies and missing values

StatConvert provides several levels of statistical inspection:

```powershell
statconvert summary input.sav
statconvert describe input.sav
statconvert frequencies input.sav
statconvert missing input.sav
```

- `summary` gives a dataset-level overview such as dimensions, type counts, missing cells,
  duplicate rows, and memory use.
- `describe` profiles individual columns.
- `frequencies` shows value counts, with limits to keep high-cardinality output practical.
- `missing` separates actual nulls from metadata-defined missing values and ranges.

These four commands support `--json` for machine-readable output. Column selection and
other inspection controls are documented in the [CLI Reference](cli.md).

## Validating datasets

Validation checks dataset quality and, optionally, readiness for a target format:

```powershell
statconvert validate input.sav
statconvert validate input.sav --to xlsx
statconvert validate input.csv --to xls
statconvert validate input.sav --to xlsx --strict
```

Without `--to`, validation reports general dataset issues. With `--to`, it also checks
known destination constraints and metadata-preservation concerns. For example, XLS target
validation checks the legacy row and column limits.

Validation exits with failure when it finds errors. `--strict` also makes warnings fail,
which is useful in automated quality gates. Validation can identify known structural and
format problems, but it cannot guarantee that the data is semantically correct for its
real-world purpose.

## Creating reports

Reports combine dataset summary, schema, metadata, labels, missing-value analysis,
column profiles, and validation according to the selected preset and sections:

```powershell
statconvert report input.sav --output report.html
statconvert report input.sav --output report.json
statconvert report input.sav --output report.csv
```

HTML is convenient for viewing and sharing. JSON is suited to downstream processing, and
CSV provides table-oriented report output. Report contents and presets are described in
the [CLI Reference](cli.md#report). PDF reports are not currently supported.

## Comparing datasets

Compare two datasets directly, select the same object on both sides, or use independent
selectors when the object names differ:

```powershell
statconvert compare before.csv after.csv
statconvert compare before.xlsx after.xlsx --object Data
statconvert compare before.xlsx after.xlsx --left-object Old --right-object New
statconvert compare before.csv after.xlsx --right-object Data
```

Comparison checks shape, column membership and order, schema, normalized metadata, and
values by default. Use `--no-values` for a structure-and-metadata comparison. `--strict`
makes warning-level differences fail as well as error-level differences.

The comparison is positional rather than key-based. Key matching, numeric tolerance,
ignored-column policies, and chunked comparison are not currently implemented. See the
[CLI Reference](cli.md#compare) for sampling, column selection, JSON, and report options.

## Batch conversion

Use `batch` to plan and convert many files to one target format:

```powershell
statconvert batch input-folder output-folder --to parquet
statconvert batch input-folder output-folder --to csv --recursive
statconvert batch input-folder output-folder --to csv --csv-delimiter ";"
statconvert batch workbooks output-folder --to parquet --object Data
statconvert batch input-folder output-folder --to xlsx --dry-run
```

`--recursive` includes subdirectories. A dry run previews the deterministic file and
output plan without converting data, creating directories, or replacing files. The root
output folder must already exist unless `--create-dirs` is supplied. Preserve-structure
subfolders generated below an existing root are created automatically during execution.
Because dry runs do not read container contents,
object-selection problems are detected during execution rather than during the dry run.

`--object` applies the same exact name or zero-based index to every pending input. Batch
does not expand every sheet or R object. In a mixed batch, a single-dataset input such as
CSV fails as an individual item when `--object` is present; the selector is not silently
ignored.

Batch transformations are not implemented. Use `transform` on individual files or batch
plain conversions with `batch`.

Batch accepts the same `--input-encoding`, `--output-encoding`, `--csv-delimiter`, and
`--csv-decimal` controls as `convert`. Unsupported encoding directions warn and continue.

## Transforming datasets

The `transform` command provides practical dataset shaping while reading one input and
writing one output:

```powershell
statconvert transform input.csv output.csv --select id --select name
statconvert transform input.csv output.csv --rename old_name=new_name
statconvert transform input.csv output.csv --type age=int
statconvert transform input.csv output.csv --filter age,gte,18
statconvert transform input.xlsx output.csv --csv-delimiter ";"
```

Transformations can select or drop columns, rename columns, change types, filter rows, and
recode values. When several operations are combined, the order is fixed: select, drop,
rename, type conversion, filtering, then recoding. This makes a command predictable but
means later operations must use names and values produced by earlier operations.

Use `transform --dry-run` to inspect the planned pipeline without writing. The complete
syntax for filters, recoding, type errors, validation, and object selection is in the
[CLI Reference](cli.md#transform).

## JSON output

Machine-readable JSON output is intended for scripts and automation. The commands
`objects`, `summary`, `describe`, `frequencies`, `missing`, `validate`, `batch`, and
`compare` support JSON on standard output:

```powershell
statconvert summary input.sav --json
statconvert validate input.sav --json
statconvert compare before.csv after.csv --json
```

Commands such as `info`, `peek`, `schema`, `labels`, and `metadata` do not currently have
a `--json` option. For `report`, the output filename selects an HTML, JSON, or CSV report;
`report --json` separately requests a concise JSON completion summary after writing the
report.

JSON output is written separately from Rich terminal rendering and can be redirected or
piped to another program. Keep diagnostic logging in a file so standard output remains
machine-readable.

## Logging

Every public command can write an opt-in diagnostic log:

```powershell
statconvert convert input.sav output.xlsx --log statconvert.log
statconvert validate input.sav --log validation.log --log-level debug
```

Logs are useful for troubleshooting and audit trails. Normal terminal or JSON output
remains separate from the log file. By default an existing selected log is replaced; use
`--log-append` to retain earlier entries. The [CLI Reference](cli.md#logging-options)
documents log levels and developer-oriented diagnostics.

## Common problems and fixes

### `statconvert` command not found

Try `python -m statconvert --version` or `python -m statconvert --help`. On Windows, pip
may have installed `statconvert.exe` in a Python `Scripts` directory that is not on
`PATH`. See the [Administrator Guide](admin-guide.md#windows-path-behavior).

### A multi-sheet workbook fails without `--object`

Run `statconvert objects workbook.xlsx`, then repeat the command with the exact sheet name
or zero-based index, such as `--object Data` or `--object 0`.

### An RData or RDA workspace reports multiple objects

Run `statconvert objects workspace.rdata`, choose an object marked as supported, and
repeat the command with `--object NAME`.

### XLS conversion exceeds a row or column limit

Legacy XLS cannot hold more than 65,535 data rows plus a header or more than 256 columns.
Use an `.xlsx` output path instead.

### The output file already exists

Choose a different output path or add `--overwrite` to `convert`, `transform`, `batch`, or
`report` when replacement is intentional.

### The output directory does not exist

Create it first or add `--create-dirs` to `convert`, `transform`, `batch`, or `report`.
For batch this applies only to the user-specified root; generated preserve-structure
subfolders are created automatically below an existing root.

### Metadata or labels are missing after conversion

The source may not contain that metadata, or the target may not support it natively. Check
the [Format Guide](formats.md#metadata-preservation) and keep any generated
`.statconvert-metadata.json` sidecar beside the output.

### Batch with `--object` fails on CSV or other single-dataset files

`--object` is only valid for container formats. Batch applies the selector strictly to
every input and reports unsupported selection as an item failure. Separate the inputs or
run the single-dataset files without `--object`.

### A PDF report was requested

PDF output is not supported. Generate an HTML, JSON, or CSV report instead.

## Where to go next

- [Examples and Recipes](examples.md) for copyable task-oriented workflows
- [CLI Reference](cli.md) for every command option and exit policy
- [Format Guide](formats.md) for the capability matrix and format caveats
- [Administrator Guide](admin-guide.md) for installation, updates, and deployment
