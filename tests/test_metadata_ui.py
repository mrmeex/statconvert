import pandas as pd

from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.ui.metadata import (
    console,
    show_labels,
    show_metadata_summary,
    show_schema,
)


def _labelled_dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label="Study dataset",
        notes=["Reviewed by data management"],
    )
    metadata.add_variable(
        VariableMetadata(
            name="age",
            label="Age in years",
            storage_type="int64",
            display_format="F8.0",
            measure="scale",
        )
    )
    metadata.add_variable(
        VariableMetadata(
            name="group",
            value_labels={
                1: "Control",
                2: "Treatment",
                3: "Followup",
            },
            storage_type="int64",
        )
    )

    return Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
                "group": [1, 2],
            }
        ),
        normalized_metadata=metadata,
        metadata_provenance={
            "dataset": "automatic_sidecar",
            "columns": {
                "age": "automatic_sidecar",
                "group": "native_file",
            },
        },
    )


def test_schema_ui_helper_can_handle_basic_dataset():

    with console.capture() as capture:
        show_schema(
            _labelled_dataset()
        )

    output = capture.get()

    assert "Schema" in output
    assert "age" in output
    assert "F8.0" in output


def test_labels_ui_helper_can_handle_no_labels():

    dataset = Dataset(
        dataframe=pd.DataFrame(
            {
                "age": [25, 30],
            }
        )
    )

    with console.capture() as capture:
        show_labels(
            dataset
        )

    assert "No labels found." in capture.get()


def test_labels_ui_helper_respects_limit():

    with console.capture() as capture:
        show_labels(
            _labelled_dataset(),
            limit=2,
        )

    output = capture.get()

    assert "Control" in output
    assert "Treatment" in output
    assert "Followup" not in output


def test_metadata_summary_helper_can_handle_basic_metadata():

    with console.capture() as capture:
        show_metadata_summary(
            _labelled_dataset()
        )

    output = capture.get()

    assert "Metadata Summary" in output
    assert "sav" in output
    assert "pyreadstat" in output
    assert "Study dataset" in output
    assert "Reviewed by data management" in output
    assert "automatic_sidecar" in output
    assert "native_file: 1" in output
