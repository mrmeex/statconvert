from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.collection import (
    CollectionError,
    build_collection_plan,
)
from statconvert.dataset import Dataset
from statconvert.inspection import ValidationIssue
from statconvert.registry import list_dataset_objects, read_dataset


runner = CliRunner()


def _manifest(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _csv(path: Path, values: list[int] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": values or [1, 2]}).to_csv(path, index=False)
    return path


def _workbook(
    path: Path,
    *,
    data: list[int] | None = None,
    lookup: list[str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"value": data or [10, 20]}).to_excel(
            writer,
            sheet_name="Data",
            index=False,
        )
        pd.DataFrame({"code": lookup or ["x", "y"]}).to_excel(
            writer,
            sheet_name="Lookup",
            index=False,
        )
    return path


def _collect(
    manifest: Path,
    output: Path,
    *options: str,
):
    return runner.invoke(
        app,
        ["collect", str(manifest), str(output), *options],
    )


def test_collect_help_lists_manifest_container_options() -> None:
    result = runner.invoke(app, ["collect", "--help"])

    assert result.exit_code == 0
    for option in (
        "--base-dir",
        "--overwrite",
        "--create-dirs",
        "--dry-run",
        "--validate",
        "--strict-validation",
        "--input-encoding",
        "--output-encoding",
        "--csv-delimiter",
        "--csv-decimal",
    ):
        assert option in result.output


def test_collection_name_priority_and_discovery_manifest_support(
    tmp_path: Path,
) -> None:
    _csv(tmp_path / "explicit.csv")
    _csv(tmp_path / "named.csv")
    _csv(tmp_path / "fallback.csv")
    _workbook(tmp_path / "book.xlsx")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_object,output_name\n"
        "explicit.csv,,Explicit,Ignored\n"
        "named.csv,,,From_Output_Name\n"
        "book.xlsx,Data,,\n"
        "fallback.csv,,,\n",
    )

    plan = build_collection_plan(manifest, tmp_path / "combined.xlsx")

    assert [item.output_object for item in plan.items] == [
        "Explicit",
        "From_Output_Name",
        "Data",
        "fallback",
    ]


def test_include_defaults_true_and_false_rows_skip_all_validation(
    tmp_path: Path,
) -> None:
    source = _csv(tmp_path / "data.csv")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "include,input_file,object_supported,file_supported\n"
        ",missing.csv,false,false\n"
        "true,data.csv,,\n",
    )

    plan = build_collection_plan(manifest, tmp_path / "combined.xlsx")

    assert len(plan.items) == 1
    assert plan.items[0].input_file == source


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "input_file,include\ndata.csv,maybe\n",
            "row 2 has an invalid include value: maybe",
        ),
        (
            "input_object\nData\n",
            "missing required column: input_file",
        ),
        (
            "input_file,include\n,true\n",
            "row 2 is included but input_file is blank",
        ),
        (
            "input_file,object_supported,message\nmissing.rdata,false,Bad object\n",
            "object_supported is false: Bad object",
        ),
        (
            "input_file,file_supported,message\nmissing.dat,false,Bad file\n",
            "file_supported is false: Bad file",
        ),
    ],
)
def test_collection_manifest_validation_is_friendly(
    tmp_path: Path,
    text: str,
    message: str,
) -> None:
    manifest = _manifest(tmp_path / "objects.csv", text)

    result = _collect(manifest, tmp_path / "combined.xlsx")

    assert result.exit_code == 1
    assert "Object collection manifest" in result.output
    assert message in result.output
    assert "Traceback" not in result.output


def test_collection_manifest_must_exist(tmp_path: Path) -> None:
    result = _collect(tmp_path / "missing.csv", tmp_path / "combined.xlsx")

    assert result.exit_code == 1
    assert "Object collection manifest file does not exist" in result.output


def test_unsupported_output_format_fails_clearly(tmp_path: Path) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")

    result = _collect(manifest, tmp_path / "combined.csv")

    assert result.exit_code == 1
    assert "collect requires a multi-object output format such as xlsx or ods" in (
        result.output
    )


def test_relative_paths_resolve_against_base_dir(tmp_path: Path) -> None:
    source = _csv(tmp_path / "incoming" / "data.csv")
    manifest = _manifest(
        tmp_path / "project" / "objects.csv",
        "input_file\ndata.csv\n",
    )

    plan = build_collection_plan(
        manifest,
        tmp_path / "combined.xlsx",
        base_dir=tmp_path / "incoming",
    )

    assert plan.items[0].input_file == source


