# StatConvert CLI reference

**Status:** authoritative command reference

## Command overview

```text
convert       Convert one dataset or a whole object container.
collect       Collect manifest-selected datasets into one XLSX or ODS container.
transform     Transform a dataset and write it to another format.
formats       List registered extensions and extension-level read/write support.
backends      List backend engines and backend-wide capabilities.
capabilities  Show details for one extension or backend.
objects       Discover dataset-like objects in a file or folder.
info          Display basic dataset information.
schema        Display normalized variable schema.
labels        Display variable and value labels.
metadata      Display a normalized metadata summary.
summary       Display a dataset-level statistical summary.
describe      Display column profiles.
frequencies   Display value-count tables.
missing       Display missing-value analysis.
validate      Validate quality and conversion readiness.
compare       Compare two datasets and optionally write a report.
report        Generate a single-dataset profile report.
batch         Plan and execute many conversions.
config        Create, validate, or run one-command TOML workflow configurations.
peek          Preview the first rows.
```

There is no separate `diff` command. Use `statconvert compare` for diff-style dataset
analysis and reports.

## Global options

Global options appear before the command:

- `--debug` shows a terminal traceback for unexpected errors.
- `--verbose`, `-v` enables additional user-facing progress information.
- `--version` prints the installed StatConvert version, Python version, and important
  runtime dependency versions, then exits successfully without requiring a command.
- `--install-completion` and `--show-completion` are provided by Typer.
- `--help` displays help.

```bash
statconvert --debug convert input.sav output.parquet
statconvert --verbose info input.sav
statconvert --version
python -m statconvert --version
```

Version status is plain text without Rich styling. Dependencies that cannot be imported
are shown as `not installed`. Use the `python -m` form when `statconvert` is not on
`PATH`.

## Repeatable workflow configuration

Each TOML workflow config maps to exactly one existing StatConvert command. Config field
names use snake_case and preserve CLI behavior; they do not define multi-step workflows.
Parsing uses Python 3.11's standard-library `tomllib`, so config support adds no required
dependency.

### `config init`

```bash
statconvert config init COMMAND --output workflow.toml [--overwrite] [--create-dirs]
```

Creates a validated starter file for `convert`, `transform`, `batch`, `compare`,
`report`, or `collect`. Existing files are protected unless `--overwrite` is supplied,
and missing parent directories require `--create-dirs`.

### `config validate`

```bash
statconvert config validate CONFIG_FILE
```

Reads TOML and reports missing or unknown fields, basic type errors, invalid values, and
command-specific conflicts without running the command.

### `config run`

```bash
statconvert config run CONFIG_FILE
```

`config run` executes `convert`, `transform`, `batch`, `compare`, `report`, and `collect`
through their existing command and service paths. Output safety, transformation behavior,
batch planning, comparison exit policy, reports, collection naming, JSON, and progress
behavior remain unchanged.

Validation and execution errors identify the config file. When a required field is
missing, the error points to `config init` for a starter file; close field or format typos
may include a concise `Did you mean ...?` suggestion.

### Writing configs from commands

`convert`, `transform`, `batch`, `compare`, `report`, and `collect` accept
`--write-config FILE`. The command writes one validated TOML file and returns without
running the workflow. Use
`--overwrite-config` to replace that TOML file; ordinary `--overwrite` remains the saved
workflow's output policy and never authorizes config replacement. Where the command
supports `--create-dirs`, it may create the config parent and is also preserved in the
generated workflow.

```bash
statconvert convert input.csv output.parquet --write-config convert.toml
statconvert transform input.csv output.parquet --select id --write-config transform.toml
statconvert batch incoming converted --to parquet --workers 1 --write-config batch.toml
statconvert compare old.csv new.csv --key id --write-config compare.toml
statconvert report input.csv --output report.html --preset quick --write-config report.toml
statconvert collect manifest.csv workbook.xlsx --write-config collect.toml
statconvert config validate batch.toml
statconvert config run batch.toml
```

## Logging options

Every public command supports:

- `--log FILE` - write diagnostics to a file;
- `--log-level debug|info|warning|error` - set the file threshold (default `info`);
- `--log-append` - append instead of replacing the selected log file; and
- `--developer-log` - include source module and line information.

Logging is opt-in, file-only, and separate from Rich terminal output. It never writes a
status message to stdout and therefore does not contaminate `--json` output. Secret-like
parameter keys are masked, and logs contain compact summaries rather than DataFrames or
file contents.

Expected non-zero results are logged as command outcomes, not crashes. This includes
validation policy blocks, compare differences that match the exit policy, and batch
blockers/failures. Unexpected exceptions remain failures and include a traceback in the
log. `--developer-log` and `--log-level` affect the log file only.

