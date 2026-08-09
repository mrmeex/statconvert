from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.metadata.sidecar import parse_payload_text


runner = CliRunner()


def _source(tmp_path):
    source = tmp_path / "data.csv"
    pd.DataFrame({"status": [1, 2]}).to_csv(source, index=False)
    return source


def _patch(tmp_path):
    path = tmp_path / "patch.toml"
    path.write_text("""
[dataset_label]
action = "set"
value = "Edited"
[[variable_labels]]
column = "status"
action = "set"
value = "Status"
[[measurement_levels]]
column = "status"
action = "set"
value = "nominal"
""", encoding="utf-8")
    return path


def test_patch_dry_run_human_and_json_write_nothing(tmp_path):
    source = _source(tmp_path)
    target = tmp_path / "out.json"
    command = [
        "metadata", str(source), "--patch", str(_patch(tmp_path)),
        "--sidecar-output", str(target), "--dry-run",
    ]

    human = runner.invoke(app, command)
    machine = runner.invoke(app, [*command, "--json"])

    assert human.exit_code == 0
    assert "Metadata Sidecar Preview" in human.output
    payload = json.loads(machine.output)
    assert payload["writes"] is False
    assert payload["source_data_modified"] is False
    assert not target.exists()


def test_patch_save_and_overwrite_protection(tmp_path):
    source = _source(tmp_path)
    before = source.read_bytes()
    target = tmp_path / "out.json"
    command = [
        "metadata", str(source), "--patch", str(_patch(tmp_path)),
        "--sidecar-output", str(target), "--json",
    ]

    saved = runner.invoke(app, command)
    collision = runner.invoke(app, command)
    overwritten = runner.invoke(app, [*command, "--overwrite-sidecar"])

    assert saved.exit_code == 0 and json.loads(saved.output)["writes"] is True
    assert collision.exit_code == 1
    assert json.loads(collision.output)["overwrite_required"] is True
    assert overwritten.exit_code == 0
    assert source.read_bytes() == before
    assert parse_payload_text(target.read_text(encoding="utf-8"), source=str(target)).dataset_label == "Edited"


def test_apply_sidecar_dry_run_and_save_to_explicit_output(tmp_path):
    source = _source(tmp_path)
    candidate = Dataset.sidecar_path(source)
    export = runner.invoke(app, ["metadata", str(source), "--export-sidecar"])
    assert export.exit_code == 0
    output = tmp_path / "applied.json"
    base = [
        "metadata", str(source), "--apply-sidecar", "--sidecar-input", str(candidate),
        "--sidecar-output", str(output), "--json",
    ]

    dry = runner.invoke(app, [*base, "--dry-run"])
    saved = runner.invoke(app, base)

    assert dry.exit_code == 0 and json.loads(dry.output)["writes"] is False
    assert not output.exists() or saved.exit_code == 0
    assert saved.exit_code == 0 and json.loads(saved.output)["writes"] is True


def test_patch_requires_explicit_output_and_existing_summary_still_works(tmp_path):
    source = _source(tmp_path)

    missing_output = runner.invoke(app, [
        "metadata", str(source), "--patch", str(_patch(tmp_path)), "--dry-run",
    ])
    summary = runner.invoke(app, ["metadata", str(source)])

    assert missing_output.exit_code == 1
    assert "--patch requires --sidecar-output" in missing_output.output
    assert summary.exit_code == 0
    assert "Metadata Summary" in summary.output


def test_patch_json_has_no_rich_markup(tmp_path):
    source = _source(tmp_path)
    result = runner.invoke(app, [
        "metadata", str(source), "--patch", str(_patch(tmp_path)),
        "--sidecar-output", str(tmp_path / "out.json"), "--dry-run", "--json",
    ])

    assert result.exit_code == 0
    json.loads(result.output)
    assert "[bold" not in result.output and "[cyan" not in result.output


def test_invalid_patch_json_error_is_plain_and_parseable(tmp_path):
    source = _source(tmp_path)
    patch = tmp_path / "bad.toml"
    patch.write_text("[dataset_label\n", encoding="utf-8")

    result = runner.invoke(app, [
        "metadata", str(source), "--patch", str(patch),
        "--sidecar-output", str(tmp_path / "out.json"), "--dry-run", "--json",
    ])

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["valid"] is False
    assert payload["writes"] is False
    assert payload["source_data_modified"] is False
    assert payload["conflicts"][0]["code"] == "metadata_edit_error"
