import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    ConvertTypesTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
        dataset_label="Type test",
        notes=[
            "Testing conversions.",
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
            storage_type="object",
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
            name="group",
            label="Group",
            value_labels={
                1: "Control",
                2: "Treatment",
            },
            storage_type="object",
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
            storage_type="object",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="birth_date",
            label="Birth date",
            storage_type="object",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": ["25", "30", None],
                "income": ["1.5", "2.75", None],
                "group": ["1", "2", "1"],
                "name": ["Alice", "Bob", 3],
                "active": ["true", "No", "1"],
                "birth_date": [
                    "2020-01-01",
                    "2020-01-02",
                    None,
                ],
                "invalid": ["1", "bad", "3"],
                "fraction": ["1.2", "2", "3"],
            }
        ),
        metadata={
            "backend": "csv",
            "legacy": {
                "kept": True,
            },
        },
        source_format="csv",
        source_file="types.csv",
        normalized_metadata=metadata,
    )


def test_empty_type_map_raises():

    with pytest.raises(
        TransformationError,
        match="At least one type conversion",
    ):
        ConvertTypesTransformation(
            type_map={}
        )


def test_missing_column_raises():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        ConvertTypesTransformation(
            type_map={
                "missing": "int",
            }
        ).apply(
            _dataset()
        )


def test_unsupported_target_type_raises():

    with pytest.raises(
        TransformationError,
        match="Unsupported target type",
    ):
        ConvertTypesTransformation(
            type_map={
                "age": "currency",
            }
        )


def test_invalid_errors_mode_raises():

    with pytest.raises(
        TransformationError,
        match="Unsupported errors mode",
    ):
        ConvertTypesTransformation(
            type_map={
                "age": "int",
            },
            errors="skip",
        )


def test_original_dataset_is_not_mutated():

    dataset = _dataset()

    result = ConvertTypesTransformation(
        type_map={
            "age": "int",
        }
    ).apply(
        dataset
    )

    result.dataframe.loc[0, "age"] = 99

    assert str(
        dataset.dataframe["age"].dtype
    ) in {
        "object",
        "str",
    }
    assert dataset.dataframe.loc[0, "age"] == "25"


def test_string_conversion_uses_pandas_string_dtype():

    result = ConvertTypesTransformation(
        type_map={
            "name": "string",
        }
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["name"].dtype
    ) == "string"


def test_integer_conversion_converts_numeric_strings_to_nullable_integer():

    result = ConvertTypesTransformation(
        type_map={
            "age": "int",
        }
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["age"].dtype
    ) == "Int64"
    assert result.dataframe["age"].tolist() == [
        25,
        30,
        pd.NA,
    ]


def test_integer_conversion_preserves_missing_values():

    result = ConvertTypesTransformation(
        type_map={
            "age": "integer",
        }
    ).apply(
        _dataset()
    )

    assert pd.isna(
        result.dataframe.loc[2, "age"]
    )


def test_non_integer_values_raise_with_errors_raise():

    with pytest.raises(
        TransformationError,
        match="Failed converting column 'fraction' to 'integer'",
    ):
        ConvertTypesTransformation(
            type_map={
                "fraction": "integer",
            }
        ).apply(
            _dataset()
        )


def test_invalid_integer_values_become_missing_with_errors_coerce():

    result = ConvertTypesTransformation(
        type_map={
            "invalid": "int",
        },
        errors="coerce",
    ).apply(
        _dataset()
    )

    assert result.dataframe["invalid"].tolist() == [
        1,
        pd.NA,
        3,
    ]


def test_invalid_integer_conversion_is_unchanged_with_errors_ignore():

    result = ConvertTypesTransformation(
        type_map={
            "invalid": "int",
        },
        errors="ignore",
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["invalid"].dtype
    ) in {
        "object",
        "str",
    }
    assert result.dataframe["invalid"].tolist() == [
        "1",
        "bad",
        "3",
    ]


