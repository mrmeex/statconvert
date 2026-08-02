import pandas as pd
import pytest

from statconvert.transformations import (
    ConvertTypesTransformation,
    DeriveColumnTransformation,
    DropColumnsTransformation,
    ExpressionFilterTransformation,
    FilterRowsTransformation,
    RecodeValuesTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
    TransformationError,
)
from statconvert.transformations.cli_parsing import (
    build_pipeline_from_cli_options,
    parse_filter_items,
    parse_key_value_items,
    parse_recode_items,
)
from statconvert.transformer import transform_file


def test_parse_key_value_items_parses_valid_values():

    assert parse_key_value_items(
        [
            "age=Age",
            "sex=Gender",
        ],
        "--rename",
    ) == {
        "age": "Age",
        "sex": "Gender",
    }


def test_parse_key_value_items_rejects_missing_equals():

    with pytest.raises(
        TransformationError,
        match="Expected KEY=VALUE",
    ):
        parse_key_value_items(
            [
                "age",
            ],
            "--rename",
        )


def test_parse_key_value_items_rejects_empty_key():

    with pytest.raises(
        TransformationError,
        match="Key cannot be empty",
    ):
        parse_key_value_items(
            [
                "=Age",
            ],
            "--rename",
        )


def test_parse_key_value_items_rejects_empty_value():

    with pytest.raises(
        TransformationError,
        match="Value cannot be empty",
    ):
        parse_key_value_items(
            [
                "age=",
            ],
            "--rename",
        )


def test_parse_key_value_items_rejects_duplicate_keys():

    with pytest.raises(
        TransformationError,
        match="Duplicate --rename key",
    ):
        parse_key_value_items(
            [
                "age=Age",
                "age=Years",
            ],
            "--rename",
        )


def test_parse_filter_items_parses_column_operator_value():

    conditions = parse_filter_items(
        [
            "age,gte,18",
        ]
    )

    assert conditions[0].column == "age"
    assert conditions[0].operator == "gte"
    assert conditions[0].value == 18


def test_parse_filter_items_parses_missing_check_without_value():

    conditions = parse_filter_items(
        [
            "deleted,is_missing",
        ]
    )

    assert conditions[0].column == "deleted"
    assert conditions[0].operator == "is_missing"
    assert conditions[0].value is None


def test_parse_filter_items_parses_pipe_values_for_membership():

    conditions = parse_filter_items(
        [
            "status,in,active|pending",
        ]
    )

    assert conditions[0].value == [
        "active",
        "pending",
    ]


def test_parse_filter_items_rejects_invalid_syntax():

    with pytest.raises(
        TransformationError,
        match="Invalid filter",
    ):
        parse_filter_items(
            [
                "age",
            ]
        )


def test_parse_recode_items_parses_mapping_pairs():

    assert parse_recode_items(
        [
            "status:A=Active,I=Inactive",
        ]
    ) == {
        "status": {
            "A": "Active",
            "I": "Inactive",
        },
    }


def test_parse_recode_items_rejects_missing_colon():

    with pytest.raises(
        TransformationError,
        match="Expected COLUMN",
    ):
        parse_recode_items(
            [
                "status=A",
            ]
        )


def test_parse_recode_items_rejects_invalid_mapping_pair():

    with pytest.raises(
        TransformationError,
        match="Expected OLD=NEW",
    ):
        parse_recode_items(
            [
                "status:A",
            ]
        )


def test_parse_recode_items_rejects_duplicate_columns():

    with pytest.raises(
        TransformationError,
        match="Duplicate recode column",
    ):
        parse_recode_items(
            [
                "status:A=Active",
                "status:I=Inactive",
            ]
        )


