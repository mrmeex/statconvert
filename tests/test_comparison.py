import math

import pandas as pd
import pytest

from statconvert.compare import (
    CompareError,
    CompareOptions,
    compare_columns,
    compare_datasets,
    compare_metadata,
    compare_schema,
    compare_shape,
    compare_values_summary,
)
from statconvert.compare.comparison import _difference_summary
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


def make_dataset(
    data: dict[str, list[object]],
    variables: list[VariableMetadata] | None = None,
    source_file: str | None = None,
) -> Dataset:
    metadata = DatasetMetadata()
    for variable in variables or []:
        metadata.add_variable(variable)
    return Dataset(
        dataframe=pd.DataFrame(data),
        normalized_metadata=metadata,
        source_file=source_file,
    )


def issue_codes(comparison) -> set[str]:
    return {issue.code for issue in comparison.issues}


def test_exact_difference_positions_are_bounded_without_full_tolist(monkeypatch):
    left = pd.Series([0] * 100)
    right = pd.Series([1] * 100)

    def fail_tolist(_self):
        raise AssertionError("difference masks must not be materialized as Python lists")

    monkeypatch.setattr(pd.Series, "tolist", fail_tolist)

    count, positions = _difference_summary(
        left,
        right,
        numeric_tolerance=0.0,
        position_limit=3,
    )

    assert count == 100
    assert positions == [0, 1, 2]


def test_compare_shape_reports_matches_and_differences():
    same = compare_shape(make_dataset({"a": [1, 2]}), make_dataset({"a": [3, 4]}))
    different_rows = compare_shape(
        make_dataset({"a": [1, 2]}), make_dataset({"a": [1]})
    )
    different_columns = compare_shape(
        make_dataset({"a": [1]}), make_dataset({"a": [1], "b": [2]})
    )

    assert same.rows_match and same.columns_match
    assert not different_rows.rows_match
    assert not different_columns.columns_match


def test_compare_columns_preserves_orders_and_finds_membership_changes():
    reordered = compare_columns(
        make_dataset({"b": [1], "a": [2]}),
        make_dataset({"a": [2], "b": [1]}),
    )
    different = compare_columns(
        make_dataset({"b": [1], "shared": [2], "left": [3]}),
        make_dataset({"shared": [2], "b": [1], "right": [3]}),
    )

    assert reordered.same_columns
    assert not reordered.same_order
    assert different.common_columns == ["b", "shared"]
    assert different.left_only_columns == ["left"]
    assert different.right_only_columns == ["right"]


def test_compare_columns_reports_same_order():
    result = compare_columns(
        make_dataset({"a": [1], "b": [2]}),
        make_dataset({"a": [3], "b": [4]}),
    )

    assert result.same_columns
    assert result.same_order


def test_compare_schema_detects_storage_type_change():
    left = make_dataset(
        {"a": [1]}, [VariableMetadata(name="a", storage_type="int32")]
    )
    right = make_dataset(
        {"a": [1]}, [VariableMetadata(name="a", storage_type="float64")]
    )

    result = compare_schema(left, right)

    assert result.storage_type_changes == {"a": ("int32", "float64")}
    assert not result.same_storage_types
    assert compare_schema(left, left).same_storage_types


def test_compare_schema_rejects_requested_missing_column():
    dataset = make_dataset({"a": [1]})

    with pytest.raises(CompareError, match="missing from left"):
        compare_schema(dataset, make_dataset({"b": [1]}), columns=["b"])


def test_compare_metadata_detects_each_normalized_change():
    left = make_dataset(
        {"a": [1]},
        [
            VariableMetadata(
                name="a",
                label="Old label",
                value_labels={1: "One"},
                missing_values=[-1],
            )
        ],
    )
    right = make_dataset(
        {"a": [1]},
        [
            VariableMetadata(
                name="a",
                label="New label",
                value_labels={1: "First"},
                missing_values=[-9],
            )
        ],
    )

    result = compare_metadata(left, right)

    assert result.variable_label_changes == {"a": ("Old label", "New label")}
    assert result.value_label_changes == {"a": ({1: "One"}, {1: "First"})}
    assert result.missing_value_changes == {"a": ([-1], [-9])}
    assert not result.same_variable_labels
    assert not result.same_value_labels
    assert not result.same_missing_values


