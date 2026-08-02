import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.streaming import StreamingSchemaError, StreamingSchemaGuard


def test_stable_ordered_columns_and_numeric_widening_pass() -> None:
    guard = StreamingSchemaGuard()

    guard.validate(Dataset(pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})))
    guard.validate(Dataset(pd.DataFrame({"a": [3.5, None], "b": ["z", None]})))

    assert guard.columns == ("a", "b")
    assert guard.logical_kinds == ["float", "string"]


@pytest.mark.parametrize(
    "dataframe",
    [
        pd.DataFrame({"b": ["z"], "a": [3]}),
        pd.DataFrame({"a": [3]}),
        pd.DataFrame({"a": [3], "b": ["z"], "c": [True]}),
    ],
)
def test_changed_columns_fail(dataframe: pd.DataFrame) -> None:
    guard = StreamingSchemaGuard()
    guard.validate(Dataset(pd.DataFrame({"a": [1], "b": ["x"]})))

    with pytest.raises(StreamingSchemaError, match="ordered columns changed"):
        guard.validate(Dataset(dataframe))


def test_incompatible_dtype_drift_fails() -> None:
    guard = StreamingSchemaGuard()
    guard.validate(Dataset(pd.DataFrame({"value": [1, 2]})))

    with pytest.raises(
        StreamingSchemaError,
        match="expected integer, received string",
    ):
        guard.validate(Dataset(pd.DataFrame({"value": ["three"]})))


def test_missing_only_chunk_is_compatible_with_established_type() -> None:
    guard = StreamingSchemaGuard()
    guard.validate(Dataset(pd.DataFrame({"value": [1, 2]})))

    guard.validate(Dataset(pd.DataFrame({"value": [None, None]})))

    assert guard.logical_kinds == ["integer"]


def test_initial_missing_only_chunk_adopts_later_type() -> None:
    guard = StreamingSchemaGuard()
    guard.validate(Dataset(pd.DataFrame({"value": [None]})))

    guard.validate(Dataset(pd.DataFrame({"value": [1]})))

    assert guard.logical_kinds == ["integer"]
