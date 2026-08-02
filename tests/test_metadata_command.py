from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyreadstat
from typer.testing import CliRunner

from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.backends.csv_backend import CSVBackend
from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.metadata.sidecar import (
    dataset_to_payload,
    parse_payload_text,
    serialize_payload,
)


runner = CliRunner()


def _write_labelled_sav(path: Path) -> Path:
    pyreadstat.write_sav(
        pd.DataFrame({"status": [1.0, 2.0]}),
        path,
        file_label="Survey",
        note=["Imported"],
        column_labels={"status": "Status"},
        variable_value_labels={
            "status": {1.0: "Active", 2.0: "Inactive"}
        },
    )
    return path


def _rich_dataset() -> Dataset:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label="Embedded survey",
        notes=["Embedded note"],
    )
    metadata.add_variable(
        VariableMetadata(
            name="status",
            label="Embedded status",
            value_labels={1: "Active", 2: "Inactive"},
            storage_type="int64",
        )
    )
    return Dataset(
        dataframe=pd.DataFrame({"status": [1, 2]}),
        source_format="sav",
        normalized_metadata=metadata,
    )


def _payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parse_payload_text(text, source=str(path))
    return json.loads(text)


def _write_custom_sidecar(
    path: Path,
    *,
    columns: tuple[str, ...] = ("status",),
    dataset_label: str = "Applied survey",
    column_label: str = "Applied status",
) -> Path:
    metadata = DatasetMetadata(
        source_format="sav",
        source_backend="pyreadstat",
        dataset_label=dataset_label,
        notes=["Applied note"],
    )
    for name in columns:
        metadata.add_variable(
            VariableMetadata(
                name=name,
                label=column_label,
                storage_type="int64",
            )
        )
    dataset = Dataset(
        dataframe=pd.DataFrame(
            {name: [1] for name in columns}
        ),
        source_format="sav",
        normalized_metadata=metadata,
    )
    path.write_text(
        serialize_payload(dataset_to_payload(dataset)),
        encoding="utf-8",
    )
    return path


def test_metadata_help_lists_explicit_sidecar_options():
    result = runner.invoke(app, ["metadata", "--help"])

    assert result.exit_code == 0
    assert "--export-sidecar" in result.output
    assert "--apply-sidecar" in result.output
    assert "--sidecar-output" in result.output
    assert "--sidecar-input" in result.output
    assert "--overwrite-sidecar" in result.output


def test_metadata_exports_standardized_version_3_sidecar(tmp_path):
    source = _write_labelled_sav(tmp_path / "survey.sav")

    result = runner.invoke(
        app,
        ["metadata", str(source), "--export-sidecar"],
    )

    target = Dataset.sidecar_path(source)
    payload = _payload(target)
    assert result.exit_code == 0
    assert target.exists()
    assert payload["sidecar_version"] == 3
    assert payload["dataset_metadata"]["dataset_label"] == "Survey"
    assert payload["dataset_metadata"]["notes"] == ["Imported"]
    assert payload["columns"][0]["label"] == "Status"
    assert "Metadata sidecar written" in result.output


def test_metadata_exports_only_requested_custom_path(tmp_path):
    source = _write_labelled_sav(tmp_path / "survey.sav")
    target = tmp_path / "copies" / "survey.metadata.json"
    target.parent.mkdir()

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert _payload(target)["sidecar_version"] == 3
    assert not Dataset.sidecar_path(source).exists()


def test_metadata_sidecar_collision_requires_specific_overwrite_option(tmp_path):
    source = _write_labelled_sav(tmp_path / "survey.sav")
    target = tmp_path / "survey.metadata.json"
    command = [
        "metadata",
        str(source),
        "--export-sidecar",
        "--sidecar-output",
        str(target),
    ]
    assert runner.invoke(app, command).exit_code == 0

    collision = runner.invoke(app, command)

    assert collision.exit_code == 1
    assert "Metadata sidecar already exists" in collision.output
    assert "Use --overwrite-sidecar to replace it" in collision.output
    assert "Use --overwrite to replace it" not in collision.output

    overwritten = runner.invoke(app, [*command, "--overwrite-sidecar"])
    assert overwritten.exit_code == 0
    assert _payload(target)["sidecar_version"] == 3


