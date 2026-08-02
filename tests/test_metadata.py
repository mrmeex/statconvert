import pandas as pd
import pyreadstat

from statconvert.backends.pyreadstat_backend import PyReadstatBackend


def test_spss_metadata_roundtrip(tmp_path):

    source = tmp_path / "source.sav"
    target = tmp_path / "target.sav"


    df = pd.DataFrame(
        {
            "sex": [1,2,1],
            "age": [25,30,40]
        }
    )


    pyreadstat.write_sav(
        df,
        source,
        column_labels={
            "sex": "Gender",
            "age": "Age"
        },
        variable_value_labels={
            "sex": {
                1: "Male",
                2: "Female"
            }
        }
    )


    backend = PyReadstatBackend()


    dataset = backend.read(source)

    assert dataset.variable_labels()["sex"] == "Gender"


    backend.write(
        dataset,
        target
    )


    result = backend.read(target)


    assert (
        result.variable_labels()["sex"]
        == "Gender"
    )