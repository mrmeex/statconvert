# Administrator Guide

## Who this guide is for

This guide is for administrators and application owners who install, deploy, verify,
update, uninstall, or support StatConvert in Windows and managed Python environments.
The [User Guide](user-guide.md) explains day-to-day dataset commands.

## Deployment model

StatConvert is distributed publicly only as a wheel attached to a GitHub Release.
Installing the wheel provides the `statconvert` console command and the equivalent
`python -m statconvert` module entry point. The module form is the reliable fallback when
the selected Python environment's `Scripts` directory is not on `PATH`.

For managed deployment, prefer a dedicated virtual environment and retain the exact wheel
that was approved for installation. The wheel installs the runtime dependencies required
for every advertised format.

## Requirements

Before installation, confirm the target has:

- Python 3.11 or newer;
- pip for that Python interpreter;
- permission to create or modify the target environment;
- the latest approved `statconvert-<version>-py3-none-any.whl` downloaded from the
  StatConvert GitHub Releases page; and
- access to the configured package index for runtime dependencies when they are not already
  installed.

Check the selected interpreter and pip together:

```powershell
where.exe python
python --version
python -m pip --version
```

Always invoke pip through the intended interpreter. A bare `pip` command can belong to a
different Python installation.

## Install the release wheel

Download the wheel from the StatConvert GitHub Releases page, keep it in an approved
location, and install it by exact path:

```powershell
python -m pip install C:\Installers\statconvert-<version>-py3-none-any.whl
```

Use the exact downloaded filename rather than wildcard expansion. The public distribution
model supports installation from the release wheel only.

## Recommended installation workflow

A dedicated virtual environment avoids dependency conflicts and gives administrators one
location to update, verify, or remove:

```powershell
py -3.11 -m venv C:\Tools\StatConvert\.venv
C:\Tools\StatConvert\.venv\Scripts\python.exe -m pip install --upgrade pip
C:\Tools\StatConvert\.venv\Scripts\python.exe -m pip install C:\Installers\statconvert-<version>-py3-none-any.whl
C:\Tools\StatConvert\.venv\Scripts\python.exe -m statconvert --version
C:\Tools\StatConvert\.venv\Scripts\python.exe -m statconvert --help
C:\Tools\StatConvert\.venv\Scripts\python.exe -m statconvert formats
```

Absolute interpreter paths avoid ambiguity when several Python versions are installed.
Administrators may expose the virtual environment's `Scripts` directory through their
normal `PATH` management process.

If internet access is restricted, the StatConvert wheel is available locally, but its
runtime dependencies must still be available from an approved package source or already
installed in the environment.

## Verification checklist

Run verification with the exact interpreter intended for users:

```powershell
python --version
python -m pip --version
python -m pip show statconvert
python -m statconvert --version
python -m statconvert --help
python -m statconvert formats
python -m statconvert capabilities xlsx
python -m statconvert capabilities xls
python -m statconvert capabilities rdata
```

The console command can be checked separately when it will be exposed to users:

```powershell
statconvert --help
statconvert --version
```

The version report identifies the installed StatConvert and Python versions and lists
important runtime dependency versions. A missing dependency is shown as `not installed`,
which makes this report useful for deployment verification and support intake.

Use a tiny, non-sensitive CSV file for optional smoke operations:

```powershell
statconvert convert sample.csv sample.xlsx
statconvert validate sample.csv --to xls
statconvert report sample.csv --output sample-report.html
```

Use a fresh output folder and remove generated smoke data, reports, logs, and metadata
sidecars after verification.

## Windows PATH behavior

