import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    ConvertTypesTransformation,
    FilterCondition,
    FilterRowsTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
        dataset_label="Filter test",
        notes=[
            "Testing filters.",
        ],
        raw_metadata={
            "raw": "kept",
        },
    )
    metadata.add_variable(
        VariableMetadata(
            name="id",
            label="Identifier",
            storage_type="int64",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            storage_type="float64",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="country",
            label="Country",
            value_labels={
                "NL": "Netherlands",
                "BE": "Belgium",
            },
            storage_type="object",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Status",
            value_labels={
                "active": "Active",
                "pending": "Pending",
                "inactive": "Inactive",
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
            name="score",
            label="Score",
            storage_type="float64",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "age": [17, 18, 21, 30, None],
                "country": ["NL", "NL", "BE", "DE", "NL"],
                "status": ["active", "pending", "inactive", "active", None],
                "name": ["Alice", "Bob", "Anna", None, "Albert"],
                "score": [1.5, 2.0, 3.5, 4.0, 5.0],
            }
        ),
        metadata={
            "backend": "csv",
            "legacy": {
                "kept": True,
            },
        },
        source_format="csv",
        source_file="filters.csv",
        normalized_metadata=metadata,
    )


def _filter(
    condition: FilterCondition,
    dataset: Dataset | None = None,
    reset_index: bool = True,
) -> Dataset:
    return FilterRowsTransformation(
        conditions=[
            condition,
        ],
        reset_index=reset_index,
    ).apply(
        dataset or _dataset()
    )


def test_empty_conditions_raises():

    with pytest.raises(
        TransformationError,
        match="At least one filter condition",
    ):
        FilterRowsTransformation(
            conditions=[]
        )


def test_missing_column_raises():

    with pytest.raises(
        TransformationError,
        match="Column not found: missing",
    ):
        _filter(
            FilterCondition(
                column="missing",
                operator="eq",
                value=1,
            )
        )


def test_unsupported_operator_raises():

    with pytest.raises(
        TransformationError,
        match="Unsupported filter operator",
    ):
        _filter(
            FilterCondition(
                column="age",
                operator="between",
                value=[1, 2],
            )
        )


def test_invalid_mode_raises():

    with pytest.raises(
        TransformationError,
        match="Unsupported filter mode",
    ):
        FilterRowsTransformation(
            conditions=[
                FilterCondition(
                    column="age",
                    operator="gt",
                    value=18,
                ),
            ],
            mode="xor",
        )


def test_value_required_for_non_missing_operators():

    with pytest.raises(
        TransformationError,
        match="requires a value",
    ):
        _filter(
            FilterCondition(
                column="age",
                operator="eq",
            )
        )


def test_original_dataset_is_not_mutated():

    dataset = _dataset()

    result = _filter(
        FilterCondition(
            column="age",
            operator="gte",
            value=18,
        ),
        dataset=dataset,
    )

    result.dataframe.loc[0, "age"] = 99

    assert dataset.dataframe["age"].tolist()[:4] == [
        17,
        18,
        21,
        30,
    ]
    assert pd.isna(
        dataset.dataframe.loc[4, "age"]
    )


def test_eq_keeps_matching_rows():

    result = _filter(
        FilterCondition(
            column="country",
            operator="eq",
            value="NL",
        )
    )

    assert result.dataframe["id"].tolist() == [
        1,
        2,
        5,
    ]


def test_ne_excludes_matching_rows():

    result = _filter(
        FilterCondition(
            column="country",
            operator="ne",
            value="NL",
        )
    )

    assert result.dataframe["id"].tolist() == [
        3,
        4,
    ]


@pytest.mark.parametrize(
    ("operator", "expected_ids"),
    [
        ("=", [1]),
        ("==", [1]),
        ("!=", [2, 3, 4, 5]),
        ("<>", [2, 3, 4, 5]),
    ],
)
def test_equality_aliases_work(
    operator,
    expected_ids,
):

    result = _filter(
        FilterCondition(
            column="id",
            operator=operator,
            value=1,
        )
    )

    assert result.dataframe["id"].tolist() == expected_ids