def test_float_conversion_converts_numeric_strings_to_float():

    result = ConvertTypesTransformation(
        type_map={
            "income": "float",
        }
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["income"].dtype
    ) == "float64"
    assert result.dataframe["income"].tolist()[:2] == [
        1.5,
        2.75,
    ]


def test_invalid_float_values_follow_raise_coerce_ignore():

    with pytest.raises(
        TransformationError,
        match="Failed converting column 'invalid' to 'float'",
    ):
        ConvertTypesTransformation(
            type_map={
                "invalid": "float",
            }
        ).apply(
            _dataset()
        )

    coerced = ConvertTypesTransformation(
        type_map={
            "invalid": "float",
        },
        errors="coerce",
    ).apply(
        _dataset()
    )
    ignored = ConvertTypesTransformation(
        type_map={
            "invalid": "float",
        },
        errors="ignore",
    ).apply(
        _dataset()
    )

    assert pd.isna(
        coerced.dataframe.loc[1, "invalid"]
    )
    assert ignored.dataframe["invalid"].tolist() == [
        "1",
        "bad",
        "3",
    ]


def test_boolean_conversion_converts_true_false_strings():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "flag": ["true", "false"],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "flag": "bool",
        }
    ).apply(
        dataset
    )

    assert str(
        result.dataframe["flag"].dtype
    ) == "boolean"
    assert result.dataframe["flag"].tolist() == [
        True,
        False,
    ]


def test_boolean_conversion_converts_yes_no_strings():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "flag": ["yes", "No"],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "flag": "boolean",
        }
    ).apply(
        dataset
    )

    assert result.dataframe["flag"].tolist() == [
        True,
        False,
    ]


def test_boolean_conversion_converts_one_zero_values():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "flag": [1, 0],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "flag": "bool",
        }
    ).apply(
        dataset
    )

    assert result.dataframe["flag"].tolist() == [
        True,
        False,
    ]


def test_boolean_conversion_handles_custom_true_false_values():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "flag": ["enabled", "disabled"],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "flag": "bool",
        },
        true_values=[
            "enabled",
        ],
        false_values=[
            "disabled",
        ],
    ).apply(
        dataset
    )

    assert result.dataframe["flag"].tolist() == [
        True,
        False,
    ]


def test_invalid_boolean_values_follow_errors_behavior():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "flag": ["yes", "maybe"],
            }
        )
    )

    with pytest.raises(
        TransformationError,
        match="Invalid boolean values",
    ):
        ConvertTypesTransformation(
            type_map={
                "flag": "bool",
            }
        ).apply(
            dataset
        )

    coerced = ConvertTypesTransformation(
        type_map={
            "flag": "bool",
        },
        errors="coerce",
    ).apply(
        dataset
    )
    ignored = ConvertTypesTransformation(
        type_map={
            "flag": "bool",
        },
        errors="ignore",
    ).apply(
        dataset
    )

    assert coerced.dataframe["flag"].tolist() == [
        True,
        pd.NA,
    ]
    assert ignored.dataframe["flag"].tolist() == [
        "yes",
        "maybe",
    ]


def test_datetime_conversion_converts_date_strings():

    result = ConvertTypesTransformation(
        type_map={
            "birth_date": "datetime",
        }
    ).apply(
        _dataset()
    )

    assert pd.api.types.is_datetime64_any_dtype(
        result.dataframe["birth_date"]
    )


def test_datetime_conversion_supports_format():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "date": ["01/31/2020"],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "date": "datetime",
        },
        datetime_format="%m/%d/%Y",
    ).apply(
        dataset
    )

    assert result.dataframe.loc[0, "date"] == pd.Timestamp(
        "2020-01-31"
    )


