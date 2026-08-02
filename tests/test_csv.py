from statconvert.backends.csv_backend import CSVBackend
from statconvert.dataset import Dataset
from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.registry import read_dataset, write_dataset

import pandas as pd
import pytest


def test_csv_roundtrip(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"


    pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"]
        }
    ).to_csv(
        input_file,
        index=False
    )


    backend = CSVBackend()

    dataset = backend.read(input_file)

    backend.write(
        dataset,
        output_file
    )


    result = backend.read(output_file)


    assert result.rows == 3
    assert result.columns == ["A", "B"]


def test_csv_write_preserves_default_comma_decimal_and_encoding(tmp_path):
    output_file = tmp_path / "default.csv"

    CSVBackend().write(_csv_dataset(), output_file)

    assert output_file.read_text(encoding="utf-8").splitlines()[:2] == [
        "value,name",
        "1.5,Ada",
    ]


def test_csv_write_uses_semicolon_delimiter(tmp_path):
    output_file = tmp_path / "semicolon.csv"

    write_dataset(
        _csv_dataset(),
        output_file,
        options=DatasetWriteOptions(csv_delimiter=";"),
    )

    assert output_file.read_text(encoding="utf-8").splitlines()[0] == "value;name"


def test_csv_write_uses_decimal_comma(tmp_path):
    output_file = tmp_path / "decimal-comma.csv"

    write_dataset(
        _csv_dataset(),
        output_file,
        options=DatasetWriteOptions(csv_decimal=","),
    )

    assert '"1,5",Ada' in output_file.read_text(encoding="utf-8")


def test_csv_write_uses_utf8_bom(tmp_path):
    output_file = tmp_path / "utf8-sig.csv"

    write_dataset(
        _csv_dataset(),
        output_file,
        options=DatasetWriteOptions(encoding="utf-8-sig"),
    )

    assert output_file.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("delimiter", ["", "||"])
def test_csv_options_reject_invalid_delimiter(delimiter):
    with pytest.raises(
        ValueError,
        match="Invalid CSV delimiter: delimiter must be exactly one character",
    ):
        DatasetWriteOptions(csv_delimiter=delimiter)


@pytest.mark.parametrize("decimal", ["", ".."])
def test_csv_options_reject_invalid_decimal_separator(decimal):
    with pytest.raises(
        ValueError,
        match=(
            "Invalid CSV decimal separator: decimal separator must be exactly one "
            "character"
        ),
    ):
        DatasetReadOptions(csv_decimal=decimal)


@pytest.mark.parametrize(
    ("delimiter", "decimal"),
    [(";", ";"), (",", ","), (".", ".")],
)
def test_csv_options_reject_equal_separators(delimiter, decimal):
    with pytest.raises(
        ValueError,
        match="CSV delimiter and decimal separator cannot be the same character",
    ):
        DatasetWriteOptions(csv_delimiter=delimiter, csv_decimal=decimal)


def test_csv_read_uses_encoding_delimiter_and_decimal(tmp_path):
    input_file = tmp_path / "latin1.csv"
    input_file.write_bytes("value;name\r\n1,5;André\r\n".encode("latin1"))

    dataset = read_dataset(
        input_file,
        options=DatasetReadOptions(
            encoding="latin1",
            csv_delimiter=";",
            csv_decimal=",",
        ),
    )

    assert dataset.dataframe.to_dict(orient="records") == [
        {"value": 1.5, "name": "André"}
    ]


def _csv_dataset() -> Dataset:
    return Dataset(
        pd.DataFrame(
            {
                "value": [1.5, 2.75],
                "name": ["Ada", "Grace"],
            }
        )
    )
