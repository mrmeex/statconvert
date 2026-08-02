from types import SimpleNamespace

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


def _dataset_with_metadata(
    metadata: DatasetMetadata
) -> Dataset:
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
                "sex": [1, 2],
                "income": [100, -99],
            }
        ),
        normalized_metadata=metadata,
    )


def test_get_normalized_metadata_creates_metadata_from_dataframe_columns():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "name": ["Alice", "Bob"],
                "age": [25, 30],
            }
        ),
        metadata={
            "backend": "csv",
        },
        source_format="csv",
    )

    metadata = dataset.get_normalized_metadata()

    assert metadata.source_format == "csv"
    assert metadata.source_backend == "csv"
    assert list(metadata.variables) == [
        "name",
        "age",
    ]
    assert metadata.get_variable("age").storage_type == "int64"


def test_variable_labels_returns_labels_from_normalized_metadata():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age in years",
        )
    )

    assert _dataset_with_metadata(metadata).variable_labels() == {
        "age": "Age in years",
    }


def test_value_labels_returns_value_labels_from_normalized_metadata():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="sex",
            value_labels={
                1: "Male",
                2: "Female",
            },
        )
    )

    assert _dataset_with_metadata(metadata).value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_missing_values_returns_missing_values_from_normalized_metadata():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="income",
            missing_values=[
                -99,
            ],
        )
    )

    assert _dataset_with_metadata(metadata).missing_values() == {
        "income": [
            -99,
        ],
    }


def test_storage_types_returns_normalized_storage_types():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            storage_type="int32",
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
            }
        ),
        normalized_metadata=metadata,
    )

    assert dataset.storage_types() == {
        "age": "int32",
    }


def test_storage_types_falls_back_to_dataframe_dtypes():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
            }
        ),
        normalized_metadata=metadata,
    )

    assert dataset.storage_types() == {
        "age": "int64",
    }


def test_variable_metadata_returns_known_variable_metadata():

    metadata = DatasetMetadata()
    variable = VariableMetadata(
        name="age",
        label="Age",
    )
    metadata.add_variable(
        variable
    )

    assert _dataset_with_metadata(metadata).variable_metadata("age") == variable


def test_variable_metadata_returns_none_for_unknown_variable():

    assert _dataset_with_metadata(
        DatasetMetadata()
    ).variable_metadata("unknown") is None


def test_display_formats_returns_only_variables_with_display_formats():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            display_format="F8.0",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="sex",
        )
    )

    assert _dataset_with_metadata(metadata).display_formats() == {
        "age": "F8.0",
    }


def test_measurement_levels_returns_only_variables_with_measure_values():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="sex",
        )
    )

    assert _dataset_with_metadata(metadata).measurement_levels() == {
        "age": "scale",
    }


def test_has_metadata_is_false_for_plain_dtype_only_metadata():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
            }
        )
    )

    assert dataset.has_metadata() is False


def test_has_metadata_is_true_when_labels_exist():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
        )
    )

    assert _dataset_with_metadata(metadata).has_metadata() is True


def test_has_metadata_is_true_when_value_labels_exist():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="sex",
            value_labels={
                1: "Male",
            },
        )
    )

    assert _dataset_with_metadata(metadata).has_metadata() is True


def test_metadata_summary_returns_correct_counts():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            display_format="F8.0",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="sex",
            value_labels={
                1: "Male",
            },
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="income",
            missing_values=[
                -99,
            ],
        )
    )

    assert _dataset_with_metadata(metadata).metadata_summary() == {
        "variables": 3,
        "variable_labels": 1,
        "value_label_sets": 1,
        "missing_value_sets": 1,
        "missing_range_sets": 0,
        "display_formats": 1,
        "measurement_levels": 1,
        "has_metadata": True,
    }


def test_legacy_pyreadstat_fallback_still_works_for_variable_labels():

    legacy_metadata = SimpleNamespace(
        column_names_to_labels={
            "sex": "Gender",
        },
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "sex": [1, 2],
            }
        ),
        metadata={
            "pyreadstat": legacy_metadata,
        },
        normalized_metadata=DatasetMetadata(),
    )

    assert dataset.variable_labels() == {
        "sex": "Gender",
    }


def test_legacy_pyreadstat_fallback_still_works_for_value_labels():

    legacy_metadata = SimpleNamespace(
        variable_value_labels={
            "sex": {
                1: "Male",
                2: "Female",
            },
        },
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "sex": [1, 2],
            }
        ),
        metadata={
            "pyreadstat": legacy_metadata,
        },
        normalized_metadata=DatasetMetadata(),
    )

    assert dataset.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }
