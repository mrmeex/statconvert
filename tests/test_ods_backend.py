import pandas as pd
from pandas.testing import assert_frame_equal

from statconvert.backends.ods_backend import ODSBackend
from statconvert.converter import transform
from statconvert.dataset import Dataset
from statconvert.registry import get_backend_for_file


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
            "C": [1.5, 2.5, 3.5],
        }
    )


def test_ods_roundtrip(tmp_path):

    backend = ODSBackend()
    output_file = tmp_path / "output.ods"
    expected = _sample_dataframe()

    backend.write(
        Dataset(dataframe=expected),
        output_file
    )

    result = backend.read(output_file)

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["backend"] == "ods"
    assert result.metadata["file_type"] == ".ods"
    assert result.metadata["sheet_name"] == 0
    assert result.metadata["engine"] == "odf"


def test_registry_resolves_ods_to_ods_backend(tmp_path):

    assert isinstance(
        get_backend_for_file(tmp_path / "sample.ods"),
        ODSBackend
    )


def test_converter_csv_to_ods(tmp_path):

    source = tmp_path / "source.csv"
    target = tmp_path / "target.ods"

    _sample_dataframe().to_csv(
        source,
        index=False
    )

    dataset = transform(
        source,
        target
    )

    assert target.exists()
    assert dataset.rows == 3

    result = ODSBackend().read(
        target
    )

    assert_frame_equal(
        result.dataframe,
        _sample_dataframe()
    )


def test_converter_ods_to_csv(tmp_path):

    source = tmp_path / "source.ods"
    target = tmp_path / "target.csv"
    expected = _sample_dataframe()

    ODSBackend().write(
        Dataset(dataframe=expected),
        source
    )

    dataset = transform(
        source,
        target
    )

    assert target.exists()
    assert dataset.rows == 3

    result = pd.read_csv(
        target
    )

    assert_frame_equal(
        result,
        expected
    )


def test_read_specific_sheet_name(tmp_path):

    output_file = tmp_path / "sheets.ods"
    expected = pd.DataFrame(
        {
            "Value": [10, 20],
        }
    )

    with pd.ExcelWriter(
        output_file,
        engine="odf"
    ) as writer:
        pd.DataFrame(
            {
                "Value": [1, 2],
            }
        ).to_excel(
            writer,
            sheet_name="First",
            index=False
        )
        expected.to_excel(
            writer,
            sheet_name="Second",
            index=False
        )

    result = ODSBackend().read(
        output_file,
        sheet_name="Second"
    )

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["sheet_name"] == "Second"
