import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from statconvert.backends.r_backend import RBackend
from statconvert.converter import transform
from statconvert.dataset import Dataset
from statconvert.exceptions import ObjectNotFoundError
from statconvert.registry import get_backend_for_file


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": ["x", "y", "z"],
            "C": [1.5, 2.5, 3.5],
        }
    )


def test_rds_roundtrip(tmp_path):

    backend = RBackend()
    output_file = tmp_path / "output.rds"
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
    assert result.metadata["backend"] == "r"
    assert result.metadata["file_type"] == ".rds"
    assert result.metadata["object_count"] == 1


def test_rdata_roundtrip(tmp_path):

    backend = RBackend()
    output_file = tmp_path / "output.RData"
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
    assert result.metadata["backend"] == "r"
    assert result.metadata["file_type"] == ".rdata"
    assert result.metadata["selected_object"] == "data"


def test_rda_roundtrip(tmp_path):

    backend = RBackend()
    output_file = tmp_path / "output.rda"
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
    assert result.metadata["backend"] == "r"
    assert result.metadata["file_type"] == ".rda"


def test_registry_resolves_r_formats_to_r_backend(tmp_path):

    assert isinstance(
        get_backend_for_file(tmp_path / "sample.rds"),
        RBackend
    )
    assert isinstance(
        get_backend_for_file(tmp_path / "sample.RData"),
        RBackend
    )
    assert isinstance(
        get_backend_for_file(tmp_path / "sample.rda"),
        RBackend
    )


def test_rdata_object_name_selection(tmp_path):

    backend = RBackend()
    output_file = tmp_path / "named.RData"
    expected = _sample_dataframe()

    backend.write(
        Dataset(dataframe=expected),
        output_file,
        object_name="survey"
    )

    result = backend.read(
        output_file,
        object_name="survey"
    )

    assert_frame_equal(
        result.dataframe,
        expected
    )
    assert result.metadata["selected_object"] == "survey"


def test_rdata_missing_object_name_raises_object_not_found_error(tmp_path):

    backend = RBackend()
    output_file = tmp_path / "named.RData"

    backend.write(
        Dataset(dataframe=_sample_dataframe()),
        output_file,
        object_name="survey"
    )

    with pytest.raises(
        ObjectNotFoundError,
        match="Object 'missing' was not found",
    ):
        backend.read(
            output_file,
            object_name="missing"
        )


def test_converter_csv_to_rds(tmp_path):

    source = tmp_path / "source.csv"
    target = tmp_path / "target.rds"

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

    result = RBackend().read(
        target
    )

    assert_frame_equal(
        result.dataframe,
        _sample_dataframe()
    )


def test_converter_rds_to_csv(tmp_path):

    source = tmp_path / "source.rds"
    target = tmp_path / "target.csv"
    expected = _sample_dataframe()

    RBackend().write(
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