@pytest.mark.parametrize(
    ("operator", "value", "expected_ids"),
    [
        ("gt", 18, [3, 4]),
        ("gte", 18, [2, 3, 4]),
        ("lt", 21, [1, 2]),
        ("lte", 21, [1, 2, 3]),
        (">", 18, [3, 4]),
        (">=", 18, [2, 3, 4]),
        ("<", 21, [1, 2]),
        ("<=", 21, [1, 2, 3]),
    ],
)
def test_comparable_operators_and_aliases_work(
    operator,
    value,
    expected_ids,
):

    result = _filter(
        FilterCondition(
            column="age",
            operator=operator,
            value=value,
        )
    )

    assert result.dataframe["id"].tolist() == expected_ids


def test_invalid_comparison_raises():

    with pytest.raises(
        TransformationError,
        match="Failed applying filter 'gt' to column 'name'",
    ):
        _filter(
            FilterCondition(
                column="name",
                operator="gt",
                value=10,
            )
        )


def test_in_keeps_rows_in_value_list():

    result = _filter(
        FilterCondition(
            column="status",
            operator="in",
            value=[
                "active",
                "pending",
            ],
        )
    )

    assert result.dataframe["id"].tolist() == [
        1,
        2,
        4,
    ]


def test_not_in_excludes_rows_in_value_list():

    result = _filter(
        FilterCondition(
            column="country",
            operator="not_in",
            value=[
                "NL",
                "BE",
            ],
        )
    )

    assert result.dataframe["id"].tolist() == [
        4,
    ]


def test_string_value_for_in_raises():

    with pytest.raises(
        TransformationError,
        match="requires a list-like value",
    ):
        _filter(
            FilterCondition(
                column="country",
                operator="in",
                value="NL",
            )
        )


def test_contains_works():

    result = _filter(
        FilterCondition(
            column="name",
            operator="contains",
            value="Al",
        )
    )

    assert result.dataframe["id"].tolist() == [
        1,
        5,
    ]


def test_not_contains_works_and_includes_missing_values():

    result = _filter(
        FilterCondition(
            column="name",
            operator="not_contains",
            value="Al",
        )
    )

    assert result.dataframe["id"].tolist() == [
        2,
        3,
        4,
    ]


def test_startswith_works():

    result = _filter(
        FilterCondition(
            column="name",
            operator="startswith",
            value="A",
        )
    )

    assert result.dataframe["id"].tolist() == [
        1,
        3,
        5,
    ]


def test_endswith_works():

    result = _filter(
        FilterCondition(
            column="name",
            operator="endswith",
            value="a",
        )
    )

    assert result.dataframe["id"].tolist() == [
        3,
    ]


def test_is_missing_keeps_missing_rows():

    result = _filter(
        FilterCondition(
            column="status",
            operator="is_missing",
        )
    )

    assert result.dataframe["id"].tolist() == [
        5,
    ]


def test_not_missing_keeps_non_missing_rows():

    result = _filter(
        FilterCondition(
            column="status",
            operator="not_missing",
        )
    )

    assert result.dataframe["id"].tolist() == [
        1,
        2,
        3,
        4,
    ]


def test_mode_and_requires_all_conditions():

    result = FilterRowsTransformation(
        conditions=[
            FilterCondition(
                column="age",
                operator="gte",
                value=18,
            ),
            FilterCondition(
                column="country",
                operator="eq",
                value="NL",
            ),
        ],
        mode="and",
    ).apply(
        _dataset()
    )

    assert result.dataframe["id"].tolist() == [
        2,
    ]


def test_mode_or_allows_any_condition():

    result = FilterRowsTransformation(
        conditions=[
            FilterCondition(
                column="age",
                operator="lt",
                value=18,
            ),
            FilterCondition(
                column="country",
                operator="eq",
                value="BE",
            ),
        ],
        mode="or",
    ).apply(
        _dataset()
    )

    assert result.dataframe["id"].tolist() == [
        1,
        3,
    ]


