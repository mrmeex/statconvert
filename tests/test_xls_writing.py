from __future__ import annotations

from datetime import date, datetime
from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from typer.testing import CliRunner

from statconvert.backends.excel_backend import ExcelBackend
from statconvert.backends.excel_constraints import (
    XLS_MAX_COLUMNS,
    XLS_MAX_DATA_ROWS,
)
from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.inspection.validation import validate_target_compatibility
from statconvert.registry import get_format_capabilities, list_dataset_objects, read_dataset


runner = CliRunner()
XLRD_AVAILABLE = find_spec("xlrd") is not None
XLWT_AVAILABLE = find_spec("xlwt") is not None
XLS_AVAILABLE = XLRD_AVAILABLE and XLWT_AVAILABLE
OLE_COMPOUND_FILE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "integer": [1, 2],
            "float": [1.5, 2.5],
            "text": ["Ada", "Linus"],
            "boolean": [True, False],
            "missing": [None, "present"],
            "date": [date(2025, 1, 2), date(2025, 2, 3)],
            "datetime": [
                datetime(2025, 1, 2, 3, 4, 5),
                datetime(2025, 2, 3, 4, 5, 6),
            ],
        }
    )


@pytest.mark.skipif(not XLS_AVAILABLE, reason="xlrd and xlwt are required")
def test_xls_writer_creates_genuine_biff_and_roundtrips(tmp_path: Path) -> None:
    output_file = tmp_path / "output.xls"
    expected = _sample_dataframe()

    ExcelBackend().write(Dataset(expected), str(output_file))

    assert output_file.exists()
    assert output_file.read_bytes().startswith(OLE_COMPOUND_FILE_SIGNATURE)
    assert not output_file.read_bytes().startswith(b"PK")
    objects = list_dataset_objects(output_file)
    assert [(item.index, item.name) for item in objects] == [(0, "Sheet1")]

    result = read_dataset(output_file).dataframe
    assert result.columns.tolist() == expected.columns.tolist()
    assert "index" not in result.columns
    assert result["integer"].tolist() == [1, 2]
    assert result["float"].tolist() == [1.5, 2.5]
    assert result["text"].tolist() == ["Ada", "Linus"]
    assert result["boolean"].tolist() == [True, False]
    assert pd.isna(result.loc[0, "missing"])
    assert result.loc[1, "missing"] == "present"
    assert result["date"].dt.date.tolist() == [date(2025, 1, 2), date(2025, 2, 3)]
    assert result["datetime"].tolist() == [
        pd.Timestamp("2025-01-02 03:04:05"),
        pd.Timestamp("2025-02-03 04:05:06"),
    ]


@pytest.mark.skipif(not XLS_AVAILABLE, reason="xlrd and xlwt are required")
@pytest.mark.parametrize("command", ["convert", "transform"])
def test_cli_writes_readable_genuine_xls(
    tmp_path: Path,
    command: str,
) -> None:
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / f"{command}.xls"
    pd.DataFrame({"id": [1, 2], "name": ["Ada", "Linus"]}).to_csv(
        input_file,
        index=False,
    )

    result = runner.invoke(app, [command, str(input_file), str(output_file)])

    assert result.exit_code == 0
    assert output_file.read_bytes().startswith(OLE_COMPOUND_FILE_SIGNATURE)
    assert_frame_equal(
        read_dataset(output_file).dataframe,
        pd.DataFrame({"id": [1, 2], "name": ["Ada", "Linus"]}),
    )


@pytest.mark.skipif(not XLS_AVAILABLE, reason="xlrd and xlwt are required")
def test_xls_backend_object_selector_sets_output_sheet_name(tmp_path: Path) -> None:
    output_file = tmp_path / "named.xls"

    ExcelBackend().write(
        Dataset(pd.DataFrame({"value": [1]})),
        str(output_file),
        object_selector="Survey Data",
    )

    assert [item.name for item in list_dataset_objects(output_file)] == ["Survey Data"]


