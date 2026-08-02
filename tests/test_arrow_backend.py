import pandas as pd
from pandas.testing import assert_frame_equal

from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.dataset import Dataset
from statconvert.converter import transform
from statconvert.registry import get_backend_for_file


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
            "C": [1.5, 2.5, 3.5],
        }
    )


def test_parquet_roundtrip(tmp_path):

    backend = ArrowBackend()
    output_file = tmp_path / "output.parquet"
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
    assert result.metadata["file_type"] == ".parquet"
    assert result.metadata["backend"] == "arrow"
    assert result.metadata["arrow_format"] == "parquet"


def test_feather_roundtrip(tmp_path):

    backend = ArrowBackend()
    output_file = tmp_path / "output.feather"
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
    assert result.metadata["file_type"] == ".feather"
    assert result.metadata["backend"] == "arrow"
    assert result.metadata["arrow_format"] == "feather"


def test_registry_resolves_arrow_formats_to_arrow_backend(tmp_path):

    assert isinstance(
        get_backend_for_file(tmp_path / "sample.parquet"),
        ArrowBackend
    )
    assert isinstance(
        get_backend_for_file(tmp_path / "sample.feather"),
        ArrowBackend
    )


def test_converter_csv_to_parquet(tmp_path):

    source = tmp_path / "source.csv"
    target = tmp_path / "target.parquet"

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

    result = ArrowBackend().read(
        target
    )

    assert_frame_equal(
        result.dataframe,
        _sample_dataframe()
    )


def test_converter_parquet_to_csv(tmp_path):

    source = tmp_path / "source.parquet"
    target = tmp_path / "target.csv"
    expected = _sample_dataframe()

    ArrowBackend().write(
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
