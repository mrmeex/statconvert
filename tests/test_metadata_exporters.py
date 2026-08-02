import pandas as pd

from statconvert.dataset import Dataset
from statconvert.metadata import (
    DatasetMetadata,
    VariableMetadata,
    column_labels_from_metadata,
    display_widths_from_metadata,
    missing_ranges_from_metadata,
    missing_values_from_metadata,
    variable_value_labels_from_metadata,
)


def _metadata_dataset() -> Dataset:
    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age in years",
            missing_values=[
                -99,
            ],
            missing_ranges=[{"lo": -10, "hi": -1}],
            display_width=12,
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="group",
            label="",
            value_labels={
                1: "Control",
                2: "Treatment",
            },
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="empty",
            label="",
            value_labels={},
            missing_values=[],
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="not_in_dataframe",
            label="Hidden variable",
            value_labels={
                1: "Hidden",
            },
            missing_values=[
                -1,
            ],
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, -99],
                "group": [1, 2],
                "empty": ["x", "y"],
            }
        ),
        normalized_metadata=metadata,
    )


def test_column_labels_from_metadata_returns_normalized_labels():

    assert column_labels_from_metadata(_metadata_dataset()) == {
        "age": "Age in years",
    }


def test_variable_value_labels_from_metadata_returns_normalized_value_labels():

    assert variable_value_labels_from_metadata(_metadata_dataset()) == {
        "group": {
            1: "Control",
            2: "Treatment",
        },
    }


def test_missing_values_from_metadata_returns_normalized_missing_values():

    assert missing_values_from_metadata(_metadata_dataset()) == {
        "age": [
            -99,
        ],
    }


def test_missing_ranges_and_display_width_exporters_use_normalized_metadata():
    dataset = _metadata_dataset()

    assert missing_ranges_from_metadata(dataset) == {
        "age": [{"lo": -10, "hi": -1}]
    }
    assert display_widths_from_metadata(dataset) == {"age": 12}


def test_exporters_only_include_columns_present_in_dataframe():

    dataset = _metadata_dataset()

    assert "not_in_dataframe" not in column_labels_from_metadata(
        dataset
    )
    assert "not_in_dataframe" not in variable_value_labels_from_metadata(
        dataset
    )
    assert "not_in_dataframe" not in missing_values_from_metadata(
        dataset
    )


def test_exporters_ignore_empty_labels_and_empty_mappings():

    dataset = _metadata_dataset()

    assert "empty" not in column_labels_from_metadata(
        dataset
    )
    assert "empty" not in variable_value_labels_from_metadata(
        dataset
    )
    assert "empty" not in missing_values_from_metadata(
        dataset
    )