```bash
statconvert convert input.sav output.parquet --log convert.log
statconvert compare before.sav after.sav --json --log compare.log
```

## JSON output

The commands `objects`, `summary`, `describe`, `frequencies`, `missing`, `validate`,
`batch`, and `compare` support machine-readable JSON stdout. `report --json` writes the requested report
and prints a concise JSON completion summary.

JSON is written directly to stdout without Rich rendering. Markup-like strings, ANSI-like
text, Unicode, non-native scalar mapping keys, and missing/non-finite scalar values are
normalized safely. When `--json` is used, redirect or pipe stdout normally:

```bash
statconvert frequencies input.csv --json > frequencies.json
```

`formats`, `backends`, `capabilities`, `info`, `peek`, `schema`, `labels`, and `metadata`
do not currently have `--json` options.

## Friendly errors and suggestions

Common operator errors use a short `Error` message followed by a `Suggestion` when there
is an obvious corrective action. Existing workflow outputs suggest `--overwrite`, config
files created by `--write-config` suggest `--overwrite-config`, and missing output parents
suggest `--create-dirs`. Unknown formats and backends may suggest a close supported
spelling. Object-selection errors point to `statconvert objects INPUT` before recommending
`--object`.

Normal mode omits tracebacks. Use the global `--debug` option before the command when
traceback detail is needed. JSON-capable command paths keep Rich error and progress
rendering out of JSON stdout.

## Exit codes

- `0` means the command completed under its default policy.
- `1` means an operational error or an intentional failing policy outcome.
- `validate` exits `1` for errors, and for warnings with `--strict`.
- `convert`, `collect`, and `transform` exit `1` when their validation write gate
  blocks output.
- `compare` exits `1` for error-level differences, and for warnings with `--strict`.
- `batch` exits `1` when a plan has blockers or an execution has failed/blocked items.
  A dry run with blockers also exits `1`.
- Report validation findings are observational; a successfully written report exits `0`.

## Conversion and transformation

### `convert`

```bash
statconvert convert INPUT_FILE OUTPUT_FILE [OPTIONS]
```

Options:

- `--object OBJECT` selects an Excel/ODS sheet or RData/RDA object by exact name or
  zero-based index.
- `--all-objects` converts every supported input object into one XLSX or ODS container.
  It conflicts with `--object`.
- `--overwrite` replaces an existing output.
- `--create-dirs` creates a missing output parent directory.
- `--write-config FILE` writes this invocation as TOML without converting data.
- `--overwrite-config` permits replacement of the selected config file only.
- `--validate` validates the loaded dataset for the output extension before writing.
- `--strict-validation` implies validation and makes warnings write-blocking.
- `--input-encoding TEXT` selects the text encoding for supported input formats.
- `--output-encoding TEXT` selects the text encoding for supported output formats.
- `--csv-delimiter TEXT` selects one delimiter character for CSV input/output paths.
- `--csv-decimal TEXT` selects one decimal separator for CSV input/output paths.
- Common logging options.

```bash
statconvert convert input.sav output.parquet
statconvert convert input.sav new-output/output.xlsx --create-dirs
statconvert convert input.sav output.dta --validate
statconvert convert input.csv output.xlsx --overwrite --log convert.log
statconvert convert input.csv output.xls
statconvert convert workbook.xlsx output.csv --object 0
statconvert convert workspace.rdata patients.csv --object patients
statconvert convert workbook.xlsx combined.xlsx --all-objects
statconvert convert workbook.xlsx combined.ods --all-objects
statconvert convert workspace.rdata workspace.xlsx --all-objects
statconvert convert input.sav output.xlsx --input-encoding cp1252
statconvert convert input.csv output.xlsx --input-encoding latin1 --csv-delimiter ";"
statconvert convert input.xlsx output.csv --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert legacy.csv clean.csv --input-encoding latin1 --output-encoding utf-8-sig --csv-delimiter ";"
statconvert convert input.xlsx output.csv --csv-delimiter ";" --csv-decimal ","
```

Validation errors always prevent writing. Warnings prevent writing only in strict mode.
Unsupported output extensions fail before a backend write. Genuine `.xls` writing uses
the normally installed `xlwt` dependency and is limited to 65,535 data rows plus one header row and
256 columns; use `.xlsx` for larger or wider datasets. `.zsav`, `.por`, and `.sas7bdat`
are read-only.

`convert --all-objects` is container-to-container conversion: one XLSX, XLS, ODS,
RData, or RDA input becomes one XLSX or ODS output with one sheet per supported input
object. It preserves input object order and names. Unsupported input objects are skipped
with warnings when at least one supported dataset object remains; zero supported objects
is an error. Empty, invalid, or duplicate target sheet names fail without automatic
renaming. Single-dataset inputs must omit `--all-objects`, and the destination must be
XLSX or ODS.

