# Format Guide

**Status:** authoritative format-specific usage and capability reference

This guide explains which dataset formats StatConvert reads and writes, how metadata and
container objects behave, and which caveats matter when choosing a destination. For a
day-to-day workflow, start with the [User Guide](user-guide.md). See the
[CLI Reference](cli.md) for every option and [Examples and Recipes](examples.md) for
copyable workflows.

## How to read this guide

StatConvert identifies a format from the filename extension, case-insensitively. Read and
write support is resolved per extension: a backend can read an extension without being
able to write it.

Check the capabilities installed in the current environment with:

```powershell
statconvert formats
statconvert capabilities xlsx
statconvert capabilities rdata
```

In the matrix below, **Sidecar** means the primary file does not natively carry
StatConvert's normalized statistical metadata. StatConvert writes a sibling
`<output>.statconvert-metadata.json` file so a later StatConvert read can restore that
metadata. Other applications usually ignore this sidecar.

## Capability matrix

| Extension | Format | Read | Write | Metadata | Objects | Notes |
|---|---|:---:|:---:|---|---|---|
| `.csv` | Comma-separated values | Yes | Yes | Sidecar | None | Simple one-table text interchange. |
| `.xlsx` | Excel workbook | Yes | Yes | Sidecar | Sheet | Recommended Excel output; rich workbook features are not preserved. |
| `.xls` | Excel 97-2003 workbook | Yes | Yes | Sidecar | Sheet | Genuine legacy BIFF; limited to 65,535 data rows plus a header and 256 columns. |
| `.ods` | OpenDocument Spreadsheet | Yes | Yes | Sidecar | Sheet | Workbook-like OpenDocument format. |
| `.sav` | SPSS system file | Yes | Yes | Native, limited | None | Reads and writes supported pyreadstat metadata. |
| `.zsav` | Compressed SPSS system file | Yes | No | Native on read | None | Read-only; StatConvert does not create ZSAV files. |
| `.por` | SPSS portable file | Yes | No | Native on read | None | Read-only. |
| `.dta` | Stata data file | Yes | Yes | Native, limited | None | Reads and writes supported labels, missing values, and formats. |
| `.sas7bdat` | SAS data set | Yes | No | Native on read | None | Read-only. |
| `.xpt` | SAS XPORT | Yes | Yes | Native, limited | None | Stricter interchange format; only supported XPORT metadata is written. |
| `.json` | JSON records | Yes | Yes | Sidecar | None | Written as one JSON array of record objects. |
| `.jsonl` | JSON Lines | Yes | Yes | Sidecar | None | One record object per line. |
| `.ndjson` | Newline-delimited JSON | Yes | Yes | Sidecar | None | Same line-oriented behavior as JSONL. |
| `.parquet` | Apache Parquet | Yes | Yes | Sidecar | None | Typed columnar data; Snappy compression is used by default. |
| `.feather` | Apache Feather | Yes | Yes | Sidecar | None | Typed columnar data; the pandas index is reset on write. |
| `.rds` | R serialized object | Yes | Yes | Sidecar | Single object | The one object must be tabular/DataFrame-like; `--object` is not accepted. |
| `.rdata` | R workspace | Yes | Yes | Sidecar | R object | Selects named tabular objects; writes one DataFrame named `data`. |
| `.rda` | R workspace | Yes | Yes | Sidecar | R object | Same behavior as `.rdata`. |

`Yes` describes the normal installation, which includes dependencies for every advertised
format. An incomplete environment can make legacy XLS unavailable; the CLI reports a
specific `xlrd` read or `xlwt` write dependency error in that case.

## Choosing an output format

- Use `.xlsx` for general delivery to Excel users and for data beyond legacy XLS limits.
- Use `.xls` only when a system specifically requires Excel 97-2003 output.
- Use `.parquet` for efficient typed analytics and interchange.
- Use `.feather` for fast Arrow-oriented interchange when Feather is expected.
- Use `.csv` for simple, widely compatible plain-text exchange where type and metadata
  fidelity are not the priority.
