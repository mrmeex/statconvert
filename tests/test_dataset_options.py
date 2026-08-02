import pandas as pd

from statconvert.dataset import Dataset
from statconvert.dataset_options import DatasetReadOptions
from statconvert.registry import get_backend, read_dataset


def test_pyreadstat_supported_input_receives_encoding(monkeypatch) -> None:
    received = {}

    def fake_read(filename, **kwargs):
        received.update(kwargs)
        return Dataset(pd.DataFrame({"value": [1]}))

    monkeypatch.setattr(get_backend("pyreadstat"), "read", fake_read)

    read_dataset(
        "input.sav",
        options=DatasetReadOptions(encoding="cp1252"),
    )

    assert received == {"encoding": "cp1252"}


def test_pyreadstat_por_warns_and_does_not_receive_encoding(monkeypatch) -> None:
    received = {}
    warning_messages = []

    def fake_read(filename, **kwargs):
        received.update(kwargs)
        return Dataset(pd.DataFrame({"value": [1]}))

    monkeypatch.setattr(get_backend("pyreadstat"), "read", fake_read)

    read_dataset(
        "input.por",
        options=DatasetReadOptions(encoding="cp1252"),
        on_option_warning=warning_messages.append,
    )

    assert received == {}
    assert len(warning_messages) == 1
    assert "--input-encoding" in warning_messages[0]
    assert "por" in warning_messages[0]
    assert "ignored" in warning_messages[0]
