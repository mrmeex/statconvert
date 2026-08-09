# Browser UI Guide

StatConvert 1.0 includes a local browser interface for its existing inspection,
conversion, validation, transformation, comparison, reporting, collection, and config
workflows. The browser UI uses the same Python services and output-safety rules as the
command line.

## Install the UI

Install the optional UI dependencies with StatConvert:

```powershell
python -m pip install "statconvert[ui]"
```

The base installation provides the complete command-line application. The `ui` extra
adds the local web server used by the browser interface; it does not add formats or
change conversion behavior.

## Launch the UI

```powershell
statconvert ui
```

StatConvert normally opens `http://statconvert.localhost:<port>`. The default port is
8765. Use `statconvert ui --no-browser` to start without opening a browser, or
`statconvert ui --help` to see the local launch options.

## Local-only operation and privacy

The UI server binds only to the loopback interface on your computer. Dataset paths refer
to local files, and workflow processing stays in the local StatConvert process. The UI
does not upload files to a cloud service and has no accounts, telemetry, cloud sync, or
remote-server mode. Closing a browser tab does not automatically stop a job; stop the
StatConvert process when you are finished.

## Home

Home links to every workflow and shows whether the StatConvert backend is connected. Start with
Inspect when you do not yet know a dataset's columns, objects, or metadata.

## Path browser basics

Path fields accept a full local path. The folder button opens a compact constrained
browser after you confirm a starting folder. Navigation stays inside that folder and its
descendants. Settings can remember the most recently selected input and output folders,
or disable that behavior completely. A drive/common-location starting view is deferred.

Format fields use registry-aligned friendly names such as **CSV (*.csv)**,
**Excel Workbook (*.xlsx)**, and **Stata (*.dta)**. They are sorted by the displayed
name; generated commands and API requests continue to use the established extension
values. Dataset target selectors share one list of the 15 normally writable extensions,
so read-only ZSAV, POR, and SAS7BDAT are not offered as destinations.

## Results and raw details

Plans and completed jobs put useful paths, counts, formats, and status fields first.
Machine-oriented response data remains available at the bottom under **Raw details**,
collapsed by default. Starting Convert, Validate, Report, Compare, or Collect replaces
its accepted plan with live progress so the two states do not compete.

Job badges use a consistent state palette: running is blue, successful completion is
green, failure is red, cancellation is orange, and queued or unknown states are neutral.

## Inspect

Select one file, then choose an inspection tab:

- **Overview** shows dimensions and columns.
- **Preview** returns a bounded sample of rows.
- **Schema** shows column types and related schema information.
- **Labels** shows variable and value labels where supported.
- **Metadata** summarizes bounded normalized metadata, includes read-only diagnostic data
  and coverage from the shared service, and can export helper scripts for R (`.R`), SPSS
  (`.sps`), or Stata (`.do`). The explicit **Edit sidecar metadata** section supports
  bounded dataset labels, notes, variable labels, typed value labels, and measurement
  levels. Validate/Preview is required before Save, the target and overwrite choice are
  explicit, and raw details stay collapsed and read-only. Source data and native metadata
  are never edited.
- **Summary** shows dataset-level statistics and memory size.
- **Describe** separates column profiles, numeric statistics, and categorical statistics.
- **Frequencies** shows a separate bounded frequency table for each selected variable.
- **Missing** shows ordinary and metadata-defined missing values.
- **Objects** discovers workbook sheets or objects in container formats.

Use an object name or zero-based object index when a container contains more than one
supported dataset.

## Convert

Choose an input file, output file, and target format, then plan before running. Parquet is
the default browser target. If an output path has no extension, the UI appends the
selected target extension. An explicit different extension is preserved and reported so
you can resolve the mismatch yourself.

JSON is the normal records-array format. JSON Lines (`.jsonl`) and newline-delimited JSON
(`.ndjson`) are separate friendly target choices and write one record object per line.
Target choices are sorted by their displayed labels.

Enable **Overwrite existing output** only when replacing a file is intentional. Enable
**Create missing directories** when the output's parent folder does not exist. Streaming
controls appear for eligible line-oriented text workflows.

## Batch Convert

Batch Convert discovers supported files in an input folder and plans their output paths.
Use **Include subfolders** for recursive discovery and preserve the folder structure when
needed. Parquet is the default browser target. JSONL and NDJSON are both available as
line-delimited targets.

Workbook and other container formats require an explicit object policy: convert every
supported object, or apply one object name/index to every input. Automatic mode pauses
the plan when that choice is required.

**Workers** is under Advanced options. Leave it blank to retain StatConvert's default, or
enter a positive integer to control parallel workers where supported. Live progress
replaces the workload plan after execution begins. Only one browser-UI Batch job may be
queued or running at a time, and returning to the page reattaches to that job.

## Validate

Validate checks dataset quality and can test readiness for a target format. A TOML schema
contract defines reusable column and dataset rules. Results appear in an issues table
with severity, code, column, message, and available expected/actual information. Strict
mode promotes the existing warning policy; it does not create additional validation
rules.

## Transform

### Recipes and step order

A transform recipe is an ordered list of changes. Each step receives the columns and rows
produced by the step above it, so order matters. For example, rename `income` before a
derive expression refers to `annual_income`.

The visual builder supports the seven existing ordered step types:

- **select** keeps named columns;
- **drop** removes named columns;
- **rename** maps old column names to new names;
- **convert_type** converts one column to a supported data type;
- **derive** creates or replaces a column from a safe expression;
- **filter** keeps rows that satisfy an expression or structured conditions; and
- **recode** maps existing values to replacements.

### Beginner example

Suppose `people.csv` contains `name`, `age`, `status`, and `income`. To create a smaller
Parquet dataset for active adults:

