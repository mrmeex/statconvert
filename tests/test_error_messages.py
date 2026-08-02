from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config
from statconvert.error_suggestions import did_you_mean, suggest_value
from statconvert.exceptions import ConfigError


runner = CliRunner()


def _write_csv(path: Path, data: dict[str, list[object]] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data or {"id": [1], "value": [10]}).to_csv(path, index=False)
    return path


def _write_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"id": [1]}).to_excel(writer, sheet_name="Data", index=False)
        pd.DataFrame({"id": [2]}).to_excel(writer, sheet_name="Lookup", index=False)
    return path


def test_suggestion_helpers_are_deterministic_and_avoid_weak_matches() -> None:
    assert suggest_value("parqet", ["csv", "parquet", "json"]) == "parquet"
    assert did_you_mean("PARQET", ["csv", "parquet"]) == "Did you mean 'parquet'?"
    assert suggest_value("unrelated", ["csv", "parquet"]) is None


def test_output_safety_errors_show_the_correct_next_step(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input.csv")
    output = tmp_path / "output.csv"
    output.write_text("existing", encoding="utf-8")

    exists = runner.invoke(app, ["convert", str(source), str(output)])
    missing_parent = runner.invoke(
        app,
        ["convert", str(source), str(tmp_path / "missing" / "output.csv")],
    )

    assert exists.exit_code == 1
    assert "Output file already exists" in exists.output
    assert "Suggestion:" in exists.output
    assert "--overwrite" in exists.output
    assert missing_parent.exit_code == 1
    assert "Output directory does not exist" in missing_parent.output
    assert "--create-dirs" in missing_parent.output


def test_write_config_collision_suggests_overwrite_config(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input.csv")
    config = tmp_path / "workflow.toml"
    config.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(tmp_path / "output.csv"),
            "--write-config",
            str(config),
        ],
    )

    assert result.exit_code == 1
    assert "Config file already exists" in result.output
    assert "Use --overwrite-config to replace it" in result.output
    assert "Use --overwrite to replace it" not in result.output


def test_unknown_format_typo_suggests_close_match(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input.csv")

    result = runner.invoke(
        app,
        ["convert", str(source), str(tmp_path / "output.parqet")],
    )

    assert result.exit_code == 1
    assert "Unsupported file format" in result.output
    assert "Did you mean 'parquet'?" in result.output


def test_invalid_config_names_file_command_and_missing_field(tmp_path: Path) -> None:
    config = tmp_path / "bad.toml"
    config.write_text('command = "batch"\noutput = "out"\nto = "parquet"\n')

    result = runner.invoke(app, ["config", "validate", str(config)])

    assert result.exit_code == 1
    assert "bad.toml" in result.output
    assert "missing required field 'input'" in result.output
    with pytest.raises(ConfigError) as error:
        load_config(config)
    assert "command 'batch'" in str(error.value)
    assert "statconvert config init batch" in str(error.value)


def test_object_selection_errors_suggest_objects_command(tmp_path: Path) -> None:
    workbook = _write_workbook(tmp_path / "book.xlsx")

    ambiguous = runner.invoke(
        app,
        ["convert", str(workbook), str(tmp_path / "output.csv")],
    )
    missing = runner.invoke(
        app,
        [
            "convert",
            str(workbook),
            str(tmp_path / "output.csv"),
            "--object",
            "Missing",
        ],
    )

    assert ambiguous.exit_code == 1
    assert "multiple sheets" in ambiguous.output
    assert "statconvert objects" in ambiguous.output
    assert missing.exit_code == 1
    assert "Missing" in missing.output
    assert "statconvert objects" in missing.output


def test_compare_and_transform_errors_include_actionable_context(tmp_path: Path) -> None:
    left = _write_csv(tmp_path / "left.csv", {"id": [1, 1], "value": [1, 2]})
    right = _write_csv(tmp_path / "right.csv", {"id": [1, 2], "value": [1, 2]})
    compare = runner.invoke(
        app,
        ["compare", str(left), str(right), "--key", "id"],
    )
    transform = runner.invoke(
        app,
        [
            "transform",
            str(right),
            str(tmp_path / "transformed.csv"),
            "--select",
            "missing",
        ],
    )

    assert compare.exit_code == 1
    assert "Duplicate key values" in compare.output
    assert "key columns: id" in compare.output
    assert "uniquely identify" in compare.output
    assert transform.exit_code == 1
    assert "Column not found: missing" in transform.output
    assert "operation: --select" in transform.output


def test_batch_no_files_and_all_skipped_have_next_steps(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    no_files = runner.invoke(
        app,
        ["batch", str(empty), str(tmp_path / "out-empty"), "--to", "parquet"],
    )

    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    (unsupported / "notes.txt").write_text("notes", encoding="utf-8")
    all_skipped = runner.invoke(
        app,
        [
            "batch",
            str(unsupported),
            str(tmp_path / "out-skipped"),
            "--to",
            "parquet",
            "--create-dirs",
        ],
    )

    assert no_files.exit_code == 1
    assert "No input files were discovered" in no_files.output
    assert "--recursive" in no_files.output
    assert all_skipped.exit_code == 0
    assert "No items were converted" in all_skipped.output
    assert "statconvert formats" in all_skipped.output


def test_batch_json_failure_remains_parseable(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_workbook(input_dir / "book.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(tmp_path / "output"),
            "--to",
            "csv",
            "--object",
            "Missing",
            "--create-dirs",
            "--json",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["items"][0]["status"] == "failed"
    assert "statconvert objects" in payload["items"][0]["error"]
