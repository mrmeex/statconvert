from types import SimpleNamespace

import pandas as pd
import pytest

from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.exceptions import ConversionError


def test_read_retries_with_datetime_conversion_disabled(monkeypatch, tmp_path):

    calls = []

    def read_sav(filename, **kwargs):
        calls.append(kwargs)

        if len(calls) == 1:
            raise ValueError(
                "STRING type with value 'Alaric Moonveil' "
                "with date type in column 'WIZNAME'"
            )

        return (
            pd.DataFrame(
                {
                    "WIZNAME": ["Alaric Moonveil"],
                }
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr(
        "statconvert.backends.pyreadstat_backend.pyreadstat.read_sav",
        read_sav
    )

    backend = PyReadstatBackend()
    dataset = backend.read(
        tmp_path / "test.sav"
    )

    assert dataset.rows == 1
    assert dataset.columns == ["WIZNAME"]
    assert calls == [
        {},
        {
            "disable_datetime_conversion": True,
        },
    ]
    assert dataset.metadata["datetime_conversion_disabled"] is True


def test_read_does_not_retry_when_datetime_conversion_already_disabled(
    monkeypatch,
    tmp_path
):

    calls = []

    def read_dta(filename, **kwargs):
        calls.append(kwargs)
        raise ValueError(
            "STRING type with value 'Alaric Moonveil' "
            "with date type in column 'WIZNAME'"
        )

    monkeypatch.setattr(
        "statconvert.backends.pyreadstat_backend.pyreadstat.read_dta",
        read_dta
    )

    backend = PyReadstatBackend()

    with pytest.raises(ConversionError):
        backend.read(
            tmp_path / "test.dta",
            disable_datetime_conversion=True
        )

    assert calls == [
        {
            "disable_datetime_conversion": True,
        },
    ]
