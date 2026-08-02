import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    ConvertTypesTransformation,
    FilterCondition,
    FilterRowsTransformation,
    RecodeValuesTransformation,
    RenameColumnsTransformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
        dataset_label="Recode test",
        notes=[
            "Testing recodes.",
        ],
        raw_metadata={
            "raw": "kept",
        },
    )
    metadata.add_variable(
        VariableMetadata(
            name="gender",
            label="Gender",
            value_labels={
                1: "Male",
                2: "Female",
                3: "Other",
            },
            missing_values=[
                9,
            ],
            storage_type="int64",
            measure="nominal",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Status",
            value_labels={
                "A": "Active",
                "I": "Inactive",
                "P": "Pending",
            },
            storage_type="object",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="group",
            label="Group",
            value_labels={
                "old": "Old",
                "new": "New",
            },
            storage_type="object",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="score",
            label="Score",
            storage_type="int64",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "gender": [
                    1,
                    2,
                    3,
                    9,
                    None,
                ],
                "status": [
                    "A",
                    "I",
                    "P",
                    "X",
                    None,
                ],
                "group": [
                    "old",
                    "new",
                    "old",
                    "other",
                    None,
                ],
                "score": [
                    10,
                    20,
                    30,
                    40,
                    50,
                ],
            }
        ),
        metadata={
            "backend": "csv",
            "legacy": {
                "kept": True,
            },
        },
        source_format="csv",
        source_file="recode.csv",
        normalized_metadata=metadata,
    )


def test_empty_recode_map_raises():

    with pytest.raises(
        TransformationError,
        match="At least one recode mapping",
    ):
        RecodeValuesTransformation(
            recode_map={}
        )


def test_missing_column_raises():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        RecodeValuesTransformation(
            recode_map={
                "missing": {
                    1: "one",
                },
            }
        ).apply(
            _dataset()
        )


def test_empty_column_mapping_raises():

    with pytest.raises(
        TransformationError,
        match="cannot be empty",
    ):
        RecodeValuesTransformation(
            recode_map={
                "gender": {},
            }
        )


def test_non_dict_column_mapping_raises():

    with pytest.raises(
        TransformationError,
        match="must be a dict",
    ):
        RecodeValuesTransformation(
            recode_map={
                "gender": [
                    1,
                    2,
                ],
            }
        )


def test_original_dataset_is_not_mutated():

    dataset = _dataset()

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        }
    ).apply(
        dataset
    )

    result.dataframe.loc[0, "status"] = "Changed"

    assert dataset.dataframe.loc[0, "status"] == "A"


def test_recode_numeric_values_to_strings():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "Male",
                2: "Female",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.dataframe["gender"].tolist()[:3] == [
        "Male",
        "Female",
        3,
    ]


def test_recode_strings_to_strings():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
                "I": "Inactive",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.dataframe["status"].tolist()[:3] == [
        "Active",
        "Inactive",
        "P",
    ]


def test_recode_multiple_columns():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
            },
            "status": {
                "A": "Active",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.dataframe.loc[0, "gender"] == "M"
    assert result.dataframe.loc[0, "status"] == "Active"


def test_unmapped_values_remain_unchanged_by_default():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.dataframe["status"].tolist()[:4] == [
        "Active",
        "I",
        "P",
        "X",
    ]


def test_use_default_replaces_unmapped_non_missing_values():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        },
        default="Other",
        use_default=True,
    ).apply(
        _dataset()
    )

    assert result.dataframe["status"].tolist()[:4] == [
        "Active",
        "Other",
        "Other",
        "Other",
    ]
    assert pd.isna(
        result.dataframe.loc[4, "status"]
    )


def test_use_default_can_deliberately_replace_with_none():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        },
        default=None,
        use_default=True,
    ).apply(
        _dataset()
    )

    assert result.dataframe.loc[1, "status"] is None
    assert result.dataframe.loc[2, "status"] is None


def test_missing_values_remain_missing_when_not_explicitly_mapped():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        },
        default="Other",
        use_default=True,
    ).apply(
        _dataset()
    )

    assert pd.isna(
        result.dataframe.loc[4, "status"]
    )


def test_missing_values_can_be_explicitly_mapped():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                None: "Missing",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.dataframe.loc[4, "status"] == "Missing"


