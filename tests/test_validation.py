import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.inspection import (
    ValidationIssue,
)
from statconvert.inspection.validation import (
    validate_basic_structure,
    validate_data_quality,
    validate_metadata_consistency,
    validate_target_compatibility,
)
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.ui.inspection import console, show_validation_issues


runner = CliRunner()


def test_empty_dataset_returns_warning():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "age": [],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "empty_dataset",
        "warning",
    )


def test_no_columns_returns_error():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame()
        )
    )

    assert _has_issue(
        issues,
        "no_columns",
        "error",
    )


def test_duplicate_column_names_return_error():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame(
                [
                    [
                        1,
                        2,
                    ],
                ],
                columns=[
                    "age",
                    "age",
                ],
            )
        )
    )

    assert _has_issue(
        issues,
        "duplicate_columns",
        "error",
    )


def test_empty_column_name_returns_error():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    " ": [
                        1,
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "empty_column_name",
        "error",
    )


def test_duplicate_rows_return_warning():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "age": [
                        1,
                        1,
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "duplicate_rows",
        "warning",
    )


def test_fully_empty_column_returns_warning():

    issues = validate_basic_structure(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "empty": [
                        None,
                        None,
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "empty_column",
        "warning",
    )


def test_extra_metadata_variable_returns_warning():

    issues = validate_metadata_consistency(
        _dataset_with_metadata(
            dataframe=pd.DataFrame(
                {
                    "age": [
                        1,
                    ],
                }
            ),
            metadata_variables=[
                VariableMetadata(
                    name="age",
                ),
                VariableMetadata(
                    name="extra",
                ),
            ],
        )
    )

    assert _has_issue(
        issues,
        "metadata_extra_variable",
        "warning",
    )


def test_missing_metadata_variable_returns_warning():

    issues = validate_metadata_consistency(
        _dataset_with_metadata(
            dataframe=pd.DataFrame(
                {
                    "age": [
                        1,
                    ],
                    "name": [
                        "Ada",
                    ],
                }
            ),
            metadata_variables=[
                VariableMetadata(
                    name="age",
                ),
            ],
        )
    )

    assert _has_issue(
        issues,
        "metadata_missing_variable",
        "warning",
    )


def test_value_labels_for_missing_column_return_warning():

    issues = validate_metadata_consistency(
        _dataset_with_metadata(
            dataframe=pd.DataFrame(
                {
                    "age": [
                        1,
                    ],
                }
            ),
            metadata_variables=[
                VariableMetadata(
                    name="status",
                    value_labels={
                        1: "Active",
                    },
                ),
            ],
        )
    )

    assert _has_issue(
        issues,
        "value_labels_for_missing_column",
        "warning",
    )


def test_unused_value_labels_return_warning():

    issues = validate_metadata_consistency(
        _dataset_with_metadata(
            dataframe=pd.DataFrame(
                {
                    "status": [
                        3,
                        4,
                    ],
                }
            ),
            metadata_variables=[
                VariableMetadata(
                    name="status",
                    value_labels={
                        1: "Active",
                        2: "Inactive",
                    },
                ),
            ],
        )
    )

    assert _has_issue(
        issues,
        "unused_value_labels",
        "warning",
    )


def test_metadata_value_validation_handles_unhashable_observed_values():
    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="answers",
            value_labels={"yes": "Yes"},
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "answers": pd.Series(
                    [["yes"], ["no"], ["yes"]],
                    dtype="object",
                )
            }
        ),
        normalized_metadata=metadata,
    )

    issues = validate_metadata_consistency(dataset)

    assert _has_issue(issues, "unused_value_labels", "warning")


def test_metadata_missing_values_return_info():

    issues = validate_metadata_consistency(
        _dataset_with_metadata(
            dataframe=pd.DataFrame(
                {
                    "score": [
                        10,
                    ],
                }
            ),
            metadata_variables=[
                VariableMetadata(
                    name="score",
                    missing_values=[
                        999,
                    ],
                ),
            ],
        )
    )

    assert _has_issue(
        issues,
        "metadata_missing_values_defined",
        "info",
    )


def test_high_missingness_returns_warning():

    issues = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "score": [
                        1,
                        None,
                        None,
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "high_missingness",
        "warning",
    )


def test_constant_column_returns_info():

    issues = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "school": [
                        "alchemy",
                        "alchemy",
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "constant_column",
        "info",
    )


def test_high_cardinality_text_column_returns_info():

    issues = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "name": [
                        f"name_{index}"
                        for index in range(
                            20
                        )
                    ],
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "high_cardinality",
        "info",
    )


def test_mixed_object_types_return_warning():

    issues = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "mixed": pd.Series(
                        [
                            1,
                            "two",
                        ],
                        dtype="object",
                    ),
                }
            )
        )
    )

    assert _has_issue(
        issues,
        "mixed_object_types",
        "warning",
    )


def test_mixed_type_scan_preserves_obvious_type_categories():
    numeric = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {"numeric": pd.Series([1, 2.5], dtype="object")}
            )
        )
    )
    boolean_numeric = validate_data_quality(
        Dataset(
            dataframe=pd.DataFrame(
                {"mixed": pd.Series([True, 1], dtype="object")}
            )
        )
    )

    assert not _has_issue(numeric, "mixed_object_types", "warning")
    assert _has_issue(boolean_numeric, "mixed_object_types", "warning")


