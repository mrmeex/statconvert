import pandas as pd


def test_dataset_preview():

    from statconvert.dataset import Dataset


    df = pd.DataFrame(
        {
            "A": [1,2,3],
            "B": ["x","y","z"]
        }
    )


    dataset = Dataset(
        dataframe=df
    )


    result = dataset.preview(2)


    assert len(result) == 2
    assert list(result.columns) == [
        "A",
        "B"
    ]