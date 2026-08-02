import json

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.cli import app
from statconvert.compare import compare_datasets
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.ui.compare import console, show_dataset_comparison


runner = CliRunner()


def test_compare_help_lists_core_options():
    result = runner.invoke(app, ["compare", "--help"])

    assert result.exit_code == 0
    assert "--ignore-columns" in result.output
    assert "--numeric-tolerance" in result.output
    assert "--key" in result.output
    assert "--max-differences" in result.output


def test_show_dataset_comparison_handles_identical_comparison():
    comparison = compare_datasets(_dataset({"age": [10, 20]}), _dataset({"age": [10, 20]}))

    output = _render(comparison)

    assert "Comparison Summary" in output
    assert "Identical" in output
    assert "No comparison issues found" in output


def test_show_dataset_comparison_handles_shape_and_long_column_differences():
    left_data = {f"left_{index}": [index, index] for index in range(10)}
    right_data = {f"right_{index}": [index] for index in range(10)}

    output = _render(compare_datasets(_dataset(left_data), _dataset(right_data)))

    assert "Shape" in output
    assert "Left only" in output
    assert "+2 more" in output
    assert "shape_rows_differ" in output


def test_show_dataset_comparison_handles_schema_metadata_and_values():
    left = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", label="Old", storage_type="int32"),
    )
    right = _dataset(
        {"age": [2]},
        VariableMetadata(name="age", label="New", storage_type="float64"),
    )

    output = _render(compare_datasets(left, right))

    assert "Changed Storage Types" in output
    assert "Variable labels" in output
    assert "Differing cells" in output
    assert "values_changed" in output


def test_show_dataset_comparison_includes_all_schema_change_categories():
    left = _dataset(
        {"age": [1]},
        VariableMetadata(
            name="age", display_format="%12.0g", measure="scale"
        ),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(
            name="age", display_format="%9.2f", measure="ordinal"
        ),
    )

    output = _render(compare_datasets(left, right))

    assert "Display Format Changes" in output
    assert "%12.0g" in output
    assert "%9.2f" in output
    assert "Measurement Level Changes" in output
    assert "scale" in output
    assert "ordinal" in output


def test_show_dataset_comparison_handles_skipped_values():
    comparison = compare_datasets(
        _dataset({"age": [1]}),
        _dataset({"age": [2]}),
        compare_values=False,
    )

    assert "comparison skipped" in _render(comparison)


def test_compare_identical_csv_files_exits_zero(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1, 2]}, {"age": [1, 2]})

    result = runner.invoke(app, ["compare", str(left), str(right)])

    assert result.exit_code == 0
    assert "Comparison Summary" in result.output
    assert "No comparison issues found" in result.output


def test_compare_changed_value_exits_one(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1, 2]}, {"age": [1, 9]})

    result = runner.invoke(app, ["compare", str(left), str(right)])

    assert result.exit_code == 1
    assert "values_changed" in result.output


def test_compare_rejects_negative_numeric_tolerance_before_reading():
    result = runner.invoke(
        app,
        [
            "compare",
            "missing-left.csv",
            "missing-right.csv",
            "--numeric-tolerance",
            "-0.1",
        ],
    )

    assert result.exit_code == 1
    assert "--numeric-tolerance must be greater than or equal to 0" in result.output
    assert "Input file does not exist" not in result.output


@pytest.mark.parametrize(
    ("key_value", "message"),
    [
        ("id,,date", "Invalid key column list"),
        ("id,id", "Duplicate key column specified: id"),
    ],
)
def test_compare_rejects_invalid_keys_before_reading(key_value, message):
    result = runner.invoke(
        app,
        ["compare", "missing-left.csv", "missing-right.csv", "--key", key_value],
    )

    assert result.exit_code == 1
    assert message in result.output
    assert "Input file does not exist" not in result.output


def test_compare_rejects_ignored_key_before_reading():
    result = runner.invoke(
        app,
        [
            "compare",
            "missing-left.csv",
            "missing-right.csv",
            "--key",
            "id",
            "--ignore-columns",
            "id",
        ],
    )

    assert result.exit_code == 1
    assert "Key columns cannot be ignored: id" in result.output
    assert "Input file does not exist" not in result.output