1. Select `people.csv` and choose an extensionless output such as `people_active`.
   With the default target, the output becomes `people_active.parquet`.
2. Add a **filter** step with `age >= 18`.
3. Add another **filter** step with `status == 'active'`.
4. Add a **derive** step named `income_monthly` with `income / 12`.
5. Add a **select** step for `name`, `age`, `status`, `income`, and `income_monthly`.
6. Review projected columns, preview before/after rows, and run the transform.

The column picker inserts columns known at that point in the recipe. The function picker
uses the active safe-expression registry, and expression validation reports unknown
columns, functions, or invalid syntax without evaluating the dataset. The preview is
bounded and does not write the output file.

The TOML panel shows the canonical ordered recipe. Save that TOML from Configs when you
want a repeatable workflow. Transform execution remains non-streaming.

## Configs

Configs creates starter TOML for supported workflows, loads a local TOML file, validates
editor text with the existing config schema, saves validated TOML, and runs it as a
background job. Transform TOML from the visual builder uses the same ordered `[[steps]]`
structure. Loading Transform TOML does not reconstruct the visual step editor; edit and
run it in Configs instead. Config results show workflow fields without repeating the CLI
command; the equivalent command remains in its Settings-controlled panel, and the full
payload remains under collapsed **Raw details**.

## Compare

Select left and right datasets and optional object selectors. You can compare selected
columns, ignore columns, match rows by keys, use numeric tolerance, bound detailed
differences, and optionally write a CSV, JSON, or HTML report. Completed results are
organized into Comparison Summary, Inputs, Shape, Columns, Schema, Metadata, and Values.
The Values section contains only the bounded differences returned by the comparison
engine. For columns identified by metadata as date-only, equivalent Python dates, naive
midnight date-times, and canonical `YYYY-MM-DD` strings compare by calendar date. This
does not change conversion output or hide separate schema and metadata warnings; numeric
date epochs such as JSON epoch milliseconds remain strict values.

## Report

Report writes a static HTML, JSON, or CSV dataset report and defaults to HTML in the
browser. An extensionless output path receives `.html`, `.json`, or `.csv` for the
selected format. An explicit different extension is preserved and reported as a warning.
Presets select established section groups, while profile columns, frequency tables,
schema contracts, and table-row limits refine the output. Planning checks the dataset
and effective output path without writing; generation replaces the plan with progress
and keeps the final output path visible.

## Collect

Collect writes selected datasets into one XLSX or ODS workbook. It requires a CSV
manifest that lists the input files in output order. The smallest useful manifest is:

```csv
input_file,input_object,output_object
data.csv,,Data
```

`input_file` is required. `input_object` selects a sheet/object from a multi-object input,
and `output_object` controls the output worksheet/object name. Paths may be absolute or
relative to the manifest directory; an optional base directory overrides relative-path
resolution. The optional `include` column accepts true/false-style values.

Use **Show manifest example** for a second workbook example. **Create starter manifest**
writes that example to a chosen `.csv` path without overwriting unless you explicitly
allow it. Replace its example rows with your files, select the manifest and output
workbook, then choose **Plan collection**. Planning is the manifest validation step: it
checks the CSV structure, paths, object selections, duplicate/unsafe output names, and
output collision policy before collection runs.

## Reference

Reference reads the active registries to show formats, backends, and format-refined
capabilities. Format rows are sorted by friendly name and show read/write, streaming,
metadata mode, object kind, multi-sheet output capability, and the most important caveat.
The detailed capability table shows the extension-refined object, streaming, and native or
embedded metadata flags. Use Reference as the browser source of truth for the current
installation; unsupported future candidates and database formats do not appear.

Metadata modes are deliberately compact: **native, limited** means the format carries a
supported subset itself; **native on read** identifies a read-only source; **sidecar**
means normalized metadata is kept in the sibling StatConvert JSON file; and
**embedded + sidecar** means Parquet/Feather also carry a fallback embedded copy, with the
sibling sidecar taking precedence. Caveats call out read-only alternatives and the most
important fidelity or object limitation; they are guidance, not automatic substitutions.

## Settings

Settings controls the default working/path-browser folders, remembered paths, table page
size, command-preview visibility, and UI job logging. Logging uses the existing CLI
spelling and behavior: enabled jobs receive `--log` and `--log-level` equivalents and
write to the displayed local log folder. Dataset preview contents are not written as UI
diagnostics.

## About

About shows the StatConvert and Python versions, license, platform, optional UI runtime
status, local network boundary, settings path, effective log path, and privacy summary.

## Troubleshooting

### UI dependencies are missing

Install the optional extra with `python -m pip install "statconvert[ui]"`, then run
`statconvert ui` again.

### The browser does not open

Copy the URL printed by StatConvert into a browser. Use `--no-browser` when you prefer to
open it manually.

### `statconvert.localhost` does not resolve

StatConvert falls back to `http://127.0.0.1:<port>`. Both addresses remain local-only.

### The server shows disconnected

Confirm the terminal process is still running. A server restart discards process-local
job state, so an earlier job may no longer be available.

### Output already exists

Choose a different path or explicitly enable overwrite. StatConvert does not silently
replace output files.

### A format or capability is unsupported

Review Reference or run `statconvert capabilities`. Some formats need an optional backend
and not every format supports writing, objects, or streaming.

### A workbook or container has multiple objects

Inspect Objects first, then select an object by name/index or choose the explicit Batch
container policy.

### Find UI job logs

Open Settings or About to see the effective log directory. Logging must be enabled before
starting the job.

For detailed command options, see the [CLI Reference](cli.md). For general workflows, see
the [User Guide](user-guide.md) and [Examples and Recipes](examples.md). StatConvert is
licensed under the [GNU Affero General Public License v3.0 or later](../LICENSE).
