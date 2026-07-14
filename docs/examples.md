# Examples and Recipes

## How to use these examples

This guide is a copy-and-adapt recipe book for common StatConvert workflows. Install
StatConvert from the downloaded GitHub Release wheel before using these recipes. The
examples assume the command is available as `statconvert`; if it is not on `PATH`, replace
it with `python -m statconvert`.

The commands use PowerShell-friendly syntax and relative paths for readability. Replace
the sample filenames, sheet names, R object names, and columns with values from your own
data. Quote any path or object name that contains spaces:

```powershell
statconvert convert "C:\Data Files\survey.sav" "C:\Converted Files\survey.xlsx"
```

Run `statconvert --help` or command-specific help such as
`statconvert convert --help` for the complete option list. The
[User Guide](user-guide.md) explains the overall workflow, the
[CLI Reference](cli.md) defines exact syntax and exit behavior, and the
[Format Guide](formats.md) records format capabilities and caveats.

Examples assume output files do not already exist. Use `--overwrite` only when replacing
an existing conversion or transformation is intentional.

## Example files and paths

Most recipes use these folders:

- `./input/` for source datasets;
- `./output/` for converted or transformed datasets and captured JSON;
- `./reports/` for dataset, comparison, and batch reports; and
- `./logs/` for diagnostic logs.

In PowerShell, create them before running recipes that write there:

```powershell
New-Item -ItemType Directory -Force -Path .\input, .\output, .\reports, .\logs | Out-Null
```

A typical command then looks like:

```powershell
statconvert convert .\input\survey.sav .\output\survey.xlsx
```

## Inspect an unfamiliar file

Start with a quick overview and preview, then inspect structure and metadata:

```powershell
statconvert info .\input\data.sav
statconvert peek .\input\data.sav
statconvert schema .\input\data.sav
statconvert metadata .\input\data.sav
statconvert labels .\input\data.sav
```

- `info` shows the backend, dimensions, variables, and types.
- `peek` displays the first five rows; add `--rows 10` for a larger preview.
- `schema` shows normalized column types and per-variable metadata counts.
- `metadata` summarizes the metadata attached to the dataset.
- `labels` displays variable and value labels when the format provides them.

For script-friendly inspection, use a command that supports JSON, such as `summary`:

```powershell
statconvert summary .\input\data.sav --json > .\output\data-summary.json
```

`info`, `peek`, `schema`, `metadata`, and `labels` are terminal-oriented and do not have a
`--json` option.

## Convert SPSS to Excel

Validate the SAV dataset for XLSX output, convert it, and create a source report for
review:

```powershell
statconvert validate .\input\survey.sav --to xlsx
statconvert convert .\input\survey.sav .\output\survey.xlsx
statconvert report .\input\survey.sav --output .\reports\survey.html
```

SPSS files may contain variable labels, value labels, missing-value definitions, and
other statistical metadata. Excel is convenient for sharing the data, but it has no
direct equivalent for every SPSS metadata feature. Keep the generated
`.statconvert-metadata.json` sidecar beside the XLSX file when later StatConvert reads
should restore normalized metadata.

## Convert Stata to Parquet

Parquet is useful for typed analytics and data-engineering pipelines:

```powershell
statconvert validate .\input\data.dta --to parquet
statconvert convert .\input\data.dta .\output\data.parquet
statconvert schema .\output\data.parquet
```

Inspect the written schema rather than assuming every Stata type or statistical metadata
feature has a native Parquet equivalent. StatConvert writes normalized metadata to a
sidecar for later StatConvert reads.

## Convert SAS or XPT to CSV or Parquet

XPT is readable and writable. Use it as input for either simple text interchange or an
analytics-oriented Parquet file:

```powershell
statconvert convert .\input\data.xpt .\output\data.csv
statconvert convert .\input\data.xpt .\output\data.parquet
```

SAS7BDAT is read-only, so it can be a source but not a destination:

```powershell
statconvert convert .\input\data.sas7bdat .\output\data.parquet
```

