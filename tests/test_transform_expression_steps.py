import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations import (
    DeriveColumnTransformation,
    ExpressionFilterTransformation,
    TransformationError,
    TransformationPipeline,
)


def _dataset():
    metadata = DatasetMetadata(source_format="csv", dataset_label="Expression test")
    metadata.add_variable(
        VariableMetadata(
            name="email",
            label="Email address",
            storage_type="object",
            role="input",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age",
            storage_type="int64",
            measure="scale",
        )
    )
    return Dataset(
        dataframe=pd.DataFrame(
            {
                "email": [" Alice@example.com ", None, "bob@example.com"],
                "age": [17, 18, 21],
            }
        ),
        source_format="csv",
        normalized_metadata=metadata,
    )


def test_derive_appends_column_and_preserves_existing_metadata():
    result = DeriveColumnTransformation(
        "email_clean",
        "lower(strip(email))",
    ).apply(_dataset())

    assert result.columns == ["email", "age", "email_clean"]
    assert result.dataframe["email_clean"].iloc[0] == "alice@example.com"
    assert pd.isna(result.dataframe["email_clean"].iloc[1])
    assert result.variable_metadata("email").label == "Email address"
    assert result.variable_metadata("age").measure == "scale"
    derived = result.variable_metadata("email_clean")
    assert derived is not None
    assert derived.storage_type == "string"
    assert derived.value_labels == {}
    assert derived.missing_values == []
    assert result.column_metadata["email_clean"].logical_type == "string"
    assert result.metadata_provenance["columns"]["email_clean"] == "derived"


def test_multiple_derive_steps_can_reference_earlier_derived_column():
    pipeline = TransformationPipeline(
        [
            DeriveColumnTransformation("email_clean", "lower(strip(email))"),
            DeriveColumnTransformation(
                "has_example",
                "contains(email_clean, '@example')",
            ),
        ]
    )

    result = pipeline.apply(_dataset())

    assert result.columns[-2:] == ["email_clean", "has_example"]
    assert result.dataframe["has_example"].tolist() == [True, False, True]


@pytest.mark.parametrize(
    ("column", "expression", "message"),
    [
        ("clean", "lower(missing)", "Unknown column 'missing'"),
        ("email", "lower(email)", "already exists"),
    ],
)
def test_derive_dependency_and_collision_errors_are_friendly(
    column,
    expression,
    message,
):
    with pytest.raises(TransformationError, match=message):
        DeriveColumnTransformation(column, expression).apply(_dataset())


def test_invalid_derive_expression_fails_before_dataset_execution():
    with pytest.raises(TransformationError, match="Unknown expression function"):
        DeriveColumnTransformation("bad", "open('file')")


def test_expression_filter_preserves_metadata_and_resets_index():
    result = ExpressionFilterTransformation("age >= 18").apply(_dataset())

    assert result.dataframe["age"].tolist() == [18, 21]
    assert result.dataframe.index.tolist() == [0, 1]
    assert result.variable_metadata("email").label == "Email address"
    assert result.variable_metadata("age").measure == "scale"


def test_expression_filter_can_use_derived_column_and_missing_mask_is_false():
    pipeline = TransformationPipeline(
        [
            DeriveColumnTransformation(
                "email_clean",
                "lower(strip(email))",
            ),
            ExpressionFilterTransformation(
                "contains(email_clean, 'example')",
            ),
        ]
    )

    result = pipeline.apply(_dataset())

    assert result.dataframe["age"].tolist() == [17, 21]


def test_expression_filter_rejects_non_boolean_result():
    with pytest.raises(TransformationError, match="boolean"):
        ExpressionFilterTransformation("lower(email)").apply(_dataset())