pip places `statconvert.exe` in the selected Python environment's `Scripts` directory. In
a virtual environment this is normally `.venv\Scripts\`. If `statconvert` is not
recognized, use one of these approaches:

- activate the virtual environment;
- call `statconvert.exe` by absolute path;
- add the correct `Scripts` directory to `PATH`; or
- use `python -m statconvert`.

For example:

```powershell
C:\Tools\StatConvert\.venv\Scripts\statconvert.exe formats
C:\Tools\StatConvert\.venv\Scripts\python.exe -m statconvert formats
```

## Managed environment considerations

- Prefer one dedicated virtual environment per deployment.
- Avoid installing into global system Python unless that is the organization's standard.
- Retain the approved downloaded wheel in a controlled location.
- Record the interpreter path and installed version.
- Use non-sensitive files for smoke tests.
- Give users writable locations for datasets, reports, sidecars, and optional logs.
- Decide whether users will call the module, activate the environment, use an absolute
  executable path, or use an externally managed shortcut.

StatConvert creates a log only when a user supplies `--log FILE`. Administrators should
apply normal access, retention, and privacy policies to those files.

## Updating StatConvert

Download the newer wheel from the StatConvert GitHub Releases page, then update the
controlled environment using its exact path:

```powershell
python -m pip install --upgrade C:\Installers\statconvert-<new-version>-py3-none-any.whl
```

Verify the installed version and rerun the entry-point and format checks:

```powershell
python -m pip show statconvert
python -m statconvert --help
python -m statconvert formats
```

## Uninstalling StatConvert

Remove StatConvert from the selected environment with:

```powershell
python -m pip uninstall statconvert
```

Uninstalling does not remove user datasets, converted outputs, reports, logs, or metadata
sidecars. If StatConvert has a dedicated virtual environment, confirm that no required user
files are stored inside it before deleting that environment.

## Supporting users

Ask users for:

- the exact command and full error message;
- `python -m statconvert --version`;
- `python -m pip show statconvert`;
- `python -m statconvert --help`;
- `python -m statconvert formats`;
- input and output extensions;
- whether the input has multiple sheets or R objects;
- whether `--object` was supplied;
- whether the output already existed; and
- the selected log file, when logging was enabled.

Do not request sensitive datasets unless approved. Prefer a small anonymized reproduction.

## Troubleshooting

### `statconvert` is not recognized

Use `python -m statconvert --help`, activate the intended virtual environment, or call the
environment's `statconvert.exe` by absolute path.

### Installation succeeds but imports fail

The wheel may have been installed for another interpreter. Compare `where.exe python`,
`python --version`, `python -m pip --version`, and `python -m pip show statconvert`, then
reinstall through the intended interpreter:

```powershell
python -m pip install --force-reinstall C:\Installers\statconvert-<version>-py3-none-any.whl
```

### Multiple Python versions are installed

Select Python explicitly with the Windows launcher or an absolute interpreter path:

```powershell
py -3.11 -m pip install C:\Installers\statconvert-<version>-py3-none-any.whl
C:\Tools\StatConvert\.venv\Scripts\python.exe -m statconvert --help
```

### Output cannot be written

Choose a writable output folder and close applications that have the destination open,
including Excel. Existing outputs require `--overwrite` for `convert`, `collect`, `transform`,
`batch`, `report`, and `objects --output`. Missing user-specified output directories
require `--create-dirs`;
the current directory and existing directories need no flag. Batch creates generated
preserve-structure subfolders below an existing root automatically. Dry-run creates no
directories and writes or replaces no files.

### A workbook or R workspace cannot be selected

List available objects and repeat the command with the required selector:

```powershell
python -m statconvert objects workbook.xlsx
python -m statconvert objects workspace.rdata
```

See the [Format Guide](formats.md) for container behavior and format limits.

For one container-to-container conversion, use XLSX or ODS output:

```powershell
python -m statconvert convert workbook.xlsx combined.xlsx --all-objects
python -m statconvert convert workbook.xlsx combined.ods --all-objects
```

Support cases should check for duplicate or target-invalid object names. StatConvert does
not rename output sheets automatically. Unsupported input objects are skipped only when
at least one supported tabular object remains.

For support cases involving a mixed input folder, collect a discovery report without
converting data:

```powershell
python -m statconvert objects incoming --recursive --include-unsupported --output objects.csv
```

The report uses paths relative to `incoming`. Treat object names and file names as
potentially sensitive operational metadata when sharing it.

After review, the same report can control a batch run:

```powershell
python -m statconvert batch incoming converted --to csv --object-manifest objects.csv
```

Manifest mode trusts included rows as the requested task set but still validates support,
input existence, safe output names, duplicate outputs, and the normal output-root policy.

For a complete supported-object export without manual editing, use `--all-objects`:

```powershell
python -m statconvert batch incoming converted --to csv --all-objects
```

One container can produce several files. Review available disk space and generated names;
duplicate paths stop planning and should be resolved through an edited object manifest.

The same established transform pipeline can be applied uniformly to every planned item:

```powershell
python -m statconvert batch incoming converted --to parquet --transform --select id --select name
```

Transformation failures follow normal per-item and fail-fast behavior. Dry-run parses the
pipeline but does not read datasets or verify referenced columns.

To place reviewed manifest rows into one workbook instead of separate files, use
`collect`:

```powershell
python -m statconvert collect objects.csv combined.xlsx --base-dir incoming --dry-run
python -m statconvert collect objects.csv combined.xlsx --base-dir incoming
```

Collection output is limited to XLSX and ODS. Relative paths use `--base-dir` or the
manifest parent. Existing outputs require `--overwrite` and missing output parents
require `--create-dirs`; dry-run creates neither. Invalid or duplicate output object
names and any included row failure stop collection before the final write. Collect does
not merge or append rows.

Capacity planning differs by workflow. Batch modes release each item after its independent
write, although multiple workers hold multiple current datasets concurrently. Batch
dry-run reports unique-file counts, total/largest input sizes, and worker settings without
predicting decoded memory. Use `--workers 1` for huge or memory-constrained runs.
`convert --all-objects` and `collect` retain all selected datasets until one final
container write, so the combined selected data must fit comfortably in memory. RData/RDA
object discovery can also load workspace data while classifying objects. For large object
sets, prefer separate batch outputs and conservative worker counts.

## Release wheel provenance

The wheel attached to a GitHub Release is the supported public installation artifact.
Release maintainers validate it before publication; administrators should retain the exact
downloaded filename when recording deployments and support cases.

## What is out of scope

The current supported deployment model does not include standalone executable deployment,
automated offline dependency bundles, central configuration files, or row
merging/appending during collection.