def test_compare_metadata_unchanged_needs_no_backend_metadata():
    left = make_dataset({"a": [1]}, [VariableMetadata(name="a", label="Label")])
    right = make_dataset({"a": [2]}, [VariableMetadata(name="a", label="Label")])

    result = compare_metadata(left, right)

    assert result.same_variable_labels
    assert result.same_value_labels
    assert result.same_missing_values


def test_compare_metadata_rejects_requested_missing_column():
    dataset = make_dataset({"a": [1]})

    with pytest.raises(CompareError):
        compare_metadata(dataset, dataset, columns=["missing"])


def test_compare_values_identical_and_changed_counts():
    left = make_dataset({"a": [1, 2], "b": ["x", "y"]})
    right = make_dataset({"a": [1, 9], "b": ["z", "y"]})

    identical = compare_values_summary(left, left)
    changed = compare_values_summary(left, right)

    assert identical.same_values
    assert changed.differing_cells == 2
    assert changed.differences_by_column == {"a": 1, "b": 1}
    assert changed.cells_compared == 4


def test_compare_values_treats_missing_values_correctly():
    left = make_dataset({"a": [math.nan, None]})
    same = make_dataset({"a": [None, math.nan]})
    changed = make_dataset({"a": [1.0, math.nan]})

    assert compare_values_summary(left, same).same_values
    assert compare_values_summary(left, changed).differing_cells == 1


def test_compare_options_reject_negative_numeric_tolerance():
    with pytest.raises(
        CompareError,
        match="--numeric-tolerance must be greater than or equal to 0",
    ):
        CompareOptions(numeric_tolerance=-0.1)


def test_compare_ignores_columns_before_shape_schema_and_values():
    left = make_dataset({"id": [1], "exported_at": ["old"]})
    right = make_dataset({"id": [1]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(ignore_columns=("exported_at",)),
    )

    assert result.is_identical
    assert result.shape.columns_match
    assert result.columns.same_columns
    assert result.columns.left_only_columns == []
    assert result.columns_compared == ["id"]
    assert result.options.ignore_columns == ("exported_at",)


def test_compare_ignores_right_only_and_shared_changed_columns():
    left = make_dataset({"id": [1], "generated": ["left"]})
    right = make_dataset(
        {"id": [1], "generated": ["right"], "source_file": ["right.csv"]}
    )

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(
            ignore_columns=("generated", "source_file", "not_present")
        ),
    )

    assert result.is_identical
    assert result.columns_compared == ["id"]