def test_metadata_custom_export_requires_existing_parent(tmp_path):
    source = _write_labelled_sav(tmp_path / "survey.sav")
    target = tmp_path / "missing" / "survey.metadata.json"

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(target),
        ],
    )

    assert result.exit_code == 1
    assert "Parent folder does not exist" in result.output
    assert "Create the folder first" in result.output
    assert not target.parent.exists()


def test_sidecar_options_require_their_workflow_flags(tmp_path):
    source = _write_labelled_sav(tmp_path / "survey.sav")

    output_only = runner.invoke(
        app,
        ["metadata", str(source), "--sidecar-output", str(tmp_path / "x.json")],
    )
    overwrite_only = runner.invoke(
        app,
        ["metadata", str(source), "--overwrite-sidecar"],
    )
    input_only = runner.invoke(
        app,
        ["metadata", str(source), "--sidecar-input", str(tmp_path / "x.json")],
    )
    both = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--apply-sidecar",
        ],
    )

    assert output_only.exit_code == 1
    assert "--sidecar-output requires --export-sidecar" in output_only.output
    assert overwrite_only.exit_code == 1
    assert "--overwrite-sidecar requires --export-sidecar or" in (
        overwrite_only.output
    )
    assert input_only.exit_code == 1
    assert "--sidecar-input requires --apply-sidecar" in input_only.output
    assert both.exit_code == 1
    assert "either --export-sidecar or --apply-sidecar" in both.output


def test_export_uses_resolved_automatic_sidecar_metadata(tmp_path):
    source = tmp_path / "source.csv"
    target = tmp_path / "resolved.json"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    metadata = DatasetMetadata(
        dataset_label="Canonical sidecar",
        notes=["Resolved note"],
    )
    metadata.add_variable(
        VariableMetadata(name="status", label="Resolved status")
    )
    Dataset(
        dataframe=pd.DataFrame({"status": [1]}),
        normalized_metadata=metadata,
    ).write_sidecar(source)

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(target),
        ],
    )

    payload = _payload(target)
    assert result.exit_code == 0
    assert payload["dataset_metadata"]["dataset_label"] == "Canonical sidecar"
    assert payload["columns"][0]["label"] == "Resolved status"
    assert payload["provenance"]["dataset"] == "automatic_sidecar"


def test_export_uses_embedded_arrow_metadata_without_sidecar(tmp_path):
    source = tmp_path / "embedded.parquet"
    target = tmp_path / "from-embedded.json"
    ArrowBackend().write(_rich_dataset(), source)
    Dataset.sidecar_path(source).unlink()

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(target),
        ],
    )

    payload = _payload(target)
    assert result.exit_code == 0
    assert payload["dataset_metadata"]["dataset_label"] == "Embedded survey"
    assert payload["columns"][0]["label"] == "Embedded status"
    assert payload["provenance"]["dataset"] == "embedded_arrow"


def test_export_prefers_sidecar_over_embedded_arrow_metadata(tmp_path):
    source = tmp_path / "both.parquet"
    target = tmp_path / "resolved.json"
    ArrowBackend().write(_rich_dataset(), source)
    sidecar = Dataset.sidecar_path(source)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["dataset_metadata"]["dataset_label"] = "Sidecar survey"
    payload["columns"][0]["label"] = "Sidecar status"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(target),
        ],
    )

    exported = _payload(target)
    assert result.exit_code == 0
    assert exported["dataset_metadata"]["dataset_label"] == "Sidecar survey"
    assert exported["columns"][0]["label"] == "Sidecar status"
    assert exported["provenance"]["dataset"] == "automatic_sidecar"


def test_selected_workbook_object_can_be_exported_but_ambiguous_input_fails(
    tmp_path,
):
    source = tmp_path / "book.xlsx"
    selected_target = tmp_path / "selected.json"
    ambiguous_target = tmp_path / "ambiguous.json"
    with pd.ExcelWriter(source, engine="xlsxwriter") as workbook:
        pd.DataFrame({"id": [1]}).to_excel(
            workbook,
            sheet_name="Data",
            index=False,
        )
        pd.DataFrame({"code": ["A"]}).to_excel(
            workbook,
            sheet_name="Lookup",
            index=False,
        )

    selected = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--object",
            "Data",
            "--export-sidecar",
            "--sidecar-output",
            str(selected_target),
        ],
    )
    ambiguous = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--export-sidecar",
            "--sidecar-output",
            str(ambiguous_target),
        ],
    )

    assert selected.exit_code == 0
    assert [column["name"] for column in _payload(selected_target)["columns"]] == [
        "id"
    ]
    assert ambiguous.exit_code == 1
    assert not ambiguous_target.exists()


