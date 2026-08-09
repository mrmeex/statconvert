from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataDiagnosticsError, OutputPathError
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.metadata.editing import (
    parse_metadata_patch,
    preview_metadata_patch,
    preview_sidecar_apply,
    save_metadata_sidecar,
)
from statconvert.metadata.sidecar import dataset_to_payload, parse_payload_text, serialize_payload


def _dataset(source: Path) -> Dataset:
    metadata = DatasetMetadata(dataset_label="Before", notes=["Original"])
    metadata.add_variable(VariableMetadata(
        name="status", label="Old status", value_labels={1: "One", "1": "String one"},
        storage_type="object", measure="nominal",
        missing_values=[-99], missing_ranges=[{"lo": 90, "hi": 99}],
        display_format="F2",
    ))
    return Dataset(
        pd.DataFrame({"status": pd.Series([1, "1"], dtype="object")}),
        source_format="csv", source_file=str(source), normalized_metadata=metadata,
    )


def _write_patch(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_patch_parser_accepts_closed_editable_schema(tmp_path):
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "set"
value = "After"
[notes]
action = "replace"
values = ["First", "Second"]
[[variable_labels]]
column = "status"
action = "delete"
[[value_labels]]
column = "status"
action = "set"
value = 2
label = "Two"
[[measurement_levels]]
column = "status"
action = "set"
value = "ordinal"
"""))

    assert patch.dataset_label.value == "After"
    assert patch.notes.values == ("First", "Second")
    assert patch.variable_labels[0].action == "delete"
    assert patch.value_labels[0].value == 2
    assert patch.measurement_levels[0].value == "ordinal"


@pytest.mark.parametrize("field", [
    "missing_values", "missing_ranges", "display_formats", "display_widths",
    "storage_types", "logical_types", "original_types", "raw_metadata", "provenance",
    "source_file", "template", "expression", "url", "callback",
])
def test_patch_parser_rejects_unknown_and_deferred_fields(tmp_path, field):
    patch = _write_patch(tmp_path / "patch.toml", f"[{field}]\naction = \"set\"\n")

    with pytest.raises(MetadataDiagnosticsError, match="Unknown or unsupported"):
        parse_metadata_patch(patch)


@pytest.mark.parametrize("value", ["", "   "])
def test_patch_parser_requires_explicit_label_delete(tmp_path, value):
    patch = _write_patch(tmp_path / "patch.toml", f"""
[[variable_labels]]
column = "status"
action = "set"
value = {json.dumps(value)}
""")

    with pytest.raises(MetadataDiagnosticsError, match="action = 'delete'"):
        parse_metadata_patch(patch)


def test_patch_preview_applies_supported_fields_and_preserves_read_only_fields(tmp_path):
    source = tmp_path / "data.csv"
    dataset = _dataset(source)
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "delete"
[notes]
action = "append"
values = ["Added"]
[[variable_labels]]
column = "status"
action = "set"
value = "New status"
[[value_labels]]
column = "status"
action = "delete"
value = 1
[[value_labels]]
column = "status"
action = "set"
value = "1"
label = "Text one"
[[measurement_levels]]
column = "status"
action = "delete"
"""))
    target = tmp_path / "edited.json"

    preview, edited = preview_metadata_patch(dataset, source, patch, target)
    variable = edited.get_normalized_metadata().get_variable("status")

    assert preview.valid and not preview.writes
    assert preview.source_data_modified is False
    assert preview.target == str(target)
    assert edited.get_normalized_metadata().dataset_label is None
    assert edited.get_normalized_metadata().notes == ["Original", "Added"]
    assert variable.label == "New status"
    assert 1 not in variable.value_labels and variable.value_labels["1"] == "Text one"
    assert variable.measure is None
    assert variable.missing_values == [-99]
    assert variable.missing_ranges == [{"lo": 90, "hi": 99}]
    assert variable.display_format == "F2"


def test_typed_value_label_keys_remain_distinct(tmp_path):
    source = tmp_path / "data.csv"
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[[value_labels]]
column = "status"
action = "set"
value = 1
label = "Numeric"
[[value_labels]]
column = "status"
action = "set"
value = "1"
label = "Text"
"""))

    preview, edited = preview_metadata_patch(_dataset(source), source, patch, tmp_path / "out.json")

    assert preview.valid
    labels = edited.get_normalized_metadata().get_variable("status").value_labels
    assert labels[1] == "Numeric"
    assert labels["1"] == "Text"


def test_duplicate_typed_keys_and_invalid_measurement_are_rejected(tmp_path):
    duplicate = parse_metadata_patch(_write_patch(tmp_path / "duplicate.toml", """
