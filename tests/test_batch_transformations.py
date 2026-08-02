from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.batch import build_batch_plan, execute_batch_plan
from statconvert.cli import app
from statconvert.inspection import ValidationIssue
from statconvert.transformations.cli_parsing import build_pipeline_from_cli_options


runner = CliRunner()


def _write_csv(path: Path, data: dict[str, list[object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _write_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame(
            {"id": [1, 2], "name": ["Ada", "Lin"], "temp": [9, 8]}
        ).to_excel(writer, sheet_name="Data", index=False)
        pd.DataFrame(
            {"id": [3], "name": ["Lookup"], "temp": [7]}
        ).to_excel(writer, sheet_name="Lookup", index=False)
    return path


def _batch(input_path: Path, output_path: Path, *options: str):
    return runner.invoke(
        app,
        [
            "batch",
            str(input_path),
            str(output_path),
            "--to",
            "csv",
            "--create-dirs",
            "--no-progress",
            *options,
        ],
    )


def test_batch_help_exposes_transform_pipeline_options() -> None:
    result = runner.invoke(app, ["batch", "--help"])

    assert result.exit_code == 0
    for option in (
        "--transform",
        "--select",
        "--drop",
        "--rename",
        "--type",
        "--filter",
        "--recode",
    ):
        assert option in result.output


def test_batch_transform_requires_an_operation(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/one.csv", {"id": [1]})

    result = _batch(source.parent, tmp_path / "output", "--transform")

    assert result.exit_code == 1
    assert "--transform requires at least one transformation option" in result.output
    assert not (tmp_path / "output").exists()


def test_batch_transform_options_require_flag(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/one.csv", {"id": [1]})

    result = _batch(source.parent, tmp_path / "output", "--select", "id")

    assert result.exit_code == 1
    assert "Transformation options require --transform" in result.output
    assert not (tmp_path / "output").exists()


def test_batch_transform_modifier_options_also_require_flag(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/one.csv", {"id": [1]})

    result = _batch(
        source.parent,
        tmp_path / "output",
        "--type-errors",
        "coerce",
    )

    assert result.exit_code == 1
    assert "Transformation options require --transform" in result.output


def test_batch_transform_applies_existing_pipeline_to_every_item(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    for name, offset in (("one", 0), ("two", 10)):
        _write_csv(
            input_dir / f"{name}.csv",
            {
                "id": [1 + offset, 2 + offset],
                "name": ["A", "B"],
                "temp": ["1", "2"],
                "status": ["A", "I"],
            },
        )

    result = _batch(
        input_dir,
        tmp_path / "output",
        "--transform",
        "--drop",
        "temp",
        "--rename",
        "name=customer_name",
        "--type",
        "id=string",
        "--filter",
        "status,eq,A",
        "--recode",
        "status:A=Active",
    )

    assert result.exit_code == 0, result.output
    for name, expected_id in (("one", "1"), ("two", "11")):
        output = pd.read_csv(tmp_path / "output" / f"{name}.csv", dtype=str)
        assert output.to_dict(orient="list") == {
            "id": [expected_id],
            "customer_name": ["A"],
            "status": ["Active"],
        }


def test_batch_transform_selects_one_object_before_transforming(tmp_path: Path) -> None:
    workbook = _write_workbook(tmp_path / "input/book.xlsx")

    result = _batch(
        workbook.parent,
        tmp_path / "output",
        "--object",
        "Data",
        "--transform",
        "--select",
        "id",
        "--select",
        "name",
    )

    assert result.exit_code == 0, result.output
    assert pd.read_csv(tmp_path / "output/book.csv").columns.tolist() == ["id", "name"]


def test_batch_object_manifest_transform_preserves_output_name(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")
    manifest = tmp_path / "objects.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["input_file", "input_object", "output_name"],
        )
        writer.writeheader()
        writer.writerow(
            {"input_file": "book.xlsx", "input_object": "Data", "output_name": "chosen"}
        )

    result = _batch(
        input_dir,
        tmp_path / "output",
        "--object-manifest",
        str(manifest),
        "--transform",
        "--drop",
        "temp",
    )

    assert result.exit_code == 0, result.output
    output = pd.read_csv(tmp_path / "output/chosen.csv")
    assert output.columns.tolist() == ["id", "name"]


def test_batch_all_objects_transform_applies_to_each_sheet(tmp_path: Path) -> None:
    workbook = _write_workbook(tmp_path / "input/book.xlsx")

    result = _batch(
        workbook.parent,
        tmp_path / "output",
        "--all-objects",
        "--transform",
        "--drop",
        "temp",
    )

    assert result.exit_code == 0, result.output
    for output_name in ("book__Data.csv", "book__Lookup.csv"):
        assert pd.read_csv(tmp_path / "output" / output_name).columns.tolist() == [
            "id",
            "name",
        ]


def test_batch_transform_failure_continues_and_is_reported(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "bad.csv", {"other": [1]})
    _write_csv(input_dir / "good.csv", {"id": [2]})
    report = tmp_path / "result.csv"

    result = _batch(
        input_dir,
        tmp_path / "output",
        "--transform",
        "--select",
        "id",
        "--report",
        str(report),
    )

    assert result.exit_code == 1
    assert not (tmp_path / "output/bad.csv").exists()
    assert (tmp_path / "output/good.csv").exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Transformation 'select-columns' failed" in report_text
    assert "bad.csv" in report_text


def test_batch_transform_fail_fast_skips_later_items(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "a_bad.csv", {"other": [1]})
    _write_csv(input_dir / "z_good.csv", {"id": [2]})

    result = _batch(
        input_dir,
        tmp_path / "output",
        "--transform",
        "--select",
        "id",
        "--fail-fast",
    )

    assert result.exit_code == 1
    assert "Not processed due to fail-fast" in result.output
    assert not (tmp_path / "output/z_good.csv").exists()


def test_batch_transform_dry_run_is_planning_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_csv(tmp_path / "input/one.csv", {"id": [1]})
    output_dir = tmp_path / "missing/output"

    monkeypatch.setattr(
        "statconvert.transformations.pipeline.TransformationPipeline.apply",
        lambda *args, **kwargs: pytest.fail("dry-run applied transformations"),
    )

    result = _batch(
        source.parent,
        output_dir,
        "--transform",
        "--select",
        "missing",
        "--dry-run",
    )

    assert result.exit_code == 0, result.output
    assert "Batch Plan Summary" in result.output
    assert not output_dir.exists()


def test_batch_validation_receives_transformed_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv", {"id": [1], "temp": [2]})
    plan = build_batch_plan(input_dir, tmp_path / "output", "csv")
    seen_columns: list[list[str]] = []

    def validator(dataset, target_format=None):
        seen_columns.append(dataset.columns)
        return [
            ValidationIssue(
                "warning",
                "transformed",
                "checked transformed dataset",
            )
        ]

    monkeypatch.setattr("statconvert.batch.execution.validate_dataset", validator)
    pipeline = build_pipeline_from_cli_options(drop_columns=["temp"])

    result = execute_batch_plan(plan, validate=True, transform_pipeline=pipeline)

    assert result.success_count == 1
    assert seen_columns == [["id"]]
