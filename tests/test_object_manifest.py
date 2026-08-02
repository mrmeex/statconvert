from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.batch import BatchError, batch_plan_to_rows, build_batch_plan
from statconvert.cli import app
from statconvert.object_manifest import read_object_manifest


runner = CliRunner()


def _write_manifest(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_csv(path: Path, values: list[int] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": values or [1, 2]}).to_csv(path, index=False)
    return path


def _write_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"selected": [10, 20]}).to_excel(
            writer, sheet_name="Data", index=False
        )
        pd.DataFrame({"other": [99]}).to_excel(
            writer, sheet_name="Responses", index=False
        )
    return path


def _batch(
    input_dir: Path,
    output_dir: Path,
    manifest: Path,
    *options: str,
):
    return runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--object-manifest",
            str(manifest),
            "--no-progress",
            *options,
        ],
    )


def test_minimal_manifest_parses_and_defaults_include_true(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_name\njan.xlsx,Data,jan\n",
    )

    row = read_object_manifest(manifest).rows[0]

    assert row.row_number == 2
    assert row.include is True
    assert row.input_file == "jan.xlsx"
    assert row.input_object == "Data"
    assert row.output_name == "jan"
    assert row.object_supported is None


def test_full_discovery_manifest_parses(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "include,input_file,input_relative_path,input_object,output_name,"
        "file_supported,object_supported,message\n"
        "True,book.xlsx,book.xlsx,Data,book__Data,True,True,\n",
    )

    row = read_object_manifest(manifest).rows[0]

    assert row.include is True
    assert row.file_supported is True
    assert row.object_supported is True
    assert row.raw["input_relative_path"] == "book.xlsx"


@pytest.mark.parametrize("value", ["true", "TRUE", "yes", "1", "y", " Y "])
def test_manifest_true_include_values(value: str, tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        f"input_file,include\ndata.csv,{value}\n",
    )

    assert read_object_manifest(manifest).rows[0].include is True


@pytest.mark.parametrize("value", ["false", "FALSE", "no", "0", "n", ""])
def test_manifest_false_include_values_skip(value: str, tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        f"input_file,include\nmissing.csv,{value}\n",
    )

    parsed = read_object_manifest(manifest)

    assert parsed.rows[0].include is False
    assert parsed.included_rows == []


def test_manifest_missing_required_column_fails(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "objects.csv", "input_object\nData\n")

    with pytest.raises(BatchError, match="missing required column: input_file"):
        read_object_manifest(manifest)


def test_manifest_file_must_exist(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    with pytest.raises(BatchError, match="Object manifest file does not exist"):
        read_object_manifest(missing)


def test_manifest_invalid_include_reports_csv_row_number(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv", "input_file,include\ndata.csv,maybe\n"
    )

    with pytest.raises(BatchError, match="row 2.*invalid include value: maybe"):
        read_object_manifest(manifest)


def test_included_blank_input_fails_but_skipped_blank_does_not(tmp_path: Path) -> None:
    included = _write_manifest(
        tmp_path / "included.csv", "input_file,include\n,true\n"
    )
    skipped = _write_manifest(
        tmp_path / "skipped.csv", "input_file,include\n,false\n"
    )

    with pytest.raises(BatchError, match="row 2.*input_file is blank"):
        read_object_manifest(included)
    assert read_object_manifest(skipped).rows[0].include is False


@pytest.mark.parametrize("field", ["object_supported", "file_supported"])
def test_included_unsupported_row_fails_early(field: str, tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        f"input_file,{field},message\nmissing.dat,false,Not supported here\n",
    )

    with pytest.raises(BatchError, match=rf"row 2.*{field} is false.*Not supported"):
        read_object_manifest(manifest)


@pytest.mark.parametrize("output_name", ["sub/name", r"sub\name", "bad:name", ".."])
def test_unsafe_output_name_fails_validation(
    output_name: str, tmp_path: Path
) -> None:
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        f"input_file,output_name\ndata.csv,{output_name}\n",
    )

    with pytest.raises(BatchError, match="row 2.*unsafe output_name"):
        read_object_manifest(manifest)


def test_manifest_plan_resolves_paths_and_preserves_structure(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    source = _write_csv(input_dir / "site_a" / "jan.csv")
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "input_file,output_name\nsite_a/jan.csv,renamed\n",
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        object_manifest=manifest,
    )

    assert plan.items[0].input_file == source
    assert plan.items[0].relative_path == Path("site_a/jan.csv")
    assert plan.items[0].output_file == tmp_path / "output/site_a/renamed.json"
    assert plan.items[0].output_name == "renamed"
    report_row = batch_plan_to_rows(plan)[0]
    assert report_row["input_object"] == ""
    assert report_row["output_name"] == "renamed"


def test_included_missing_input_fails_during_planning(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    manifest = _write_manifest(tmp_path / "objects.csv", "input_file\nmissing.csv\n")

    with pytest.raises(BatchError, match="row 2 input file does not exist"):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            object_manifest=manifest,
        )


def test_manifest_flatten_ignores_relative_parent(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "site_a" / "jan.csv")
    manifest = _write_manifest(
        tmp_path / "objects.csv", "input_file\nsite_a/jan.csv\n"
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        preserve_structure=False,
        object_manifest=manifest,
    )

    assert plan.items[0].output_file == tmp_path / "output/jan.json"


