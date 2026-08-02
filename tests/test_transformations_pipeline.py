import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformer import transform_dataset
from statconvert.transformations import (
    NoOpTransformation,
    Transformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="csv",
        source_backend="csv",
    )
    metadata.add_variable(
        VariableMetadata(
            name="value",
            label="Value",
            storage_type="int64",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "value": [1, 2, 3],
            }
        ),
        metadata={
            "backend": "csv",
            "custom": {
                "source": "test",
            },
        },
        source_format="csv",
        source_file="input.csv",
        normalized_metadata=metadata,
    )


class AddColumnTransformation(Transformation):
    name = "add-column"

    def __init__(
        self,
        column: str,
        value: int
    ) -> None:
        self.column = column
        self.value = value


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        result = dataset.copy()
        result.dataframe[self.column] = self.value

        return result


class MultiplyColumnTransformation(Transformation):
    name = "multiply-column"

    def __init__(
        self,
        column: str,
        multiplier: int
    ) -> None:
        self.column = column
        self.multiplier = multiplier


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        result = dataset.copy()
        result.dataframe[self.column] = (
            result.dataframe[self.column] * self.multiplier
        )

        return result


class FailingTransformation(Transformation):
    name = "failing"

    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        raise ValueError(
            "intentional failure"
        )


def test_noop_transformation_returns_dataset():

    result = NoOpTransformation().apply(
        _dataset()
    )

    assert isinstance(
        result,
        Dataset,
    )


def test_noop_transformation_does_not_mutate_original_dataframe():

    dataset = _dataset()
    result = NoOpTransformation().apply(
        dataset
    )

    result.dataframe.loc[0, "value"] = 99

    assert dataset.dataframe.loc[0, "value"] == 1
    assert result.dataframe.loc[0, "value"] == 99


def test_pipeline_is_empty_works():

    pipeline = TransformationPipeline()

    assert pipeline.is_empty() is True

    pipeline.add(
        NoOpTransformation()
    )

    assert pipeline.is_empty() is False


def test_pipeline_len_works():

    pipeline = TransformationPipeline(
        [
            NoOpTransformation(),
        ]
    )

    assert len(
        pipeline
    ) == 1

    pipeline.add(
        NoOpTransformation()
    )

    assert len(
        pipeline
    ) == 2


def test_empty_pipeline_returns_original_dataset_unchanged():

    dataset = _dataset()

    result = TransformationPipeline().apply(
        dataset
    )

    assert result is dataset


def test_pipeline_applies_transformations_in_order():

    dataset = _dataset()
    pipeline = TransformationPipeline(
        [
            AddColumnTransformation(
                "score",
                5,
            ),
            MultiplyColumnTransformation(
                "score",
                2,
            ),
        ]
    )

    result = pipeline.apply(
        dataset
    )

    assert result.dataframe["score"].tolist() == [
        10,
        10,
        10,
    ]
    assert "score" not in dataset.dataframe.columns


def test_pipeline_wraps_transformation_failure():

    pipeline = TransformationPipeline(
        [
            FailingTransformation(),
        ]
    )

    with pytest.raises(
        TransformationError,
        match="Transformation 'failing' failed",
    ):
        pipeline.apply(
            _dataset()
        )


def test_dataset_copy_deep_copies_dataframe_data():

    dataset = _dataset()
    copied = dataset.copy(
        deep=True
    )

    copied.dataframe.loc[0, "value"] = 99

    assert dataset.dataframe.loc[0, "value"] == 1
    assert copied.dataframe.loc[0, "value"] == 99


def test_dataset_copy_preserves_metadata():

    dataset = _dataset()
    copied = dataset.copy()

    assert copied.metadata == dataset.metadata
    assert copied.metadata is not dataset.metadata

    copied.metadata["custom"]["source"] = "changed"

    assert dataset.metadata["custom"]["source"] == "test"


def test_dataset_copy_preserves_normalized_metadata():

    dataset = _dataset()
    copied = dataset.copy()

    assert copied.normalized_metadata is not dataset.normalized_metadata
    assert copied.variable_labels() == {
        "value": "Value",
    }

    copied.normalized_metadata.variables["value"].label = "Changed"

    assert dataset.variable_labels() == {
        "value": "Value",
    }


def test_transform_dataset_returns_input_when_pipeline_missing_or_empty():

    dataset = _dataset()

    assert transform_dataset(
        dataset
    ) is dataset
    assert transform_dataset(
        dataset,
        TransformationPipeline(),
    ) is dataset


def test_transform_dataset_applies_pipeline():

    dataset = _dataset()
    pipeline = TransformationPipeline(
        [
            MultiplyColumnTransformation(
                "value",
                3,
            ),
        ]
    )

    result = transform_dataset(
        dataset,
        pipeline,
    )

    assert result.dataframe["value"].tolist() == [
        3,
        6,
        9,
    ]