def test_invalid_dates_follow_errors_behavior():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "date": ["2020-01-01", "not-a-date"],
            }
        )
    )

    with pytest.raises(
        TransformationError,
        match="Failed converting column 'date' to 'datetime'",
    ):
        ConvertTypesTransformation(
            type_map={
                "date": "datetime",
            }
        ).apply(
            dataset
        )

    coerced = ConvertTypesTransformation(
        type_map={
            "date": "datetime",
        },
        errors="coerce",
    ).apply(
        dataset
    )
    ignored = ConvertTypesTransformation(
        type_map={
            "date": "datetime",
        },
        errors="ignore",
    ).apply(
        dataset
    )

    assert pd.isna(
        coerced.dataframe.loc[1, "date"]
    )
    assert ignored.dataframe["date"].tolist() == [
        "2020-01-01",
        "not-a-date",
    ]


def test_date_conversion_normalizes_to_midnight():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "date": ["2020-01-01 12:34:56"],
            }
        )
    )

    result = ConvertTypesTransformation(
        type_map={
            "date": "date",
        }
    ).apply(
        dataset
    )

    assert result.dataframe.loc[0, "date"] == pd.Timestamp(
        "2020-01-01"
    )


def test_category_conversion_converts_to_category_dtype():

    result = ConvertTypesTransformation(
        type_map={
            "group": "category",
        }
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["group"].dtype
    ) == "category"


def test_normalized_metadata_is_preserved_and_storage_type_updated():

    result = ConvertTypesTransformation(
        type_map={
            "age": "int",
        }
    ).apply(
        _dataset()
    )
    metadata = result.get_normalized_metadata()
    variable = metadata.get_variable(
        "age"
    )

    assert metadata.source_format == "csv"
    assert metadata.source_backend == "csv"
    assert metadata.dataset_label == "Type test"
    assert metadata.notes == [
        "Testing conversions.",
    ]
    assert metadata.raw_metadata == {
        "raw": "kept",
    }
    assert variable.storage_type == "Int64"


def test_variable_labels_remain_attached_to_converted_columns():

    result = ConvertTypesTransformation(
        type_map={
            "age": "int",
        }
    ).apply(
        _dataset()
    )

    assert result.variable_labels()["age"] == "Age"


def test_value_labels_remain_attached_where_applicable():

    result = ConvertTypesTransformation(
        type_map={
            "group": "category",
        }
    ).apply(
        _dataset()
    )

    assert result.value_labels() == {
        "group": {
            1: "Control",
            2: "Treatment",
        },
    }


def test_metadata_for_non_converted_columns_remains_intact():

    result = ConvertTypesTransformation(
        type_map={
            "age": "int",
        }
    ).apply(
        _dataset()
    )

    assert result.variable_metadata("group").label == "Group"
    assert result.variable_metadata("group").storage_type == "object"


def test_datetime_and_date_update_display_format_when_missing():

    result = ConvertTypesTransformation(
        type_map={
            "birth_date": "datetime",
        }
    ).apply(
        _dataset()
    )

    assert result.variable_metadata("birth_date").display_format == "datetime"


def test_pipeline_can_apply_convert_types_transformation():

    result = TransformationPipeline(
        [
            ConvertTypesTransformation(
                type_map={
                    "age": "int",
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["age"].dtype
    ) == "Int64"


def test_pipeline_can_apply_rename_followed_by_type_conversion():

    result = TransformationPipeline(
        [
            RenameColumnsTransformation(
                rename_map={
                    "age": "Age",
                }
            ),
            ConvertTypesTransformation(
                type_map={
                    "Age": "int",
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert str(
        result.dataframe["Age"].dtype
    ) == "Int64"
    assert result.variable_labels()["Age"] == "Age"


def test_pipeline_can_apply_select_followed_by_type_conversion():

    result = TransformationPipeline(
        [
            SelectColumnsTransformation(
                columns=[
                    "age",
                    "group",
                ]
            ),
            ConvertTypesTransformation(
                type_map={
                    "age": "int",
                    "group": "category",
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "age",
        "group",
    ]
    assert str(
        result.dataframe["age"].dtype
    ) == "Int64"
    assert str(
        result.dataframe["group"].dtype
    ) == "category"