- Use `.jsonl` or `.ndjson` for line-oriented record processing; use `.json` for one
  JSON record array.
- Use `.sav`, `.dta`, or `.xpt` when the receiving statistical package requires that
  format and verify the metadata that survives the conversion.
- Use `.rds` for one R dataset-like object. Use `.rdata` or `.rda` when R workspace
  compatibility or a named workspace object is required.

No destination preserves every source feature. Validate against the intended target
before writing when compatibility matters:

```powershell
statconvert validate input.csv --to xls
```

## Container formats and object selection

XLSX, XLS, and ODS files can contain sheets. RData and RDA workspaces can contain named R
objects. StatConvert represents both as dataset objects so commands use one generic
`--object` option.

List available objects, then select one by exact name or zero-based index:

```powershell
statconvert objects workbook.xlsx
statconvert convert workbook.xlsx output.csv --object Data
statconvert peek workbook.xls --object 0

statconvert objects workspace.rdata
statconvert convert workspace.rdata patients.csv --object patients
```

When exactly one supported object exists, StatConvert selects it automatically. When
several supported objects exist, `--object` is required; the first sheet or object is
never selected silently. R object names take precedence over index interpretation when a
name itself looks numeric.

RDS and single-dataset files such as CSV, JSON, Parquet, and SAV reject `--object` rather
than ignoring it. Object selection reads one dataset only. StatConvert does not expand
all sheets or workspace objects into multiple outputs. Compare can use shared or
left/right selectors, while batch applies one selector to every input file.

## CSV

CSV is the simplest choice for a single table that must be readable by many tools.
StatConvert reads and writes comma-separated files without a pandas index. Column types
are inferred during reading, so text, dates, identifiers with leading zeroes, and mixed
columns may need inspection after import.

The datafile-writing commands `convert`, `transform`, and `batch` can select CSV input or
output encoding independently with `--input-encoding` and `--output-encoding`. The
CSV-specific `--csv-delimiter` and `--csv-decimal` options apply to CSV input/output
paths. Delimiters and decimal separators are limited to one character and cannot be the
same when both are supplied. Read-only inspection and comparison commands do not expose
these controls, sniffing, dialect presets, or auto-detection.

CSV has no native variable labels, value labels, statistical missing-value definitions,
or measurement levels. StatConvert writes normalized metadata to a sidecar, but software
that reads only the CSV will see data and column names only.

```powershell
statconvert peek data.csv
statconvert convert data.csv data.xlsx
statconvert validate data.csv --to parquet
statconvert convert data.xlsx data.csv --csv-delimiter ";" --csv-decimal ","
```

CSV contains one dataset and does not support object selection.

## Excel XLSX

XLSX is the recommended Excel format. A workbook can have several sheets; use `objects`
and `--object` when more than one sheet is present.

```powershell
statconvert objects workbook.xlsx
statconvert convert workbook.xlsx output.csv --object Data
statconvert report workbook.xlsx --object Data --output report.html
```

StatConvert treats a selected sheet as tabular data. It does not act as a workbook editor
and does not preserve formulas as formulas, cell formatting, charts, macros, or other
existing sheets. XLSX output contains one data sheet and a metadata sidecar.

## Legacy Excel XLS

XLS support produces and reads genuine Excel 97-2003 BIFF/OLE workbooks. Output is not
XLSX data renamed with an `.xls` suffix. The normal installation includes `xlrd` for
reading/listing and `xlwt` for writing.

One XLS worksheet can contain at most 65,536 total rows and 256 columns. StatConvert uses
the first row for headers, leaving at most 65,535 data rows. Validate first and use XLSX
for larger or wider data:

```powershell
statconvert validate input.csv --to xls
statconvert convert input.csv output.xls
```

XLS sheets follow the standard object-selection policy:

```powershell
statconvert objects legacy.xls
statconvert convert legacy.xls output.csv --object 0
```

StatConvert writes values plus minimal date/datetime number formats. It does not preserve
workbook formatting, formulas, charts, macros, or existing sheets.

## OpenDocument Spreadsheet ODS

ODS is a workbook-like OpenDocument format. Sheets are dataset objects and follow the
same listing, exact-name/index selection, and ambiguity rules as Excel.

```powershell
statconvert objects workbook.ods
statconvert convert workbook.ods output.csv --object Sheet1
```

ODS output contains one sheet named `Sheet1` unless an internal API caller overrides it.
Rich spreadsheet formatting and formulas are not preserved as workbook features.
Statistical metadata is stored in a StatConvert sidecar. ODS support and its dependencies
are included in the normal installation.

## SPSS SAV, ZSAV, and POR

StatConvert reads `.sav`, `.zsav`, and `.por` through pyreadstat. SAV is writable; ZSAV
and POR are read-only. Depending on the source file, reads can expose variable labels,
value labels, user-defined missing values or ranges, display formats, and measurement
metadata through the normalized Dataset model.

```powershell
statconvert labels survey.sav
statconvert metadata survey.sav
statconvert convert survey.sav survey.xlsx
statconvert convert survey.sav survey.parquet
```

SAV writing preserves the subset of labels, missing ranges, formats, and display widths
supported by the writer. It is not a guarantee of perfect round-trip fidelity for every
SPSS feature. Use target validation to flag incompatible names and likely metadata loss:

```powershell
statconvert validate input.csv --to sav
```

## Stata DTA

DTA is readable and writable. Variable labels, value labels, user-missing values, and
display formats may be available from a source file and are written where supported.
Choose DTA when the receiving workflow requires Stata compatibility.

```powershell
statconvert convert input.csv output.dta
statconvert validate input.csv --to dta
statconvert convert input.dta output.parquet
```

Target validation warns about Stata variable names longer than 32 characters, invalid
name characters, and sampled very long strings. Other Stata version, type, or package
constraints can still apply; a successful validation is not a complete compatibility
guarantee.

## SAS SAS7BDAT and XPT

SAS7BDAT is readable but not writable. XPT is readable and writable and is intended for
SAS-compatible data interchange. XPT is more restrictive than a general-purpose
DataFrame format, and metadata preservation is limited to the column labels and formats
supported by the pyreadstat XPORT writer; value labels are not written to XPT.

```powershell
statconvert convert data.sas7bdat data.csv
statconvert convert data.xpt data.parquet
statconvert validate data.csv --to xpt
```

Target validation confirms that XPT is writable and reports general metadata concerns,
but it does not prove compliance with every XPORT consumer restriction. StatConvert does
not write SAS7BDAT files.

## JSON, JSONL, and NDJSON

The JSON backend is for tabular, record-oriented data. `.json` output is an indented JSON
array of record objects. `.jsonl` and `.ndjson` contain one record object per line, which
is useful for streaming-oriented tools even though StatConvert itself does not implement
streaming conversion.

```powershell
statconvert convert input.csv output.json
statconvert convert input.csv output.jsonl
statconvert convert input.jsonl output.parquet
```

Arbitrary nested-document flattening is not implemented. Input must be compatible with
pandas' tabular JSON reader, and statistical metadata is stored only in a sidecar.

## Parquet and Feather

Parquet and Feather are efficient typed columnar formats for analytics workflows. They
usually preserve tabular data types more effectively than CSV, but StatConvert does not
treat their file-level metadata as native statistical-package labels or missing-value
definitions. Normalized statistical metadata is written to a sidecar.

Parquet uses the pyarrow engine and Snappy compression by default. Feather output resets
the pandas index before writing.

```powershell
statconvert convert input.sav output.parquet
statconvert convert input.csv output.feather
statconvert validate input.parquet
```