def test_filter_can_return_empty_dataset_with_metadata():

    result = _filter(
        FilterCondition(
            column="age",
            operator="gt",
            value=100,
        )
    )

    assert result.dataframe.empty
    assert result.columns == [
        "id",
        "age",
        "country",
        "status",
        "name",
        "score",
    ]
    assert result.variable_labels()["age"] == "Age"


def test_reset_index_true_resets_index():

    result = _filter(
        FilterCondition(
            column="age",
            operator="gt",
            value=20,
        )
    )

    assert result.dataframe.index.tolist() == [
        0,
        1,
    ]


def test_reset_index_false_preserves_original_index():

    result = _filter(
        FilterCondition(
            column="age",
            operator="gt",
            value=20,
        ),
        reset_index=False,
    )

    assert result.dataframe.index.tolist() == [
        2,
        3,
    ]


def test_normalized_metadata_is_preserved():

    result = _filter(
        FilterCondition(
            column="country",
            operator="eq",
            value="NL",
        )
    )
    metadata = result.get_normalized_metadata()

    assert metadata.source_format == "csv"
    assert metadata.source_backend == "csv"
    assert metadata.dataset_label == "Filter test"
    assert metadata.notes == [
        "Testing filters.",
    ]
    assert metadata.raw_metadata == {
        "raw": "kept",
    }


def test_variable_labels_and_value_labels_remain_attached():

    result = _filter(
        FilterCondition(
            column="country",
            operator="eq",
            value="NL",
        )
    )

    assert result.variable_labels()["country"] == "Country"
    assert result.value_labels()["country"] == {
        "NL": "Netherlands",
        "BE": "Belgium",
    }


def test_metadata_summary_remains_valid():

    result = _filter(
        FilterCondition(
            column="country",
            operator="eq",
            value="NL",
        )
    )
    summary = result.metadata_summary()

    assert summary["variables"] == 6
    assert summary["variable_labels"] == 6
    assert summary["value_label_sets"] == 2
    assert summary["has_metadata"] is True


def test_pipeline_can_apply_filter_rows_transformation():

    result = TransformationPipeline(
        [
            FilterRowsTransformation(
                conditions=[
                    FilterCondition(
                        column="age",
                        operator="gte",
                        value=18,
                    ),
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.dataframe["id"].tolist() == [
        2,
        3,
        4,
    ]


def test_pipeline_can_apply_select_followed_by_filter():

    result = TransformationPipeline(
        [
            SelectColumnsTransformation(
                columns=[
                    "id",
                    "country",
                ]
            ),
            FilterRowsTransformation(
                conditions=[
                    FilterCondition(
                        column="country",
                        operator="eq",
                        value="NL",
                    ),
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "id",
        "country",
    ]
    assert result.dataframe["id"].tolist() == [
        1,
        2,
        5,
    ]


def test_pipeline_can_apply_rename_followed_by_filter():

    result = TransformationPipeline(
        [
            RenameColumnsTransformation(
                rename_map={
                    "country": "Country",
                }
            ),
            FilterRowsTransformation(
                conditions=[
                    FilterCondition(
                        column="Country",
                        operator="eq",
                        value="NL",
                    ),
                ]
            ),
        ]
    ).apply(
        _dataset()
    )

    assert result.columns == [
        "id",
        "age",
        "Country",
        "status",
        "name",
        "score",
    ]
    assert result.variable_labels()["Country"] == "Country"


def test_pipeline_can_apply_type_conversion_followed_by_filter():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [
                    "17",
                    "18",
                    "21",
                ],
            }
        )
    )

    result = TransformationPipeline(
        [
            ConvertTypesTransformation(
                type_map={
                    "age": "int",
                }
            ),
            FilterRowsTransformation(
                conditions=[
                    FilterCondition(
                        column="age",
                        operator="gte",
                        value=18,
                    ),
                ]
            ),
        ]
    ).apply(
        dataset
    )

    assert result.dataframe["age"].tolist() == [
        18,
        21,
    ]
