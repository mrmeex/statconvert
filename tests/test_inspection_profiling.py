import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.inspection import (
    InspectionError,
    frequency_table,
    frequency_tables,
    missing_profile,
    profile_column,
    profile_columns,
    summarize_dataset,
)
from statconvert.metadata import DatasetMetadata, VariableMetadata


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            missing_values=[
                -99,
            ],
            storage_type="float64",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="name",
            label="Name",
            storage_type="object",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="active",
            label="Active",
            value_labels={
                True: "Active",
                False: "Inactive",
            },
            storage_type="bool",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="created",
            label="Created",
            storage_type="datetime64[ns]",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="group",
            label="Group",
            value_labels={
                "A": "Alpha",
                "B": "Beta",
            },
            storage_type="category",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="all_missing",
            label="All missing",
            storage_type="float64",
        )
    )

    dataframe = pd.DataFrame(
        {
            "age": [
                10.0,
                20.0,
                None,
                20.0,
                20.0,
                20.0,
            ],
            "name": [
                "Alice",
                "Bob",
                "Alice",
                None,
                "Bob",
                "Bob",
            ],
            "active": [
                True,
                False,
                True,
                True,
                False,
                False,
            ],
            "created": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-03",
                    None,
                    "2020-01-02",
                    "2020-01-02",
                    "2020-01-02",
                ]
            ),
            "group": pd.Series(
                [
                    "A",
                    "B",
                    "A",
                    "B",
                    "B",
                    "B",
                ],
                dtype="category",
            ),
            "all_missing": pd.Series(
                [
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                dtype="float64",
            ),
        }
    )

    dataframe.loc[5] = dataframe.loc[4]

    return Dataset(
        dataframe=dataframe,
        metadata={
            "backend": "csv",
        },
        source_format="csv",
        normalized_metadata=metadata,
    )


def test_summarize_dataset_counts_rows_and_columns():

    summary = summarize_dataset(
        _dataset()
    )

    assert summary.row_count == 6
    assert summary.column_count == 6


def test_summarize_dataset_counts_dtype_groups():

    summary = summarize_dataset(
        _dataset()
    )

    assert summary.numeric_columns == 2
    assert summary.text_columns == 1
    assert summary.boolean_columns == 1
    assert summary.datetime_columns == 1
    assert summary.categorical_columns == 1
    assert summary.other_columns == 0


def test_summarize_dataset_counts_metadata_columns():

    summary = summarize_dataset(
        _dataset()
    )

    assert summary.columns_with_variable_labels == 6
    assert summary.columns_with_value_labels == 2


def test_summarize_dataset_counts_missing_duplicates_and_memory():

    summary = summarize_dataset(
        _dataset()
    )

    assert summary.total_missing_cells == 9
    assert summary.duplicate_rows == 1
    assert isinstance(
        summary.memory_usage_bytes,
        int,
    )
    assert summary.memory_usage_bytes > 0


def test_profile_column_raises_for_missing_column():

    with pytest.raises(
        InspectionError,
        match="Column not found: missing",
    ):
        profile_column(
            _dataset(),
            "missing",
        )


def test_profile_column_profiles_numeric_column():

    profile = profile_column(
        _dataset(),
        "age",
    )

    assert profile.profile_type == "numeric"
    assert profile.non_missing_count == 5
    assert profile.missing_count == 1
    assert profile.unique_count == 2
    assert profile.numeric.count == 5
    assert profile.numeric.mean == 18.0
    assert profile.numeric.min == 10.0
    assert profile.numeric.max == 20.0


def test_profile_column_handles_all_missing_numeric_column():

    profile = profile_column(
        _dataset(),
        "all_missing",
    )

    assert profile.profile_type == "numeric"
    assert profile.non_missing_count == 0
    assert profile.numeric.count == 0
    assert profile.numeric.mean is None


def test_profile_column_profiles_string_column():

    profile = profile_column(
        _dataset(),
        "name",
    )

    assert profile.profile_type == "categorical"
    assert profile.categorical.count == 5
    assert profile.categorical.unique_count == 2
    assert profile.categorical.top_value == "Bob"
    assert profile.categorical.top_count == 3


def test_profile_column_maps_top_value_label():

    profile = profile_column(
        _dataset(),
        "group",
    )

    assert profile.profile_type == "categorical"
    assert profile.categorical.top_value == "B"
    assert profile.categorical.top_label == "Beta"


def test_profile_columns_respects_requested_order():

    profiles = profile_columns(
        _dataset(),
        columns=[
            "group",
            "age",
        ],
    )

    assert [
        profile.name
        for profile in profiles
    ] == [
        "group",
        "age",
    ]


def test_profile_columns_profiles_all_columns_by_default():

    profiles = profile_columns(
        _dataset()
    )

    assert [
        profile.name
        for profile in profiles
    ] == [
        "age",
        "name",
        "active",
        "created",
        "group",
        "all_missing",
    ]


def test_missing_profile_counts_missing_values():

    profiles = missing_profile(
        _dataset()
    )
    by_column = {
        profile.column: profile
        for profile in profiles
    }

    assert by_column["age"].missing_count == 1
    assert by_column["all_missing"].missing_count == 6


def test_missing_profile_includes_variable_label():

    profile = missing_profile(
        _dataset(),
        columns=[
            "age",
        ],
    )[0]

    assert profile.label == "Age"


def test_missing_profile_includes_metadata_missing_values():

    profile = missing_profile(
        _dataset(),
        columns=[
            "age",
        ],
    )[0]

    assert profile.metadata_missing_values == [
        -99,
    ]


def test_missing_profile_respects_requested_columns():

    profiles = missing_profile(
        _dataset(),
        columns=[
            "name",
        ],
    )

    assert len(
        profiles
    ) == 1
    assert profiles[0].column == "name"


def test_frequency_table_counts_values():

    table = frequency_table(
        _dataset(),
        "group",
    )

    assert [
        item.count
        for item in table.items
    ] == [
        4,
        2,
    ]


def test_frequency_table_calculates_percent_from_total_rows():

    table = frequency_table(
        _dataset(),
        "name",
    )
    bob = next(
        item
        for item in table.items
        if item.value == "Bob"
    )

    assert bob.percent == 50.0


def test_frequency_table_maps_value_labels():

    table = frequency_table(
        _dataset(),
        "group",
    )

    labels = {
        item.value: item.label
        for item in table.items
    }

    assert labels["A"] == "Alpha"
    assert labels["B"] == "Beta"


def test_frequency_table_respects_top_limit():

    table = frequency_table(
        _dataset(),
        "name",
        top=1,
    )

    assert len(
        table.items
    ) == 1
    assert table.items[0].value == "Bob"


def test_frequency_table_includes_missing_when_requested():

    table = frequency_table(
        _dataset(),
        "name",
        include_missing=True,
    )

    assert any(
        pd.isna(
            item.value
        )
        for item in table.items
    )
    assert table.missing_count == 1


def test_frequency_tables_chooses_categorical_and_value_labelled_columns():

    tables = frequency_tables(
        _dataset()
    )

    assert [
        table.column
        for table in tables
    ] == [
        "name",
        "active",
        "group",
    ]


def test_frequency_tables_respects_max_unique():

    dataset = _dataset()
    dataset.dataframe["free_text"] = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
    ]

    tables = frequency_tables(
        dataset,
        max_unique=3,
    )

    assert "free_text" not in {
        table.column
        for table in tables
    }


def test_frequency_tables_respects_requested_columns():

    tables = frequency_tables(
        _dataset(),
        columns=[
            "age",
        ],
    )

    assert len(
        tables
    ) == 1
    assert tables[0].column == "age"
