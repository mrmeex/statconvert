from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from typer.testing import CliRunner

from statconvert.backends.r_backend import RBackend
from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.exceptions import (
    AmbiguousObjectError,
    ObjectNotFoundError,
    ObjectSelectionError,
    ObjectSelectionNotSupportedError,
)
from statconvert.registry import list_dataset_objects, read_dataset


runner = CliRunner()
REMAINING_SINGLE_DATASET_COMMANDS = [
    "labels",
    "describe",
    "frequencies",
    "missing",
]


def _patients() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "patient_id": [1, 2],
            "age": [30, 40],
            "group": ["A", "B"],
        }
    )


def _visits() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "visit_id": [101, 102, 103],
            "score": [5.5, 6.0, 7.5],
        }
    )


def _install_fake_workspace(
    monkeypatch: pytest.MonkeyPatch,
    objects: dict[str, Any],
    *,
    descriptors: list[dict[str, Any]] | None = None,
) -> None:
    if descriptors is None:
        descriptors = [
            {
                "object_name": name,
                "columns": list(value.columns)
                if isinstance(value, pd.DataFrame)
                else None,
            }
            for name, value in objects.items()
        ]

    monkeypatch.setattr(
        "statconvert.backends.r_backend.pyreadr.read_r",
        lambda filename, **kwargs: objects.copy(),
    )
    monkeypatch.setattr(
        "statconvert.backends.r_backend.pyreadr.list_objects",
        lambda filename: list(descriptors),
    )


def _workspace_path(tmp_path: Path, extension: str = ".rdata") -> Path:
    path = tmp_path / f"workspace{extension}"
    path.write_bytes(b"test workspace placeholder")
    return path


@pytest.mark.parametrize("extension", [".rdata", ".rda"])
def test_real_single_object_workspace_lists_and_reads(
    tmp_path: Path,
    extension: str,
) -> None:
    path = tmp_path / f"patients{extension}"
    expected = _patients()
    backend = RBackend()
    backend.write(Dataset(dataframe=expected), path, object_name="patients")

    objects = backend.list_objects(path)

    assert len(objects) == 1
    assert objects[0].name == "patients"
    assert objects[0].index == 0
    assert objects[0].kind == "r_object"
    assert objects[0].rows == 2
    assert objects[0].columns == 3
    assert objects[0].supported is True
    assert_frame_equal(read_dataset(path).dataframe, expected)
    assert_frame_equal(
        read_dataset(path, object_selector="patients").dataframe,
        expected,
    )


@pytest.mark.parametrize("extension", [".rdata", ".rda"])
def test_objects_command_lists_real_r_workspace_as_json(
    tmp_path: Path,
    extension: str,
) -> None:
    path = tmp_path / f"patients{extension}"
    RBackend().write(
        Dataset(dataframe=_patients()),
        path,
        object_name="patients",
    )

    human = runner.invoke(app, ["objects", str(path)])
    json_result = runner.invoke(app, ["objects", str(path), "--json"])

    assert human.exit_code == 0
    assert "patients" in human.output
    assert "r_object" in human.output
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout) == [
        {
            "name": "patients",
            "index": 0,
            "kind": "r_object",
            "rows": 2,
            "columns": 3,
            "supported": True,
            "message": None,
        }
    ]


def test_multi_object_workspace_requires_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    with pytest.raises(AmbiguousObjectError) as exc_info:
        read_dataset(path)

    message = str(exc_info.value)
    assert "Use --object to choose one" in message
    assert "patients" in message
    assert "visits" in message


@pytest.mark.parametrize(
    ("selector", "expected"),
    [("patients", _patients()), ("1", _visits())],
)
def test_multi_object_workspace_selects_by_name_or_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selector: str,
    expected: pd.DataFrame,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    dataset = read_dataset(path, object_selector=selector)

    assert_frame_equal(dataset.dataframe, expected)
    assert dataset.metadata["selected_object"] in {"patients", "visits"}


@pytest.mark.parametrize(
    ("selector", "expected_message"),
    [
        ("missing", "Object 'missing' was not found"),
        ("9", "Object index 9 is out of range"),
    ],
)
def test_unknown_workspace_selector_lists_available_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selector: str,
    expected_message: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    with pytest.raises(ObjectNotFoundError) as exc_info:
        read_dataset(path, object_selector=selector)

    message = str(exc_info.value)
    assert expected_message in message
    assert "patients" in message
    assert "visits" in message


def test_exact_numeric_object_name_is_preferred_over_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"first": _patients(), "1": _visits()},
    )

    dataset = read_dataset(path, object_selector="1")

    assert_frame_equal(dataset.dataframe, _visits())
    assert dataset.metadata["selected_object"] == "1"


def test_unsupported_descriptor_is_listed_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    descriptors = [
        {"object_name": "patients", "columns": ["patient_id", "age", "group"]},
        {"object_name": "model", "columns": None},
    ]
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients()},
        descriptors=descriptors,
    )

    objects = list_dataset_objects(path)

    assert [info.name for info in objects] == ["patients", "model"]
    assert objects[0].supported is True
    assert objects[1].supported is False
    assert "not exposed" in (objects[1].message or "")
    with pytest.raises(ObjectSelectionError) as exc_info:
        read_dataset(path, object_selector="model")
    assert "not a supported tabular dataset object" in str(exc_info.value)
    assert "patients" in str(exc_info.value)


