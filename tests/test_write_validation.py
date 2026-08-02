import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.converter import transform as convert_file
from statconvert.dataset import Dataset
from statconvert.inspection import (
    ValidationFailedError,
    ValidationIssue,
    validate_for_write,
    validation_has_errors,
    validation_has_warnings,
    validation_should_fail,
)
from statconvert.transformer import transform_file
from statconvert.transformations import (
    RenameColumnsTransformation,
    TransformationPipeline,
)


runner = CliRunner()


def test_shared_validation_gate_predicates():
    error = ValidationIssue("error", "error", "Error")
    warning = ValidationIssue("warning", "warning", "Warning")
    info = ValidationIssue("info", "info", "Info")

    assert validation_has_errors([error])
    assert not validation_has_errors([warning, info])
    assert validation_has_warnings([warning])
    assert validation_should_fail([error])
    assert not validation_should_fail([warning], strict=False)
    assert validation_should_fail([warning], strict=True)
    assert not validation_should_fail([info], strict=True)


def test_validate_for_write_calls_dataset_validator(monkeypatch):
    dataset = Dataset(pd.DataFrame({"value": [1]}))
    expected = [ValidationIssue("warning", "test", "Test warning")]
    calls = []

    def controlled_validator(dataset_arg, target_format=None, strict=False):
        calls.append((dataset_arg, target_format, strict))
        return expected

    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        controlled_validator,
    )

    assert validate_for_write(dataset, ".csv", strict=True) is expected
    assert calls == [(dataset, ".csv", True)]


@pytest.mark.parametrize("validate", [False, True])
def test_convert_writes_without_or_with_passing_validation(monkeypatch, tmp_path, validate):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [],
    )

    convert_file(
        str(input_file),
        str(output_file),
        validate=validate,
    )

    assert output_file.exists()


def test_convert_validation_error_prevents_write(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [
            ValidationIssue("error", "blocked", "Blocked output")
        ],
    )

    with pytest.raises(ValidationFailedError):
        convert_file(str(input_file), str(output_file), validate=True)

    assert not output_file.exists()


def test_convert_warning_policy_and_strict_implies_validation(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input.csv")
    normal_output = tmp_path / "normal.json"
    strict_output = tmp_path / "strict.json"
    calls = []

    def warning_validator(dataset, target_format=None, strict=False):
        calls.append((target_format, strict))
        return [ValidationIssue("warning", "warning", "Controlled warning")]

    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        warning_validator,
    )
    convert_file(str(input_file), str(normal_output), validate=True)
    with pytest.raises(ValidationFailedError):
        convert_file(
            str(input_file),
            str(strict_output),
            strict_validation=True,
        )

    assert normal_output.exists()
    assert not strict_output.exists()
    assert calls == [(".json", False), (".json", True)]


def test_transform_validates_after_rename_and_prevents_write(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    seen_columns = []

    def transformed_validator(dataset, target_format=None, strict=False):
        seen_columns.append(list(dataset.columns))
        return [ValidationIssue("error", "blocked", "Blocked transformed output")]

    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        transformed_validator,
    )
    pipeline = TransformationPipeline(
        [RenameColumnsTransformation({"name": "display_name"})]
    )

    with pytest.raises(ValidationFailedError):
        transform_file(
            str(input_file),
            str(output_file),
            pipeline,
            validate=True,
        )

    assert seen_columns == [["id", "display_name"]]
    assert not output_file.exists()


def test_transform_strict_warning_prevents_write(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.json"
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: [
            ValidationIssue("warning", "warning", "Controlled warning")
        ],
    )

    with pytest.raises(ValidationFailedError):
        transform_file(
            str(input_file),
            str(output_file),
            TransformationPipeline(),
            strict_validation=True,
        )

    assert not output_file.exists()


def test_convert_and_transform_cli_validation_exit_codes(monkeypatch, tmp_path):
    input_file = _write_csv(tmp_path / "input.csv")
    issues = [ValidationIssue("warning", "warning", "Controlled warning")]
    monkeypatch.setattr(
        "statconvert.inspection.gates.validate_dataset",
        lambda dataset, target_format=None, strict=False: issues,
    )

    convert_result = runner.invoke(
        app,
        ["convert", str(input_file), str(tmp_path / "convert.json"), "--validate"],
    )
    transform_result = runner.invoke(
        app,
        [
            "transform", str(input_file), str(tmp_path / "transform.json"),
            "--rename", "name=display_name", "--strict-validation",
        ],
    )

    assert convert_result.exit_code == 0
    assert (tmp_path / "convert.json").exists()
    assert transform_result.exit_code == 1
    assert "Validation failed" in transform_result.output
    assert not (tmp_path / "transform.json").exists()


def _write_csv(path):
    pd.DataFrame({"id": [1, 2], "name": ["Ada", "Grace"]}).to_csv(
        path,
        index=False,
    )
    return path
