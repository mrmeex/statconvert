# Examples and Recipes

## How to use these examples

This guide is a copy-and-adapt recipe book for common StatConvert workflows. Install
StatConvert from the wheel attached to a GitHub Release before using these recipes. The
examples assume it is available as `statconvert`; if the console command is not on
`PATH`, replace it with `python -m statconvert`.

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

Examples assume output files do not already exist and their parent directories exist.
Use `--overwrite` only when replacement is intentional and `--create-dirs` when the
user-specified output directory is missing.

To capture the exact installed application, Python, and dependency versions for support,
run:

```powershell
statconvert --version
```

Use `python -m statconvert --version` when the console command is not on `PATH`. Missing
dependencies appear as `not installed`.

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
statconvert convert .\input\data.sav .\output\data.xlsx --input-encoding cp1252
statconvert convert .\input\data.csv .\output\data.xlsx --input-encoding latin1 --csv-delimiter ";"
statconvert convert .\input\data.xlsx .\output\data.csv --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert .\input\legacy.csv .\output\clean.csv --input-encoding latin1 --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert .\input\data.xlsx .\output\data.csv --csv-delimiter ";" --csv-decimal ","
statconvert convert .\input\data.xpt .\output\data.parquet
```

SAS7BDAT is read-only, so it can be a source but not a destination:

```powershell
statconvert convert .\input\data.sas7bdat .\output\data.parquet
```

Metadata fidelity depends on the destination. See the
[SAS and XPT format guidance](formats.md#sas-sas7bdat-and-xpt) before relying on a
cross-format round trip.

Encoding and CSV controls are available only on `convert`, `collect`, `transform`, and `batch`.
Input and output encodings are independent; unsupported backends warn and ignore the
relevant directional option. These controls are not added to `peek`, `info`, `compare`,
or other read-only commands.

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

## Convert one whole container to another

Use `convert --all-objects` when one input container should become one multi-sheet XLSX
or ODS output:

```powershell
statconvert convert .\input\workbook.xlsx .\output\combined.xlsx --all-objects
statconvert convert .\input\workbook.xlsx .\output\combined.ods --all-objects
statconvert convert .\input\workspace.rdata .\output\workspace.xlsx --all-objects
```

Every supported input object is read independently and written under its original name,
in listing order. Unsupported objects are skipped with warnings if supported objects
remain. Invalid or duplicate output sheet names stop conversion; names are not changed
automatically.

Use `batch --all-objects` instead when each object should become a separate file. These
commands do not merge, append, join, or deduplicate rows.

## Build a folder object discovery report

Inspect direct files, recurse through subfolders, or write an editable manifest-ready
report:

```powershell
statconvert objects .\incoming
statconvert objects .\incoming --recursive
statconvert objects .\incoming --recursive --output .\reports\objects.csv
statconvert objects .\incoming --recursive --include-unsupported --output .\reports\objects-with-unsupported.csv
statconvert objects .\incoming --recursive --json --output .\reports\objects.json
```

Use `--pattern *.xlsx` and repeatable `--exclude-pattern` values to focus a scan. The CSV
columns `include`, `input_file`, `input_object`, and `output_name` are intended for later
manifest workflows. This discovery step does not convert or expand any object.

## Collect selected files and objects into one workbook

Generate a discovery manifest, add an `output_object` column if custom sheet names are
needed, and preview the collection:

```powershell
statconvert objects .\incoming --recursive --output .\objects.csv
statconvert collect .\objects.csv .\output\combined.xlsx --base-dir .\incoming --dry-run
```

A minimal collection manifest is also valid:

```csv
include,input_file,input_object,output_object
true,data.csv,,Imported_Data
true,book.xlsx,Data,Book_Data
true,book.xlsx,Lookup,Book_Lookup
```

Write XLSX or ODS after reviewing the plan:

```powershell
statconvert collect .\objects.csv .\output\combined.xlsx --base-dir .\incoming
statconvert collect .\objects.csv .\output\combined.ods --base-dir .\incoming
```

Without `--base-dir`, relative `input_file` values resolve from the manifest directory.
Sheet names use `output_object` first, followed by `output_name`, `input_object`, and
the input file stem. Duplicate or invalid names fail; they are not rewritten. Excluded
rows are ignored, but every included row must read and validate successfully before the
single output write begins.

This recipe places datasets on separate sheets. It does not append or relationally
combine their rows.

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
statconvert compare .\input\before.csv .\input\after.csv --ignore-columns exported_at,source_file
statconvert compare .\input\before.csv .\input\after.csv --numeric-tolerance 0.0001
statconvert compare .\input\before.csv .\input\after.csv --key id
statconvert compare .\input\before.csv .\input\after.csv --key id,date --numeric-tolerance 0.001
statconvert compare .\input\before.csv .\input\after.csv --key id --ignore-columns exported_at
statconvert compare .\input\before.csv .\input\after.csv --max-differences 10
statconvert compare .\input\before.csv .\input\after.csv --key id --numeric-tolerance 0.001 --max-differences 25
```