def test_relative_paths_default_to_manifest_parent(tmp_path: Path) -> None:
    source = _csv(tmp_path / "project" / "data.csv")
    manifest = _manifest(
        tmp_path / "project" / "objects.csv",
        "input_file\ndata.csv\n",
    )

    plan = build_collection_plan(manifest, tmp_path / "combined.xlsx")

    assert plan.items[0].input_file == source


def test_absolute_input_path_is_used_as_is(tmp_path: Path) -> None:
    source = _csv(tmp_path / "incoming" / "data.csv").resolve()
    manifest = _manifest(
        tmp_path / "objects.csv",
        f"input_file\n{source}\n",
    )

    plan = build_collection_plan(manifest, tmp_path / "combined.xlsx")

    assert plan.items[0].input_file == source


def test_missing_included_input_fails_but_skipped_missing_does_not(
    tmp_path: Path,
) -> None:
    valid = _csv(tmp_path / "valid.csv")
    invalid_manifest = _manifest(
        tmp_path / "invalid.csv",
        "input_file\nmissing.csv\n",
    )
    skipped_manifest = _manifest(
        tmp_path / "skipped.csv",
        "include,input_file\nfalse,missing.csv\ntrue,valid.csv\n",
    )

    with pytest.raises(CollectionError, match="row 2.*missing file"):
        build_collection_plan(invalid_manifest, tmp_path / "invalid.xlsx")
    plan = build_collection_plan(skipped_manifest, tmp_path / "valid.xlsx")
    assert plan.items[0].input_file == valid


def test_collect_csv_and_selected_workbook_sheets_to_xlsx(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "incoming"
    _csv(input_dir / "data.csv", [1, 2, 3])
    _workbook(input_dir / "book.xlsx")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "include,input_file,input_object,output_object\n"
        "true,data.csv,,Imported_Data\n"
        "true,book.xlsx,Data,Book_Data\n"
        "true,book.xlsx,Lookup,Book_Lookup\n",
    )
    output = tmp_path / "combined.xlsx"

    result = _collect(
        manifest,
        output,
        "--base-dir",
        str(input_dir),
    )

    assert result.exit_code == 0, result.output
    assert [item.name for item in list_dataset_objects(output)] == [
        "Imported_Data",
        "Book_Data",
        "Book_Lookup",
    ]
    assert read_dataset(
        output,
        object_selector="Imported_Data",
    ).dataframe["value"].tolist() == [1, 2, 3]
    assert read_dataset(
        output,
        object_selector="Book_Data",
    ).dataframe["value"].tolist() == [10, 20]
    assert read_dataset(
        output,
        object_selector="Book_Lookup",
    ).dataframe["code"].tolist() == ["x", "y"]


def test_collect_selected_sheets_from_multiple_workbooks_in_manifest_order(
    tmp_path: Path,
) -> None:
    _workbook(tmp_path / "first.xlsx", data=[1])
    _workbook(tmp_path / "second.xlsx", data=[2])
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_object\n"
        "second.xlsx,Data,Second\n"
        "first.xlsx,Data,First\n",
    )
    output = tmp_path / "combined.xlsx"

    result = _collect(manifest, output)

    assert result.exit_code == 0, result.output
    assert [item.name for item in list_dataset_objects(output)] == [
        "Second",
        "First",
    ]
    assert read_dataset(output, object_selector="Second").dataframe["value"].tolist() == [
        2
    ]
    assert read_dataset(output, object_selector="First").dataframe["value"].tolist() == [
        1
    ]


def test_collect_to_ods_preserves_names_order_and_data(tmp_path: Path) -> None:
    _csv(tmp_path / "data.csv", [3, 4])
    _workbook(tmp_path / "book.xlsx")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_object\n"
        "book.xlsx,Lookup,Lookup_First\n"
        "data.csv,,CSV_Second\n",
    )
    output = tmp_path / "combined.ods"

    result = _collect(manifest, output)

    assert result.exit_code == 0, result.output
    assert [item.name for item in list_dataset_objects(output)] == [
        "Lookup_First",
        "CSV_Second",
    ]
    assert read_dataset(
        output,
        object_selector="CSV_Second",
    ).dataframe["value"].tolist() == [3, 4]


def test_blank_selector_on_multi_object_input_fails_during_planning(
    tmp_path: Path,
) -> None:
    _workbook(tmp_path / "book.xlsx")
    manifest = _manifest(tmp_path / "objects.csv", "input_file\nbook.xlsx\n")

    result = _collect(manifest, tmp_path / "combined.xlsx")

    assert result.exit_code == 1
    assert "contains multiple objects" in result.output
    assert "Use --object" in result.output