@pytest.mark.parametrize("value", ["0", "-1"])
def test_compare_rejects_invalid_max_differences_before_reading(value):
    result = runner.invoke(
        app,
        [
            "compare",
            "missing-left.csv",
            "missing-right.csv",
            "--max-differences",
            value,
        ],
    )

    assert result.exit_code == 1
    assert "--max-differences must be greater than 0" in result.output
    assert "Input file does not exist" not in result.output


def test_compare_cli_caps_first_differences_but_preserves_summary(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"a": [1, 2, 3]},
        {"a": [4, 5, 6]},
    )

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--max-differences", "1"],
    )

    assert result.exit_code == 1
    assert "First Differences" in result.output
    assert "Cells different" in result.output
    assert "3" in result.output
    assert "Showing first 1 of 3 detailed differences" in result.output


def test_compare_cli_matches_reordered_rows_by_compound_key(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"id": [1, 1], "visit": [1, 2], "name": ["Alice", "Bob"]},
        {"id": [1, 1], "visit": [2, 1], "name": ["Bob", "Alice"]},
    )

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--key", "id,visit"],
    )

    assert result.exit_code == 0, result.output
    assert "Row matching" in result.output
    assert "id, visit" in result.output
    assert "Matched rows" in result.output


def test_compare_cli_ignores_comma_separated_columns(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"id": [1], "exported_at": ["old"], "source_file": ["left.csv"]},
        {"id": [1]},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--ignore-columns",
            "exported_at,source_file",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Comparison Options" in result.output
    assert "exported_at, source_file" in result.output
    assert "No comparison issues found" in result.output


def test_compare_cli_numeric_tolerance_and_zero_behavior(tmp_path):
    left, right = _write_pair(tmp_path, {"value": [1.0]}, {"value": [1.00005]})

    tolerant = runner.invoke(
        app,
        ["compare", str(left), str(right), "--numeric-tolerance", "0.0001"],
    )
    exact = runner.invoke(
        app,
        ["compare", str(left), str(right), "--numeric-tolerance", "0"],
    )

    assert tolerant.exit_code == 0, tolerant.output
    assert "Numeric tolerance" in tolerant.output
    assert exact.exit_code == 1
    assert "values_changed" in exact.output


def test_compare_cli_rejects_invalid_or_exhaustive_ignore_lists(tmp_path):
    left, right = _write_pair(tmp_path, {"id": [1]}, {"id": [1]})

    invalid = runner.invoke(
        app,
        ["compare", str(left), str(right), "--ignore-columns", "id,,other"],
    )
    exhaustive = runner.invoke(
        app,
        ["compare", str(left), str(right), "--ignore-columns", "id"],
    )

    assert invalid.exit_code == 1
    assert "Invalid ignore column list" in invalid.output
    assert exhaustive.exit_code == 1
    assert "No columns remain to compare" in exhaustive.output


def test_compare_no_values_ignores_value_differences(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1, 2]}, {"age": [1, 9]})

    result = runner.invoke(app, ["compare", str(left), str(right), "--no-values"])

    assert result.exit_code == 0
    assert "comparison skipped" in result.output
    assert "values_changed" not in result.output


def test_compare_schema_warning_and_strict_exit_code(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1, 2]}, {"age": [1.5, 2.5]})

    normal = runner.invoke(app, ["compare", str(left), str(right), "--no-values"])
    strict = runner.invoke(
        app, ["compare", str(left), str(right), "--no-values", "--strict"]
    )

    assert normal.exit_code == 0
    assert "storage_types_changed" in normal.output
    assert strict.exit_code == 1


def test_compare_strict_fails_for_display_format_only_warning(monkeypatch):
    left = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", display_format="F8.0"),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", display_format="F9.2"),
    )

    normal = _invoke_with_datasets(monkeypatch, left, right, "--no-values")
    strict = _invoke_with_datasets(
        monkeypatch, left, right, "--no-values", "--strict"
    )

    assert normal.exit_code == 0
    assert "display_formats_changed" in normal.output
    assert strict.exit_code == 1


def test_compare_strict_fails_for_measurement_level_only_warning(monkeypatch):
    left = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", measure="scale"),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", measure="ordinal"),
    )

    normal = _invoke_with_datasets(monkeypatch, left, right, "--no-values")
    strict = _invoke_with_datasets(
        monkeypatch, left, right, "--no-values", "--strict"
    )

    assert normal.exit_code == 0
    assert "measurement_levels_changed" in normal.output
    assert strict.exit_code == 1