[[value_labels]]
column = "status"
action = "set"
value = 1
label = "One"
[[value_labels]]
column = "status"
action = "delete"
value = 1
"""))
    preview, _ = preview_metadata_patch(
        _dataset(tmp_path / "data.csv"), tmp_path / "data.csv", duplicate, tmp_path / "out.json",
    )
    assert not preview.valid
    assert "metadata_patch_duplicate_value_label_key" in {
        issue.code for issue in preview.conflicts
    }

    invalid = _write_patch(tmp_path / "invalid.toml", """
[[measurement_levels]]
column = "status"
action = "set"
value = "interval"
""")
    with pytest.raises(MetadataDiagnosticsError, match="nominal, ordinal, or scale"):
        parse_metadata_patch(invalid)


def test_preview_creates_no_output_or_parent_directory(tmp_path):
    source = tmp_path / "data.csv"
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "set"
value = "After"
"""))
    target = tmp_path / "missing" / "out.json"

    preview, _ = preview_metadata_patch(_dataset(source), source, patch, target)

    assert preview.valid
    assert not target.exists()
    assert not target.parent.exists()


def test_save_writes_only_sidecar_and_requires_overwrite(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("status\n1\n", encoding="utf-8")
    before = source.read_bytes()
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "set"
value = "After"
"""))
    target = tmp_path / "out.json"
    preview, edited = preview_metadata_patch(_dataset(source), source, patch, target)

    result = save_metadata_sidecar(preview, edited)

    assert result.writes and result.sidecar_target_modified
    assert source.read_bytes() == before
    payload = parse_payload_text(target.read_text(encoding="utf-8"), source=str(target))
    assert payload.dataset_label == "After"
    collision, _ = preview_metadata_patch(_dataset(source), source, patch, target)
    assert not collision.valid and collision.overwrite_required
    with pytest.raises(MetadataDiagnosticsError):
        save_metadata_sidecar(collision, edited)


def test_atomic_overwrite_and_temp_cleanup_on_failure(tmp_path, monkeypatch):
    source = tmp_path / "data.csv"
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "set"
value = "After"
"""))
    preview, edited = preview_metadata_patch(
        _dataset(source), source, patch, target, overwrite=True, dry_run=False,
    )
    original_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("blocked")))

    with pytest.raises(Exception, match="atomically write"):
        save_metadata_sidecar(preview, edited, overwrite=True)

    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".out.json.*.tmp"))
    monkeypatch.setattr(os, "replace", original_replace)
    saved = save_metadata_sidecar(preview, edited, overwrite=True)
    assert saved.writes and "After" in target.read_text(encoding="utf-8")


def test_invalid_utf8_patch_fails_before_preview(tmp_path):
    patch = tmp_path / "patch.toml"
    patch.write_bytes(b"\xff\xfe")

    with pytest.raises(MetadataDiagnosticsError, match="not valid UTF-8"):
        parse_metadata_patch(patch)


def test_apply_sidecar_preview_and_save_are_sidecar_only(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("status\n1\n", encoding="utf-8")
    before = source.read_bytes()
    candidate = tmp_path / "candidate.json"
    payload = dataset_to_payload(_dataset(source))
    payload["dataset_metadata"]["dataset_label"] = "Applied"
    candidate.write_text(serialize_payload(payload), encoding="utf-8")
    target = tmp_path / "applied.json"

    preview, edited = preview_sidecar_apply(
        _dataset(source), source, candidate, target, dry_run=True,
    )
    result = save_metadata_sidecar(preview, edited)

    assert preview.valid and not preview.writes
    assert result.writes
    assert source.read_bytes() == before
    assert parse_payload_text(target.read_text(encoding="utf-8"), source=str(target)).dataset_label == "Applied"


def test_container_editing_is_explicitly_deferred(tmp_path):
    source = tmp_path / "book.xlsx"
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "set"
value = "After"
"""))

    with pytest.raises(MetadataDiagnosticsError, match="container formats is deferred"):
        preview_metadata_patch(_dataset(source), source, patch, tmp_path / "out.json", object_name="Data")


def test_source_data_path_cannot_be_sidecar_target(tmp_path):
    source = tmp_path / "data.csv"
    patch = parse_metadata_patch(_write_patch(tmp_path / "patch.toml", """
[dataset_label]
action = "delete"
"""))

    with pytest.raises(OutputPathError, match="replace the source data file"):
        preview_metadata_patch(_dataset(source), source, patch, source)