def test_apply_validates_active_standardized_sidecar_without_rewriting(tmp_path):
    source = tmp_path / "plain.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    target = Dataset.sidecar_path(source)
    _write_custom_sidecar(target)
    before = target.read_bytes()

    result = runner.invoke(
        app,
        ["metadata", str(source), "--apply-sidecar"],
    )

    assert result.exit_code == 0
    assert "Metadata sidecar is valid and active" in result.output
    assert target.read_bytes() == before


def test_apply_without_standardized_sidecar_reports_expected_path(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "plain.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        ["metadata", "plain.csv", "--apply-sidecar"],
    )

    assert result.exit_code == 1
    assert "No standardized sidecar found" in result.output
    assert "Expected: plain.csv.statconvert-metadata.json" in result.output
    assert "Use --sidecar-input PATH" in result.output


def test_apply_custom_sidecar_writes_v3_without_changing_primary_data(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "plain.csv"
    _write_custom_sidecar(tmp_path / "edited.json")
    pd.DataFrame({"status": [1], "extra": ["x"]}).to_csv(source, index=False)
    before = source.read_bytes()

    result = runner.invoke(
        app,
        [
            "metadata",
            "plain.csv",
            "--apply-sidecar",
            "--sidecar-input",
            "edited.json",
        ],
    )

    target = Dataset.sidecar_path(source)
    payload = _payload(target)
    restored = CSVBackend().read(source)
    assert result.exit_code == 0
    assert "Metadata sidecar applied" in result.output
    assert "Columns without sidecar" in result.output
    assert "metadata: extra" in result.output
    assert source.read_bytes() == before
    assert payload["sidecar_version"] == 3
    assert payload["provenance"]["dataset"] == "explicit_sidecar"
    assert payload["provenance"]["applied_from"] == "edited.json"
    assert restored.get_normalized_metadata().dataset_label == "Applied survey"
    assert restored.variable_labels()["status"] == "Applied status"
    assert restored.metadata_provenance["dataset"] == "automatic_sidecar"
    assert restored.metadata_provenance["transport_provenance"]["dataset"] == (
        "explicit_sidecar"
    )


def test_apply_custom_sidecar_collision_uses_specific_overwrite_option(tmp_path):
    source = tmp_path / "plain.csv"
    first = _write_custom_sidecar(
        tmp_path / "first.json",
        dataset_label="First",
    )
    second = _write_custom_sidecar(
        tmp_path / "second.json",
        dataset_label="Second",
    )
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    base_command = [
        "metadata",
        str(source),
        "--apply-sidecar",
        "--sidecar-input",
    ]
    assert runner.invoke(app, [*base_command, str(first)]).exit_code == 0

    collision = runner.invoke(app, [*base_command, str(second)])

    assert collision.exit_code == 1
    assert "Metadata sidecar already exists" in collision.output
    assert "Use --overwrite-sidecar to replace it" in collision.output
    assert "Use --overwrite to replace it" not in collision.output

    overwritten = runner.invoke(
        app,
        [*base_command, str(second), "--overwrite-sidecar"],
    )
    assert overwritten.exit_code == 0
    assert _payload(Dataset.sidecar_path(source))["dataset_metadata"][
        "dataset_label"
    ] == "Second"


def test_apply_overwrite_can_replace_an_invalid_existing_sidecar(tmp_path):
    source = tmp_path / "plain.csv"
    custom = _write_custom_sidecar(tmp_path / "valid.json")
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    Dataset.sidecar_path(source).write_text("{", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(custom),
            "--overwrite-sidecar",
        ],
    )

    assert result.exit_code == 0
    assert _payload(Dataset.sidecar_path(source))["sidecar_version"] == 3


def test_apply_upgrades_version_2_custom_sidecar_to_version_3(tmp_path):
    source = tmp_path / "plain.csv"
    custom = _write_custom_sidecar(tmp_path / "legacy.json")
    legacy = _payload(custom)
    legacy["sidecar_version"] = 2
    legacy.pop("dataset_metadata")
    legacy.pop("provenance")
    custom.write_text(json.dumps(legacy), encoding="utf-8")
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(custom),
        ],
    )

    assert result.exit_code == 0
    assert _payload(Dataset.sidecar_path(source))["sidecar_version"] == 3