def test_compare_sample_accepts_positive_and_rejects_zero(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1, 2]}, {"age": [1, 9]})

    sampled = runner.invoke(
        app, ["compare", str(left), str(right), "--sample", "1"]
    )
    invalid = runner.invoke(
        app, ["compare", str(left), str(right), "--sample", "0"]
    )

    assert sampled.exit_code == 0
    assert "first 1 rows" in sampled.output
    assert invalid.exit_code == 1
    assert "--sample must be greater than 0" in invalid.output


def test_compare_rejects_sample_with_no_values(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1]}, {"age": [1]})

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--no-values", "--sample", "1"],
    )

    assert result.exit_code == 1
    assert "--sample cannot be used with --no-values" in result.output


def test_compare_columns_restricts_comparison_and_preserves_compact_syntax(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"age": [1], "sex": [1], "income": [10]},
        {"age": [9], "sex": [1], "income": [10]},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--columns",
            "sex",
            "income",
        ],
    )

    assert result.exit_code == 0
    assert "values_changed" not in result.output


def test_compare_missing_requested_column_is_friendly(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1]}, {"age": [1]})

    result = runner.invoke(
        app, ["compare", str(left), str(right), "--columns", "missing"]
    )

    assert result.exit_code == 1
    assert "Requested comparison columns are invalid" in result.output


def test_compare_json_outputs_one_valid_object(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1]}, {"age": [1]})

    result = runner.invoke(app, ["compare", str(left), str(right), "--json"])
    data = json.loads(result.output)

    assert result.exit_code == 0
    assert data["shape"]["rows_match"] is True
    assert data["values"]["same_values"] is True


def test_compare_json_includes_applied_core_options(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"id": [1.0], "generated": ["left"]},
        {"id": [1.00005], "generated": ["right"]},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--ignore-columns",
            "generated",
            "--numeric-tolerance",
            "0.0001",
            "--json",
        ],
    )
    data = json.loads(result.output)

    assert result.exit_code == 0
    assert data["options"] == {
        "ignore_columns": ["generated"],
        "numeric_tolerance": 0.0001,
        "key_columns": [],
        "max_differences": 50,
    }
    assert data["columns_compared"] == ["id"]


def test_compare_json_includes_key_matching_summary(tmp_path):
    left, right = _write_pair(
        tmp_path,
        {"id": [1, 2], "value": [10.0, 20.0]},
        {"id": [2, 3], "value": [20.005, 30.0]},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--key",
            "id",
            "--numeric-tolerance",
            "0.01",
            "--json",
        ],
    )
    data = json.loads(result.output)

    assert result.exit_code == 1
    assert data["options"]["key_columns"] == ["id"]
    assert data["row_matching_mode"] == "key"
    assert data["key_columns"] == ["id"]
    assert data["matched_rows"] == 1
    assert data["rows_only_left"] == 1
    assert data["rows_only_right"] == 1


def test_compare_json_includes_complete_bounded_detail_summary(tmp_path):
    left, right = _write_pair(tmp_path, {"a": [1, 2]}, {"a": [3, 4]})

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--max-differences",
            "1",
            "--json",
        ],
    )
    data = json.loads(result.output)

    assert result.exit_code == 1
    assert data["equal"] is False
    assert data["options"]["max_differences"] == 1
    assert data["summary"]["row_matching_mode"] == "positional"
    assert data["summary"]["max_differences"] == 1
    assert data["summary"]["cells_compared"] == 2
    assert data["summary"]["cells_different"] == 2
    assert data["summary"]["detailed_differences_shown"] == 1
    assert data["summary"]["detailed_differences_truncated"] is True
    assert len(data["differences"]) == 1
    assert data["differences"][0]["row"] == 0
    assert data["differences"][0]["column"] == "a"


