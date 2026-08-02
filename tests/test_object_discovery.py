from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.backends.r_backend import RBackend
from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.object_discovery import DISCOVERY_COLUMNS


runner = CliRunner()


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": [1, 2]}).to_csv(path, index=False)
    return path


def _write_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"value": [1]}).to_excel(
            writer, sheet_name="Data", index=False
        )
        pd.DataFrame({"code": ["A"]}).to_excel(
            writer, sheet_name="Lookup Codes", index=False
        )
    return path


def _json_discovery(input_dir: Path, *options: str) -> dict:
    result = runner.invoke(
        app,
        ["objects", str(input_dir), *options, "--json"],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_folder_discovery_non_recursive_finds_direct_files_only(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "direct.csv")
    _write_csv(input_dir / "nested" / "nested.csv")

    payload = _json_discovery(input_dir)

    assert [item["input_file"] for item in payload["files"]] == ["direct.csv"]


def test_folder_discovery_recursive_finds_nested_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "direct.csv")
    _write_csv(input_dir / "nested" / "nested.csv")

    payload = _json_discovery(input_dir, "--recursive")

    assert [item["input_file"] for item in payload["files"]] == [
        "direct.csv",
        "nested/nested.csv",
    ]
    assert payload["recursive"] is True


def test_folder_discovery_applies_include_and_exclude_patterns(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "keep.csv")
    _write_csv(input_dir / "skip.csv")
    _write_workbook(input_dir / "book.xlsx")

    payload = _json_discovery(
        input_dir,
        "--pattern",
        "*.csv",
        "--exclude-pattern",
        "skip*",
    )

    assert [item["input_file"] for item in payload["files"]] == ["keep.csv"]


def test_single_dataset_file_has_one_manifest_ready_row(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "survey.csv")

    payload = _json_discovery(input_dir)
    item = payload["files"][0]
    row = item["objects"][0]

    assert item["file_supported"] is True
    assert row["include"] is True
    assert row["input_object"] is None
    assert row["output_name"] == "survey"
    assert row["object_kind"] == "dataset"
    assert row["object_supported"] is True


def test_multi_sheet_workbook_has_one_row_per_sheet(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "workbook.xlsx")

    payload = _json_discovery(input_dir)
    rows = payload["files"][0]["objects"]

    assert [(row["object_index"], row["object_name"]) for row in rows] == [
        (0, "Data"),
        (1, "Lookup Codes"),
    ]
    assert [row["input_object"] for row in rows] == ["Data", "Lookup Codes"]
    assert [row["output_name"] for row in rows] == [
        "workbook__Data",
        "workbook__Lookup Codes",
    ]


def test_rdata_discovery_uses_backend_object_metadata(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    workspace = input_dir / "patients.rdata"
    RBackend().write(
        Dataset(dataframe=pd.DataFrame({"patient_id": [1, 2]})),
        workspace,
        object_name="patients",
    )

    row = _json_discovery(input_dir)["files"][0]["objects"][0]

    assert row["input_object"] == "patients"
    assert row["object_kind"] == "r_object"
    assert row["rows"] == 2
    assert row["columns"] == 1


def test_unsupported_files_are_hidden_by_default_and_optional(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    (input_dir / "notes.txt").write_text("notes", encoding="utf-8")

    hidden = _json_discovery(input_dir)
    included = _json_discovery(input_dir, "--include-unsupported")

    assert [item["input_file"] for item in hidden["files"]] == ["data.csv"]
    assert [item["input_file"] for item in included["files"]] == [
        "data.csv",
        "notes.txt",
    ]
    unsupported = included["files"][1]
    assert unsupported["file_supported"] is False
    assert unsupported["objects"][0]["include"] is False
    assert "Unsupported input file format" in unsupported["objects"][0]["message"]


def test_all_unsupported_folder_requires_include_unsupported(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("notes", encoding="utf-8")

    hidden = runner.invoke(app, ["objects", str(input_dir)])
    included = runner.invoke(
        app,
        ["objects", str(input_dir), "--include-unsupported", "--json"],
    )

    assert hidden.exit_code == 1
    assert "No supported input files were discovered" in hidden.output
    assert "Traceback" not in hidden.output
    assert included.exit_code == 0


def test_csv_report_has_stable_manifest_ready_columns(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    _write_workbook(input_dir / "workbook.xlsx")
    output = tmp_path / "objects.csv"

    result = runner.invoke(
        app,
        ["objects", str(input_dir), "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    with output.open(encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert tuple(rows[0]) == DISCOVERY_COLUMNS
    assert {"include", "input_file", "input_object", "output_name"} <= rows[0].keys()
    assert len(rows) == 3


def test_json_report_is_written_and_valid(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    output = tmp_path / "objects.json"

    result = runner.invoke(
        app,
        ["objects", str(input_dir), "--json", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["files"][0]["objects"][0]["output_name"] == "data"


def test_report_output_requires_overwrite(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    output = tmp_path / "objects.csv"
    output.write_text("original", encoding="utf-8")

    blocked = runner.invoke(
        app, ["objects", str(input_dir), "--output", str(output)]
    )
    unchanged_after_block = output.read_text(encoding="utf-8") == "original"
    allowed = runner.invoke(
        app,
        ["objects", str(input_dir), "--output", str(output), "--overwrite"],
    )

    assert blocked.exit_code == 1
    assert "--overwrite" in blocked.output
    assert unchanged_after_block
    assert allowed.exit_code == 0
    assert output.read_text(encoding="utf-8") != "original"


def test_report_output_requires_create_dirs(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    output = tmp_path / "reports" / "objects.csv"

    blocked = runner.invoke(
        app, ["objects", str(input_dir), "--output", str(output)]
    )
    absent_after_block = not output.exists()
    allowed = runner.invoke(
        app,
        ["objects", str(input_dir), "--output", str(output), "--create-dirs"],
    )

    assert blocked.exit_code == 1
    assert "--create-dirs" in blocked.output
    assert absent_after_block
    assert allowed.exit_code == 0
    assert output.exists()


def test_discovery_does_not_write_converted_files_or_directories(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    source = _write_csv(input_dir / "data.csv")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    result = runner.invoke(app, ["objects", str(input_dir), "--recursive"])

    assert result.exit_code == 0
    assert source.exists()
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before


def test_objects_help_lists_folder_report_options() -> None:
    result = runner.invoke(app, ["objects", "--help"])

    assert result.exit_code == 0
    for option in (
        "--recursive",
        "--pattern",
        "--exclude-pattern",
        "--include-unsupported",
        "--output",
        "--json",
        "--overwrite",
        "--create-dirs",
    ):
        assert option in result.output