def test_apply_source_equal_to_standardized_target_does_not_need_overwrite(
    tmp_path,
):
    source = tmp_path / "plain.csv"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    target = _write_custom_sidecar(Dataset.sidecar_path(source))
    before = target.read_bytes()

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert "valid and active" in result.output
    assert target.read_bytes() == before


def test_apply_rejects_missing_sidecar_columns_and_duplicate_entries(tmp_path):
    source = tmp_path / "plain.csv"
    missing = _write_custom_sidecar(
        tmp_path / "missing.json",
        columns=("old_name",),
    )
    duplicate = tmp_path / "duplicate.json"
    pd.DataFrame({"status": [1]}).to_csv(source, index=False)
    duplicate_payload = _payload(
        _write_custom_sidecar(tmp_path / "base.json")
    )
    duplicate_payload["columns"].append(
        dict(duplicate_payload["columns"][0])
    )
    duplicate.write_text(json.dumps(duplicate_payload), encoding="utf-8")

    missing_result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(missing),
        ],
    )
    duplicate_result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(duplicate),
        ],
    )

    assert missing_result.exit_code == 1
    assert "Sidecar references columns not present" in missing_result.output
    assert "Edit the sidecar" in missing_result.output
    assert duplicate_result.exit_code == 1
    assert "duplicate column metadata name" in duplicate_result.output
    assert not Dataset.sidecar_path(source).exists()


def test_export_edit_apply_then_automatic_read_uses_applied_metadata(tmp_path):
    labelled = _write_labelled_sav(tmp_path / "labelled.sav")
    edited = tmp_path / "edited.json"
    plain = tmp_path / "plain.csv"
    pd.DataFrame({"status": [1.0, 2.0]}).to_csv(plain, index=False)
    export = runner.invoke(
        app,
        [
            "metadata",
            str(labelled),
            "--export-sidecar",
            "--sidecar-output",
            str(edited),
        ],
    )
    payload = _payload(edited)
    payload["dataset_metadata"]["dataset_label"] = "Edited survey"
    payload["columns"][0]["label"] = "Edited status"
    edited.write_text(json.dumps(payload), encoding="utf-8")

    applied = runner.invoke(
        app,
        [
            "metadata",
            str(plain),
            "--apply-sidecar",
            "--sidecar-input",
            str(edited),
        ],
    )
    inspected = runner.invoke(app, ["labels", str(plain)])

    assert export.exit_code == 0
    assert applied.exit_code == 0
    assert inspected.exit_code == 0
    assert "Edited status" in inspected.output


def test_selected_workbook_object_apply_works_and_ambiguous_apply_fails(
    tmp_path,
):
    source = tmp_path / "book.xlsx"
    custom = _write_custom_sidecar(
        tmp_path / "sheet.json",
        columns=("id",),
        column_label="Selected identifier",
    )
    with pd.ExcelWriter(source, engine="xlsxwriter") as workbook:
        pd.DataFrame({"id": [1]}).to_excel(
            workbook,
            sheet_name="Data",
            index=False,
        )
        pd.DataFrame({"code": ["A"]}).to_excel(
            workbook,
            sheet_name="Lookup",
            index=False,
        )

    selected = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--object",
            "Data",
            "--apply-sidecar",
            "--sidecar-input",
            str(custom),
        ],
    )
    Dataset.sidecar_path(source).unlink()
    ambiguous = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(custom),
        ],
    )

    assert selected.exit_code == 0
    assert ambiguous.exit_code == 1
    assert not Dataset.sidecar_path(source).exists()


def test_apply_sidecar_options_exist_only_on_metadata_command():
    for command in ("convert", "batch", "transform"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "--apply-sidecar" not in result.output
        assert "--sidecar-input" not in result.output


def test_apply_does_not_claim_to_modify_native_statistical_metadata(tmp_path):
    source = _write_labelled_sav(tmp_path / "native.sav")
    custom = _write_custom_sidecar(tmp_path / "custom.json")

    result = runner.invoke(
        app,
        [
            "metadata",
            str(source),
            "--apply-sidecar",
            "--sidecar-input",
            str(custom),
        ],
    )

    assert result.exit_code == 1
    assert "not supported for native statistical formats" in result.output
    assert not Dataset.sidecar_path(source).exists()