This differs from `batch --all-objects`, which expands objects into separate output
files. `convert --all-objects` validates output safety and object names first, then reads
all selected datasets before the one final container write. The selected datasets must fit
comfortably in memory together. Neither mode merges, appends, or joins rows.

### `collect`

```bash
statconvert collect MANIFEST OUTPUT_FILE [OPTIONS]
```

Collect reads included rows from a collection, discovery, or minimal object manifest and
writes each selected dataset as a separate sheet in one XLSX or ODS output file.

Options:

- `--base-dir PATH` resolves relative `input_file` values from this directory. Without
  it, paths resolve from the manifest parent directory.
- `--overwrite` replaces an existing output.
- `--create-dirs` creates a missing output parent directory.
- `--dry-run` validates and displays the plan without reading datasets, creating
  directories, or writing output.
- `--validate` validates every selected dataset before the one final write.
- `--strict-validation` implies validation and makes warnings write-blocking.
- `--input-encoding`, `--output-encoding`, `--csv-delimiter`, and `--csv-decimal` use
  the shared dataset I/O option behavior.
- `--write-config FILE` writes this invocation as TOML without collecting data.
- `--overwrite-config` permits replacement of the selected config file only.
- Common logging options.

```bash
statconvert collect objects.csv combined.xlsx --base-dir incoming
statconvert collect objects.csv combined.ods --base-dir incoming
statconvert collect objects.csv combined.xlsx --base-dir incoming --dry-run
```

The manifest requires `input_file`. `include` defaults to true; false rows are ignored
without file or support validation. Optional names use this priority:
`output_object`, `output_name`, `input_object`, then the input filename stem. Names must
already be valid and unique for the selected output; StatConvert never sanitizes,
renames, or suffixes them.

Included `object_supported=false` or `file_supported=false` rows fail before dataset
reads. A blank `input_object` uses normal single-dataset behavior and remains ambiguous
for a multi-object input. Any included read or validation failure stops the whole
collection before its final write. Collect does not append, join, merge, deduplicate, or
transform rows. Because partial container output is intentionally avoided, all selected
datasets are retained in memory until the final XLSX or ODS write.

### `transform`

```bash
statconvert transform INPUT_FILE OUTPUT_FILE [OPTIONS]
```

Options:

- `--object OBJECT` selects an Excel/ODS sheet or RData/RDA object by exact name or
  zero-based index.
- `--select COLUMN` - keep columns; repeat or supply trailing column values.
- `--drop COLUMN` - remove columns; repeat or supply trailing column values.
- `--rename OLD=NEW` - rename a column; repeatable.
- `--type COLUMN=TYPE` - convert a column; repeatable. Supported targets are `string`,
  `integer`/`int`, `float`, `boolean`/`bool`, `datetime`, `date`, and `category`.
- `--type-errors raise|coerce|ignore` - type error policy (default `raise`).
- `--datetime-format FORMAT` - pandas datetime parsing format.
- `--filter COLUMN,OPERATOR,VALUE` - filter rows; repeatable. Missing checks omit VALUE.
- `--filter-mode and|or` - combine filters (default `and`).
- `--recode COLUMN:OLD=NEW,OLD=NEW` - recode values; repeatable.
- `--recode-default VALUE` - value for unmapped non-missing recode values.
- `--update-value-labels` / `--no-update-value-labels` - control recoded labels.
- `--ignore-missing-columns` - ignore missing select/drop/rename columns.
- `--reset-index` / `--no-reset-index` - control index reset after filtering.
- `--overwrite`, `--create-dirs`, `--dry-run`, `--validate`, and
  `--strict-validation`.
- `--input-encoding TEXT` and `--output-encoding TEXT` control supported input and output
  backends independently.
- `--csv-delimiter TEXT` and `--csv-decimal TEXT` control CSV input/output paths.
- `--write-config FILE` writes this invocation as TOML without transforming data.
- `--overwrite-config` permits replacement of the selected config file only.
- Common logging options.

