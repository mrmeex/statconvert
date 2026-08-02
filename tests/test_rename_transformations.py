import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    DropColumnsTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label="Survey dataset",
        notes=[
            "Rename test.",
        ],
        raw_metadata={
            "raw": "kept",
        },
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            missing_values=[
                -99,
            ],
            storage_type="int64",
            display_format="F8.0",
            measure="scale",
            role="input",
            width=8,
            decimals=0,
            raw={
                "original": "age",
            },
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="sex",
            label="Sex",
            value_labels={
                1: "Male",
                2: "Female",
            },
            storage_type="int64",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="income",
            label="Income",
            storage_type="float64",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, -99],
                "sex": [1, 2],
                "income": [100.0, 200.0],
            }
        ),
        metadata={
            "backend": "pyreadstat",
            "legacy": {
                "kept": True,
            },
        },
        source_format="sav",
        source_file="survey.sav",
        normalized_metadata=metadata,
    )


def test_renaming_one_column_changes_dataframe_column_name():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
        }
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "Age",
        "sex",
        "income",
    ]


def test_renaming_multiple_columns_works():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
            "sex": "Gender",
        }
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "Age",
        "Gender",
        "income",
    ]


def test_renaming_preserves_original_column_order():

    result = RenameColumnsTransformation(
        rename_map={
            "income": "Income",
            "age": "Age",
        }
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "Age",
        "sex",
        "Income",
    ]


def test_renaming_missing_column_raises_by_default():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        RenameColumnsTransformation(
            rename_map={
                "missing": "Missing",
            }
        ).apply(
            _dataset()
        )


def test_renaming_missing_column_with_ignore_missing_skips_it():

    result = RenameColumnsTransformation(
        rename_map={
            "missing": "Missing",
            "sex": "Gender",
        },
        ignore_missing=True,
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "Gender",
        "income",
    ]


def test_renaming_only_missing_columns_with_ignore_missing_raises():

    with pytest.raises(
        TransformationError,
        match="No requested columns were found",
    ):
        RenameColumnsTransformation(
            rename_map={
                "missing": "Missing",
            },
            ignore_missing=True,
        ).apply(
            _dataset()
        )


def test_empty_rename_map_raises():

    with pytest.raises(
        TransformationError,
        match="At least one column rename",
    ):
        RenameColumnsTransformation(
            rename_map={}
        ).apply(
            _dataset()
        )


def test_empty_target_name_raises():

    with pytest.raises(
        TransformationError,
        match="Target column name cannot be empty",
    ):
        RenameColumnsTransformation(
            rename_map={
                "age": "",
            }
        ).apply(
            _dataset()
        )


def test_whitespace_only_target_name_raises():

    with pytest.raises(
        TransformationError,
        match="Target column name cannot be empty",
    ):
        RenameColumnsTransformation(
            rename_map={
                "age": "   ",
            }
        ).apply(
            _dataset()
        )


def test_duplicate_target_names_raise():

    with pytest.raises(
        TransformationError,
        match="duplicate columns",
    ):
        RenameColumnsTransformation(
            rename_map={
                "age": "person",
                "sex": "person",
            }
        ).apply(
            _dataset()
        )


def test_target_name_colliding_with_existing_non_renamed_column_raises():

    with pytest.raises(
        TransformationError,
        match="Target column already exists: sex",
    ):
        RenameColumnsTransformation(
            rename_map={
                "age": "sex",
            }
        ).apply(
            _dataset()
        )


def test_renaming_original_dataset_is_not_mutated():

    dataset = _dataset()

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
        }
    ).apply(
        dataset
    )

    result.dataframe.loc[0, "Age"] = 99

    assert dataset.columns == [
        "age",
        "sex",
        "income",
    ]
    assert dataset.dataframe.loc[0, "age"] == 25


def test_renaming_normalized_metadata_is_renamed():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
            "sex": "Gender",
        }
    ).apply(
        _dataset()
    )
    metadata = result.get_normalized_metadata()

    assert list(metadata.variables) == [
        "Age",
        "Gender",
        "income",
    ]
    assert metadata.get_variable("Age").name == "Age"
    assert metadata.get_variable("Gender").name == "Gender"
    assert metadata.source_format == "sav"
    assert metadata.source_backend == "pyreadstat"
    assert metadata.dataset_label == "Survey dataset"
    assert metadata.notes == [
        "Rename test.",
    ]
    assert metadata.raw_metadata == {
        "raw": "kept",
    }


def test_variable_labels_remain_attached_to_renamed_column():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
        }
    ).apply(
        _dataset()
    )

    assert result.variable_labels()["Age"] == "Age"


def test_value_labels_remain_attached_to_renamed_column():

    result = RenameColumnsTransformation(
        rename_map={
            "sex": "Gender",
        }
    ).apply(
        _dataset()
    )

    assert result.value_labels() == {
        "Gender": {
            1: "Male",
            2: "Female",
        },
    }


def test_missing_values_remain_attached_to_renamed_column():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
        }
    ).apply(
        _dataset()
    )

    assert result.missing_values() == {
        "Age": [
            -99,
        ],
    }


def test_metadata_for_non_renamed_columns_remains_intact():

    result = RenameColumnsTransformation(
        rename_map={
            "age": "Age",
        }
    ).apply(
        _dataset()
    )

    assert result.variable_metadata("income").label == "Income"
    assert result.variable_metadata("income").storage_type == "float64"


def test_pipeline_can_apply_rename_columns_transformation():

    result = TransformationPipeline(
        [
            RenameColumnsTransformation(
                rename_map={
                    "age": "Age",
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "Age",
        "sex",
        "income",
    ]


def test_pipeline_can_apply_select_followed_by_rename():

    result = TransformationPipeline(
        [
            SelectColumnsTransformation(
                columns=[
                    "sex",
                    "age",
                ]
            ),
            RenameColumnsTransformation(
                rename_map={
                    "sex": "Gender",
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "Gender",
        "age",
    ]


def test_pipeline_can_apply_rename_followed_by_drop():

    result = TransformationPipeline(
        [
            RenameColumnsTransformation(
                rename_map={
                    "sex": "Gender",
                }
            ),
            DropColumnsTransformation(
                columns=[
                    "Gender",
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "income",
    ]
