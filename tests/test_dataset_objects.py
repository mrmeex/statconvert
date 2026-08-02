from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.objects import DatasetObjectInfo, object_selector_matches
from statconvert.cli import app
from statconvert.exceptions import ObjectSelectionNotSupportedError
from statconvert.registry import (
    format_object_kind,
    format_supports_objects,
    get_format_capabilities,
    list_dataset_objects,
    read_dataset,
)


runner = CliRunner()


def test_dataset_object_info_defaults_are_serializable() -> None:
    info = DatasetObjectInfo(name="SurveyData")

    assert asdict(info) == {
        "name": "SurveyData",
        "index": None,
        "kind": "dataset",
        "rows": None,
        "columns": None,
        "supported": True,
        "message": None,
    }


def test_dataset_object_info_can_describe_unsupported_object() -> None:
    info = DatasetObjectInfo(
        name="model",
        kind="unsupported",
        supported=False,
        message="This R object is not tabular.",
    )

    assert info.supported is False
    assert info.message == "This R object is not tabular."


def test_object_selector_matches_exact_name_or_index() -> None:
    info = DatasetObjectInfo(name="Sheet 1", index=1, kind="sheet")

    assert object_selector_matches(info, "Sheet 1") is True
    assert object_selector_matches(info, "1") is True
    assert object_selector_matches(info, "sheet 1") is False
    assert object_selector_matches(info, "0") is False


def test_single_dataset_backend_object_api_defaults() -> None:
    backend = CSVBackend()

    assert backend.supports_object_selection() is False
    assert backend.list_objects(Path("input.csv")) == []


def test_rds_remains_a_single_object_format() -> None:
    assert format_supports_objects("rds") is False
    assert format_object_kind(".rds") is None


def test_csv_read_without_object_selector_is_unchanged(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(input_file, index=False)

    dataset = read_dataset(input_file)

    assert dataset.rows == 2
    assert dataset.columns == ["value"]


def test_csv_read_with_object_selector_fails_clearly(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    pd.DataFrame({"value": [1]}).to_csv(input_file, index=False)

    with pytest.raises(
        ObjectSelectionNotSupportedError,
        match=r"Object selection is not supported for \.csv files",
    ):
        read_dataset(input_file, object_selector="0")


@pytest.mark.parametrize(
    ("extension", "kind"),
    [
        ("xlsx", "sheet"),
        (".ODS", "sheet"),
        ("rdata", "r_object"),
        (".rda", "r_object"),
    ],
)
def test_container_formats_report_object_support(
    extension: str,
    kind: str,
) -> None:
    capabilities = get_format_capabilities(extension)

    assert capabilities.is_container is True
    assert capabilities.object_selection is True
    assert format_supports_objects(extension) is True
    assert format_object_kind(extension) == kind


def test_single_dataset_format_reports_no_object_support() -> None:
    assert format_supports_objects("csv") is False
    assert format_object_kind(".csv") is None


def test_unknown_object_capability_is_handled_cleanly() -> None:
    assert format_supports_objects("unknown") is False
    with pytest.raises(ValueError, match="Unsupported file format: .unknown"):
        format_object_kind("unknown")


def test_list_dataset_objects_rejects_single_dataset_format(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    input_file.write_text("value\n1\n", encoding="utf-8")

    with pytest.raises(
        ObjectSelectionNotSupportedError,
        match="does not expose multiple dataset objects",
    ):
        list_dataset_objects(input_file)


def test_objects_command_is_listed_in_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "objects" in result.output


def test_objects_command_on_csv_exits_cleanly(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    input_file.write_text("value\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["objects", str(input_file)])

    assert result.exit_code == 0
    assert "This format does not expose multiple dataset objects." in result.output


def test_objects_command_json_on_csv_is_plain_json(tmp_path: Path) -> None:
    input_file = tmp_path / "input.csv"
    input_file.write_text("value\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["objects", str(input_file), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_objects_command_rejects_unknown_extension(tmp_path: Path) -> None:
    input_file = tmp_path / "input.unknown"
    input_file.write_text("data", encoding="utf-8")

    result = runner.invoke(app, ["objects", str(input_file)])

    assert result.exit_code == 1
    assert "Unsupported file format: .unknown" in result.output
