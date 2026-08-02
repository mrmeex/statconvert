from statconvert.backends.excel_backend import ExcelBackend


def test_excel_roundtrip(tmp_path):

    backend = ExcelBackend()

    input_file = tmp_path / "input.xlsx"
    output_file = tmp_path / "output.xlsx"

    import pandas as pd

    pd.DataFrame({
        "A": [1, 2, 3]
    }).to_excel(
        input_file,
        index=False
    )


    dataset = backend.read(input_file)

    backend.write(
        dataset,
        output_file
    )


    result = backend.read(output_file)

    assert result.rows == 3
    assert result.columns == ["A"]


def test_excel_roundtrip_preserves_shape_missing_and_datetime_without_index(tmp_path):
    import pandas as pd

    from statconvert.dataset import Dataset

    backend = ExcelBackend()
    output_file = tmp_path / "mixed.xlsx"
    source = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "score": [1.5, None, 3.5],
            "event_date": pd.to_datetime(
                ["2026-01-01", "2026-01-02", None]
            ),
        }
    )

    backend.write(Dataset(source), output_file)
    restored = backend.read(output_file).dataframe

    assert list(restored.columns) == ["id", "score", "event_date"]
    assert restored.shape == source.shape
    assert restored["score"].isna().sum() == 1
    assert restored["event_date"].isna().sum() == 1
    assert pd.api.types.is_datetime64_any_dtype(restored["event_date"])
