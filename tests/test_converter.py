from statconvert.converter import transform


def test_excel_to_excel_conversion(tmp_path):

    import pandas as pd


    source = tmp_path / "source.xlsx"
    target = tmp_path / "target.xlsx"


    # Create source file
    pd.DataFrame(
        {
            "Name": ["Alice", "Bob"],
            "Age": [25, 30],
        }
    ).to_excel(
        source,
        index=False
    )


    # Run converter pipeline
    dataset = transform(
        source,
        target
    )


    # Validate result
    assert dataset.rows == 2
    assert dataset.columns == [
        "Name",
        "Age"
    ]

    assert target.exists()