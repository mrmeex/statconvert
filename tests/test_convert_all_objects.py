from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.backends.objects import DatasetObjectInfo, NamedDataset
from statconvert.cli import app
from statconvert.converter import transform_all_objects
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.inspection import ValidationFailedError, ValidationIssue
from statconvert.registry import (
    format_supports_multi_object_write,
    list_dataset_objects,
    read_dataset,
    write_dataset_objects,
)


runner = CliRunner()


def _write_workbook(path: Path) -> Path:
    with pd.ExcelWriter(path, engine="xlsxwriter") as workbook:
        pd.DataFrame({"value": [1, 2]}).to_excel(
            workbook,
            sheet_name="Data",
            index=False,
        )
        pd.DataFrame({"code": ["a", "b"]}).to_excel(
            workbook,
            sheet_name="Lookup",
            index=False,
        )
    return path


def test_convert_help_exposes_all_objects_only_on_convert() -> None:
    convert_help = runner.invoke(app, ["convert", "--help"])
    transform_help = runner.invoke(app, ["transform", "--help"])

    assert convert_help.exit_code == 0
    assert "--all-objects" in convert_help.output
    assert transform_help.exit_code == 0
    assert "--all-objects" not in transform_help.output


def test_convert_object_conflicts_with_all_objects() -> None:
    result = runner.invoke(
        app,
        [
            "convert",
            "input.xlsx",
            "output.xlsx",
            "--object",
            "Data",
            "--all-objects",
        ],
    )

    assert result.exit_code == 1
    assert "Use either --object or --all-objects, not both." in result.output
    assert "Traceback" not in result.output


def test_single_dataset_input_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    source.write_text("value\n1\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["convert", str(source), str(tmp_path / "output.xlsx"), "--all-objects"],
    )

    assert result.exit_code == 1
    assert "requires a multi-object input format" in result.output
    assert "omit --all-objects" in result.output


def test_single_object_output_format_fails_clearly(tmp_path: Path) -> None:
    source = _write_workbook(tmp_path / "input.xlsx")

    result = runner.invoke(
        app,
        ["convert", str(source), str(tmp_path / "output.csv"), "--all-objects"],
    )

    assert result.exit_code == 1
    assert "requires a multi-object output format" in result.output
    assert "batch --all-objects" in result.output


def test_xls_is_not_a_multi_object_output_target(tmp_path: Path) -> None:
    source = _write_workbook(tmp_path / "input.xlsx")

    result = runner.invoke(
        app,
        ["convert", str(source), str(tmp_path / "output.xls"), "--all-objects"],
    )

    assert result.exit_code == 1
    assert "requires a multi-object output format" in result.output


def test_xlsx_to_xlsx_preserves_sheet_names_order_and_data(
    tmp_path: Path,
) -> None:
    source = _write_workbook(tmp_path / "input.xlsx")
    output = tmp_path / "output.xlsx"

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )

    assert result.exit_code == 0, result.output
    assert [item.name for item in list_dataset_objects(output)] == [
        "Data",
        "Lookup",
    ]
    assert read_dataset(output, object_selector="Data").dataframe.to_dict(
        orient="list"
    ) == {"value": [1, 2]}
    assert read_dataset(output, object_selector="Lookup").dataframe.to_dict(
        orient="list"
    ) == {"code": ["a", "b"]}
    assert "Objects converted: 2" in result.output


def test_xlsx_to_ods_preserves_sheets_and_data(tmp_path: Path) -> None:
    source = _write_workbook(tmp_path / "input.xlsx")
    output = tmp_path / "output.ods"

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )

    assert result.exit_code == 0, result.output
    assert [item.name for item in list_dataset_objects(output)] == [
        "Data",
        "Lookup",
    ]
    assert read_dataset(output, object_selector="Data").dataframe["value"].tolist() == [
        1,
        2,
    ]


def test_registry_multi_object_writer_api_writes_xlsx(tmp_path: Path) -> None:
    output = tmp_path / "api.xlsx"
    objects = [
        NamedDataset("First", Dataset(pd.DataFrame({"x": [1]}))),
        NamedDataset("Second", Dataset(pd.DataFrame({"y": [2]}))),
    ]

    write_dataset_objects(objects, output)

    assert [item.name for item in list_dataset_objects(output)] == [
        "First",
        "Second",
    ]
    assert format_supports_multi_object_write(".xlsx") is True
    assert format_supports_multi_object_write(".ods") is True
    assert format_supports_multi_object_write(".xls") is False
    assert format_supports_multi_object_write(".rdata") is False


def test_output_safety_applies_before_object_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    output.write_bytes(b"existing")

    def unexpected_listing(path: Path) -> list[DatasetObjectInfo]:
        raise AssertionError(f"unexpected listing: {path}")

    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        unexpected_listing,
    )

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )

    assert result.exit_code == 1
    assert "--overwrite" in result.output


def test_missing_output_parent_fails_before_object_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "missing" / "output.xlsx"

    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda *args, **kwargs: pytest.fail(
            "output safety failure listed input objects"
        ),
    )

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )

    assert result.exit_code == 1
    assert "--create-dirs" in result.output
    assert not output.parent.exists()


