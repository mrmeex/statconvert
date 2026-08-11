from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    DistinctRowsTransformation,
    RowNumberTransformation,
    SortKey,
    SortRowsTransformation,
    TransformationError,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(dataset_label="Rows")
    metadata.add_variable(
        VariableMetadata(
            name="group", label="Group", storage_type="object", measure="nominal"
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="value", label="Value", storage_type="int64", measure="scale"
        )
    )
    metadata.add_variable(
        VariableMetadata(name="id", label="Identifier", storage_type="int64")
    )
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "group": ["B", "A", "A", "B", None],
                "value": [2, 1, 1, 1, 9],
                "id": [1, 2, 3, 4, 5],
            }
        ),
        normalized_metadata=metadata,
    )


def test_sort_single_column_ascending_and_descending() -> None:
    source = _dataset()

    ascending = SortRowsTransformation([SortKey("value")]).apply(source)
    descending = SortRowsTransformation(
        [SortKey("value", "descending", "last")]
    ).apply(source)

    assert ascending.dataframe["id"].tolist() == [2, 3, 4, 1, 5]
    assert descending.dataframe["id"].tolist() == [5, 1, 2, 3, 4]


def test_sort_multi_column_is_stable_and_honors_null_policy() -> None:
    source = _dataset()
    metadata_before = deepcopy(source.variables_metadata())

    sorted_rows = SortRowsTransformation(
        [
            SortKey("group", "ascending", "last"),
            SortKey("value", "descending", "first"),
        ]
    ).apply(source)
    nulls_first = SortRowsTransformation(
        [SortKey("group", "ascending", "first")]
    ).apply(source)

    assert sorted_rows.dataframe["id"].tolist() == [2, 3, 1, 4, 5]
    assert nulls_first.dataframe["id"].tolist()[0] == 5
    assert sorted_rows.variables_metadata() == metadata_before
    assert source.dataframe["id"].tolist() == [1, 2, 3, 4, 5]
    assert sorted_rows.dataframe.index.tolist() == [0, 1, 2, 3, 4]


@pytest.mark.parametrize(
    "keys, match",
    [
        ([SortKey("missing")], "Column not found"),
        ([SortKey("group"), SortKey("group")], "Duplicate sort"),
    ],
)
def test_sort_rejects_missing_or_duplicate_keys(keys, match: str) -> None:
    with pytest.raises(TransformationError, match=match):
        SortRowsTransformation(keys).apply(_dataset())


def test_distinct_keep_first_last_and_multi_key_preserve_retained_order() -> None:
    source = _dataset()
    metadata_before = deepcopy(source.variables_metadata())

    first = DistinctRowsTransformation(["group"], "first").apply(source)
    last = DistinctRowsTransformation(["group"], "last").apply(source)
    multi = DistinctRowsTransformation(["group", "value"], "first").apply(source)

    assert first.dataframe["id"].tolist() == [1, 2, 5]
    assert last.dataframe["id"].tolist() == [3, 4, 5]
    assert multi.dataframe["id"].tolist() == [1, 2, 4, 5]
    assert first.variables_metadata() == metadata_before
    assert source.rows == 5


@pytest.mark.parametrize(
    "columns, match",
    [(["missing"], "Column not found"), (["group", "group"], "Duplicate distinct")],
)
def test_distinct_rejects_missing_or_duplicate_columns(columns, match: str) -> None:
    with pytest.raises(TransformationError, match=match):
        DistinctRowsTransformation(columns).apply(_dataset())


def test_row_number_defaults_and_custom_sequence_add_metadata() -> None:
    source = _dataset()

    defaulted = RowNumberTransformation("row_id").apply(source)
    custom = RowNumberTransformation("sequence", start=-2, step=3).apply(source)

    assert defaulted.dataframe["row_id"].tolist() == [1, 2, 3, 4, 5]
    assert custom.dataframe["sequence"].tolist() == [-2, 1, 4, 7, 10]
    assert str(defaulted.dataframe["row_id"].dtype) == "int64"
    assert defaulted.variable_metadata("row_id").storage_type == "int64"
    assert defaulted.variable_metadata("row_id").measure == "scale"
    assert defaulted.column_metadata["row_id"].physical_type == "int64"
    assert defaulted.column_metadata["row_id"].measure == "scale"
    assert defaulted.metadata_provenance["columns"]["row_id"] == "generated"
    assert "row_id" not in source.columns


def test_row_number_rejects_collision_and_invalid_step() -> None:
    with pytest.raises(TransformationError, match="already exists"):
        RowNumberTransformation("id").apply(_dataset())
    with pytest.raises(TransformationError, match="positive integer"):
        RowNumberTransformation("row_id", step=0)
    with pytest.raises(TransformationError, match="positive integer"):
        RowNumberTransformation("row_id", step=True)