def test_row_count_index_and_column_order_are_preserved():

    dataset = _dataset()
    dataset.dataframe.index = [
        10,
        20,
        30,
        40,
        50,
    ]

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        }
    ).apply(
        dataset
    )

    assert result.rows == dataset.rows
    assert result.dataframe.index.tolist() == [
        10,
        20,
        30,
        40,
        50,
    ]
    assert result.columns == [
        "gender",
        "status",
        "group",
        "score",
    ]


def test_normalized_metadata_is_preserved():

    result = RecodeValuesTransformation(
        recode_map={
            "status": {
                "A": "Active",
            },
        }
    ).apply(
        _dataset()
    )
    metadata = result.get_normalized_metadata()

    assert metadata.source_format == "csv"
    assert metadata.source_backend == "csv"
    assert metadata.dataset_label == "Recode test"
    assert metadata.raw_metadata == {
        "raw": "kept",
    }


def test_storage_type_is_updated_for_recoded_columns():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "Male",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.variable_metadata("gender").storage_type == str(
        result.dataframe["gender"].dtype
    )


def test_variable_labels_remain_attached():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "Male",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.variable_labels()["gender"] == "Gender"


def test_missing_values_metadata_is_updated_safely():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                9: "Missing",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.missing_values()["gender"] == [
        "Missing",
    ]


def test_metadata_for_non_recoded_columns_remains_intact():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "Male",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.variable_metadata("status").label == "Status"
    assert result.variable_metadata("status").value_labels == {
        "A": "Active",
        "I": "Inactive",
        "P": "Pending",
    }


def test_value_labels_are_recoded_when_enabled():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
                2: "F",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        "M": "Male",
        "F": "Female",
        3: "Other",
    }


def test_value_labels_remain_unchanged_when_disabled():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
            },
        },
        update_value_labels=False,
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        1: "Male",
        2: "Female",
        3: "Other",
    }


def test_unmapped_value_labels_are_kept_by_default():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        "M": "Male",
        2: "Female",
        3: "Other",
    }


def test_unmapped_value_labels_are_dropped_when_requested():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
            },
        },
        drop_unmapped_value_labels=True,
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        "M": "Male",
    }


def test_label_merge_conflicts_add_note():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "Known",
                2: "Known",
            },
        }
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        "Known": "Male",
        3: "Other",
    }
    assert (
        "Value labels merged during recode for column gender."
        in result.get_normalized_metadata().notes
    )


def test_use_default_with_multiple_labelled_values_collapsing_adds_note():

    result = RecodeValuesTransformation(
        recode_map={
            "gender": {
                1: "M",
            },
        },
        default="Other",
        use_default=True,
    ).apply(
        _dataset()
    )

    assert result.value_labels()["gender"] == {
        "M": "Male",
        "Other": "Female",
    }
    assert (
        "Unmapped value labels collapsed to default during recode for column gender."
        in result.get_normalized_metadata().notes
    )


def test_pipeline_can_apply_recode_values_transformation():

    result = TransformationPipeline(
        [
            RecodeValuesTransformation(
                recode_map={
                    "status": {
                        "A": "Active",
                    },
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.dataframe.loc[0, "status"] == "Active"


def test_pipeline_can_apply_filter_followed_by_recode():

    result = TransformationPipeline(
        [
            FilterRowsTransformation(
                conditions=[
                    FilterCondition(
                        column="status",
                        operator="eq",
                        value="A",
                    ),
                ]
            ),
            RecodeValuesTransformation(
                recode_map={
                    "status": {
                        "A": "Active",
                    },
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.dataframe["status"].tolist() == [
        "Active",
    ]


def test_pipeline_can_apply_type_conversion_followed_by_recode():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "code": [
                    "1",
                    "2",
                ],
            }
        )
    )

    result = TransformationPipeline(
        [
            ConvertTypesTransformation(
                type_map={
                    "code": "int",
                }
            ),
            RecodeValuesTransformation(
                recode_map={
                    "code": {
                        1: "one",
                    },
                }
            ),
        ]
    ).apply(
        dataset
    )

    assert result.dataframe["code"].tolist() == [
        "one",
        2,
    ]


def test_pipeline_can_apply_rename_followed_by_recode():

    result = TransformationPipeline(
        [
            RenameColumnsTransformation(
                rename_map={
                    "status": "Status",
                }
            ),
            RecodeValuesTransformation(
                recode_map={
                    "Status": {
                        "A": "Active",
                    },
                }
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.dataframe.loc[0, "Status"] == "Active"
    assert result.variable_labels()["Status"] == "Status"
