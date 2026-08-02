from types import SimpleNamespace

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


def test_variable_metadata_creation():

    variable = VariableMetadata(
        name="sex",
        label="Gender",
        value_labels={
            1: "Male",
            2: "Female",
        },
        missing_values=[
            9,
        ],
        storage_type="float64",
    )

    assert variable.name == "sex"
    assert variable.has_label()
    assert variable.has_value_labels()
    assert variable.has_missing_values()


def test_dataset_metadata_add_variable():

    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
    )
    variable = VariableMetadata(
        name="age",
        label="Age",
    )

    metadata.add_variable(
        variable
    )

    assert metadata.get_variable("age") == variable
    assert metadata.get_variable("missing") is None


def test_dataset_metadata_variable_labels():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="score",
        )
    )

    assert metadata.variable_labels() == {
        "age": "Age",
    }


def test_dataset_metadata_value_labels():

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

    assert metadata.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_dataset_metadata_missing_values():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="income",
            missing_values=[
                -99,
            ],
        )
    )

    assert metadata.missing_values() == {
        "income": [
            -99,
        ],
    }


def test_get_normalized_metadata_creates_variables_from_dataframe():

    dataframe = pd.DataFrame(
        {
            "name": ["Alice", "Bob"],
            "age": [25, 30],
        }
    )
    dataset = Dataset(
        dataframe=dataframe,
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
    assert dataset.get_normalized_metadata() is metadata


def test_dataset_variable_labels_prefers_normalized_metadata():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age in years",
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

    assert dataset.variable_labels() == {
        "age": "Age in years",
    }


def test_dataset_variable_labels_falls_back_to_legacy_pyreadstat_metadata():

    legacy_metadata = SimpleNamespace(
        column_names_to_labels={
            "sex": "Gender",
        },
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
    )

    assert dataset.variable_labels() == {
        "sex": "Gender",
    }
    assert dataset.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_dataset_missing_values_prefers_normalized_metadata():

    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="income",
            missing_values=[
                -99,
            ],
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "income": [10, -99],
            }
        ),
        normalized_metadata=metadata,
    )

    assert dataset.missing_values() == {
        "income": [
            -99,
        ],
    }