def test_pipeline_builder_adds_select_transformation():

    pipeline = build_pipeline_from_cli_options(
        select_columns=[
            "age",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        SelectColumnsTransformation,
    )


def test_pipeline_builder_adds_drop_transformation():

    pipeline = build_pipeline_from_cli_options(
        drop_columns=[
            "notes",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        DropColumnsTransformation,
    )


def test_pipeline_builder_adds_rename_transformation():

    pipeline = build_pipeline_from_cli_options(
        rename_items=[
            "age=Age",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        RenameColumnsTransformation,
    )


def test_pipeline_builder_adds_type_transformation():

    pipeline = build_pipeline_from_cli_options(
        type_items=[
            "age=int",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        ConvertTypesTransformation,
    )


def test_pipeline_builder_adds_filter_transformation():

    pipeline = build_pipeline_from_cli_options(
        filter_items=[
            "age,gte,18",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        FilterRowsTransformation,
    )


def test_pipeline_builder_adds_derive_and_expression_filter_transformations():
    pipeline = build_pipeline_from_cli_options(
        derive_items=["adult=age >= 18"],
        filter_expression_items=["adult"],
    )

    assert [
        transformation.__class__
        for transformation in pipeline.transformations
    ] == [
        DeriveColumnTransformation,
        ExpressionFilterTransformation,
    ]


def test_pipeline_builder_adds_recode_transformation():

    pipeline = build_pipeline_from_cli_options(
        recode_items=[
            "status:A=Active",
        ]
    )

    assert isinstance(
        pipeline.transformations[0],
        RecodeValuesTransformation,
    )


def test_pipeline_builder_uses_documented_order():

    pipeline = build_pipeline_from_cli_options(
        select_columns=[
            "age",
            "status",
        ],
        drop_columns=[
            "notes",
        ],
        rename_items=[
            "age=Age",
        ],
        type_items=[
            "Age=int",
        ],
        filter_items=[
            "Age,gte,18",
        ],
        recode_items=[
            "status:A=Active",
        ],
    )

    assert [
        transformation.__class__
        for transformation in pipeline.transformations
    ] == [
        SelectColumnsTransformation,
        DropColumnsTransformation,
        RenameColumnsTransformation,
        ConvertTypesTransformation,
        FilterRowsTransformation,
        RecodeValuesTransformation,
    ]


def test_pipeline_builder_places_derive_before_both_filter_forms():
    pipeline = build_pipeline_from_cli_options(
        select_columns=["age", "status"],
        drop_columns=["notes"],
        rename_items=["age=Age"],
        type_items=["Age=int"],
        derive_items=["adult=Age >= 18"],
        filter_items=["Age,gte,18"],
        filter_expression_items=["adult"],
        recode_items=["status:A=Active"],
    )

    assert [
        transformation.__class__
        for transformation in pipeline.transformations
    ] == [
        SelectColumnsTransformation,
        DropColumnsTransformation,
        RenameColumnsTransformation,
        ConvertTypesTransformation,
        DeriveColumnTransformation,
        FilterRowsTransformation,
        ExpressionFilterTransformation,
        RecodeValuesTransformation,
    ]


def test_pipeline_builder_with_empty_options_returns_empty_pipeline():

    pipeline = build_pipeline_from_cli_options()

    assert pipeline.is_empty()


def test_transform_file_dry_run_does_not_write_output(tmp_path):

    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    pd.DataFrame(
        {
            "age": [
                17,
                18,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    dataset = transform_file(
        input_file=str(
            input_file
        ),
        output_file=str(
            output_file
        ),
        pipeline=build_pipeline_from_cli_options(
            filter_items=[
                "age,gte,18",
            ]
        ),
        dry_run=True,
    )

    assert not output_file.exists()
    assert dataset.dataframe["age"].tolist() == [
        18,
    ]


def test_transform_file_refuses_existing_output_without_overwrite(tmp_path):

    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    pd.DataFrame(
        {
            "age": [
                1,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )
    output_file.write_text(
        "existing",
        encoding="utf-8",
    )

    with pytest.raises(
        Exception,
        match="Output file already exists",
    ):
        transform_file(
            input_file=str(
                input_file
            ),
            output_file=str(
                output_file
            ),
            pipeline=build_pipeline_from_cli_options(),
        )


def test_transform_file_overwrite_allows_existing_output(tmp_path):

    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    pd.DataFrame(
        {
            "age": [
                1,
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )
    output_file.write_text(
        "existing",
        encoding="utf-8",
    )

    transform_file(
        input_file=str(
            input_file
        ),
        output_file=str(
            output_file
        ),
        pipeline=build_pipeline_from_cli_options(),
        overwrite=True,
    )

    assert pd.read_csv(
        output_file
    ).columns.tolist() == [
        "age",
    ]


def test_transform_file_applies_pipeline(tmp_path):

    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    pd.DataFrame(
        {
            "age": [
                17,
                18,
                21,
            ],
            "status": [
                "A",
                "I",
                "A",
            ],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    dataset = transform_file(
        input_file=str(
            input_file
        ),
        output_file=str(
            output_file
        ),
        pipeline=build_pipeline_from_cli_options(
            select_columns=[
                "age",
                "status",
            ],
            rename_items=[
                "age=Age",
            ],
            type_items=[
                "Age=int",
            ],
            filter_items=[
                "Age,gte,18",
            ],
            recode_items=[
                "status:A=Active",
            ],
        ),
    )

    assert dataset.columns == [
        "Age",
        "status",
    ]
    assert dataset.dataframe["Age"].tolist() == [
        18,
        21,
    ]
    assert dataset.dataframe["status"].tolist() == [
        "I",
        "Active",
    ]
    assert pd.read_csv(
        output_file
    ).columns.tolist() == [
        "Age",
        "status",
    ]
