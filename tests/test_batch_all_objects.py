from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.backends.objects import DatasetObjectInfo
from statconvert.batch import (
    BATCH_STATUS_SKIPPED,
    BatchError,
    batch_plan_to_rows,
    build_batch_plan,
    execute_batch_plan,
)
from statconvert.cli import app


runner = CliRunner()


def _write_csv(path: Path, values: list[int] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": values or [1, 2]}).to_csv(path, index=False)
    return path


def _write_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"selected": [10, 20], "label": ["x", "y"]}).to_excel(
            writer, sheet_name="Data", index=False
        )
        pd.DataFrame({"code": ["A", "B"]}).to_excel(
            writer, sheet_name="Lookup Table", index=False
        )
    return path


def _batch(input_dir: Path, output_dir: Path, *options: str):
    return runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--all-objects",
            "--no-progress",
            *options,
        ],
    )


def test_all_objects_plan_expands_xlsx_and_keeps_single_dataset(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    workbook = _write_workbook(input_dir / "workbook.xlsx")

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        all_objects=True,
    )
    assert [(item.input_file.name, item.input_object) for item in plan.items] == [
        ("data.csv", None),
        ("workbook.xlsx", "Data"),
        ("workbook.xlsx", "Lookup Table"),
    ]
    assert [item.output_file for item in plan.items] == [
        tmp_path / "output/data.csv",
        tmp_path / "output/workbook__Data.csv",
        tmp_path / "output/workbook__Lookup Table.csv",
    ]
    assert plan.items[1].input_file == workbook
    assert plan.items[1].object_index == 0
    assert plan.items[1].object_name == "Data"
    assert plan.options.all_objects is True


def test_all_objects_plan_expands_controlled_rdata_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    workspace = input_dir / "workspace.rdata"
    workspace.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "statconvert.batch.planning.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo("patients", index=0, kind="r_object"),
            DatasetObjectInfo("visits", index=1, kind="r_object"),
        ],
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        all_objects=True,
    )

    assert [item.input_object for item in plan.items] == ["patients", "visits"]
    assert [item.output_name for item in plan.items] == [
        "workspace__patients",
        "workspace__visits",
    ]


def test_all_objects_recursive_preserves_structure_and_flatten_removes_it(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "site_a" / "book.xlsx")

    preserved = build_batch_plan(
        input_dir,
        tmp_path / "preserved",
        "csv",
        recursive=True,
        all_objects=True,
    )
    flattened = build_batch_plan(
        input_dir,
        tmp_path / "flat",
        "csv",
        recursive=True,
        preserve_structure=False,
        all_objects=True,
    )

    assert preserved.items[0].output_file == tmp_path / "preserved/site_a/book__Data.csv"
    assert flattened.items[0].output_file == tmp_path / "flat/book__Data.csv"


def test_all_objects_duplicate_flattened_paths_fail(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "a" / "book.xlsx")
    _write_workbook(input_dir / "b" / "book.xlsx")

    with pytest.raises(
        BatchError,
        match="(?s)Duplicate planned output path.*object manifest",
    ):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            recursive=True,
            preserve_structure=False,
            all_objects=True,
        )


def test_sanitized_object_name_collision_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    workbook = input_dir / "book.xlsx"
    workbook.parent.mkdir()
    workbook.touch()
    monkeypatch.setattr(
        "statconvert.batch.planning.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo("A:B", index=0, kind="sheet"),
            DatasetObjectInfo("A?B", index=1, kind="sheet"),
        ],
    )

    with pytest.raises(BatchError, match="Duplicate planned output path.*book__A_B.csv"):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            all_objects=True,
        )


def test_empty_object_name_falls_back_to_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    workbook = input_dir / "book.xlsx"
    workbook.parent.mkdir()
    workbook.touch()
    monkeypatch.setattr(
        "statconvert.batch.planning.list_dataset_objects",
        lambda path: [DatasetObjectInfo("", index=3, kind="sheet")],
    )

    item = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        all_objects=True,
    ).items[0]

    assert item.input_object == "3"
    assert item.output_name == "book__object_3"