def test_overwrite_and_create_dirs_apply_to_multi_object_convert(
    tmp_path: Path,
) -> None:
    source = _write_workbook(tmp_path / "input.xlsx")
    output = tmp_path / "missing" / "output.xlsx"

    blocked_parent = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )
    created = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(output),
            "--all-objects",
            "--create-dirs",
        ],
    )
    blocked_existing = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )
    overwritten = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects", "--overwrite"],
    )

    assert blocked_parent.exit_code == 1
    assert "--create-dirs" in blocked_parent.output
    assert created.exit_code == 0, created.output
    assert blocked_existing.exit_code == 1
    assert "--overwrite" in blocked_existing.output
    assert overwritten.exit_code == 0, overwritten.output


@pytest.mark.parametrize(
    ("objects", "message"),
    [
        (
            [
                DatasetObjectInfo("Data", index=0),
                DatasetObjectInfo("data", index=1),
            ],
            "Duplicate output object name: data",
        ),
        (
            [DatasetObjectInfo("Very/Bad:Sheet", index=0)],
            "Object name is not valid for xlsx output",
        ),
    ],
)
def test_output_object_names_fail_before_dataset_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    objects: list[DatasetObjectInfo],
    message: str,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")

    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: objects,
    )

    def unexpected_read(*args, **kwargs):
        raise AssertionError("dataset read should not occur")

    monkeypatch.setattr("statconvert.converter.read_dataset", unexpected_read)

    with pytest.raises(ConversionError, match=message):
        transform_all_objects(str(source), str(tmp_path / "output.xlsx"))


def test_unsupported_objects_are_skipped_and_not_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    objects = [
        DatasetObjectInfo("patients", index=0),
        DatasetObjectInfo(
            "model",
            index=1,
            kind="r_object",
            supported=False,
            message="Unsupported R object",
        ),
    ]
    selectors: list[str | None] = []
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: objects,
    )

    def fake_read(path, *, object_selector=None, **kwargs):
        selectors.append(object_selector)
        return Dataset(pd.DataFrame({"id": [1, 2]}))

    monkeypatch.setattr("statconvert.converter.read_dataset", fake_read)

    result = transform_all_objects(str(source), str(output))

    assert selectors == ["patients"]
    assert [item.name for item in result.objects] == ["patients"]
    assert [item.name for item in result.skipped_objects] == ["model"]
    assert [item.name for item in list_dataset_objects(output)] == ["patients"]


def test_cli_reports_skipped_unsupported_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo("patients", index=0),
            DatasetObjectInfo(
                "model",
                index=1,
                supported=False,
                message="Unsupported R object",
            ),
        ],
    )
    monkeypatch.setattr(
        "statconvert.converter.read_dataset",
        lambda *args, **kwargs: Dataset(pd.DataFrame({"id": [1]})),
    )

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--all-objects"],
    )

    assert result.exit_code == 0, result.output
    assert "Skipped unsupported object: model - Unsupported R object" in result.output


def test_zero_supported_objects_fails_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo(
                "model",
                index=0,
                supported=False,
                message="Unsupported R object",
            )
        ],
    )

    with pytest.raises(ConversionError, match="No supported dataset objects"):
        transform_all_objects(str(source), str(tmp_path / "output.xlsx"))


def test_blank_object_name_uses_index_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: [DatasetObjectInfo("", index=3)],
    )
    monkeypatch.setattr(
        "statconvert.converter.read_dataset",
        lambda *args, **kwargs: Dataset(pd.DataFrame({"x": [1]})),
    )

    transform_all_objects(str(source), str(output))

    assert [item.name for item in list_dataset_objects(output)] == ["object_3"]


def test_validation_runs_once_per_selected_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    objects = [
        DatasetObjectInfo("one", index=0),
        DatasetObjectInfo("two", index=1),
    ]
    validated: list[int] = []
    reported: list[str] = []
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: objects,
    )
    monkeypatch.setattr(
        "statconvert.converter.read_dataset",
        lambda *args, **kwargs: Dataset(pd.DataFrame({"x": [1]})),
    )

    def fake_validate(dataset, *, target_format, strict):
        validated.append(dataset.rows)
        return []

    monkeypatch.setattr("statconvert.converter.validate_for_write", fake_validate)

    transform_all_objects(
        str(source),
        str(tmp_path / "output.xlsx"),
        validate=True,
        on_validation=lambda name, issues: reported.append(name),
    )

    assert validated == [1, 1]
    assert reported == ["one", "two"]


def test_strict_validation_failure_writes_no_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: [DatasetObjectInfo("Data", index=0)],
    )
    monkeypatch.setattr(
        "statconvert.converter.read_dataset",
        lambda *args, **kwargs: Dataset(pd.DataFrame({"x": [1]})),
    )
    monkeypatch.setattr(
        "statconvert.converter.validate_for_write",
        lambda *args, **kwargs: [
            ValidationIssue(
                severity="warning",
                code="test_warning",
                message="test warning",
            )
        ],
    )

    with pytest.raises(ValidationFailedError):
        transform_all_objects(
            str(source),
            str(output),
            strict_validation=True,
        )

    assert not output.exists()


def test_object_read_failure_writes_no_partial_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.rdata"
    source.write_bytes(b"placeholder")
    output = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        "statconvert.converter.list_dataset_objects",
        lambda path: [
            DatasetObjectInfo("one", index=0),
            DatasetObjectInfo("two", index=1),
        ],
    )

    def fake_read(path, *, object_selector=None, **kwargs):
        if object_selector == "two":
            raise ConversionError("second object failed")
        return Dataset(pd.DataFrame({"x": [1]}))

    monkeypatch.setattr("statconvert.converter.read_dataset", fake_read)

    with pytest.raises(ConversionError, match="second object failed"):
        transform_all_objects(str(source), str(output))

    assert not output.exists()
