from types import SimpleNamespace

import pandas as pd

from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.metadata import (
    build_basic_metadata,
    metadata_from_pyreadstat,
)


def test_build_basic_metadata_creates_variable_per_column():

    dataframe = pd.DataFrame(
        {
            "name": ["Alice", "Bob"],
            "age": [25, 30],
        }
    )

    metadata = build_basic_metadata(
        dataframe=dataframe,
        source_format="csv",
        source_backend="csv",
    )

    assert list(metadata.variables) == [
        "name",
        "age",
    ]
    assert metadata.source_format == "csv"
    assert metadata.source_backend == "csv"


def test_build_basic_metadata_stores_dtype_as_storage_type():

    dataframe = pd.DataFrame(
        {
            "age": [25, 30],
            "score": [1.5, 2.5],
        }
    )

    metadata = build_basic_metadata(
        dataframe=dataframe
    )

    assert metadata.get_variable("age").storage_type == "int64"
    assert metadata.get_variable("score").storage_type == "float64"


def test_metadata_from_pyreadstat_maps_column_labels():

    dataframe = pd.DataFrame(
        {
            "sex": [1, 2],
        }
    )
    pyreadstat_metadata = SimpleNamespace(
        column_names_to_labels={
            "sex": "Gender",
        },
    )

    metadata = metadata_from_pyreadstat(
        dataframe=dataframe,
        pyreadstat_metadata=pyreadstat_metadata,
        source_format="sav",
    )

    assert metadata.variable_labels() == {
        "sex": "Gender",
    }


def test_metadata_from_pyreadstat_maps_value_labels():

    dataframe = pd.DataFrame(
        {
            "sex": [1, 2],
        }
    )
    pyreadstat_metadata = SimpleNamespace(
        variable_value_labels={
            "sex": {
                1: "Male",
                2: "Female",
            },
        },
    )

    metadata = metadata_from_pyreadstat(
        dataframe=dataframe,
        pyreadstat_metadata=pyreadstat_metadata,
    )

    assert metadata.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }


def test_metadata_from_pyreadstat_ignores_missing_optional_attributes():

    dataframe = pd.DataFrame(
        {
            "age": [25, 30],
        }
    )
    pyreadstat_metadata = SimpleNamespace()

    metadata = metadata_from_pyreadstat(
        dataframe=dataframe,
        pyreadstat_metadata=pyreadstat_metadata,
    )

    assert list(metadata.variables) == [
        "age",
    ]
    assert metadata.variable_labels() == {}
    assert metadata.value_labels() == {}
    assert metadata.raw_metadata["pyreadstat"] is pyreadstat_metadata


def test_metadata_from_pyreadstat_maps_optional_metadata_defensively():

    dataframe = pd.DataFrame(
        {
            "age": [25, 30],
        }
    )
    pyreadstat_metadata = SimpleNamespace(
        original_variable_types={
            "age": "F8.0",
        },
        readstat_variable_types={
            "age": "double",
        },
        variable_storage_width={
            "age": 8,
        },
        variable_display_width={
            "age": 10,
        },
        variable_measure={
            "age": "scale",
        },
        missing_user_values={
            "age": [
                -99,
            ],
        },
    )

    metadata = metadata_from_pyreadstat(
        dataframe=dataframe,
        pyreadstat_metadata=pyreadstat_metadata,
    )
    variable = metadata.get_variable(
        "age"
    )

    assert variable.width == 8
    assert variable.measure == "scale"
    assert variable.display_format == "F8.0"
    assert variable.missing_values == [
        -99,
    ]
    assert variable.raw["readstat_variable_type"] == "double"
    assert variable.raw["display_width"] == 10


def test_metadata_from_pyreadstat_maps_dataset_label_and_notes():
    dataframe = pd.DataFrame({"age": [25, 30]})
    pyreadstat_metadata = SimpleNamespace(
        file_label="Household survey",
        notes=["First note", "Second note"],
    )

    metadata = metadata_from_pyreadstat(
        dataframe=dataframe,
        pyreadstat_metadata=pyreadstat_metadata,
        source_format="sav",
    )

    assert metadata.dataset_label == "Household survey"
    assert metadata.notes == ["First note", "Second note"]


def test_metadata_from_pyreadstat_normalizes_one_note_string():
    metadata = metadata_from_pyreadstat(
        dataframe=pd.DataFrame({"age": [25]}),
        pyreadstat_metadata=SimpleNamespace(notes="One note"),
    )

    assert metadata.notes == ["One note"]


def test_metadata_from_pyreadstat_normalizes_missing_ranges():
    dataframe = pd.DataFrame({"score": [1, 99]})
    pyreadstat_metadata = SimpleNamespace(
        missing_ranges={
            "score": [
                {"lo": 90, "hi": 99},
            ]
        },
        missing_user_values={"score": [-1]},
    )

    metadata = metadata_from_pyreadstat(dataframe, pyreadstat_metadata)
    variable = metadata.get_variable("score")

    assert variable.missing_values == [-1]
    assert variable.missing_ranges == [{"lo": 90, "hi": 99}]
    assert metadata.missing_ranges() == {
        "score": [{"lo": 90, "hi": 99}]
    }


def test_pyreadstat_backend_read_populates_normalized_metadata(monkeypatch):

    dataframe = pd.DataFrame(
        {
            "sex": [1, 2],
        }
    )
    pyreadstat_metadata = SimpleNamespace(
        column_names_to_labels={
            "sex": "Gender",
        },
        variable_value_labels={
            "sex": {
                1: "Male",
                2: "Female",
            },
        },
    )

    def read_file(self, filename, extension, **kwargs):
        return dataframe, pyreadstat_metadata

    monkeypatch.setattr(
        PyReadstatBackend,
        "_read_file",
        read_file,
    )

    dataset = PyReadstatBackend().read(
        "sample.sav"
    )

    assert dataset.normalized_metadata is not None
    assert dataset.normalized_metadata.source_format == "sav"
    assert dataset.normalized_metadata.source_backend == "pyreadstat"
    assert dataset.variable_labels() == {
        "sex": "Gender",
    }
    assert dataset.value_labels() == {
        "sex": {
            1: "Male",
            2: "Female",
        },
    }
    assert dataset.metadata["pyreadstat"] is pyreadstat_metadata
