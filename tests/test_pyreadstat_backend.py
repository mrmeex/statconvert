import pandas as pd
import pyreadstat

from statconvert.backends.pyreadstat_backend import PyReadstatBackend


def test_spss_read(tmp_path):

    source = tmp_path / "test.sav"


    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "score": [10.5, 20.5, 30.5]
        }
    )


    pyreadstat.write_sav(
        df,
        source
    )


    backend = PyReadstatBackend()

    dataset = backend.read(
        source
    )


    assert dataset.rows == 3

    assert dataset.columns == [
        "id",
        "score"
    ]

    assert dataset.source_format == "sav"



def test_spss_write(tmp_path):

    source = tmp_path / "source.sav"
    target = tmp_path / "output.sav"


    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": ["A", "B", "C"]
        }
    )


    pyreadstat.write_sav(
        df,
        source
    )


    backend = PyReadstatBackend()


    dataset = backend.read(
        source
    )


    backend.write(
        dataset,
        target
    )


    result = backend.read(
        target
    )


    assert result.rows == 3

    assert result.columns == [
        "id",
        "value"
    ]