from types import SimpleNamespace

import pandas as pd

from statconvert.backends.csv_backend import CSVBackend
from statconvert.compare import compare_datasets
from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.reporting import build_metadata_section, build_schema_section
from statconvert.transformations import (
    ConvertTypesTransformation,
    DropColumnsTransformation,
    RecodeValuesTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
)


def _rich_metadata() -> DatasetMetadata:
    metadata = DatasetMetadata(dataset_label="Survey")
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Status label",
            value_labels={1: "Active", 2: "Inactive"},
            missing_values=[-99],
            missing_ranges=[{"lo": -10, "hi": -1}],
            storage_type="int32",
            display_format="F8.0",
            display_width=10,
            measure="nominal",
        )
    )
    return metadata


def test_normalized_metadata_wins_and_synchronizes_legacy_columns():
    dataset = Dataset(
        dataframe=pd.DataFrame({"status": [1, 2]}),
        normalized_metadata=_rich_metadata(),
        column_metadata={
            "status": ColumnMetadata(
                name="status",
                label="Stale label",
                value_labels={1: "Stale"},
                missing_values={"user_values": [-1]},
                physical_type="float64",
                original_format="F4.0",
            )
        },
    )

    assert dataset.variable_labels() == {"status": "Status label"}
    assert dataset.value_labels() == {
        "status": {1: "Active", 2: "Inactive"}
    }
    assert dataset.missing_values() == {"status": [-99]}
    assert dataset.missing_ranges() == {
        "status": [{"lo": -10, "hi": -1}]
    }
    assert dataset.column_metadata["status"].label == "Status label"
    assert dataset.column_metadata["status"].physical_type == "int32"
    assert dataset.column_metadata["status"].measure == "nominal"


def test_partial_normalized_metadata_falls_back_per_column():
    normalized = DatasetMetadata()
    normalized.add_variable(VariableMetadata(name="age", label="Age"))
    dataset = Dataset(
        dataframe=pd.DataFrame({"age": [20], "status": [1]}),
        normalized_metadata=normalized,
        column_metadata={
            "status": ColumnMetadata(
                name="status",
                label="Status",
                value_labels={1: "Active"},
                missing_values={"user_values": [-99]},
                original_format="F8.0",
                measure="nominal",
            )
        },
    )

    assert dataset.variable_labels() == {"age": "Age", "status": "Status"}
    assert dataset.value_labels() == {"status": {1: "Active"}}
    assert dataset.missing_values() == {"status": [-99]}
    assert dataset.display_formats() == {"status": "F8.0"}
    assert dataset.measurement_levels() == {"status": "nominal"}


def test_raw_pyreadstat_missing_metadata_is_normalized_for_accessors():
    raw = SimpleNamespace(
        column_names_to_labels={"score": "Score"},
        variable_value_labels={"score": {1: "One"}},
        missing_user_values={"score": [-99]},
        missing_ranges={"score": [{"lo": 90, "hi": 99}]},
    )
    dataset = Dataset(
        dataframe=pd.DataFrame({"score": [1, 99]}),
        metadata={"pyreadstat": raw},
        normalized_metadata=DatasetMetadata(),
    )

    assert dataset.variable_labels() == {"score": "Score"}
    assert dataset.value_labels() == {"score": {1: "One"}}
    assert dataset.missing_values() == {"score": [-99]}
    assert dataset.missing_ranges() == {
        "score": [{"lo": 90, "hi": 99}]
    }
    assert isinstance(dataset.variable_metadata("score"), VariableMetadata)


def test_csv_sidecar_restores_all_normalized_variable_metadata(tmp_path):
    path = tmp_path / "metadata.csv"
    source = Dataset(
        dataframe=pd.DataFrame({"status": [1, 2]}),
        normalized_metadata=_rich_metadata(),
    )

    CSVBackend().write(source, path)
    restored = CSVBackend().read(path)

    assert restored.variable_labels() == source.variable_labels()
    assert restored.value_labels() == source.value_labels()
    assert restored.missing_values() == source.missing_values()
    assert restored.missing_ranges() == source.missing_ranges()
    assert restored.storage_types() == {"status": "int32"}
    assert restored.display_formats() == source.display_formats()
    assert restored.measurement_levels() == source.measurement_levels()
    assert restored.metadata_summary()["missing_range_sets"] == 1

    schema_rows = build_schema_section(restored).tables[0].rows
    schema_row = next(row for row in schema_rows if row["column"] == "status")
    metadata_metrics = {
        metric.name: metric.value for metric in build_metadata_section(restored).metrics
    }
    assert schema_row["display_format"] == "F8.0"
    assert schema_row["measurement_level"] == "nominal"
    assert metadata_metrics["missing_range_sets"] == 1


def test_transformations_keep_normalized_and_legacy_metadata_in_sync():
    metadata = _rich_metadata()
    metadata.add_variable(VariableMetadata(name="keep", label="Keep"))
    source = Dataset(
        dataframe=pd.DataFrame({"status": [1, 2], "keep": [10, 20]}),
        normalized_metadata=metadata,
    )

    selected = SelectColumnsTransformation(["status"]).apply(source)
    assert set(selected.variables_metadata()) == {"status"}
    assert set(selected.column_metadata) == {"status"}

    dropped = DropColumnsTransformation(["status"]).apply(source)
    assert set(dropped.variables_metadata()) == {"keep"}
    assert set(dropped.column_metadata) == {"keep"}

    recoded = RecodeValuesTransformation(
        {"status": {1: "A", 2: "I", -99: "M"}}
    ).apply(source)
    assert recoded.column_metadata["status"].value_labels == {
        "A": "Active",
        "I": "Inactive",
    }
    assert recoded.column_metadata["status"].missing_values["user_values"] == [
        "M"
    ]

    converted = ConvertTypesTransformation(
        {"status": "string"}
    ).apply(recoded)
    assert converted.column_metadata["status"].physical_type == str(
        converted.dataframe["status"].dtype
    )

    renamed = RenameColumnsTransformation({"status": "Status"}).apply(converted)
    assert "status" not in renamed.variables_metadata()
    assert "status" not in renamed.column_metadata
    assert renamed.variable_labels() == {
        "Status": "Status label",
        "keep": "Keep",
    }
    assert renamed.column_metadata["Status"].label == "Status label"


def test_compare_uses_synchronized_metadata_after_transformation():
    left = Dataset(
        dataframe=pd.DataFrame({"status": [1]}),
        normalized_metadata=_rich_metadata(),
    )
    right = RenameColumnsTransformation({"status": "Status"}).apply(left)
    round_trip = RenameColumnsTransformation({"Status": "status"}).apply(right)

    comparison = compare_datasets(left, round_trip)

    assert comparison.metadata.same_variable_labels
    assert comparison.metadata.same_value_labels
    assert comparison.metadata.same_missing_values