def test_compare_json_normalizes_numpy_value_label_keys(monkeypatch):
    left = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", value_labels={np.int64(1): "One"}),
    )
    right = _dataset(
        {"age": [1]},
        VariableMetadata(name="age", value_labels={np.int64(1): "First"}),
    )

    result = _invoke_with_datasets(
        monkeypatch, left, right, "--no-values", "--json"
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["metadata"]["value_label_changes"]["age"] == [
        {"1": "One"},
        {"1": "First"},
    ]


def test_compare_unsupported_file_is_friendly(tmp_path):
    left = tmp_path / "left.unsupported"
    right = tmp_path / "right.csv"
    left.write_text("age\n1\n", encoding="utf-8")
    right.write_text("age\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["compare", str(left), str(right)])

    assert result.exit_code == 1
    assert "Unsupported file format" in result.output


def test_compare_shared_object_selects_same_sheet_on_both_sides(tmp_path):
    left = _write_workbook(
        tmp_path / "left.xlsx",
        {"Other": {"value": [0]}, "Data": {"value": [1, 2]}},
    )
    right = _write_workbook(
        tmp_path / "right.xlsx",
        {"Other": {"value": [9]}, "Data": {"value": [1, 2]}},
    )

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--object", "Data", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["values"]["same_values"] is True


def test_compare_supports_different_left_and_right_objects(tmp_path):
    left = _write_workbook(
        tmp_path / "left.xlsx",
        {"Old": {"value": [1]}, "Other": {"value": [0]}},
    )
    right = _write_workbook(
        tmp_path / "right.xlsx",
        {"New": {"value": [1]}, "Other": {"value": [9]}},
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--left-object",
            "Old",
            "--right-object",
            "New",
        ],
    )

    assert result.exit_code == 0


def test_compare_one_sided_object_selector_supports_csv_and_workbook(tmp_path):
    left = tmp_path / "left.csv"
    pd.DataFrame({"value": [1]}).to_csv(left, index=False)
    right = _write_workbook(
        tmp_path / "right.xlsx",
        {"Other": {"value": [0]}, "Data": {"value": [1]}},
    )

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--right-object", "Data"],
    )

    assert result.exit_code == 0


def test_compare_multi_sheet_input_without_selector_is_friendly(tmp_path):
    left = _write_workbook(
        tmp_path / "left.xlsx",
        {"First": {"value": [1]}, "Data": {"value": [1]}},
    )
    right = tmp_path / "right.csv"
    pd.DataFrame({"value": [1]}).to_csv(right, index=False)

    result = runner.invoke(app, ["compare", str(left), str(right)])

    assert result.exit_code == 1
    assert "multiple sheets" in result.output
    assert "First" in result.output and "Data" in result.output


def test_compare_rejects_shared_and_side_specific_object_options(tmp_path):
    left, right = _write_pair(tmp_path, {"age": [1]}, {"age": [1]})

    result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--object",
            "Data",
            "--left-object",
            "Old",
        ],
    )

    assert result.exit_code == 1
    assert "--object cannot be combined" in result.output


def test_compare_unknown_side_selector_lists_available_sheets(tmp_path):
    left = _write_workbook(
        tmp_path / "left.xlsx",
        {"First": {"value": [1]}, "Data": {"value": [1]}},
    )
    right = tmp_path / "right.csv"
    pd.DataFrame({"value": [1]}).to_csv(right, index=False)

    result = runner.invoke(
        app,
        ["compare", str(left), str(right), "--left-object", "Missing"],
    )

    assert result.exit_code == 1
    assert "Sheet 'Missing' was not found" in result.output
    assert "First" in result.output and "Data" in result.output


def _dataset(
    data: dict[str, list[object]],
    variable: VariableMetadata | None = None,
) -> Dataset:
    metadata = DatasetMetadata()
    if variable is not None:
        metadata.add_variable(variable)
    return Dataset(dataframe=pd.DataFrame(data), normalized_metadata=metadata)


def _render(comparison) -> str:
    with console.capture() as capture:
        show_dataset_comparison(comparison)
    return capture.get()


def _write_pair(tmp_path, left_data, right_data):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame(left_data).to_csv(left, index=False)
    pd.DataFrame(right_data).to_csv(right, index=False)
    return left, right


def _write_workbook(path, sheets):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for name, data in sheets.items():
            pd.DataFrame(data).to_excel(writer, sheet_name=name, index=False)
    return path


def _invoke_with_datasets(monkeypatch, left, right, *arguments):
    datasets = iter((left, right))
    monkeypatch.setattr(
        cli_module,
        "_read_dataset",
        lambda _path, **_kwargs: next(datasets),
    )
    return runner.invoke(app, ["compare", "left.sav", "right.sav", *arguments])