Filter operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`,
`not_contains`, `startswith`, `endswith`, `is_missing`, and `not_missing`. Symbol aliases
such as `==`, `!=`, `>`, `>=`, `<`, and `<=` are accepted. Membership values use `|`.

The pipeline order is fixed: select, drop, rename, type conversion, filtering, then
recoding. Validation runs on the transformed `Dataset` before writing.

```bash
statconvert transform input.sav output.csv --select age sex
statconvert transform input.csv output.parquet --rename age=Age --type Age=int
statconvert transform input.csv output.xlsx --filter age,gte,18 --recode status:A=Active,I=Inactive
statconvert transform input.csv output.csv --drop notes --dry-run
statconvert transform workbook.ods output.csv --object "Survey Data"
statconvert transform input.xlsx output.csv --csv-delimiter ";"
```

Encoding and CSV options are available only on the datafile-writing commands `convert`,
`collect`, `transform`, and `batch`. `--input-encoding` affects only readers that support explicit
encoding; `--output-encoding` affects only supporting writers. An unsupported backend
produces a warning and ignores that directional option. CSV delimiter and decimal values
apply only to CSV input/output paths, must each be one character, and cannot be the same
when both are supplied. Read-only and comparison commands do not expose these controls in
0.2.0.

## Discovery and metadata commands

### `formats`

```bash
statconvert formats
```

Lists extension, format name, backend, extension-level read/write support, and dataset
object kind (`sheet`, `r_object`, or `-`). It has only the common logging options.

### `backends`

```bash
statconvert backends
```

Lists backend name/class, whether any registered extension is readable or writable, and
whether the backend declares metadata support. Backend-wide write support does not imply
that every extension owned by the backend is writable.

### `capabilities`

```bash
statconvert capabilities TARGET
```

`TARGET` may be a bare extension, dotted extension, filename-like value, or backend name.
Format targets show extension-refined read/write truth; backend targets show broad engine
capabilities. Format details include container status, object selection, object kind, and
multiple-sheet/table flags.

```bash
statconvert capabilities zsav
statconvert capabilities .xlsx
statconvert capabilities pyreadstat
```

### `objects`

```bash
statconvert objects INPUT_PATH [OPTIONS]
```

For a single container file, lists workbook sheets and named RData/RDA objects with
zero-based indices. Existing single-file console and JSON behavior remains unchanged:
single-dataset formats report that they expose no multiple objects, and single-file
`--json` emits the existing object array.

For a folder, builds a manifest-ready discovery report without converting files. Direct
files are scanned by default; `--recursive`/`-r` includes subfolders. Repeatable
`--pattern` and `--exclude-pattern` values match file names or paths relative to the scan
root. Unsupported files are hidden unless `--include-unsupported` is supplied.

Folder console output shows flat discovery rows. `--json` without `--output` writes a
grouped JSON document to stdout. `--output PATH` writes an editable flat CSV with this
stable column order:

```text
include,input_file,input_relative_path,input_object,output_name,file_format,file_supported,object_index,object_name,object_kind,object_supported,rows,columns,message
```

Use `--json --output objects.json` for grouped JSON on disk. Existing report files require
`--overwrite`; missing report parents require `--create-dirs`. `input_file` is relative to
the scanned folder, `input_object` is a reusable selector for container objects, and
`output_name` is a conservatively sanitized suggested base name. Discovery reports do not
convert datasets, expand objects into outputs, or resolve suggested-name collisions.

`--object TEXT` selects an exact Excel/ODS sheet or RData/RDA object name, or a zero-based
index. A single supported object is selected automatically. A container with multiple
supported objects fails with the available choices unless `--object` is provided;
StatConvert never silently reads the first one. Unsupported R objects are shown when
`pyreadr` can expose them. No format-specific `--sheet` or `--r-object` option is provided.

```bash
statconvert objects workbook.xlsx
statconvert objects workbook.ods --json
statconvert objects incoming --recursive
statconvert objects incoming --recursive --output objects.csv
statconvert objects incoming --recursive --include-unsupported --output objects.csv
statconvert objects incoming --recursive --json --output objects.json
statconvert peek workbook.xlsx --object "Survey Data"
statconvert objects workspace.rdata
statconvert peek workspace.rdata --object patients
statconvert convert workspace.rdata patients.csv --object patients
```

Every command that reads exactly one dataset exposes `--object`: convert, transform, info,
peek, schema, labels, metadata, summary, describe, frequencies, missing, validate, and
report. Compare provides shared and side-specific selectors, and batch applies one shared
selector to every input file. Choosing an output workbook sheet name is not exposed at the
CLI level. The Excel backend accepts an output `object_selector` for internal/API callers
without changing this input-selector convention.

### `info`

```bash
statconvert info INPUT_FILE [--object OBJECT]
```

Displays source format/backend, dimensions, variables, and types. It has only common
logging options.

### `peek`

```bash
statconvert peek INPUT_FILE [--rows N] [--object OBJECT]
```

`--rows` defaults to `5`.

### `schema`

```bash
statconvert schema INPUT_FILE [--object OBJECT]
```

Displays normalized names, storage types, labels, value-label/missing counts, display
formats, and measurement levels.

### `labels`

```bash
statconvert labels INPUT_FILE [--limit N] [--object OBJECT]
```

Displays variable and value labels. `--limit` defaults to `100` value labels.
`--object` selects an Excel/ODS sheet or RData/RDA object.

### `metadata`

```bash
statconvert metadata INPUT_FILE [--object OBJECT] [--export-sidecar]
    [--sidecar-output PATH] [--apply-sidecar] [--sidecar-input PATH]
    [--overwrite-sidecar] [--export-dictionary PATH]
    [--overwrite-dictionary] [--export-script PATH]
    [--overwrite-script]