def test_compare_ignored_columns_do_not_hide_remaining_differences():
    left = make_dataset({"id": [1], "generated": ["left"]})
    right = make_dataset({"id": [2], "generated": ["right"]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(ignore_columns=("generated",)),
    )

    assert result.values is not None
    assert result.values.differences_by_column == {"id": 1}
    assert result.has_errors


def test_compare_fails_when_ignored_columns_remove_every_comparable_column():
    dataset = make_dataset({"generated": ["value"]})

    with pytest.raises(CompareError, match="No columns remain to compare"):
        compare_datasets(
            dataset,
            dataset,
            options=CompareOptions(ignore_columns=("generated",)),
        )


def test_numeric_tolerance_is_absolute_and_zero_remains_exact():
    left = make_dataset({"value": [1.0, 2.0]})
    right = make_dataset({"value": [1.00005, 2.001]})

    tolerant = compare_values_summary(left, right, numeric_tolerance=0.0001)
    exact = compare_values_summary(left, right, numeric_tolerance=0.0)

    assert tolerant.differences_by_column == {"value": 1}
    assert exact.differences_by_column == {"value": 2}


def test_numeric_tolerance_preserves_missing_value_semantics():
    left = make_dataset({"value": [math.nan, math.nan]})
    right = make_dataset({"value": [math.nan, 0.0]})

    result = compare_values_summary(left, right, numeric_tolerance=1.0)

    assert result.differences_by_column == {"value": 1}


def test_numeric_tolerance_does_not_coerce_strings_or_booleans():
    string_left = make_dataset({"value": ["1.0"]})
    string_right = make_dataset({"value": ["1.00"]})
    bool_left = make_dataset({"value": [True]})
    bool_right = make_dataset({"value": [False]})

    assert not compare_values_summary(
        string_left,
        string_right,
        numeric_tolerance=1.0,
    ).same_values
    assert not compare_values_summary(
        bool_left,
        bool_right,
        numeric_tolerance=1.0,
    ).same_values


def test_numeric_tolerance_handles_mixed_numeric_dtypes_positionally():
    left = make_dataset({"value": pd.Series([1, 2], dtype="int64")})
    right = make_dataset({"value": pd.Series([1.05, 2.2], dtype="float64")})

    result = compare_values_summary(left, right, numeric_tolerance=0.1)

    assert result.differences_by_column == {"value": 1}


def test_positional_comparison_remains_order_sensitive():
    left = make_dataset({"id": [1, 2]})
    right = make_dataset({"id": [2, 1]})

    result = compare_datasets(left, right, options=CompareOptions())

    assert result.values is not None
    assert result.values.differing_cells == 2


def test_key_comparison_matches_reordered_rows_and_reports_alignment():
    left = make_dataset({"id": [1, 2], "name": ["Alice", "Bob"]})
    right = make_dataset({"id": [2, 1], "name": ["Bob", "Alice"]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id",)),
    )

    assert result.is_identical
    assert result.row_matching_mode == "key"
    assert result.key_columns == ["id"]
    assert result.matched_rows == 2
    assert result.rows_only_left == 0
    assert result.rows_only_right == 0
    assert result.values is not None
    assert result.values.differing_cells == 0


def test_compound_key_matching_detects_value_changes():
    left = make_dataset(
        {"id": [1, 1], "visit": [1, 2], "value": [10, 20]}
    )
    right = make_dataset(
        {"id": [1, 1], "visit": [2, 1], "value": [21, 10]}
    )

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id", "visit")),
    )

    assert result.values is not None
    assert result.values.differences_by_column == {
        "id": 0,
        "visit": 0,
        "value": 1,
    }
    assert result.has_errors


def test_key_comparison_reports_rows_present_on_only_one_side():
    left = make_dataset({"id": [1, 2], "value": [10, 20]})
    right = make_dataset({"id": [2, 3], "value": [20, 30]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id",)),
    )

    assert result.matched_rows == 1
    assert result.rows_only_left == 1
    assert result.rows_only_right == 1
    assert {"rows_only_left", "rows_only_right"} <= issue_codes(result)
    assert not result.is_identical


@pytest.mark.parametrize("side", ["left", "right"])
def test_key_comparison_rejects_duplicate_values(side):
    duplicate = make_dataset({"id": [1, 1], "value": [10, 20]})
    unique = make_dataset({"id": [1, 2], "value": [10, 20]})
    left, right = (duplicate, unique) if side == "left" else (unique, duplicate)

    with pytest.raises(
        CompareError,
        match=rf"Duplicate key values found in {side} dataset",
    ):
        compare_datasets(
            left,
            right,
            options=CompareOptions(key_columns=("id",)),
        )


@pytest.mark.parametrize("side", ["left", "right"])
def test_key_comparison_requires_columns_on_both_sides(side):
    with_key = make_dataset({"id": [1], "value": [10]})
    without_key = make_dataset({"value": [10]})
    left, right = (
        (without_key, with_key) if side == "left" else (with_key, without_key)
    )

    with pytest.raises(
        CompareError,
        match=rf"Key column not found in {side} dataset: id",
    ):
        compare_datasets(
            left,
            right,
            options=CompareOptions(key_columns=("id",)),
        )


def test_key_comparison_allows_one_null_key_but_rejects_duplicate_nulls():
    left = make_dataset({"id": [None, 1], "value": ["missing", "one"]})
    right = make_dataset({"id": [1, None], "value": ["one", "missing"]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id",)),
    )

    assert result.is_identical
    with pytest.raises(CompareError, match="Duplicate key values found in left"):
        compare_datasets(
            make_dataset({"id": [None, None], "value": [1, 2]}),
            right,
            options=CompareOptions(key_columns=("id",)),
        )


def test_key_comparison_combines_ignored_columns_and_numeric_tolerance():
    left = make_dataset(
        {"id": [1, 2], "value": [10.0, 20.0], "generated": ["a", "b"]}
    )
    right = make_dataset(
        {"id": [2, 1], "value": [20.005, 10.005], "right_only": [1, 2]}
    )

    tolerant = compare_datasets(
        left,
        right,
        options=CompareOptions(
            key_columns=("id",),
            ignore_columns=("generated", "right_only"),
            numeric_tolerance=0.01,
        ),
    )
    exact = compare_datasets(
        left,
        right,
        options=CompareOptions(
            key_columns=("id",),
            ignore_columns=("generated", "right_only"),
        ),
    )

    assert tolerant.is_identical
    assert exact.values is not None
    assert exact.values.differences_by_column["value"] == 2


def test_key_only_comparison_is_allowed_when_non_key_columns_are_ignored():
    left = make_dataset({"id": [1, 2], "value": ["left", "left"]})
    right = make_dataset({"id": [2, 1], "value": ["right", "right"]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(
            key_columns=("id",),
            ignore_columns=("value",),
        ),
    )

    assert result.is_identical
    assert result.columns_compared == ["id"]


def test_compare_options_reject_duplicate_or_ignored_key_columns():
    with pytest.raises(CompareError, match="Duplicate key column specified: id"):
        CompareOptions(key_columns=("id", "id"))
    with pytest.raises(CompareError, match="Key columns cannot be ignored: id"):
        CompareOptions(key_columns=("id",), ignore_columns=("id",))


def test_compare_options_default_and_validate_max_differences():
    assert CompareOptions().max_differences == 50
    for invalid in (0, -1):
        with pytest.raises(
            CompareError,
            match="--max-differences must be greater than 0",
        ):
            CompareOptions(max_differences=invalid)


def test_positional_difference_details_are_bounded_without_capping_counts():
    left = make_dataset({"a": [1, 2, 3], "b": [4, 5, 6]})
    right = make_dataset({"a": [7, 8, 9], "b": [10, 11, 12]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(max_differences=1),
    )

    assert result.values is not None
    assert result.values.differing_cells == 6
    assert result.detailed_differences_total == 6
    assert result.detailed_differences_shown == 1
    assert result.detailed_differences_truncated
    assert len(result.differences) == 1
    assert result.differences[0].kind == "value"
    assert result.differences[0].row == 0
    assert result.differences[0].column == "a"
    assert result.differences[0].left == 1
    assert result.differences[0].right == 7
    assert result.has_errors


def test_key_value_difference_detail_contains_key_and_column():
    left = make_dataset({"id": [1, 2], "value": [10.0, 20.0]})
    right = make_dataset({"id": [2, 1], "value": [20.0, 11.0]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id",)),
    )

    detail = result.differences[0]
    assert detail.kind == "value"
    assert detail.row is None
    assert detail.key == {"id": 1.0}
    assert detail.column == "value"
    assert detail.left == 10.0
    assert detail.right == 11.0


def test_key_row_only_details_are_bounded_and_deterministic():
    left = make_dataset({"id": [1, 2], "value": [10, 20]})
    right = make_dataset({"id": [2, 3], "value": [20, 30]})

    result = compare_datasets(
        left,
        right,
        options=CompareOptions(key_columns=("id",), max_differences=2),
    )

    assert [detail.kind for detail in result.differences] == [
        "row_only_left",
        "row_only_right",
    ]
    assert [detail.key for detail in result.differences] == [
        {"id": 1},
        {"id": 3},
    ]
    assert result.detailed_differences_total == 2
    assert not result.detailed_differences_truncated


def test_column_and_schema_details_use_lightweight_values_only():
    left = make_dataset({"id": pd.Series([1], dtype="int64"), "left": [1]})
    right = make_dataset({"id": pd.Series([1.0], dtype="float64"), "right": [1]})

    result = compare_datasets(left, right)

    assert [detail.kind for detail in result.differences] == [
        "column_only_left",
        "column_only_right",
        "schema",
    ]
    assert all(
        not isinstance(value, (Dataset, pd.DataFrame))
        for detail in result.differences
        for value in (
            detail.row,
            detail.key,
            detail.column,
            detail.left,
            detail.right,
            detail.message,
        )
    )


def test_compare_values_uses_minimum_rows_and_sample_size():
    left = make_dataset({"a": [1, 2, 3]})
    short = make_dataset({"a": [1, 2]})

    row_limited = compare_values_summary(left, short)
    sampled = compare_values_summary(left, left, sample_size=1)

    assert row_limited.compared_rows == 2
    assert row_limited.same_values
    assert sampled.compared_rows == 1
    assert sampled.sampled
    assert sampled.sample_size == 1


def test_compare_values_restricts_and_validates_requested_columns():
    left = make_dataset({"a": [1], "b": [2]})
    right = make_dataset({"a": [9], "b": [2]})

    result = compare_values_summary(left, right, columns=["b"])

    assert result.same_values
    assert result.compared_columns == 1
    assert result.differences_by_column == {"b": 0}
    with pytest.raises(CompareError):
        compare_values_summary(left, right, columns=["missing"])


def test_identical_dataset_comparison_and_sources():
    left = make_dataset({"a": [1, 2]}, source_file="left.sav")
    right = make_dataset({"a": [1, 2]}, source_file="right.sav")

    result = compare_datasets(left, right)

    assert result.is_identical
    assert result.is_compatible
    assert not result.has_errors
    assert not result.has_warnings
    assert result.left_source == "left.sav"
    assert result.right_source == "right.sav"


def test_dataset_comparison_builds_value_schema_and_metadata_issues():
    left = make_dataset(
        {"a": [1]},
        [VariableMetadata(name="a", label="Old", storage_type="int32")],
    )
    right = make_dataset(
        {"a": [2]},
        [VariableMetadata(name="a", label="New", storage_type="float64")],
    )

    result = compare_datasets(left, right)

    assert {
        "values_changed",
        "storage_types_changed",
        "variable_labels_changed",
    } <= issue_codes(result)
    assert result.has_errors
    assert result.has_warnings
    assert not result.is_compatible


def test_display_format_only_difference_builds_warning_issue():
    left = make_dataset(
        {"a": [1]},
        [VariableMetadata(name="a", display_format="%12.0g")],
    )
    right = make_dataset(
        {"a": [1]},
        [VariableMetadata(name="a", display_format="%9.2f")],
    )

    result = compare_datasets(left, right)

    assert not result.is_identical
    assert result.has_warnings
    assert not result.has_errors
    assert issue_codes(result) == {"display_formats_changed"}
    assert result.issues[0].message == "Display format changed for 1 column."


def test_measurement_level_only_difference_builds_warning_issue():
    left = make_dataset(
        {"a": [1]},
        [VariableMetadata(name="a", measure="scale")],
    )
    right = make_dataset(
        {"a": [1]},
        [VariableMetadata(name="a", measure="ordinal")],
    )

    result = compare_datasets(left, right)

    assert not result.is_identical
    assert result.has_warnings
    assert not result.has_errors
    assert issue_codes(result) == {"measurement_levels_changed"}
    assert result.issues[0].message == "Measurement level changed for 1 column."


def test_schema_detail_issue_order_is_deterministic():
    left = make_dataset(
        {"a": [1], "b": [2]},
        [
            VariableMetadata(name="a", display_format="F8.0", measure="scale"),
            VariableMetadata(name="b", display_format="F6.0"),
        ],
    )
    right = make_dataset(
        {"a": [1], "b": [2]},
        [
            VariableMetadata(name="a", display_format="F9.2", measure="ordinal"),
            VariableMetadata(name="b", display_format="F7.1"),
        ],
    )

    result = compare_datasets(left, right)

    assert [issue.code for issue in result.issues] == [
        "display_formats_changed",
        "measurement_levels_changed",
    ]
    assert result.issues[0].message == "Display format changed for 2 columns."


def test_dataset_comparison_reports_sampling_and_row_mismatch():
    left = make_dataset({"a": [1, 2]})
    right = make_dataset({"a": [1]})

    result = compare_datasets(left, right, sample_size=1)

    assert {"shape_rows_differ", "values_sampled"} <= issue_codes(result)
    assert result.has_errors


def test_compare_datasets_validates_columns_even_without_values():
    dataset = make_dataset({"a": [1]})

    with pytest.raises(CompareError):
        compare_datasets(dataset, dataset, compare_values=False, columns=["missing"])
