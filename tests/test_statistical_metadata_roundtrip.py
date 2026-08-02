import pandas as pd
import pyreadstat

from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.dataset import ColumnMetadata, Dataset


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Alaric", "Mira"],
            "count": [1, 2],
            "score": [1.25, 2.5],
            "group": [1, 2],
            "survey_date": [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-02"),
            ],
            "survey_time": [
                pd.Timestamp("2020-01-01 08:30:00"),
                pd.Timestamp("2020-01-02 09:45:00"),
            ],
        }
    )


def _stata_sample_dataframe() -> pd.DataFrame:
    dataframe = _sample_dataframe().copy()
    stata_epoch = pd.Timestamp("1960-01-01")

    dataframe["survey_date"] = (
        dataframe["survey_date"] - stata_epoch
    ).dt.days
    dataframe["survey_time"] = (
        dataframe["survey_time"] - stata_epoch
    ).dt.total_seconds() * 1000

    return dataframe


def _column_labels() -> dict[str, str]:
    return {
        "name": "Respondent name",
        "count": "Integer count",
        "score": "Score",
        "group": "Group",
        "survey_date": "Survey date",
        "survey_time": "Survey time",
    }


def _value_labels() -> dict[str, dict[int, str]]:
    return {
        "group": {
            1: "Control",
            2: "Treatment",
        }
    }


def _assert_metadata_preserved(dataset: Dataset) -> None:
    columns = dataset.column_metadata

    assert columns["name"].logical_type == "string"
    assert columns["count"].logical_type == "integer"
    assert columns["score"].logical_type == "float"
    assert columns["group"].logical_type == "labelled"
    assert columns["survey_date"].logical_type == "date"
    assert columns["survey_time"].logical_type == "datetime"

    assert columns["name"].label == "Respondent name"
    assert columns["group"].label == "Group"
    assert columns["survey_date"].label == "Survey date"
    assert columns["survey_time"].label == "Survey time"

    assert columns["group"].value_labels


def test_spss_to_stata_to_spss_preserves_logical_metadata(tmp_path):

    source = tmp_path / "source.sav"
    intermediate = tmp_path / "intermediate.dta"
    target = tmp_path / "target.sav"

    pyreadstat.write_sav(
        _sample_dataframe(),
        source,
        column_labels=_column_labels(),
        variable_value_labels=_value_labels(),
        variable_format={
            "count": "F8.0",
            "score": "F8.2",
            "survey_date": "DATE10",
            "survey_time": "DATETIME20",
        },
    )

    backend = PyReadstatBackend()

    source_dataset = backend.read(source)
    backend.write(source_dataset, intermediate)

    stata_dataset = backend.read(intermediate)
    _assert_metadata_preserved(stata_dataset)

    backend.write(stata_dataset, target)

    final_dataset = backend.read(target)
    _assert_metadata_preserved(final_dataset)


def test_stata_to_spss_to_stata_preserves_logical_metadata(tmp_path):

    source = tmp_path / "source.dta"
    intermediate = tmp_path / "intermediate.sav"
    target = tmp_path / "target.dta"

    pyreadstat.write_dta(
        _stata_sample_dataframe(),
        source,
        column_labels=_column_labels(),
        variable_value_labels=_value_labels(),
        variable_format={
            "survey_date": "%td",
            "survey_time": "%tc",
        },
    )

    backend = PyReadstatBackend()

    source_dataset = backend.read(source)
    backend.write(source_dataset, intermediate)

    spss_dataset = backend.read(intermediate)
    _assert_metadata_preserved(spss_dataset)

    backend.write(spss_dataset, target)

    final_dataset = backend.read(target)
    _assert_metadata_preserved(final_dataset)


def test_csv_sidecar_restores_column_metadata(tmp_path):

    output_file = tmp_path / "metadata.csv"
    dataset = Dataset(
        dataframe=_sample_dataframe(),
        column_metadata={
            "name": ColumnMetadata(
                name="name",
                label="Respondent name",
                physical_type="object",
                logical_type="string",
                source_format="sav",
                original_format="A6",
            )
        },
    )

    backend = CSVBackend()
    backend.write(dataset, output_file)

    result = backend.read(output_file)

    assert result.column_metadata["name"].label == "Respondent name"
    assert result.column_metadata["name"].logical_type == "string"
