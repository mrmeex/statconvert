from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
import re

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.inspection.validation import validate_target_compatibility
from statconvert.registry import (
    can_read_format,
    can_write_format,
    format_write_error,
    get_format_capabilities,
    list_formats,
)


runner = CliRunner()
XLRD_AVAILABLE = find_spec("xlrd") is not None
XLWT_AVAILABLE = find_spec("xlwt") is not None
EXPECTED_EXTENSIONS = {
    ".csv", ".dta", ".feather", ".json", ".jsonl", ".ndjson", ".ods",
    ".parquet", ".por", ".rda", ".rdata", ".rds", ".sas7bdat", ".sav",
    ".xls", ".xlsx", ".xpt", ".zsav",
}
READ_ONLY_EXTENSIONS = {".por", ".sas7bdat", ".zsav"}
READ_ONLY_ALTERNATIVES = {
    ".por": ".sav",
    ".sas7bdat": ".xpt",
    ".zsav": ".sav",
}


def test_registered_format_matrix_has_the_expected_supported_boundary() -> None:
    formats = list_formats()

    assert set(formats) == EXPECTED_EXTENSIONS
    assert {
        extension for extension, info in formats.items() if not info["can_write"]
    } == READ_ONLY_EXTENSIONS
    assert all(info["metadata_mode"] for info in formats.values())
    assert all(info["caveat"] for info in formats.values())


def test_format_guide_extension_matrix_matches_the_registry() -> None:
    guide = (
        Path(__file__).resolve().parents[1] / "docs" / "formats.md"
    ).read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `(\.[a-z0-9]+)` \|", guide, re.MULTILINE))

    assert documented == EXPECTED_EXTENSIONS


@pytest.mark.parametrize(
    ("extension", "can_read", "can_write"),
    [
        ("sav", True, True),
        (".zsav", True, False),
        ("POR", True, False),
        (".dta", True, True),
        ("SAS7BDAT", True, False),
        (".xpt", True, True),
        ("xlsx", True, True),
        (".XLS", XLRD_AVAILABLE, XLWT_AVAILABLE),
    ],
)
def test_extension_capabilities_are_normalized_and_truthful(
    extension: str,
    can_read: bool,
    can_write: bool,
) -> None:
    capabilities = get_format_capabilities(extension)

    assert capabilities.can_read is can_read
    assert capabilities.can_write is can_write


def test_unknown_extension_capability_checks_return_false() -> None:
    assert can_read_format("unknown") is False
    assert can_write_format("unknown") is False


@pytest.mark.parametrize(
    ("extension", "alternative"), READ_ONLY_ALTERNATIVES.items()
)
def test_read_only_formats_report_actionable_write_alternatives(
    extension: str,
    alternative: str,
) -> None:
    record = list_formats()[extension]

    assert record["write_alternative"] == alternative
    assert "Read-only" in record["caveat"]
    assert alternative in record["caveat"]
    assert format_write_error(extension) == (
        f"Writing {extension} is not supported. Use {alternative} instead."
    )


@pytest.mark.parametrize("extension", ["zsav", "por", "sas7bdat"])
def test_convert_rejects_non_writable_targets_early(
    tmp_path: Path,
    extension: str,
) -> None:
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / f"output.{extension}"

    result = runner.invoke(app, ["convert", str(input_file), str(output_file)])

    assert result.exit_code == 1
    assert f"Writing .{extension} is not supported" in result.output
    assert not output_file.exists()
@pytest.mark.parametrize("extension", ["zsav"])
def test_transform_rejects_non_writable_targets_early(
    tmp_path: Path,
    extension: str,
) -> None:
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / f"output.{extension}"

    result = runner.invoke(app, ["transform", str(input_file), str(output_file)])

    assert result.exit_code == 1
    assert f"Writing .{extension} is not supported" in result.output
    assert not output_file.exists()


def test_convert_and_transform_keep_xlsx_writes_valid(tmp_path: Path) -> None:
    input_file = _write_csv(tmp_path / "input.csv")
    converted = tmp_path / "converted.xlsx"
    transformed = tmp_path / "transformed.xlsx"

    convert_result = runner.invoke(app, ["convert", str(input_file), str(converted)])
    transform_result = runner.invoke(
        app,
        ["transform", str(input_file), str(transformed)],
    )

    assert convert_result.exit_code == 0
    assert transform_result.exit_code == 0
    assert converted.read_bytes().startswith(b"PK")
    assert transformed.read_bytes().startswith(b"PK")


