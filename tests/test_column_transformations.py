import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    DropColumnsTransformation,
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
            "Imported for testing.",
        ],
        raw_metadata={
            "raw": "kept",
        },
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            value_labels={},
            storage_type="int64",
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
    metadata.add_variable(
        VariableMetadata(
            name="notes",
            label="Notes",
            storage_type="object",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
                "sex": [1, 2],
                "income": [100.0, 200.0],
                "notes": ["a", "b"],
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


def test_selecting_one_column_returns_only_that_column():

    result = SelectColumnsTransformation(
        columns=[
            "age",
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
    ]


def test_selecting_multiple_columns_preserves_requested_order():

    result = SelectColumnsTransformation(
        columns=[
            "income",
            "age",
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "income",
        "age",
    ]


def test_selecting_missing_column_raises_by_default():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        SelectColumnsTransformation(
            columns=[
                "age",
                "missing",
            ]
        ).apply(
            _dataset()
        )


def test_selecting_missing_column_with_ignore_missing_skips_it():

    result = SelectColumnsTransformation(
        columns=[
            "missing",
            "sex",
        ],
        ignore_missing=True,
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "sex",
    ]


def test_selecting_only_missing_columns_with_ignore_missing_raises():

    with pytest.raises(
        TransformationError,
        match="No requested columns were found",
    ):
        SelectColumnsTransformation(
            columns=[
                "missing",
            ],
            ignore_missing=True,
        ).apply(
            _dataset()
        )


def test_selecting_empty_column_list_raises():

    with pytest.raises(
        TransformationError,
        match="At least one column",
    ):
        SelectColumnsTransformation(
            columns=[]
        ).apply(
            _dataset()
        )


def test_select_does_not_mutate_original_dataset():

    dataset = _dataset()

    result = SelectColumnsTransformation(
        columns=[
            "age",
        ]
    ).apply(
        dataset
    )

    result.dataframe.loc[0, "age"] = 99

    assert dataset.columns == [
        "age",
        "sex",
        "income",
        "notes",
    ]
    assert dataset.dataframe.loc[0, "age"] == 25


def test_select_filters_normalized_metadata_to_selected_columns():

    result = SelectColumnsTransformation(
        columns=[
            "sex",
            "age",
        ]
    ).apply(
        _dataset()
    )

    metadata = result.get_normalized_metadata()

    assert list(metadata.variables) == [
        "sex",
        "age",
    ]
    assert metadata.source_format == "sav"
    assert metadata.source_backend == "pyreadstat"
    assert metadata.dataset_label == "Survey dataset"
    assert metadata.notes == [
        "Imported for testing.",
    ]
    assert metadata.raw_metadata == {
        "raw": "kept",
    }


def test_select_preserves_labels_and_value_labels_for_selected_columns():

    result = SelectColumnsTransformation(
        columns=[
            "sex",
        ]
    ).apply(
        _dataset()
    )

    assert result.variable_labels() == {
        "sex": "Sex",
    }
    assert result.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_dropping_one_column_removes_it():

    result = DropColumnsTransformation(
        columns=[
            "notes",
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "sex",
        "income",
    ]


def test_dropping_multiple_columns_removes_them():

    result = DropColumnsTransformation(
        columns=[
            "notes",
            "income",
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "sex",
    ]


def test_dropping_missing_column_raises_by_default():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        DropColumnsTransformation(
            columns=[
                "missing",
            ]
        ).apply(
            _dataset()
        )


def test_dropping_missing_column_with_ignore_missing_ignores_it():

    result = DropColumnsTransformation(
        columns=[
            "missing",
            "notes",
        ],
        ignore_missing=True,
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "sex",
        "income",
    ]


def test_dropping_all_columns_raises():

    with pytest.raises(
        TransformationError,
        match="Cannot drop all columns",
    ):
        DropColumnsTransformation(
            columns=[
                "age",
                "sex",
                "income",
                "notes",
            ]
        ).apply(
            _dataset()
        )


def test_dropping_empty_column_list_raises():

    with pytest.raises(
        TransformationError,
        match="At least one column",
    ):
        DropColumnsTransformation(
            columns=[]
        ).apply(
            _dataset()
        )


def test_drop_does_not_mutate_original_dataset():

    dataset = _dataset()

    result = DropColumnsTransformation(
        columns=[
            "notes",
        ]
    ).apply(
        dataset
    )

    result.dataframe.loc[0, "age"] = 99

    assert dataset.columns == [
        "age",
        "sex",
        "income",
        "notes",
    ]
    assert dataset.dataframe.loc[0, "age"] == 25


def test_drop_filters_normalized_metadata_to_remaining_columns():

    result = DropColumnsTransformation(
        columns=[
            "notes",
            "income",
        ]
    ).apply(
        _dataset()
    )

    assert list(
        result.get_normalized_metadata().variables
    ) == [
        "age",
        "sex",
    ]


def test_drop_preserves_labels_and_value_labels_for_remaining_columns():

    result = DropColumnsTransformation(
        columns=[
            "notes",
            "income",
        ]
    ).apply(
        _dataset()
    )

    assert result.variable_labels() == {
        "age": "Age",
        "sex": "Sex",
    }
    assert result.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_pipeline_can_apply_select_columns_transformation():

    result = TransformationPipeline(
        [
            SelectColumnsTransformation(
                columns=[
                    "age",
                    "sex",
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "sex",
    ]


def test_pipeline_can_apply_drop_columns_transformation():

    result = TransformationPipeline(
        [
            DropColumnsTransformation(
                columns=[
                    "notes",
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "sex",
        "income",
    ]


def test_pipeline_can_apply_select_followed_by_drop_in_order():

    result = TransformationPipeline(
        [
            SelectColumnsTransformation(
                columns=[
                    "income",
                    "sex",
                    "age",
                ]
            ),
            DropColumnsTransformation(
                columns=[
                    "sex",
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "income",
        "age",
    ]