Neither format exposes selectable dataset objects.

## RDS

RDS stores one serialized R object. StatConvert supports an RDS file when pyreadr exposes
that object as a pandas DataFrame. It does not convert arbitrary R object types.

```powershell
statconvert convert dataset.rds dataset.csv
statconvert metadata dataset.rds
```

RDS is a single-object format and rejects `--object`. StatConvert writes one DataFrame,
resets its pandas index, and stores normalized statistical metadata in a sidecar.

## RData and RDA

RData and RDA are workspace formats that may contain several named objects. Use
`objects` to discover what pyreadr can expose, then select a supported tabular object:

```powershell
statconvert objects workspace.rdata
statconvert convert workspace.rdata patients.csv --object patients
statconvert compare before.rdata after.rdata --object patients
statconvert batch rdata-folder output-folder --to csv --object patients
```

Unsupported objects are listed with an explanation when pyreadr can describe them. Some R
object types may not be exposed at all and therefore cannot appear in the listing. There
is no automatic first-object fallback when several supported tables exist.

Writing `.rdata` or `.rda` creates one DataFrame named `data`. The input `--object`
selector does not choose an output object name, and multi-object output is not
implemented. Normalized metadata is stored in a sidecar.

## Metadata preservation

StatConvert normalizes available variable labels, value labels, missing values and
ranges, storage types, display formats, and measurement levels. Inspect the source before
choosing a destination:

```powershell
statconvert labels input.sav
statconvert metadata input.sav
statconvert schema input.sav
```

Statistical formats can represent some of this metadata natively. CSV, spreadsheets,
record JSON, Arrow formats, and R files do not represent it in the same statistical model,
so StatConvert uses a sidecar. Keep the sidecar beside the data file for later StatConvert
reads. Conversion preserves what the target writer can safely represent; perfect metadata
round trips across different format families are not promised.

## Validation and target limits

General validation checks dataset structure, metadata consistency, and common quality
issues. Adding `--to` also verifies target writability and reports known compatibility
issues:

```powershell
statconvert validate input.csv --to xls
statconvert validate input.csv --to dta
statconvert validate input.csv --to xpt
```

Current target-specific checks include legacy XLS and XLSX worksheet dimensions, Stata
variable names and sampled long strings, and SPSS variable-name compatibility. All
targets can also report likely label loss based on their declared metadata capabilities.
Validation catches known risks; it does not certify semantic correctness or every limit
of external statistical software.

For a container input, object selection happens before dataset validation. List and
select the sheet or R object first if the input is ambiguous.

## Common format workflows

SPSS to Excel:

```powershell
statconvert convert survey.sav survey.xlsx
```

Stata to Parquet:

```powershell
statconvert convert data.dta data.parquet
```

One Excel sheet to CSV:

```powershell
statconvert objects workbook.xlsx
statconvert convert workbook.xlsx data.csv --object Data --csv-delimiter ";"
```

One RData object to CSV:

```powershell
statconvert objects workspace.rdata
statconvert convert workspace.rdata patients.csv --object patients
```

Legacy XLS output:

```powershell
statconvert validate input.csv --to xls
statconvert convert input.csv output.xls
```

The same sheet from monthly workbooks:

```powershell
statconvert batch monthly-workbooks converted --to parquet --object Data
```

More task-oriented combinations belong in [Examples and Recipes](examples.md).

## Unsupported or deferred behavior

StatConvert does not currently provide:

- arbitrary nested JSON flattening;
- spreadsheet formatting, chart, macro, or formula preservation;
- formula recalculation;
- PDF reports;
- batch expansion of every sheet or R object;
- per-input object manifest mapping;
- multi-object output expansion;
- key-based, tolerance-based, ignored-column, or chunked comparison options; or
- human-readable descriptions of raw display-format codes.

These limitations are not hidden format modes; commands reject unsupported behavior rather
than silently approximating it.