Metadata fidelity depends on the destination. See the
[SAS and XPT format guidance](formats.md#sas-sas7bdat-and-xpt) before relying on a
cross-format round trip.

## Convert CSV to Excel XLSX

Use modern XLSX for normal Excel delivery:

```powershell
statconvert validate .\input\data.csv --to xlsx
statconvert convert .\input\data.csv .\output\data.xlsx
```

CSV has no native variable labels or value labels. XLSX is preferred over legacy XLS for
modern Excel users and larger or wider datasets.

## Create genuine legacy XLS output

Validate before writing an Excel 97-2003 workbook:

```powershell
statconvert validate .\input\data.csv --to xls
statconvert convert .\input\data.csv .\output\data.xls
```

The output is genuine legacy BIFF/OLE Excel data, not renamed XLSX content. XLS is limited
to 65,535 data rows plus one header row and 256 columns. If validation reports either
limit, write `.xlsx` instead.

## Work with Excel workbook sheets

List sheets before reading a workbook whose contents are unfamiliar:

```powershell
statconvert objects .\input\workbook.xlsx
statconvert peek .\input\workbook.xlsx --object Data
statconvert convert .\input\workbook.xlsx .\output\data.csv --object Data
statconvert report .\input\workbook.xlsx --object Data --output .\reports\data.html
```

Sheet names are exact and should be quoted when they contain spaces. A zero-based sheet
index is also accepted:

```powershell
statconvert convert .\input\workbook.xlsx .\output\first-sheet.csv --object 0
```

A workbook with one sheet can be read automatically. A multi-sheet workbook requires
`--object`; StatConvert never silently reads its first sheet.

## Work with ODS sheets

ODS follows the same container and object-selection model as Excel:

```powershell
statconvert objects .\input\workbook.ods
statconvert convert .\input\workbook.ods .\output\data.csv --object Sheet1
```

Select an exact sheet name or zero-based index. StatConvert reads tabular sheet content;
it does not preserve rich spreadsheet formatting or formulas as workbook features.

## Work with RDS files

RDS stores one R object, so no selector is used:

```powershell
statconvert metadata .\input\dataset.rds
statconvert convert .\input\dataset.rds .\output\dataset.csv
```

The object must be tabular and convertible through the R backend. RDS rejects
`--object`; it is not an R workspace container.

## Work with RData or RDA workspaces

List the workspace objects, choose a supported tabular object, then use its exact name:

```powershell
statconvert objects .\input\workspace.rdata
statconvert peek .\input\workspace.rdata --object patients
statconvert convert .\input\workspace.rdata .\output\patients.csv --object patients
statconvert report .\input\workspace.rdata --object patients --output .\reports\patients.html
```

RData and RDA may contain several named objects. Unsupported objects can appear in the
listing with a message when the backend can describe them. StatConvert does not choose
the first object silently and does not convert arbitrary non-tabular R objects.

## Validate before converting

Run general validation for data-quality and metadata issues, or add a destination to
check known output constraints:

```powershell
statconvert validate .\input\data.sav
statconvert validate .\input\data.sav --to xlsx
statconvert validate .\input\data.csv --to xls
statconvert validate .\input\data.csv --to dta
```

Use strict mode when warning-level findings should also make the command fail:

```powershell
statconvert validate .\input\data.csv --to xls --strict
```

Target validation can catch known format limits, invalid target writability, and likely
metadata loss. It does not guarantee that a dataset is semantically correct or accepted
by every version of an external statistical package.

## Generate an HTML, JSON, or CSV report

Write the same dataset report in any supported report format:

```powershell
statconvert report .\input\data.sav --output .\reports\data.html
statconvert report .\input\data.sav --output .\reports\data.json
statconvert report .\input\data.sav --output .\reports\data.csv
```

HTML is convenient for review and sharing. JSON retains the complete report model for
automation, while CSV provides table-oriented output. PDF report output is not supported.
Use `statconvert report --help` for presets and section controls.

## Compare two datasets

Compare a before/after pair in the terminal, as JSON, or under strict warning policy:

```powershell
statconvert compare .\input\before.csv .\input\after.csv
statconvert compare .\input\before.csv .\input\after.csv --json
statconvert compare .\input\before.csv .\input\after.csv --strict
```

Compare is useful after conversion or transformation because it checks shape, schema,
normalized metadata, and positional values by default. A difference can intentionally
produce exit code `1`. Key-based row matching, numeric tolerance, ignored-column policy,
and chunked comparison are deferred.

## Compare selected workbook sheets or RData objects

Apply one selector to both container inputs when the object name is the same:

```powershell
statconvert compare .\input\before.xlsx .\input\after.xlsx --object Data
statconvert compare .\input\before.rdata .\input\after.rdata --object patients
```

Use side-specific selectors when workbook sheet names differ:

```powershell
statconvert compare .\input\before.xlsx .\input\after.xlsx --left-object OldData --right-object NewData
```

`--object` cannot be combined with `--left-object` or `--right-object`. Side-specific
selectors can also select a container on only one side of a mixed-format comparison.

## Batch convert a folder

Convert supported files in one folder, include subfolders, or preview a plan:

```powershell
statconvert batch .\input .\output --to parquet
statconvert batch .\input .\output --to csv --recursive
statconvert batch .\input .\output --to xlsx --dry-run
```

The output extension comes from `--to`. Planning and result order are deterministic, even
when several workers are used. A dry run does not read datasets or container contents; it
previews paths, capabilities, collisions, and other plan information.

Capture a JSON plan or write a durable CSV result report:

```powershell
statconvert batch .\input .\output --to parquet --dry-run --json > .\output\batch-plan.json
statconvert batch .\input .\output --to parquet --report .\reports\batch-results.csv
```

## Batch convert standardized workbooks

Apply one sheet selector to every workbook:

```powershell
statconvert batch .\monthly-workbooks .\converted --to parquet --object Data
```

Every input workbook must contain the same exact sheet name, or the selected zero-based
index must identify the intended sheet in every workbook. Object-selection failures are
reported per item. Batch selects one sheet per input; it does not expand all sheets.
A mixed single-dataset file such as CSV fails as an item when `--object` is supplied.

## Batch convert standardized RData files

Apply one R object selector to every workspace:

```powershell
statconvert batch .\site-workspaces .\converted --to csv --object patients
```

Every RData/RDA workspace must expose the selected object as a supported tabular dataset.
Selection failures are reported per item. Batch does not discover and expand every object
and does not support a per-file object manifest.

## Transform selected or dropped columns

Keep only selected columns:

```powershell
statconvert transform .\input\data.csv .\output\data-selected.csv --select id --select name --select age
```

Or remove an unwanted column:

```powershell
statconvert transform .\input\data.csv .\output\data-clean.csv --drop temporary_column
```

Use `--dry-run` to review a transformation plan without writing the output.

## Rename and type-convert columns

Rename a column:

```powershell
statconvert transform .\input\data.csv .\output\data-renamed.csv --rename old_name=new_name
```

Convert a column to an integer type:

```powershell
statconvert transform .\input\data.csv .\output\data-typed.csv --type age=int
```

Operations can be combined. Later stages use names produced by earlier stages:

```powershell
statconvert transform .\input\data.csv .\output\data-ready.csv --rename years=age --type age=int
```

## Filter rows

Keep rows where `age` is at least 18:

```powershell
statconvert transform .\input\data.csv .\output\adults.csv --filter age,gte,18
```

The supported operator is `gte` (or the `>=` symbol alias), not `ge`. Quote a filter if
its value or shell syntax requires it; the [CLI Reference](cli.md#transform) lists every
operator and combination rule.

## Recode values

Replace status codes with readable values:

```powershell
statconvert transform .\input\data.csv .\output\data-recoded.csv --recode status:1=Active,0=Inactive
```

The fixed transformation order is select, drop, rename, type conversion, filtering, then
recoding. Batch transformations are not implemented; apply `transform` to one input at a
time.

## Use JSON output in scripts

Commands with JSON support write plain, script-safe JSON to standard output:

```powershell
statconvert summary .\input\data.sav --json > .\output\summary.json
statconvert validate .\input\data.sav --json > .\output\validation.json
statconvert compare .\input\before.csv .\input\after.csv --json > .\output\comparison.json
```

Other JSON-capable commands are `objects`, `describe`, `frequencies`, `missing`, and
`batch`. `info` does not support `--json`; use `summary` when a machine-readable overview
is needed. A report filename ending in `.json` writes a full JSON report, while
`report --json` separately controls the command's completion summary.

Keep diagnostics in a log file rather than mixing human-oriented output into captured
JSON:

```powershell
statconvert validate .\input\data.sav --json --log .\logs\validation.log > .\output\validation.json
```

## Write logs for troubleshooting

Add a diagnostic log to any public command:

```powershell
statconvert convert .\input\data.sav .\output\data.xlsx --log .\logs\convert.log
statconvert validate .\input\data.sav --log .\logs\validate.log --log-level debug
```

Logs are written only to the path supplied with `--log` and stay separate from terminal
or JSON output. They help support staff reproduce failures and identify the active command
context. Logs can contain paths, options, and error details, so handle them according to
the environment's privacy and retention rules. Use `--log-append` only when retaining
earlier entries is intentional.

## Suggested safe workflow

This sequence discovers formats and workbook objects, previews and validates one sheet,
converts it, reports on the result, and compares source with output:

```powershell
statconvert formats
statconvert objects .\input\workbook.xlsx
statconvert peek .\input\workbook.xlsx --object Data
statconvert validate .\input\workbook.xlsx --object Data --to parquet
statconvert convert .\input\workbook.xlsx .\output\data.parquet --object Data
statconvert report .\output\data.parquet --output .\reports\data.html
statconvert compare .\input\workbook.xlsx .\output\data.parquet --left-object Data
```

The final comparison is valid because only the left workbook needs an object selector;
Parquet is a single-dataset format. A non-zero compare result can represent expected
format, metadata, or value differences rather than a command crash.

## Recipes by task

| Goal | Start here |
|---|---|
| I need Excel output | [Convert CSV to Excel XLSX](#convert-csv-to-excel-xlsx) or [Convert SPSS to Excel](#convert-spss-to-excel) |
| I need old Excel output | [Create genuine legacy XLS output](#create-genuine-legacy-xls-output) |
| I need to select one sheet | [Work with Excel workbook sheets](#work-with-excel-workbook-sheets) |
| I need one object from RData | [Work with RData or RDA workspaces](#work-with-rdata-or-rda-workspaces) |
| I need many files converted | [Batch convert a folder](#batch-convert-a-folder) |
| I need a dataset report | [Generate an HTML, JSON, or CSV report](#generate-an-html-json-or-csv-report) |
| I need to compare before and after | [Compare two datasets](#compare-two-datasets) |
| I need automation output | [Use JSON output in scripts](#use-json-output-in-scripts) and [Write logs for troubleshooting](#write-logs-for-troubleshooting) |

For deeper behavior, return to the [User Guide](user-guide.md),
[CLI Reference](cli.md), or [Format Guide](formats.md).