def test_all_objects_conflicts_are_friendly(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    manifest = tmp_path / "objects.csv"
    manifest.write_text("input_file\ndata.csv\n", encoding="utf-8")

    object_conflict = _batch(
        input_dir,
        tmp_path / "one",
        "--object",
        "Data",
    )
    manifest_conflict = _batch(
        input_dir,
        tmp_path / "two",
        "--object-manifest",
        str(manifest),
    )

    assert object_conflict.exit_code == 1
    assert "Use either --object or --all-objects, not both" in object_conflict.output
    assert manifest_conflict.exit_code == 1
    assert (
        "Use either --object-manifest or --all-objects, not both"
        in manifest_conflict.output
    )
    assert "Traceback" not in object_conflict.output + manifest_conflict.output


def test_all_objects_converts_mixed_folder_and_sheet_contents(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv", [5])
    _write_workbook(input_dir / "workbook.xlsx")
    output_dir = tmp_path / "output"

    result = _batch(input_dir, output_dir, "--create-dirs")

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in output_dir.glob("*.csv")) == [
        "data.csv",
        "workbook__Data.csv",
        "workbook__Lookup Table.csv",
    ]
    assert pd.read_csv(output_dir / "workbook__Data.csv")["selected"].tolist() == [
        10,
        20,
    ]
    assert pd.read_csv(output_dir / "workbook__Lookup Table.csv")["code"].tolist() == [
        "A",
        "B",
    ]


def test_all_objects_output_safety_create_dirs_and_overwrite(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    output_dir = tmp_path / "output"

    missing_root = _batch(input_dir, output_dir)
    created = _batch(input_dir, output_dir, "--create-dirs")
    original = (output_dir / "book__Data.csv").read_bytes()
    blocked = _batch(input_dir, output_dir)
    unchanged = (output_dir / "book__Data.csv").read_bytes() == original
    overwritten = _batch(input_dir, output_dir, "--overwrite")

    assert missing_root.exit_code == 1 and "--create-dirs" in missing_root.output
    assert created.exit_code == 0
    assert blocked.exit_code == 1 and "--overwrite" in blocked.output
    assert unchanged
    assert overwritten.exit_code == 0


def test_all_objects_validation_and_csv_output_options(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    output_dir = tmp_path / "output"

    result = _batch(
        input_dir,
        output_dir,
        "--create-dirs",
        "--validate",
        "--output-encoding",
        "utf-8-sig",
        "--csv-delimiter",
        ";",
        "--json",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert all(item["validation_issues"] is not None for item in payload["items"])
    text = (output_dir / "book__Data.csv").read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "selected;label"
    lookup_text = (output_dir / "book__Lookup Table.csv").read_text(
        encoding="utf-8-sig"
    )
    assert ";" not in lookup_text.splitlines()[0]


def test_all_objects_unsupported_files_follow_visibility_policy(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("notes", encoding="utf-8")
    _write_csv(input_dir / "data.csv")

    included = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        all_objects=True,
    )
    hidden = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "json",
        include_unsupported=False,
        all_objects=True,
    )

    assert [(item.input_file.name, item.status) for item in included.items] == [
        ("data.csv", "pending"),
        ("notes.txt", "skipped"),
    ]
    assert [item.input_file.name for item in hidden.items] == ["data.csv"]


def test_unsupported_objects_are_skipped_and_never_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    workspace = input_dir / "workspace.rdata"
    workspace.parent.mkdir()
    workspace.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "statconvert.batch.planning.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo(
                "model",
                index=0,
                kind="unsupported",
                supported=False,
                message="Unsupported R object",
            )
        ],
    )
    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        all_objects=True,
    )
    monkeypatch.setattr(
        "statconvert.batch.execution._read_file",
        lambda *args, **kwargs: pytest.fail("unsupported object was read"),
    )

    result = execute_batch_plan(plan)

    assert result.items[0].status == BATCH_STATUS_SKIPPED
    assert result.items[0].input_object == "model"
    assert result.items[0].reason == "Unsupported R object"
    assert result.items[0].output_file is None


def test_all_objects_dry_run_expands_without_reading_or_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "statconvert.batch.execution._read_file",
        lambda *args, **kwargs: pytest.fail("dry-run read a full dataset"),
    )

    result = _batch(
        input_dir,
        output_dir,
        "--dry-run",
        "--create-dirs",
        "--json",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert [item["input_object"] for item in payload["items"]] == [
        "Data",
        "Lookup Table",
    ]
    assert not output_dir.exists()


def test_all_objects_report_contains_deterministic_expanded_rows(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "data.csv")
    _write_workbook(input_dir / "workbook.xlsx")
    output_dir = tmp_path / "output"
    report = tmp_path / "result.csv"

    result = _batch(
        input_dir,
        output_dir,
        "--create-dirs",
        "--report",
        str(report),
    )

    assert result.exit_code == 0, result.output
    with report.open(encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert [(row["input_object"], row["output_name"]) for row in rows] == [
        ("", "data"),
        ("Data", "workbook__Data"),
        ("Lookup Table", "workbook__Lookup Table"),
    ]
    assert [row["object_index"] for row in rows] == ["", "0", "1"]
    assert [row["status"] for row in rows] == ["success", "success", "success"]


def test_batch_plan_report_rows_include_object_fields(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")

    rows = batch_plan_to_rows(
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            all_objects=True,
        )
    )

    assert [(row["input_object"], row["object_name"]) for row in rows] == [
        ("Data", "Data"),
        ("Lookup Table", "Lookup Table"),
    ]


def test_all_objects_option_is_available_on_batch_and_convert_only() -> None:
    batch_help = runner.invoke(app, ["batch", "--help"])
    convert_help = runner.invoke(app, ["convert", "--help"])
    transform_help = runner.invoke(app, ["transform", "--help"])
    objects_help = runner.invoke(app, ["objects", "--help"])

    assert "--all-objects" in batch_help.output
    assert "--all-objects" in convert_help.output
    assert "--all-objects" not in transform_help.output
    assert "--all-objects" not in objects_help.output