```

Displays normalized source metadata and metadata counts through `Dataset` accessors.
For CSV, spreadsheet, JSON, Arrow, and R inputs, the responsible backend automatically
loads a sibling `<input>.statconvert-metadata.json` sidecar when present. No explicit
sidecar option is required. New version 3 sidecars restore column metadata plus dataset
labels, notes, and safe normalized raw metadata. Existing version 2 sidecars remain
readable. Parquet and Feather also carry a StatConvert-namespaced embedded copy, but the
sibling sidecar wins when both are present.

`--export-sidecar` writes the metadata resolved by those same precedence rules as a
version 3 sidecar. By default it uses
`<input>.statconvert-metadata.json`. Add `--sidecar-output PATH` for a custom destination
and `--overwrite-sidecar` to replace an existing export. A custom parent folder must
already exist. `--sidecar-output` and `--overwrite-sidecar` require
`--export-sidecar`.

`--apply-sidecar` without a custom source validates the standardized sibling sidecar and
reports that it is active without rewriting it. Add `--sidecar-input PATH` to validate a
custom sidecar and write a version 3 copy to the standardized sibling path.
`--overwrite-sidecar` is required only when that target already exists. Sidecar columns
match physical columns by name; missing referenced columns fail, while extra data
columns are allowed and reported.

For a workbook or workspace, use `--object` so a flat sidecar describes one selected
sheet/object. An ambiguous multi-object input still fails rather than applying shared
metadata. Explicit apply activates sidecars for sidecar-aware formats; it does not modify
native SAV/DTA/XPT metadata. The `metadata` command remains terminal-oriented and has no
`--json` option. Export and apply cannot be combined in one invocation.

`--export-dictionary PATH` writes the currently resolved metadata as a human-readable
`.csv` or `.xlsx` data dictionary. CSV contains one row per physical column. XLSX contains
`Dictionary`, `Dataset`, and `Value Labels` sheets. Both preserve physical column order
and show labels, types, formats, missing definitions, value labels, dataset context, and
metadata provenance where available. Complex values use compact deterministic text;
missing metadata is blank. Existing output requires `--overwrite-dictionary`, and the
parent folder must already exist.

A dictionary is a review/handover artifact, not a reusable sidecar. StatConvert does not
automatically restore metadata from dictionaries. Use sidecar export/apply for
machine-readable metadata transport. Multi-object inputs still require `--object`;
`convert`, `batch`, and `transform` do not expose dictionary-export options.

`--export-script PATH` writes a best-effort external-tool metadata helper inferred from
the extension: `.R` for base R, `.do` for Stata, or `.sps` for SPSS. The scripts assume
the data are already loaded, contain no load/save commands, and must be reviewed before
use. They apply only metadata that maps conservatively to the target; invalid target
names, incompatible formats, complex values, ambiguous missing definitions, provenance,
and other unsupported details appear in a final review-required comment section.

Existing script output requires `--overwrite-script`, and the parent folder must already
exist. Scripts use the same resolved native/embedded/sidecar metadata as the terminal
summary and dictionary export. They are helpers rather than full-fidelity restoration
artifacts; sidecars remain the reusable machine-readable representation. No script
options exist on `convert`, `batch`, or `transform`.

## Statistical inspection and validation

### `summary`

```bash
statconvert summary INPUT_FILE [--json] [--object OBJECT]
```

Shows dimensions, type counts, label counts, missing cells, duplicate rows, and memory
usage.

### `describe`

```bash
statconvert describe INPUT_FILE [--object OBJECT] [OPTIONS]
```

Options:

- `--columns COLUMN` - restrict columns; repeatable/trailing values supported;
- `--only numeric|categorical|datetime|other` - restrict profile type; and
- `--json` - emit the profile model as JSON.
- `--object OBJECT` - select an Excel/ODS sheet or RData/RDA object.

```bash
statconvert describe workbook.xlsx --object Survey
```

### `frequencies`

```bash
statconvert frequencies INPUT_FILE [--object OBJECT] [OPTIONS]
```

Options:

- `--columns COLUMN` - restrict columns;
- `--top N` - maximum values per column (default `20`);
- `--include-missing` - include missing values;
- `--max-unique N` - skip default columns above the unique-value limit; and
- `--json`; and
- `--object OBJECT` - select an Excel/ODS sheet or RData/RDA object.

```bash
statconvert frequencies workspace.rdata --object patients
```

### `missing`

```bash
statconvert missing INPUT_FILE [--object OBJECT] [OPTIONS]
```

Options:

- `--columns COLUMN` - restrict columns;
- `--only-missing` - omit columns without actual or metadata-defined missing values;
- `--threshold PERCENT` - minimum missing percentage; and
- `--json`; and
- `--object OBJECT` - select an Excel/ODS sheet or RData/RDA object.

```bash
statconvert missing workbook.ods --object 0
```

Actual nulls and metadata-defined missing values/ranges are reported separately.

### `validate`

```bash
statconvert validate INPUT_FILE [--to FORMAT] [--strict] [--json] [--object OBJECT]
```

- `--to FORMAT` adds destination-format readiness and metadata-preservation checks.
- `--strict` makes warnings fail validation.
- `--json` emits issue objects only.
- `--object OBJECT` selects an Excel/ODS sheet or RData/RDA object.

Read-only targets such as `zsav`, `por`, and `sas7bdat` are reported as invalid write
targets. `xls`, `xlsx`, `sav`, `dta`, and `xpt` are valid writable targets when their
backend dependencies are available. Validation reports the legacy XLS row and column
limits before conversion.

## Batch conversion

### `batch`

```bash
statconvert batch INPUT_PATH OUTPUT_PATH --to FORMAT [OPTIONS]
```

Options:

- `--to FORMAT` - required writable target extension.
- `--object OBJECT` - apply the same dataset-object selector to every input file.
- `--object-manifest FILE` - process included CSV manifest rows with per-row selectors and
  output names. It cannot be combined with `--object`.
- `--all-objects` - expand every supported object in each container into a separate batch
  item. It cannot be combined with `--object` or `--object-manifest`.
- `--transform` - apply one shared transformation pipeline to every planned batch item.
- `--select`, `--drop`, `--rename`, `--type`, `--filter`, and `--recode`, plus their
  existing modifier options, have the same syntax and fixed order as `transform`.
- `--recursive`, `-r` - include subdirectories.
- `--overwrite` - allow existing output replacement.
- `--create-dirs` - create the root output directory when it is missing.
- `--preserve-structure` / `--flatten` - path policy (preserve is default).
- `--include-unsupported` / `--supported-only` - skipped-input visibility.
- `--pattern GLOB` and `--exclude-pattern GLOB` - repeatable discovery filters.
- `--dry-run` - show/write a plan without conversion.
- `--fail-fast` - stop after the first failure; running worker tasks may finish.
- `--allow-blocked` - execute pending items despite other blocked items.
- `--json` - emit the plan or result as JSON.
- `--report FILE` - write a CSV or JSON plan/result report.
- `--report-format csv|json` - override suffix inference.
- `--no-progress` - disable file-level progress.
- `--workers N` - worker threads (default `1`).
- `--validate` - validate each pending dataset before writing.
- `--strict-validation` - make warnings fail; requires `--validate`.
- `--input-encoding TEXT` and `--output-encoding TEXT` control supported batch readers
  and writers independently.
- `--csv-delimiter TEXT` and `--csv-decimal TEXT` control CSV input/output paths.
- `--write-config FILE` writes this invocation as TOML without running the batch.
- `--overwrite-config` permits replacement of the selected config file only.
- Common logging options.

Planning is deterministic. It detects unsupported inputs, output-path collisions, nested
output discovery, and unsupported targets before execution. The user-specified output
root must exist unless `--create-dirs` is used. Recursive runs preserve relative folders
by default, and generated subfolders below an existing root are created automatically.
Existing item outputs fail during execution unless `--overwrite` is used, following the
normal fail-fast policy. Result and report order follows plan order even with multiple
workers. Dry-run and JSON planning output include planned item/file counts, supported and
skipped file counts, total input bytes, largest input size, worker count, target, structure,
transform/validation state, and object mode. These are filesystem facts, not peak-memory
estimates. When workers exceed one, console output notes that each worker may hold one
dataset in memory; use `--workers 1` for very large files. Human execution output shows a
concise workload table before conversion, the files currently active in stable worker
slots, completed status counts, and a result summary afterward. When a report is requested,
its path is shown with the result; failed runs include a short corrective next step.
`--json` and JSON config runs bypass Rich progress so stdout remains one parseable JSON
document. Worker defaults and scheduling semantics are unchanged. With `--transform`, each item
is read, transformed, optionally validated, and then written. The same transformation
specification applies to every item; transformation
failures use normal item-failure and fail-fast behavior. Dry-run parses the specification
but does not read data, apply transformations, check dataset columns, create directories,
or write or replace files. In ordinary and shared-`--object` mode, object selection happens
during execution, so dry-run performs no dataset or object reads. Shared `--object` mode
selects one object per file; expansion requires `--all-objects`. A format that
does not support object selection fails as an individual item rather than silently
ignoring `--object`.

Manifest mode reads either the full CSV from `objects --output` or a minimal CSV:

```csv
input_file,input_object,output_name
jan.xlsx,Data,jan
feb.xlsx,Responses,feb
data.csv,,data
```

Only rows whose `include` value is true are planned; a missing `include` column defaults
to true. Accepted true values are `true`, `yes`, `1`, and `y`; accepted false values are
`false`, `no`, `0`, `n`, and blank, case-insensitively. Skipped rows are not validated as
conversion tasks. Included rows marked `file_supported=false` or
`object_supported=false` fail manifest validation before conversion.

Relative `input_file` values resolve below `INPUT_PATH`; absolute inputs are accepted. By
default, a relative input's parent folders are preserved below `OUTPUT_PATH`, while
`--flatten` writes directly below the output root. `output_name` controls the base file
name. If blank, it defaults to the input stem for a single dataset or
`input-stem__input-object` when a selector is present. Duplicate planned paths fail; no
automatic suffix is added. An absolute input outside `INPUT_PATH` uses no preserved parent
folder.

Manifest dry-run parses and validates the CSV, checks input paths, and plans outputs but
does not read datasets or create output directories. Blank `input_object` means normal
single-dataset/automatic-selection behavior, never all-object expansion.

All-object mode uses normal deterministic discovery and lists container objects during
planning. A single-dataset file still creates one item named `input-stem.ext`. Each
supported container object creates a separate item named
`input-stem__object-name.ext`; blank names fall back to `input-stem__object_INDEX.ext`.
Object-derived names are conservatively sanitized. Unsupported objects are never read or
converted; when unsupported inputs are included in the plan, they appear as skipped rows
with a message where the backend can provide one.

Preserve-structure keeps the input file's relative parent for every expanded item, while
`--flatten` writes all generated names below the output root. Any duplicate path after
sanitization or flattening fails planning. Use the object discovery/manifest workflow to
choose custom `output_name` values; StatConvert does not add suffixes automatically.
All-object dry-run performs object listing but does not execute dataset reads, write files,
or create output directories. XLSX/XLS/ODS listing reads container structure without
loading every sheet. RData/RDA listing may load workspace data to classify which objects
are supported because `pyreadr` descriptors alone are not always sufficient.

```bash
statconvert batch input output --to csv --recursive --dry-run
statconvert batch input new-output --to csv --create-dirs
statconvert batch input output --to parquet --workers 4 --report result.csv
statconvert batch input output --to xlsx --validate --strict-validation
statconvert batch workbooks output --to csv --object Data
statconvert batch input output --to csv --output-encoding utf-8-sig --csv-delimiter ";"
statconvert batch rdata output --to parquet --object patients
statconvert batch incoming converted --to csv --object-manifest objects.csv
statconvert batch incoming converted --to csv --all-objects
statconvert batch incoming converted --to parquet --all-objects --recursive
statconvert batch incoming converted --to parquet --transform --select id --select name
statconvert batch incoming converted --to csv --all-objects --transform --drop notes
```

`--transform` requires at least one operation, and transformation options require the
flag. It works with ordinary batches, `--object`, `--object-manifest`, and
`--all-objects`. Per-file, per-object, and manifest-row transformation rules are not
supported. Batch transformation does not append, join, merge, or deduplicate rows.

## Dataset comparison

### `compare`

```bash
statconvert compare LEFT_FILE RIGHT_FILE [OPTIONS]
```

Options:

- `--values` / `--no-values` - enable/disable cell comparison (enabled by default).
- `--sample N` - compare only the first N rows of values; incompatible with `--no-values`.
- `--columns COLUMN` - restrict schema, metadata, and values; repeatable/trailing values.
- `--ignore-columns TEXT` - ignore comma-separated columns in shape, schema, metadata,
  and positional value comparison; repeatable.
- `--numeric-tolerance FLOAT` - absolute tolerance for numeric values (default `0`).
- `--key TEXT` - match rows by one or more comma-separated key columns instead of
  physical row position.
- `--max-differences N` - cap detailed difference examples (default `50`) without
  changing complete summary counts or comparison status.
- `--object OBJECT` - apply one selector to both input files.
- `--left-object OBJECT` - select an object only from the left input.
- `--right-object OBJECT` - select an object only from the right input.
- `--json` - emit the full comparison model.
- `--strict` - make warning-level differences fail.
- `--report FILE` - write CSV, JSON, or HTML.
- `--report-format csv|json|html` - override suffix inference.
- `--write-config FILE` writes this invocation as TOML without comparing data.
- `--overwrite-config` permits replacement of the selected config file only.
- Common logging options.

Comparison covers shape, full column membership/order, storage types, display formats,
measurement levels, normalized variable/value labels and missing metadata, and optional
cell values. Ignored columns are removed before those checks. Numeric tolerance applies
only when both compared columns are numeric; booleans, datetimes, strings, and missing
versus non-missing values retain exact comparison semantics. Reports and terminal output
show the applied options.
Without `--key`, row comparison remains positional. With `--key`, every key column must
exist on both sides, compound key values must be unique on each side, and key columns
cannot be ignored. Rows are aligned by exact key values before non-key values are checked;
numeric tolerance still applies after alignment. A single null key value is allowed, but
repeated null keys are duplicates.
`--object` cannot be combined with either side-specific selector; left and right selectors
may be used independently or together.

```bash
statconvert compare before.sav after.parquet
statconvert compare before.csv after.csv --sample 1000 --strict
statconvert compare before.csv after.csv --ignore-columns exported_at,source_file
statconvert compare before.csv after.csv --numeric-tolerance 0.0001
statconvert compare before.csv after.csv --key id
statconvert compare before.csv after.csv --key id,date --numeric-tolerance 0.001
statconvert compare before.csv after.csv --key id --ignore-columns exported_at
statconvert compare before.csv after.csv --max-differences 10
statconvert compare before.csv after.csv --key id --numeric-tolerance 0.001 --max-differences 25
statconvert compare before.csv after.csv --json --report comparison.html
statconvert compare before.xlsx after.xlsx --object SurveyData
statconvert compare before.xlsx after.xlsx --left-object Old --right-object New
statconvert compare before.rdata after.rdata --object patients
```

Reports are written even when differences result in exit code `1`. Key-based reports
include matching mode, key columns, matched rows, and left-only/right-only row counts.
Console and HTML output show a bounded first-differences table. CSV includes bounded
detail rows, while JSON is the most complete machine-readable summary and detail format.
Chunked comparison remains deferred.

## Dataset reports

### `report`

```bash
statconvert report INPUT_FILE --output FILE [--object OBJECT] [OPTIONS]
```

Options:

- `--object OBJECT` selects an Excel/ODS sheet or RData/RDA object by exact name or
  zero-based index.
- `--output FILE`, `-o FILE` - required `.html`, `.htm`, `.json`, or `.csv` report.
- `--format html|json|csv` - override suffix inference.
- `--overwrite` - replace an existing report file.
- `--create-dirs` - create a missing report output parent directory.
- `--preset quick|full|validation|metadata` - section preset.
- `--section NAME` - include only named sections; repeatable.
- `--no-summary`, `--no-schema`, `--no-metadata`, `--no-labels`, `--no-missing`,
  `--no-describe`, and `--no-validation` - omit default/preset sections.
- `--frequencies` - include frequency tables.
- `--columns COLUMN` - restrict describe/frequency columns.
- `--frequency-top N` - maximum frequency values (default `20`).
- `--frequency-include-missing` - include missing values in frequencies.
- `--frequency-max-unique N` - skip high-cardinality default frequency columns.
- `--max-table-rows N` - HTML/CSV rows per table (default `1000`).
- `--max-preview-values N` - value-label preview limit (default `5`).
- `--target-format FORMAT` - add conversion-readiness validation.
- `--strict-validation` - use strict validation severity in the report.
- `--json` - print a concise JSON summary after writing.
- `--quiet` - suppress the normal Rich completion summary.
- `--write-config FILE` writes this invocation as TOML without generating the report.
- `--overwrite-config` permits replacement of the selected config file only.
- Common logging options.

Default sections are summary, schema, metadata, labels, missing, describe, and validation.
`full` adds frequencies; `quick` selects summary/schema/missing/validation; `validation`
selects summary/schema/validation; `metadata` selects summary/schema/metadata/labels.
Explicit `--section`, `--frequencies`, and `--no-*` options refine the preset.

`--max-table-rows` limits HTML/CSV tables and adds truncation notices; JSON report files
retain the complete model. Reports are static and Rich-free.

```bash
statconvert report input.sav --output report.html --preset quick
statconvert report input.sav --output reports/report.html --create-dirs
statconvert report input.sav --output report.json --preset full
statconvert report input.sav --output report.csv --section summary --section validation
```