@pytest.mark.parametrize("extension", ["zsav", "sas7bdat"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_batch_rejects_non_writable_targets_before_planning(
    tmp_path: Path,
    extension: str,
    dry_run: bool,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_csv(input_dir / "input.csv")
    arguments = [
        "batch",
        str(input_dir),
        str(tmp_path / "output"),
        "--to",
        extension,
    ]
    if dry_run:
        arguments.append("--dry-run")

    result = runner.invoke(app, arguments)

    assert result.exit_code == 1
    assert f"Writing .{extension} is not supported" in result.output
    assert not (tmp_path / "output").exists()


def test_batch_keeps_xlsx_target_writable(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_csv(input_dir / "input.csv")

    result = runner.invoke(
        app,
        [
            "batch", str(input_dir), str(output_dir), "--to", "XLSX",
            "--create-dirs",
        ],
    )

    output_file = output_dir / "input.xlsx"
    assert result.exit_code == 0
    assert output_file.read_bytes().startswith(b"PK")


@pytest.mark.parametrize("extension", ["zsav", "por", "sas7bdat"])
def test_validation_reports_non_writable_target(extension: str) -> None:
    issues = validate_target_compatibility(
        Dataset(pd.DataFrame({"value": [1]})),
        extension,
    )

    issue = next(item for item in issues if item.code == "target_not_writable")
    assert issue.severity == "error"
    assert f"Writing .{extension} is not supported" in issue.message


@pytest.mark.parametrize(
    "extension",
    ["xlsx", "sav", "dta", "xpt"] + (["xls"] if XLWT_AVAILABLE else []),
)
def test_validation_does_not_reject_writable_target(extension: str) -> None:
    issues = validate_target_compatibility(
        Dataset(pd.DataFrame({"value": [1]})),
        extension,
    )

    assert all(item.code != "target_not_writable" for item in issues)


def test_validate_cli_reports_read_only_target(tmp_path: Path) -> None:
    input_file = _write_csv(tmp_path / "input.csv")

    rejected = runner.invoke(
        app,
        ["validate", str(input_file), "--to", "zsav"],
    )
    accepted = runner.invoke(
        app,
        ["validate", str(input_file), "--to", "xlsx"],
    )

    assert rejected.exit_code == 1
    assert "target_not_writable" in rejected.output
    assert "Writing .zsav is not supported" in rejected.output
    assert accepted.exit_code == 0
    assert "target_not_writable" not in accepted.output


@pytest.mark.parametrize(
    ("target", "expected_read", "expected_write"),
    [
        ("zsav", "yes", "no"),
        (
            "xls",
            "yes" if XLRD_AVAILABLE else "no",
            "yes" if XLWT_AVAILABLE else "no",
        ),
        ("xlsx", "yes", "yes"),
    ],
)
def test_capabilities_cli_uses_extension_level_truth(
    target: str,
    expected_read: str,
    expected_write: str,
) -> None:
    result = runner.invoke(app, ["capabilities", target])

    assert result.exit_code == 0
    assert f"Read {expected_read}" in _without_table_borders(result.output)
    assert f"Write {expected_write}" in _without_table_borders(result.output)


def test_formats_cli_shows_extension_level_read_write_truth() -> None:
    result = runner.invoke(app, ["formats"])
    output = _without_table_borders(result.output)

    assert result.exit_code == 0
    assert ".zsav SPSS Compressed (ZSAV) pyreadstat yes no" in output
    assert ".sas7bdat SAS Dataset pyreadstat yes no" in output
    xls_read = "yes" if XLRD_AVAILABLE else "no"
    xls_write = "yes" if XLWT_AVAILABLE else "no"
    assert f".xls Excel 97-2003 Workbook excel {xls_read} {xls_write}" in output
    assert ".xlsx Excel Workbook excel yes yes" in output


@pytest.mark.parametrize(
    ("extension", "name", "streaming"),
    [
        (".json", "JSON", False),
        (".jsonl", "JSON Lines", True),
        (".ndjson", "Newline-delimited JSON", True),
    ],
)
def test_json_family_format_capabilities_are_distinct_and_truthful(
    extension: str,
    name: str,
    streaming: bool,
) -> None:
    info = list_formats()[extension]
    capabilities = get_format_capabilities(extension)

    assert info["name"] == name
    assert info["can_read"] is True
    assert info["can_write"] is True
    assert info["supports_streaming"] is streaming
    assert capabilities.supports_streaming is streaming


@pytest.mark.parametrize(
    ("target", "expected"),
    [("json", "no"), ("jsonl", "yes"), ("ndjson", "yes")],
)
def test_capabilities_cli_reports_json_family_streaming_truth(
    target: str,
    expected: str,
) -> None:
    result = runner.invoke(app, ["capabilities", target])

    assert result.exit_code == 0
    assert f"Streaming {expected}" in _without_table_borders(result.output)


@pytest.mark.parametrize(
    ("extension", "is_container", "object_selection", "object_kind"),
    [
        (".csv", False, False, None),
        (".xlsx", True, True, "sheet"),
        (".xls", True, True, "sheet"),
        (".sav", False, False, None),
        (".zsav", False, False, None),
        (".por", False, False, None),
        (".dta", False, False, None),
        (".sas7bdat", False, False, None),
        (".xpt", False, False, None),
        (".json", False, False, None),
        (".ndjson", False, False, None),
        (".jsonl", False, False, None),
        (".parquet", False, False, None),
        (".feather", False, False, None),
        (".rds", False, False, None),
        (".rdata", True, True, "r_object"),
        (".rda", True, True, "r_object"),
        (".ods", True, True, "sheet"),
    ],
)
def test_complete_extension_object_capability_matrix(
    extension: str,
    is_container: bool,
    object_selection: bool,
    object_kind: str | None,
) -> None:
    capabilities = get_format_capabilities(extension)

    assert capabilities.is_container is is_container
    assert capabilities.object_selection is object_selection
    assert capabilities.object_kind == object_kind
    assert capabilities.supports_multiple_sheets is (object_kind == "sheet")
    assert capabilities.supports_multiple_tables is (object_kind == "r_object")


def test_resolved_format_records_expose_complete_object_matrix() -> None:
    formats = list_formats()

    for info in formats.values():
        assert {
            "can_read",
            "can_write",
            "is_container",
            "object_selection",
            "object_kind",
            "multi_object_write",
            "output_object_kind",
            "supports_multiple_sheets",
            "supports_multiple_tables",
        } <= info.keys()
        assert info["object_selection"] is info["is_container"]
        assert (info["object_kind"] is not None) is info["object_selection"]


@pytest.mark.parametrize(
    ("extension", "supported", "output_kind"),
    [
        (".xlsx", True, "sheet"),
        (".ods", True, "sheet"),
        (".xls", False, None),
        (".rdata", False, None),
        (".rda", False, None),
        (".csv", False, None),
    ],
)
def test_multi_object_output_capability_matrix(
    extension: str,
    supported: bool,
    output_kind: str | None,
) -> None:
    capabilities = get_format_capabilities(extension)

    assert capabilities.multi_object_write is supported
    assert capabilities.output_object_kind == output_kind


def test_rds_extension_does_not_inherit_workspace_table_capability() -> None:
    rds = get_format_capabilities("rds")
    rdata = get_format_capabilities("rdata")

    assert rds.supports_multiple_tables is False
    assert rds.is_container is False
    assert rdata.supports_multiple_tables is True
    assert rdata.is_container is True


def test_formats_cli_shows_container_and_object_capabilities() -> None:
    result = runner.invoke(app, ["formats"])
    output = _without_table_borders(result.output)

    assert result.exit_code == 0
    assert "Objects" in output
    assert ".csv CSV csv yes yes -" in output
    assert ".xlsx Excel Workbook excel yes yes sheet" in output
    assert ".rds RDS r yes yes -" in output
    assert ".rdata RData r yes yes r_object" in output


@pytest.mark.parametrize("extension", sorted(list_formats()))
def test_target_validation_matches_registered_write_capability(extension: str) -> None:
    issues = validate_target_compatibility(
        Dataset(pd.DataFrame({"value": [1]})),
        extension,
    )
    rejected = any(item.code == "target_not_writable" for item in issues)

    assert rejected is (not get_format_capabilities(extension).can_write)


def _write_csv(path: Path) -> Path:
    path.write_text("id,name\n1,Ada\n2,Linus\n", encoding="utf-8")
    return path


def _without_table_borders(output: str) -> str:
    border_characters = "|│─┌┐└┘├┤┬┴┼╭╮╰╯"
    translation = str.maketrans({character: " " for character in border_characters})
    return "\n".join(
        " ".join(
            line.translate(translation).split()
        )
        for line in output.splitlines()
    )