def test_workspace_with_no_supported_objects_fails_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {},
        descriptors=[{"object_name": "model", "columns": None}],
    )

    with pytest.raises(
        ObjectNotFoundError,
        match="No supported tabular R objects were found",
    ):
        read_dataset(path)


def test_rds_rejects_object_selector_without_breaking_default_read(
    tmp_path: Path,
) -> None:
    path = tmp_path / "patients.rds"
    expected = _patients()
    RBackend().write(Dataset(dataframe=expected), path)

    assert_frame_equal(read_dataset(path).dataframe, expected)
    with pytest.raises(
        ObjectSelectionNotSupportedError,
        match=r"Object selection is not supported for \.rds files",
    ):
        read_dataset(path, object_selector="patients")


def test_rdata_cli_reports_ambiguity_without_first_object_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(app, ["peek", str(path)])

    assert result.exit_code == 1
    assert "Use --object to choose one" in result.output
    assert "patients" in result.output
    assert "visits" in result.output
    assert "Traceback" not in result.output


def test_rdata_cli_parity_for_read_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    for command in ["peek", "info", "schema", "metadata", "summary", "validate"]:
        result = runner.invoke(
            app,
            [command, str(path), "--object", "patients"],
        )
        assert result.exit_code == 0, (command, result.output)

    csv_output = tmp_path / "patients.csv"
    convert_result = runner.invoke(
        app,
        ["convert", str(path), str(csv_output), "--object", "patients"],
    )
    assert convert_result.exit_code == 0
    assert_frame_equal(pd.read_csv(csv_output), _patients())

    transformed_output = tmp_path / "selected.csv"
    transform_result = runner.invoke(
        app,
        [
            "transform",
            str(path),
            str(transformed_output),
            "--object",
            "patients",
            "--select",
            "patient_id",
        ],
    )
    assert transform_result.exit_code == 0
    assert list(pd.read_csv(transformed_output).columns) == ["patient_id"]

    report_output = tmp_path / "patients.html"
    report_result = runner.invoke(
        app,
        [
            "report",
            str(path),
            "--object",
            "patients",
            "--output",
            str(report_output),
        ],
    )
    assert report_result.exit_code == 0
    assert report_output.exists()


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_read_selected_rdata_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(
        app,
        [command, str(path), "--object", "patients"],
    )

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_require_selector_for_multi_object_rdata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(app, [command, str(path)])

    assert result.exit_code == 1
    assert "multiple objects" in result.output
    assert "Use --object" in result.output
    assert "patients" in result.output
    assert "visits" in result.output
    assert "patient_id" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_reject_unknown_rdata_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(
        app,
        [command, str(path), "--object", "missing"],
    )

    assert result.exit_code == 1
    assert "Object 'missing' was not found" in result.output
    assert "patients" in result.output
    assert "visits" in result.output


@pytest.mark.parametrize(
    ("command", "extra_arguments", "selected_field", "selected_column"),
    [
        ("describe", [], "name", "patient_id"),
        ("frequencies", ["--columns", "group"], "column", "group"),
        ("missing", [], "column", "patient_id"),
    ],
)
def test_remaining_rdata_json_commands_describe_selected_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    extra_arguments: list[str],
    selected_field: str,
    selected_column: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(
        app,
        [
            command,
            str(path),
            "--object",
            "patients",
            *extra_arguments,
                "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert any(item[selected_field] == selected_column for item in payload)
    assert all(item.get(selected_field) != "visit_id" for item in payload)


@pytest.mark.parametrize("command", REMAINING_SINGLE_DATASET_COMMANDS)
def test_remaining_commands_read_single_rdata_object_without_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    path = _workspace_path(tmp_path)
    _install_fake_workspace(monkeypatch, {"patients": _patients()})

    result = runner.invoke(app, [command, str(path)])

    assert result.exit_code == 0, result.output


def test_compare_multi_object_rdata_with_shared_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = _workspace_path(tmp_path)
    right = tmp_path / "other.rdata"
    right.write_bytes(b"test workspace placeholder")
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--object", "patients", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["values"]["same_values"] is True


def test_compare_rdata_supports_different_named_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = _workspace_path(tmp_path)
    right = tmp_path / "other.rda"
    right.write_bytes(b"test workspace placeholder")
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "people": _patients(), "visits": _visits()},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--left-object",
            "patients",
            "--right-object",
            "people",
        ],
    )

    assert result.exit_code == 0


def test_compare_multi_object_rdata_without_selector_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = _workspace_path(tmp_path)
    right = tmp_path / "right.csv"
    _patients().to_csv(right, index=False)
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    result = runner.invoke(app, ["compare", str(left), str(right)])

    assert result.exit_code == 1
    assert "multiple objects" in result.output
    assert "patients" in result.output and "visits" in result.output


def test_batch_selects_rdata_object_and_reports_unknown_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name in ("one.rdata", "two.rdata"):
        (input_dir / name).write_bytes(b"test workspace placeholder")
    _install_fake_workspace(
        monkeypatch,
        {"patients": _patients(), "visits": _visits()},
    )

    success = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "csv",
            "--object",
            "patients",
            "--json",
            "--create-dirs",
        ],
    )
    failed = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(tmp_path / "other-output"),
            "--to",
            "csv",
            "--object",
            "missing",
            "--json",
            "--create-dirs",
        ],
    )

    assert success.exit_code == 0
    assert all(item["status"] == "success" for item in json.loads(success.output)["items"])
    failed_items = json.loads(failed.output)["items"]
    assert failed.exit_code == 1
    assert all("Object 'missing' was not found" in item["error"] for item in failed_items)
