from __future__ import annotations

from importlib.util import find_spec
import json
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from typer.testing import CliRunner

from statconvert.backends.excel_backend import ExcelBackend
from statconvert.backends.ods_backend import ODSBackend
from statconvert.cli import app
from statconvert.exceptions import AmbiguousObjectError, ObjectNotFoundError
from statconvert.registry import list_dataset_objects, read_dataset


runner = CliRunner()
REMAINING_SINGLE_DATASET_COMMANDS = [
    "labels",
    "describe",
    "frequencies",
    "missing",
]


def _write_workbook(path: Path, *, engine: str) -> Path:
    with pd.ExcelWriter(path, engine=engine) as writer:
        pd.DataFrame({"FirstValue": [1, 2]}).to_excel(
            writer,
            sheet_name="First",
            index=False,
        )
        pd.DataFrame({"SurveyValue": [10, 20]}).to_excel(
            writer,
            sheet_name="Survey Data",
            index=False,
        )
    return path


def _write_xls(
    path: Path,
    sheets: list[tuple[str, list[str], list[list[object]]]],
) -> Path:
    pytest.importorskip(
        "xlrd",
        reason="xlrd is required to run genuine XLS read/listing tests.",
    )
    xlwt = pytest.importorskip(
        "xlwt",
        reason="xlwt is required only to generate genuine XLS test fixtures.",
    )
    workbook = xlwt.Workbook()
    for sheet_name, columns, rows in sheets:
        sheet = workbook.add_sheet(sheet_name)
        for column_index, column in enumerate(columns):
            sheet.write(0, column_index, column)
        for row_index, row in enumerate(rows, start=1):
            for column_index, value in enumerate(row):
                sheet.write(row_index, column_index, value)
    workbook.save(str(path))
    return path


@pytest.fixture
def xlsx_workbook(tmp_path: Path) -> Path:
    return _write_workbook(tmp_path / "workbook.xlsx", engine="xlsxwriter")


@pytest.fixture
def ods_workbook(tmp_path: Path) -> Path:
    return _write_workbook(tmp_path / "workbook.ods", engine="odf")


@pytest.fixture
def xls_workbook(tmp_path: Path) -> Path:
    return _write_xls(
        tmp_path / "workbook.xls",
        [
            ("RawData", ["RawValue"], [[1], [2]]),
            ("SurveyData", ["SurveyValue"], [[10], [20]]),
            ("Lookup", ["Code", "Label"], [["A", "Active"]]),
        ],
    )


@pytest.fixture
def single_sheet_xls(tmp_path: Path) -> Path:
    return _write_xls(
        tmp_path / "single.xls",
        [("OnlySheet", ["OnlyValue"], [[3], [4]])],
    )


def test_excel_lists_sheets_with_indices(xlsx_workbook: Path) -> None:
    objects = ExcelBackend().list_objects(xlsx_workbook)

    assert [(item.index, item.name, item.kind) for item in objects] == [
        (0, "First", "sheet"),
        (1, "Survey Data", "sheet"),
    ]
    assert all(item.rows is None and item.columns is None for item in objects)