Compare is useful after conversion or transformation because it checks shape, schema,
normalized metadata, and positional values by default. A difference can intentionally
produce exit code `1`. `--key` aligns unique rows by stable identifiers when physical row
order should not matter. Ignored non-key columns are removed before comparison, and
numeric tolerance is absolute and applies only to numeric columns. Detailed examples are
bounded to 50 by default; use `--max-differences` to change the cap without changing the
complete difference counts or exit status.

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
statconvert batch .\input .\output --to csv --csv-delimiter ";"
statconvert batch .\input .\output --to xlsx --dry-run
statconvert batch .\input .\new-output --to csv --create-dirs
```

The output extension comes from `--to`. Planning and result order are deterministic, even
when several workers are used. The output root must exist unless `--create-dirs` is used;
generated preserve-structure folders below an existing root are automatic. A dry run
does not read datasets, create directories, write files, or replace existing outputs; it
previews paths, capabilities, collisions, and other plan information.

Single-file output policy is the same for conversion, transformation, and reports:

```powershell
statconvert convert .\input\data.sav .\output\data.xlsx --overwrite
statconvert transform .\input\data.xlsx .\new-output\data.csv --create-dirs
statconvert report .\input\data.sav --output .\reports\data.html --create-dirs
```

Capture a JSON plan or write a durable CSV result report:

```powershell
statconvert batch .\input .\output --to parquet --dry-run --json > .\output\batch-plan.json
statconvert batch .\input .\output --to parquet --report .\reports\batch-results.csv
```

For regional CSV output, combine a semicolon field delimiter with a comma decimal
separator:

```powershell
statconvert batch .\input .\output --to csv --output-encoding utf-8-sig --csv-delimiter ";" --csv-decimal ","
```

## Batch convert standardized workbooks

Apply one sheet selector to every workbook:

```powershell
statconvert batch .\monthly-workbooks .\converted --to parquet --object Data
```

Every input workbook must contain the same exact sheet name, or the selected zero-based
index must identify the intended sheet in every workbook. Object-selection failures are
reported per item. Shared `--object` mode selects one sheet per input; use `--all-objects`
for expansion.
A mixed single-dataset file such as CSV fails as an item when `--object` is supplied.

## Batch convert standardized RData files

Apply one R object selector to every workspace:

```powershell
statconvert batch .\site-workspaces .\converted --to csv --object patients
```

Every RData/RDA workspace must expose the selected object as a supported tabular dataset.
Selection failures are reported per item. Batch does not discover and expand every object.

## Convert selected rows from an object manifest

Generate a discovery CSV, edit `include`, `input_object`, and `output_name`, then use the
included rows as the complete set of batch tasks:

```powershell
statconvert objects .\incoming --recursive --output .\objects.csv
statconvert batch .\incoming .\converted --to csv --object-manifest .\objects.csv --create-dirs
```

A minimal hand-written manifest is also valid:

```csv
input_file,input_object,output_name
jan.xlsx,Data,jan
feb.xlsx,Responses,feb
data.csv,,data
```

With the default preserve-structure policy, `site_a\jan.xlsx` and output name `jan`
produce `converted\site_a\jan.csv`. Add `--flatten` for `converted\jan.csv`. Rows with
`include=false` are ignored. Manifest mode selects one object per included row; it does
not expand every object, collect objects, or apply manifest-specific transformations.
The separate `collect` command can consume included manifest rows into one XLSX or ODS
container; batch manifest mode itself still writes separate files.

One command-level pipeline can transform every included manifest row consistently:

```powershell
statconvert batch .\incoming .\converted --to parquet --object-manifest .\objects.csv --transform --rename old_id=id
```

## Convert every supported object to separate files

Expand each supported workbook sheet or R workspace object while keeping ordinary files
as one task each:

```powershell
statconvert batch .\incoming .\converted --to csv --all-objects
statconvert batch .\incoming .\converted --to parquet --all-objects --recursive
```

`workbook.xlsx` sheets `Data` and `Lookup` become `workbook__Data.csv` and
`workbook__Lookup.csv`. A `data.csv` input remains `data.csv`. Recursive runs preserve
relative parent folders unless `--flatten` is used.

Generated-name collisions fail rather than receiving automatic suffixes. Resolve them
through the editable manifest workflow:

```powershell
statconvert objects .\incoming --recursive --output .\objects.csv
# Edit output_name values.
statconvert batch .\incoming .\converted --to csv --object-manifest .\objects.csv
```

Unsupported objects are not converted. This workflow creates separate dataset files and
does not merge rows. A shared pipeline can be applied to every expanded object:

```powershell
statconvert batch .\incoming .\converted --to csv --all-objects --transform --drop notes
```

Per-object transformation rules are not supported. Use `collect` when reviewed manifest
rows should become separate sheets in one container.

## Transform selected or dropped columns

CSV transformation output accepts the same focused controls:

```powershell
statconvert transform .\input\data.xlsx .\output\data.csv --csv-delimiter ";"
```

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
recoding. Use `transform` for one input, or apply the same pipeline to many planned items:

```powershell
statconvert batch .\incoming .\converted --to parquet --transform --select id --select name --filter active,eq,true
```

Batch dry-run plans paths and parses the options without reading datasets or checking
whether referenced columns exist.

## Choose separate outputs for large object sets

`convert --all-objects` and `collect` create one final container, so all selected datasets
are read before that final XLSX or ODS write. When the selected data may be large, prefer
independent batch outputs:

```powershell
statconvert batch .\incoming .\converted --to parquet --all-objects --recursive
```

Batch items are processed independently; with multiple workers, memory use includes one
current dataset per active worker. None of these workflows append, join, merge, or
deduplicate rows.

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