@pytest.mark.skipif(not XLWT_AVAILABLE, reason="xlwt is required")
def test_xls_writer_rejects_data_row_limit_before_creating_file(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "too-many-rows.xls"
    dataframe = pd.DataFrame({"value": range(XLS_MAX_DATA_ROWS + 1)})

    with pytest.raises(
        ConversionError,
        match=rf"limited to {XLS_MAX_DATA_ROWS:,} data rows",
    ):
        ExcelBackend().write(Dataset(dataframe), str(output_file))

    assert not output_file.exists()


@pytest.mark.skipif(not XLWT_AVAILABLE, reason="xlwt is required")
def test_xls_writer_rejects_column_limit_before_creating_file(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "too-many-columns.xls"
    dataframe = pd.DataFrame(
        [[0] * (XLS_MAX_COLUMNS + 1)],
        columns=[f"column_{index}" for index in range(XLS_MAX_COLUMNS + 1)],
    )

    with pytest.raises(
        ConversionError,
        match=rf"limited to {XLS_MAX_COLUMNS} columns",
    ):
        ExcelBackend().write(Dataset(dataframe), str(output_file))

    assert not output_file.exists()


def test_xls_target_validation_reports_legacy_limits() -> None:
    row_issues = validate_target_compatibility(
        Dataset(pd.DataFrame({"value": range(XLS_MAX_DATA_ROWS + 1)})),
        "xls",
    )
    column_issues = validate_target_compatibility(
        Dataset(
            pd.DataFrame(
                [[0] * (XLS_MAX_COLUMNS + 1)],
                columns=[f"column_{index}" for index in range(XLS_MAX_COLUMNS + 1)],
            )
        ),
        ".xls",
    )

    if XLWT_AVAILABLE:
        assert any(issue.code == "xls_row_limit_exceeded" for issue in row_issues)
        assert any(issue.code == "xls_column_limit_exceeded" for issue in column_issues)
    else:
        assert any(issue.code == "target_not_writable" for issue in row_issues)
        assert any(issue.code == "target_not_writable" for issue in column_issues)


def test_xlsx_validation_does_not_apply_xls_limits() -> None:
    row_issues = validate_target_compatibility(
        Dataset(pd.DataFrame({"value": range(XLS_MAX_DATA_ROWS + 1)})),
        "xlsx",
    )
    column_issues = validate_target_compatibility(
        Dataset(
            pd.DataFrame(
                [[0] * (XLS_MAX_COLUMNS + 1)],
                columns=[f"column_{index}" for index in range(XLS_MAX_COLUMNS + 1)],
            )
        ),
        "xlsx",
    )

    assert all(not issue.code.startswith("xls_") for issue in row_issues)
    assert all(not issue.code.startswith("xls_") for issue in column_issues)


@pytest.mark.parametrize("extension", ["xls", "xlsx"])
@pytest.mark.parametrize(
    ("sheet_name", "message"),
    [
        ("", "cannot be empty"),
        ("x" * 32, "limited to 31 characters"),
        ("Invalid/Name", "cannot contain"),
    ],
)
def test_excel_writer_rejects_invalid_sheet_names_before_writing(
    tmp_path: Path,
    extension: str,
    sheet_name: str,
    message: str,
) -> None:
    output_file = tmp_path / f"invalid.{extension}"

    with pytest.raises(ConversionError, match=message):
        ExcelBackend().write(
            Dataset(pd.DataFrame({"value": [1]})),
            str(output_file),
            sheet_name=sheet_name,
        )

    assert not output_file.exists()


def test_missing_xlwt_fails_clearly_without_creating_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_file = tmp_path / "missing-xlwt.xls"
    monkeypatch.setattr(
        "statconvert.backends.excel_backend.find_spec",
        lambda name: None if name == "xlwt" else find_spec(name),
    )

    with pytest.raises(
        ConversionError,
        match=r"Writing \.xls requires dependency 'xlwt'",
    ):
        ExcelBackend().write(
            Dataset(pd.DataFrame({"value": [1]})),
            str(output_file),
        )

    assert not output_file.exists()


def test_convert_reports_missing_xlwt_without_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.xls"
    pd.DataFrame({"value": [1]}).to_csv(input_file, index=False)
    monkeypatch.setattr(
        "statconvert.backends.excel_backend.find_spec",
        lambda name: None if name == "xlwt" else find_spec(name),
    )

    result = runner.invoke(app, ["convert", str(input_file), str(output_file)])

    assert result.exit_code == 1
    assert "Writing .xls requires dependency 'xlwt'" in result.output
    assert not output_file.exists()


def test_xlsx_write_does_not_require_xlwt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_file = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        "statconvert.backends.excel_backend.find_spec",
        lambda name: None if name == "xlwt" else find_spec(name),
    )

    ExcelBackend().write(
        Dataset(pd.DataFrame({"value": [1]})),
        str(output_file),
    )

    assert output_file.read_bytes().startswith(b"PK")


@pytest.mark.skipif(not XLWT_AVAILABLE, reason="xlwt is required")
def test_validate_cli_accepts_xls_as_writable_target(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(input_file, index=False)

    result = runner.invoke(app, ["validate", str(input_file), "--to", "xls"])

    assert result.exit_code == 0
    assert "target_not_writable" not in result.output


def test_xls_capability_is_runtime_aware() -> None:
    capabilities = get_format_capabilities("xls")

    assert capabilities.can_read is XLRD_AVAILABLE
    assert capabilities.can_write is XLWT_AVAILABLE
    assert capabilities.is_container is True
    assert capabilities.object_kind == "sheet"