def test_ods_lists_sheets_with_indices(ods_workbook: Path) -> None:
    objects = ODSBackend().list_objects(ods_workbook)

    assert [(item.index, item.name, item.kind) for item in objects] == [
        (0, "First", "sheet"),
        (1, "Survey Data", "sheet"),
    ]


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_registry_lists_workbook_objects(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    assert [item.name for item in list_dataset_objects(workbook)] == [
        "First",
        "Survey Data",
    ]


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_objects_command_lists_workbook_sheets(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    result = runner.invoke(app, ["objects", str(workbook)])

    assert result.exit_code == 0
    assert "0" in result.output
    assert "First" in result.output
    assert "1" in result.output
    assert "Survey Data" in result.output


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_objects_command_json_is_plain_and_complete(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    result = runner.invoke(app, ["objects", str(workbook), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [(item["index"], item["name"]) for item in payload] == [
        (0, "First"),
        (1, "Survey Data"),
    ]


@pytest.mark.parametrize("suffix,engine", [("xlsx", "xlsxwriter"), ("ods", "odf")])
def test_single_sheet_workbook_reads_without_selector(
    tmp_path: Path,
    suffix: str,
    engine: str,
) -> None:
    workbook = tmp_path / f"single.{suffix}"
    expected = pd.DataFrame({"OnlyValue": [3, 4]})
    expected.to_excel(
        workbook,
        sheet_name="Only Sheet",
        index=False,
        engine=engine,
    )

    result = read_dataset(workbook)

    assert_frame_equal(result.dataframe, expected)
    assert result.metadata["selected_object"] == "Only Sheet"


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_multi_sheet_workbook_never_silently_reads_first_sheet(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    with pytest.raises(
        AmbiguousObjectError,
        match=r"multiple sheets.*Use --object.*0: First.*1: Survey Data",
    ):
        read_dataset(workbook)


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
@pytest.mark.parametrize("selector", ["Survey Data", "1"])
def test_workbook_sheet_can_be_selected_by_name_or_index(
    fixture_name: str,
    selector: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    result = read_dataset(workbook, object_selector=selector)

    assert result.columns == ["SurveyValue"]
    assert result.dataframe["SurveyValue"].tolist() == [10, 20]
    assert result.metadata["selected_object"] == "Survey Data"
    assert result.metadata["sheet_index"] == 1


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_unknown_sheet_lists_available_sheets(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    with pytest.raises(
        ObjectNotFoundError,
        match=r"Sheet 'Missing'.*Available sheets: 0: First, 1: Survey Data",
    ):
        read_dataset(workbook, object_selector="Missing")


@pytest.mark.parametrize("fixture_name", ["xlsx_workbook", "ods_workbook"])
def test_out_of_range_sheet_index_lists_available_sheets(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    workbook = request.getfixturevalue(fixture_name)

    with pytest.raises(
        ObjectNotFoundError,
        match=r"Sheet index 4 is out of range.*0: First, 1: Survey Data",
    ):
        read_dataset(workbook, object_selector="4")


def test_xls_listing_reports_missing_optional_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "statconvert.backends.excel_backend.find_spec",
        lambda name: None if name == "xlrd" else find_spec(name),
    )
    workbook = tmp_path / "legacy.xls"
    workbook.write_bytes(b"not loaded because xlrd is unavailable")

    result = runner.invoke(app, ["objects", str(workbook)])

    assert result.exit_code == 1
    assert "requires the 'xlrd' dependency" in result.output


def test_xls_backend_lists_real_biff_sheets(xls_workbook: Path) -> None:
    objects = ExcelBackend().list_objects(xls_workbook)

    assert [
        (item.index, item.name, item.kind, item.supported)
        for item in objects
    ] == [
        (0, "RawData", "sheet", True),
        (1, "SurveyData", "sheet", True),
        (2, "Lookup", "sheet", True),
    ]


def test_xls_objects_command_lists_all_sheets(xls_workbook: Path) -> None:
    result = runner.invoke(app, ["objects", str(xls_workbook)])

    assert result.exit_code == 0
    assert "0" in result.output and "RawData" in result.output
    assert "1" in result.output and "SurveyData" in result.output
    assert "2" in result.output and "Lookup" in result.output


def test_xls_objects_command_json_lists_all_sheets(xls_workbook: Path) -> None:
    result = runner.invoke(app, ["objects", str(xls_workbook), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [(item["index"], item["name"]) for item in payload] == [
        (0, "RawData"),
        (1, "SurveyData"),
        (2, "Lookup"),
    ]


def test_single_sheet_xls_reads_without_selector(single_sheet_xls: Path) -> None:
    dataset = read_dataset(single_sheet_xls)

    assert dataset.columns == ["OnlyValue"]
    assert dataset.dataframe["OnlyValue"].tolist() == [3, 4]
    assert dataset.metadata["selected_object"] == "OnlySheet"


def test_multi_sheet_xls_requires_selector(xls_workbook: Path) -> None:
    with pytest.raises(
        AmbiguousObjectError,
        match=r"multiple sheets.*0: RawData.*1: SurveyData.*2: Lookup",
    ):
        read_dataset(xls_workbook)


@pytest.mark.parametrize("selector", ["SurveyData", "1"])
def test_xls_sheet_selection_by_name_or_index(
    xls_workbook: Path,
    selector: str,
) -> None:
    dataset = read_dataset(xls_workbook, object_selector=selector)

    assert dataset.columns == ["SurveyValue"]
    assert dataset.dataframe["SurveyValue"].tolist() == [10, 20]
    assert dataset.metadata["selected_object"] == "SurveyData"
    assert dataset.metadata["sheet_index"] == 1


def test_xls_unknown_sheet_lists_available_sheets(xls_workbook: Path) -> None:
    with pytest.raises(
        ObjectNotFoundError,
        match=r"Sheet 'Missing'.*0: RawData, 1: SurveyData, 2: Lookup",
    ):
        read_dataset(xls_workbook, object_selector="Missing")


def test_xls_out_of_range_index_lists_available_sheets(
    xls_workbook: Path,
) -> None:
    with pytest.raises(
        ObjectNotFoundError,
        match=r"Sheet index 4 is out of range.*0: RawData, 1: SurveyData, 2: Lookup",
    ):
        read_dataset(xls_workbook, object_selector="4")


@pytest.mark.parametrize(
    "command",
    ["peek", "info", "schema", "summary", "validate"],
)
def test_xls_inspection_commands_select_sheet(
    xls_workbook: Path,
    command: str,
) -> None:
    result = runner.invoke(
        app,
        [command, str(xls_workbook), "--object", "SurveyData"],
    )

    assert result.exit_code == 0


def test_xls_peek_without_selector_does_not_read_first_sheet(
    xls_workbook: Path,
) -> None:
    result = runner.invoke(app, ["peek", str(xls_workbook)])

    assert result.exit_code == 1
    assert "multiple sheets" in result.output
    assert "Use --object" in result.output
    assert "RawValue" not in result.output


def test_convert_reads_selected_xls_sheet(
    xls_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "selected.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(xls_workbook),
            str(output_file),
            "--object",
            "SurveyData",
        ],
    )

    assert result.exit_code == 0
    assert pd.read_csv(output_file).columns.tolist() == ["SurveyValue"]


def test_transform_reads_selected_xls_sheet(
    xls_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "selected.csv"

    result = runner.invoke(
        app,
        [
            "transform",
            str(xls_workbook),
            str(output_file),
            "--object",
            "SurveyData",
            "--select",
            "SurveyValue",
        ],
    )

    assert result.exit_code == 0
    assert pd.read_csv(output_file).columns.tolist() == ["SurveyValue"]


def test_report_reads_selected_xls_sheet(
    xls_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report",
            str(xls_workbook),
            "--object",
            "SurveyData",
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    assert "SurveyValue" in output_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "command",
    [
        ["peek"],
        ["info"],
        ["schema"],
        ["metadata"],
        ["summary"],
        ["validate"],
    ],
)
def test_inspection_commands_accept_object_selector(
    xlsx_workbook: Path,
    command: list[str],
) -> None:
    result = runner.invoke(
        app,
        [*command, str(xlsx_workbook), "--object", "Survey Data"],
    )

    assert result.exit_code == 0


def test_peek_without_selector_fails_friendly_for_multi_sheet_workbook(
    xlsx_workbook: Path,
) -> None:
    result = runner.invoke(app, ["peek", str(xlsx_workbook)])

    assert result.exit_code == 1
    assert "multiple sheets" in result.output
    assert "Use --object" in result.output
    assert "Survey Data" in result.output
    assert "Traceback" not in result.output


def test_convert_reads_selected_sheet(
    xlsx_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "selected.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(xlsx_workbook),
            str(output_file),
            "--object",
            "Survey Data",
        ],
    )

    assert result.exit_code == 0
    assert pd.read_csv(output_file).columns.tolist() == ["SurveyValue"]


def test_transform_reads_selected_sheet(
    xlsx_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "selected.csv"

    result = runner.invoke(
        app,
        [
            "transform",
            str(xlsx_workbook),
            str(output_file),
            "--object",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert pd.read_csv(output_file).columns.tolist() == ["SurveyValue"]


def test_report_reads_selected_sheet(
    xlsx_workbook: Path,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report",
            str(xlsx_workbook),
            "--object",
            "Survey Data",
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    assert "SurveyValue" in output_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_read_selected_workbook_sheet(
    xlsx_workbook: Path,
    command: str,
) -> None:
    result = runner.invoke(
        app,
        [command, str(xlsx_workbook), "--object", "Survey Data"],
    )

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_require_selector_for_multi_sheet_workbook(
    xlsx_workbook: Path,
    command: str,
) -> None:
    result = runner.invoke(app, [command, str(xlsx_workbook)])

    assert result.exit_code == 1
    assert "multiple sheets" in result.output
    assert "Use --object" in result.output
    assert "First" in result.output
    assert "Survey Data" in result.output
    assert "FirstValue" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_reject_unknown_workbook_sheet(
    xlsx_workbook: Path,
    command: str,
) -> None:
    result = runner.invoke(
        app,
        [command, str(xlsx_workbook), "--object", "Missing"],
    )

    assert result.exit_code == 1
    assert "Sheet 'Missing' was not found" in result.output
    assert "First" in result.output
    assert "Survey Data" in result.output


@pytest.mark.parametrize(
    ("command", "extra_arguments", "selected_field"),
    [
        ("describe", [], "name"),
        ("frequencies", ["--columns", "SurveyValue"], "column"),
        ("missing", [], "column"),
    ],
)
def test_remaining_workbook_json_commands_describe_selected_sheet(
    xlsx_workbook: Path,
    command: str,
    extra_arguments: list[str],
    selected_field: str,
) -> None:
    result = runner.invoke(
        app,
        [
            command,
            str(xlsx_workbook),
            "--object",
            "Survey Data",
            *extra_arguments,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert any(item[selected_field] == "SurveyValue" for item in payload)


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_read_single_sheet_workbook_without_selector(
    tmp_path: Path,
    command: str,
) -> None:
    workbook = tmp_path / "single-command.xlsx"
    pd.DataFrame({"group": ["A", "B"], "value": [1, None]}).to_excel(
        workbook,
        sheet_name="Only Sheet",
        index=False,
        engine="xlsxwriter",
    )

    result = runner.invoke(app, [command, str(workbook)])

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_reject_object_selector_for_csv(
    tmp_path: Path,
    command: str,
) -> None:
    input_file = tmp_path / "input.csv"
    pd.DataFrame({"value": [1]}).to_csv(input_file, index=False)

    result = runner.invoke(
        app,
        [command, str(input_file), "--object", "anything"],
    )

    assert result.exit_code == 1
    assert "Object selection is not supported for .csv files" in result.output


@pytest.mark.parametrize(
    "command",
    [
        "peek",
        "info",
        "schema",
        "metadata",
        "summary",
        "validate",
        "convert",
        "transform",
        "report",
        "labels",
        "describe",
        "frequencies",
        "missing",
    ],
)
def test_wired_command_help_exposes_generic_object_option(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--object" in result.output
    assert "--sheet" not in result.output
    if command in REMAINING_SINGLE_DATASET_COMMANDS:
        normalized_output = " ".join(result.output.split())
        assert "Excel sheet or RData object" in normalized_output
