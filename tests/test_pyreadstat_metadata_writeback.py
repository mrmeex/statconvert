import pandas as pd
import pyreadstat

from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.converter import transform
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


def _labelled_dataset() -> Dataset:
    metadata = DatasetMetadata(
        dataset_label="Study dataset",
        notes=["Imported questionnaire", "Reviewed"],
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age in years",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="group",
            label="Treatment group",
            value_labels={
                1: "Control",
                2: "Treatment",
            },
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
                "group": [1, 2],
            }
        ),
        normalized_metadata=metadata,
    )


def test_pyreadstat_backend_writes_sav_with_normalized_variable_labels(tmp_path):

    output_file = tmp_path / "labelled.sav"

    PyReadstatBackend().write(
        _labelled_dataset(),
        output_file,
    )

    _, metadata = pyreadstat.read_sav(
        output_file
    )

    assert metadata.column_names_to_labels["age"] == "Age in years"
    assert metadata.column_names_to_labels["group"] == "Treatment group"


def test_pyreadstat_backend_writes_sav_with_normalized_value_labels(tmp_path):

    output_file = tmp_path / "labelled_values.sav"

    PyReadstatBackend().write(
        _labelled_dataset(),
        output_file,
    )

    _, metadata = pyreadstat.read_sav(
        output_file
    )

    assert metadata.variable_value_labels["group"] == {
        1.0: "Control",
        2.0: "Treatment",
    }


def test_pyreadstat_backend_writes_supported_sav_dataset_metadata(tmp_path):
    output_file = tmp_path / "dataset_metadata.sav"

    PyReadstatBackend().write(_labelled_dataset(), output_file)

    _, metadata = pyreadstat.read_sav(output_file)

    assert metadata.file_label == "Study dataset"
    assert metadata.notes == ["Imported questionnaire", "Reviewed"]
    assert metadata.variable_measure["age"] == "scale"


def test_pyreadstat_writers_pass_supported_file_labels(monkeypatch, tmp_path):
    captured: dict[str, dict] = {}

    monkeypatch.setattr(
        pyreadstat,
        "write_dta",
        lambda dataframe, filename, **kwargs: captured.setdefault("dta", kwargs),
    )
    monkeypatch.setattr(
        pyreadstat,
        "write_xport",
        lambda dataframe, filename, **kwargs: captured.setdefault("xpt", kwargs),
    )

    backend = PyReadstatBackend()
    backend.write(_labelled_dataset(), tmp_path / "labelled.dta")
    backend.write(_labelled_dataset(), tmp_path / "labelled.xpt")

    assert captured["dta"]["file_label"] == "Study dataset"
    assert captured["xpt"]["file_label"] == "Study dataset"
    assert "note" not in captured["dta"]
    assert "variable_measure" not in captured["dta"]
    assert "note" not in captured["xpt"]
    assert "variable_measure" not in captured["xpt"]


def test_pyreadstat_backend_writes_dta_with_column_labels_argument(
    tmp_path,
    monkeypatch,
):

    captured_options = {}

    def fake_write_dta(
        dataframe,
        filename,
        **kwargs,
    ):
        captured_options.update(
            kwargs
        )

    monkeypatch.setattr(
        pyreadstat,
        "write_dta",
        fake_write_dta,
    )

    PyReadstatBackend().write(
        _labelled_dataset(),
        tmp_path / "labelled.dta",
    )

    assert captured_options["column_labels"] == {
        "age": "Age in years",
        "group": "Treatment group",
    }
    assert "variable_labels" not in captured_options


def test_pyreadstat_writers_use_normalized_missing_metadata(monkeypatch, tmp_path):
    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="score",
            missing_values=[-99],
            missing_ranges=[{"lo": 90, "hi": 99}],
            display_width=12,
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame({"score": [1, 2]}),
        normalized_metadata=metadata,
    )
    sav_options = {}
    dta_options = {}

    monkeypatch.setattr(
        pyreadstat,
        "write_sav",
        lambda dataframe, filename, **kwargs: sav_options.update(kwargs),
    )
    monkeypatch.setattr(
        pyreadstat,
        "write_dta",
        lambda dataframe, filename, **kwargs: dta_options.update(kwargs),
    )

    backend = PyReadstatBackend()
    backend.write(dataset, tmp_path / "score.sav")
    backend.write(dataset, tmp_path / "score.dta")

    assert sav_options["missing_ranges"] == {
        "score": [{"lo": 90, "hi": 99}]
    }
    assert sav_options["variable_display_width"] == {"score": 12}
    assert dta_options["missing_user_values"] == {"score": [-99]}


def test_csv_conversion_still_works_with_metadata_writeback_changes(tmp_path):

    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"

    pd.DataFrame(
        {
            "age": [25, 30],
            "group": [1, 2],
        }
    ).to_csv(
        input_file,
        index=False,
    )

    transform(
        str(input_file),
        str(output_file),
        overwrite=True,
    )

    result = pd.read_csv(
        output_file
    )

    assert result.to_dict(
        orient="list"
    ) == {
        "age": [25, 30],
        "group": [1, 2],
    }
