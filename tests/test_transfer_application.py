from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pandas.testing as pdt
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transfer import (
    TransferPlanningError,
    apply_transfer_plan,
    build_transfer_plan,
)


def _smallest_plan(dataset: Dataset):
    return build_transfer_plan(
        dataset,
        source_path="source.parquet",
        target="parquet",
        policy="smallest-types",
    )


def test_application_narrows_integer_nullable_integer_and_exact_float() -> None:
    source_frame = pd.DataFrame(
        {
            "integer": pd.Series([1, 2, 3], dtype="int64"),
            "nullable": pd.Series([1, None, 3], dtype="Int64"),
            "exact_float": pd.Series([1.5, 2.0, 3.25], dtype="float64"),
            "inexact_float": pd.Series([0.1, 0.2, 0.3], dtype="float64"),
        }
    )
    dataset = Dataset(source_frame.copy(deep=True))
    original = dataset.dataframe.copy(deep=True)

    result = apply_transfer_plan(dataset, _smallest_plan(dataset))

    assert str(result.dataset.dataframe["integer"].dtype) == "int8"
    assert str(result.dataset.dataframe["nullable"].dtype) == "Int8"
    assert str(result.dataset.dataframe["exact_float"].dtype) == "float32"
    assert str(result.dataset.dataframe["inexact_float"].dtype) == "float64"
    assert result.applied_columns == ("integer", "nullable", "exact_float")
    assert list(result.dataset.dataframe.columns) == list(original.columns)
    assert result.dataset.dataframe.isna().equals(original.isna())
    pdt.assert_series_equal(
        result.dataset.dataframe["integer"].astype("int64"),
        original["integer"],
    )
    pdt.assert_series_equal(
        result.dataset.dataframe["nullable"].astype("Int64"),
        original["nullable"],
    )
    pdt.assert_series_equal(
        result.dataset.dataframe["exact_float"].astype("float64"),
        original["exact_float"],
    )
    pdt.assert_frame_equal(dataset.dataframe, original)


def test_application_keeps_ambiguous_strings_and_all_missing_columns() -> None:
    dataset = Dataset(
        pd.DataFrame(
            {
                "identifier": pd.Series(["001", "010", "100"], dtype="string"),
                "all_missing": pd.Series([None, None, None], dtype="object"),
                "mixed": pd.Series([1, "two", 3], dtype="object"),
            }
        )
    )

    result = apply_transfer_plan(dataset, _smallest_plan(dataset))

    assert result.applied_count == 0
    assert result.dataset.dataframe["identifier"].tolist() == ["001", "010", "100"]
    pdt.assert_frame_equal(result.dataset.dataframe, dataset.dataframe)


def test_application_preserves_protected_value_and_missing_metadata() -> None:
    metadata = DatasetMetadata(source_format="sav")
    metadata.add_variable(
        VariableMetadata(
            name="code",
            storage_type="int64",
            value_labels={1: "One", 2: "Two"},
            missing_values=[-9],
        )
    )
    dataset = Dataset(
        pd.DataFrame({"code": pd.Series([1, 2, -9], dtype="int64")}),
        normalized_metadata=metadata,
    )

    result = apply_transfer_plan(dataset, _smallest_plan(dataset))

    variable = result.dataset.get_normalized_metadata().get_variable("code")
    assert result.applied_count == 0
    assert result.retained_columns == ("code",)
    assert variable is not None
    assert variable.value_labels == {1: "One", 2: "Two"}
    assert variable.missing_values == [-9]
    assert str(dataset.dataframe["code"].dtype) == "int64"


def test_application_updates_storage_metadata_for_applied_columns() -> None:
    metadata = DatasetMetadata(source_format="parquet")
    metadata.add_variable(VariableMetadata(name="small", storage_type="int64"))
    dataset = Dataset(
        pd.DataFrame({"small": pd.Series([1, 2], dtype="int64")}),
        normalized_metadata=metadata,
    )

    result = apply_transfer_plan(dataset, _smallest_plan(dataset))

    variable = result.dataset.get_normalized_metadata().get_variable("small")
    assert variable is not None and variable.storage_type == "int8"
    assert dataset.get_normalized_metadata().get_variable("small").storage_type == "int64"


def test_application_rejects_non_smallest_and_blocked_plans() -> None:
    dataset = Dataset(pd.DataFrame({"value": [1, 2]}))
    safe = build_transfer_plan(
        dataset, source_path="source.csv", target="parquet", policy="safe"
    )
    with pytest.raises(TransferPlanningError, match="smallest-types"):
        apply_transfer_plan(dataset, safe)
    blocked = replace(_smallest_plan(dataset), status="blocked")
    with pytest.raises(TransferPlanningError, match="blocked"):
        apply_transfer_plan(dataset, blocked)