def test_selector_on_single_dataset_input_fails_during_planning(
    tmp_path: Path,
) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,input_object\ndata.csv,Data\n",
    )

    result = _collect(manifest, tmp_path / "combined.xlsx")

    assert result.exit_code == 1
    assert "Object selection is not supported for .csv files" in result.output


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            "data.csv,,Patients\ndata.csv,,Patients\n",
            "Duplicate output object name: Patients",
        ),
        (
            "data.csv,,Very/Bad:Sheet\n",
            "Object name is not valid for xlsx output: Very/Bad:Sheet",
        ),
    ],
)
def test_invalid_or_duplicate_output_object_names_fail_without_renaming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: str,
    message: str,
) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,input_object,output_object\n" + rows,
    )

    monkeypatch.setattr(
        "statconvert.collection.read_dataset",
        lambda *args, **kwargs: pytest.fail(
            "invalid collection plan read a dataset"
        ),
    )

    result = _collect(manifest, tmp_path / "combined.xlsx")

    assert result.exit_code == 1
    assert message in result.output
    assert not (tmp_path / "combined.xlsx").exists()


def test_output_safety_overwrite_and_create_dirs(tmp_path: Path) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")
    output = tmp_path / "missing" / "combined.xlsx"

    missing_parent = _collect(manifest, output)
    created = _collect(manifest, output, "--create-dirs")
    blocked = _collect(manifest, output)
    overwritten = _collect(manifest, output, "--overwrite")

    assert missing_parent.exit_code == 1
    assert "--create-dirs" in missing_parent.output
    assert created.exit_code == 0, created.output
    assert blocked.exit_code == 1
    assert "--overwrite" in blocked.output
    assert overwritten.exit_code == 0, overwritten.output


def test_dry_run_reports_plan_without_reading_or_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file,output_object\ndata.csv,Imported_Data\n",
    )
    output = tmp_path / "missing" / "combined.xlsx"

    def unexpected_read(*args, **kwargs):
        raise AssertionError("dry-run must not read datasets")

    monkeypatch.setattr("statconvert.collection.read_dataset", unexpected_read)

    result = _collect(manifest, output, "--dry-run")

    assert result.exit_code == 0, result.output
    assert "Planned Object Collection" in result.output
    assert "Imported_Data" in result.output
    assert output.name in result.output
    assert not output.exists()
    assert not output.parent.exists()


def test_dry_run_skips_excluded_rows(tmp_path: Path) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(
        tmp_path / "objects.csv",
        "include,input_file,output_object\n"
        "false,missing.csv,Excluded\n"
        "true,data.csv,Included\n",
    )

    result = _collect(
        manifest,
        tmp_path / "combined.xlsx",
        "--dry-run",
    )

    assert result.exit_code == 0, result.output
    assert "Included" in result.output
    assert "Excluded" not in result.output


def test_csv_read_options_apply_during_collection(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    source.write_text("value;label\n1,5;A\n", encoding="utf-8")
    manifest = _manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")
    output = tmp_path / "combined.xlsx"

    result = _collect(
        manifest,
        output,
        "--csv-delimiter",
        ";",
        "--csv-decimal",
        ",",
    )

    assert result.exit_code == 0, result.output
    dataset = read_dataset(output, object_selector="data")
    assert dataset.dataframe.to_dict(orient="records") == [
        {"value": 1.5, "label": "A"}
    ]


def test_strict_validation_failure_writes_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _csv(tmp_path / "data.csv")
    manifest = _manifest(tmp_path / "objects.csv", "input_file\ndata.csv\n")
    output = tmp_path / "combined.xlsx"
    monkeypatch.setattr(
        "statconvert.collection.validate_for_write",
        lambda *args, **kwargs: [
            ValidationIssue(
                severity="warning",
                code="collection_warning",
                message="collection warning",
            )
        ],
    )

    result = _collect(manifest, output, "--strict-validation")

    assert result.exit_code == 1
    assert "Manifest row 2" in result.output
    assert "Validation failed. Output was not written." in result.output
    assert not output.exists()


def test_later_read_failure_writes_no_partial_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _csv(tmp_path / "one.csv", [1])
    _csv(tmp_path / "two.csv", [2])
    manifest = _manifest(
        tmp_path / "objects.csv",
        "input_file\none.csv\ntwo.csv\n",
    )
    output = tmp_path / "combined.xlsx"
    calls = 0

    def fake_read(path, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CollectionError("second read failed")
        return Dataset(pd.DataFrame({"value": [1]}))

    monkeypatch.setattr("statconvert.collection.read_dataset", fake_read)

    result = _collect(manifest, output)

    assert result.exit_code == 1
    assert "second read failed" in result.output
    assert not output.exists()