def test_csv_target_warns_about_metadata_not_preserved():

    issues = validate_target_compatibility(
        _labelled_dataset(),
        ".csv",
    )

    assert _has_issue(
        issues,
        "csv_metadata_not_preserved",
        "warning",
    )


def test_target_without_metadata_support_warns_when_labels_exist():

    issues = validate_target_compatibility(
        _labelled_dataset(),
        ".xlsx",
    )

    assert _has_issue(
        issues,
        "metadata_may_not_be_preserved",
        "warning",
    )


def test_dta_target_warns_for_long_column_names():

    issues = validate_target_compatibility(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "this_column_name_is_far_too_long_for_stata": [
                        1,
                    ],
                }
            )
        ),
        ".dta",
    )

    assert _has_issue(
        issues,
        "stata_column_name_too_long",
        "warning",
    )


def test_dta_target_warns_for_invalid_column_names():

    issues = validate_target_compatibility(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "bad name": [
                        1,
                    ],
                }
            )
        ),
        ".dta",
    )

    assert _has_issue(
        issues,
        "stata_invalid_column_name",
        "warning",
    )


def test_excel_target_errors_when_row_limit_exceeded():

    issues = validate_target_compatibility(
        Dataset(
            dataframe=pd.DataFrame(
                {
                    "id": range(
                        1_048_577
                    ),
                }
            )
        ),
        ".xlsx",
    )

    assert _has_issue(
        issues,
        "excel_row_limit_exceeded",
        "error",
    )


def test_show_validation_issues_handles_no_issues():

    with console.capture() as capture:
        show_validation_issues(
            []
        )

    assert "No validation issues found" in capture.get()


def test_show_validation_issues_handles_info_warning_and_error():

    issues = [
        ValidationIssue(
            severity="info",
            code="readable",
            message="Readable.",
        ),
        ValidationIssue(
            severity="warning",
            code="duplicate_rows",
            message="Duplicates.",
            column="id",
        ),
        ValidationIssue(
            severity="error",
            code="no_columns",
            message="No columns.",
        ),
    ]

    with console.capture() as capture:
        show_validation_issues(
            issues
        )

    output = capture.get()

    assert "readable" in output
    assert "duplicate_rows" in output
    assert "no_columns" in output


def test_show_validation_issues_handles_target_format():

    with console.capture() as capture:
        show_validation_issues(
            [
                ValidationIssue(
                    severity="info",
                    code="readable",
                    message="Readable.",
                ),
            ],
            target_format=".csv",
        )

    assert "for .csv" in capture.get()


def test_validate_command_reads_csv_successfully(tmp_path):

    input_file = _write_csv(
        tmp_path,
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(
                input_file
            ),
        ],
    )

    assert result.exit_code == 0
    assert "Validation Issues" in result.output


def test_validate_command_strict_returns_nonzero_on_warning(tmp_path):

    input_file = _write_duplicate_csv(
        tmp_path,
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(
                input_file
            ),
            "--strict",
        ],
    )

    assert result.exit_code == 1
    assert "duplicate_rows" in result.output


def test_validate_command_returns_nonzero_on_error(tmp_path):

    input_file = _write_csv(
        tmp_path,
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(
                input_file
            ),
            "--to",
            "unsupported",
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported target format" in result.output


def test_validate_command_outputs_json(tmp_path):

    input_file = _write_csv(
        tmp_path,
    )

    result = runner.invoke(
        app,
        [
            "validate",
            str(
                input_file
            ),
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(
        result.output
    )

    assert data[0]["code"] == "readable"


def _dataset_with_metadata(
    dataframe: pd.DataFrame,
    metadata_variables: list[VariableMetadata],
) -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
    )

    for variable in metadata_variables:
        metadata.add_variable(
            variable
        )

    return Dataset(
        dataframe=dataframe,
        normalized_metadata=metadata,
    )


def _labelled_dataset() -> Dataset:
    return _dataset_with_metadata(
        dataframe=pd.DataFrame(
            {
                "status": [
                    1,
                    2,
                ],
            }
        ),
        metadata_variables=[
            VariableMetadata(
                name="status",
                label="Status",
                value_labels={
                    1: "Active",
                    2: "Inactive",
                },
            ),
        ],
    )


def _write_csv(
    tmp_path
):
    input_file = tmp_path / "validate.csv"
    pd.DataFrame(
        {
            "id": [
                1,
                2,
            ],
            "name": [
                "Ada",
                "Grace",
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    return input_file


def _write_duplicate_csv(
    tmp_path
):
    input_file = tmp_path / "validate_duplicates.csv"
    pd.DataFrame(
        {
            "id": [
                1,
                1,
            ],
            "name": [
                "Ada",
                "Ada",
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    return input_file


def _has_issue(
    issues: list[ValidationIssue],
    code: str,
    severity: str,
) -> bool:
    return any(
        issue.code == code and issue.severity == severity
        for issue in issues
    )