def test_absolute_manifest_input_outside_root_uses_no_relative_parent(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = _write_csv(tmp_path / "outside" / "data.csv")
    manifest = _write_manifest(
        tmp_path / "objects.csv", f"input_file\n{outside}\n"
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        object_manifest=manifest,
    )

    assert plan.items[0].relative_path == Path("data.csv")
    assert plan.items[0].output_file == tmp_path / "output/data.json"


def test_blank_output_name_uses_object_aware_fallback(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_name\nbook.xlsx,Data,\n",
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        object_manifest=manifest,
    )

    assert plan.items[0].output_name == "book__Data"
    assert plan.items[0].output_file == tmp_path / "output/book__Data.csv"


def test_duplicate_planned_output_paths_fail_planning(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    _write_csv(input_dir / "two.csv")
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "input_file,output_name\none.csv,same\ntwo.csv,same\n",
    )

    with pytest.raises(BatchError, match="Duplicate planned output path.*same.csv"):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            object_manifest=manifest,
        )


def test_batch_manifest_processes_only_included_rows(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv", [1])
    _write_csv(input_dir / "two.csv", [2])
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        "input_file,include,output_name\none.csv,true,chosen\ntwo.csv,false,ignored\n",
    )
    output_dir = tmp_path / "output"

    result = _batch(input_dir, output_dir, manifest, "--create-dirs")

    assert result.exit_code == 0, result.output
    assert (output_dir / "chosen.csv").exists()
    assert not (output_dir / "ignored.csv").exists()


@pytest.mark.parametrize(("selector", "column"), [("Data", "selected"), ("0", "selected")])
def test_batch_manifest_selects_named_or_numeric_workbook_object(
    selector: str,
    column: str,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    manifest = _write_manifest(
        tmp_path / "objects.csv",
        f"input_file,input_object,output_name\nbook.xlsx,{selector},chosen\n",
    )
    output_dir = tmp_path / "output"

    result = _batch(input_dir, output_dir, manifest, "--create-dirs")

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output_dir / "chosen.csv").columns.tolist() == [column]


def test_blank_object_works_for_csv_and_fails_for_multi_sheet_workbook(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    _write_workbook(input_dir / "book.xlsx")
    csv_manifest = _write_manifest(
        tmp_path / "csv-manifest.csv", "input_file\ndata.csv\n"
    )
    workbook_manifest = _write_manifest(
        tmp_path / "book-manifest.csv", "input_file\nbook.xlsx\n"
    )

    csv_result = _batch(
        input_dir, tmp_path / "csv-output", csv_manifest, "--create-dirs"
    )
    workbook_result = _batch(
        input_dir,
        tmp_path / "book-output",
        workbook_manifest,
        "--create-dirs",
        "--json",
    )

    assert csv_result.exit_code == 0
    assert workbook_result.exit_code == 1
    assert "multiple sheets" in json.loads(workbook_result.stdout)["items"][0]["error"]


def test_object_and_object_manifest_are_mutually_exclusive(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    manifest = _write_manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")

    result = _batch(input_dir, tmp_path / "output", manifest, "--object", "Data")

    assert result.exit_code == 1
    assert "Use either --object or --object-manifest, not both" in result.output
    assert "Traceback" not in result.output


def test_manifest_dry_run_plans_without_reading_or_creating_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    manifest = _write_manifest(
        tmp_path / "objects.csv", "input_file,output_name\ndata.csv,planned\n"
    )
    output_dir = tmp_path / "missing-output"

    monkeypatch.setattr(
        "statconvert.batch.execution._read_file",
        lambda *args, **kwargs: pytest.fail("manifest dry-run read a dataset"),
    )

    result = _batch(
        input_dir,
        output_dir,
        manifest,
        "--dry-run",
        "--create-dirs",
        "--json",
    )

    assert result.exit_code == 0, result.output
    assert not output_dir.exists()
    payload = json.loads(result.stdout)
    assert payload["items"][0]["output_file"].endswith("planned.csv")
    assert payload["items"][0]["input_object"] is None


def test_manifest_output_root_and_existing_output_safety(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv", [7])
    manifest = _write_manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")
    output_dir = tmp_path / "output"

    missing_root = _batch(input_dir, output_dir, manifest)
    created = _batch(input_dir, output_dir, manifest, "--create-dirs")
    original = (output_dir / "data.csv").read_bytes()
    blocked = _batch(input_dir, output_dir, manifest)
    unchanged = (output_dir / "data.csv").read_bytes() == original
    overwritten = _batch(input_dir, output_dir, manifest, "--overwrite")

    assert missing_root.exit_code == 1 and "--create-dirs" in missing_root.output
    assert created.exit_code == 0
    assert blocked.exit_code == 1 and "--overwrite" in blocked.output
    assert unchanged
    assert overwritten.exit_code == 0


def test_discovery_csv_can_drive_manifest_batch_end_to_end(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    _write_csv(input_dir / "data.csv", [5])
    (input_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    manifest = tmp_path / "objects.csv"
    discovery = runner.invoke(
        app,
        [
            "objects",
            str(input_dir),
            "--include-unsupported",
            "--output",
            str(manifest),
        ],
    )
    assert discovery.exit_code == 0, discovery.output

    with manifest.open(encoding="utf-8", newline="") as manifest_file:
        rows = list(csv.DictReader(manifest_file))
        fieldnames = list(rows[0])
    for row in rows:
        include = row["input_file"] == "data.csv" or row["object_name"] == "Data"
        row["include"] = "true" if include else "false"
        if row["input_file"] == "data.csv":
            row["output_name"] = "csv-result"
        elif row["object_name"] == "Data":
            row["output_name"] = "sheet-result"
    with manifest.open("w", encoding="utf-8", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    output_dir = tmp_path / "output"
    result = _batch(input_dir, output_dir, manifest, "--create-dirs")

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in output_dir.glob("*.csv")) == [
        "csv-result.csv",
        "sheet-result.csv",
    ]
    assert pd.read_csv(output_dir / "sheet-result.csv").columns.tolist() == [
        "selected"
    ]
