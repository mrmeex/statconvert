from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def test_type_plan_defaults_to_safe_and_writes_nothing(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    before = _identity(source)
    before_files = sorted(path.name for path in tmp_path.iterdir())

    result = runner.invoke(app, ["type-plan", str(source), "--target", "parquet"])

    assert result.exit_code == 0
    assert "Transfer Type Plan" in result.output
    assert "Policy: safe" in result.output
    assert "Writes: none" in result.output
    assert _identity(source) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == before_files


def test_type_plan_smallest_types_reports_proposal(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    result = runner.invoke(
        app,
        ["type-plan", str(source), "--target", "parquet", "--policy", "smallest-types"],
    )

    assert result.exit_code == 0
    assert "smallest-types" in result.output
    assert "TYPE_NARROW_SAFE" in result.output


def test_type_plan_json_is_parseable_bounded_and_rich_free(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    result = runner.invoke(
        app, ["type-plan", str(source), "--target", ".parquet", "--json"]
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["policy"] == "safe"
    assert payload["status"] in {"ready", "warnings"}
    assert payload["scan"]["full_scan"] is True
    assert payload["output"] is None
    assert "\x1b[" not in result.output
    assert "[bold" not in result.output


def test_strict_blocked_plan_exits_nonzero_with_json(tmp_path: Path) -> None:
    source = tmp_path / "mixed.json"
    source.write_text('[{"mixed": 1}, {"mixed": "text"}]', encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "type-plan", str(source), "--target", "parquet",
            "--policy", "strict", "--json",
        ],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["status"] == "blocked"
    assert any(issue["code"] == "TYPE_MIXED_OBJECT_UNSAFE" for issue in payload["issues"])


def test_warning_only_plan_exits_zero(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    result = runner.invoke(
        app, ["type-plan", str(source), "--target", "csv", "--json"]
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["status"] == "warnings"
    assert payload["summary"]["warning_count"] > 0


def test_read_only_and_unknown_targets_are_blocked_json(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    read_only = runner.invoke(
        app, ["type-plan", str(source), "--target", "sas7bdat", "--json"]
    )
    unknown = runner.invoke(
        app, ["type-plan", str(source), "--target", "orc", "--json"]
    )

    assert read_only.exit_code == 1
    assert json.loads(read_only.output)["issues"][0]["code"] == "TRANSFER_TARGET_UNWRITABLE"
    assert unknown.exit_code == 1
    assert json.loads(unknown.output)["issues"][0]["code"] == "TRANSFER_TARGET_UNKNOWN"


def test_legacy_and_unknown_policies_are_rejected(tmp_path: Path) -> None:
    source = _csv(tmp_path)
    legacy = runner.invoke(
        app,
        ["type-plan", str(source), "--target", "parquet", "--policy", "legacy-compatible"],
    )
    unknown = runner.invoke(
        app,
        ["type-plan", str(source), "--target", "parquet", "--policy", "anything"],
    )

    assert legacy.exit_code == 1
    assert "not implemented" in legacy.output
    assert unknown.exit_code == 1
    assert "Unknown transfer policy" in unknown.output


def test_type_plan_selects_existing_workbook_object_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "book.xlsx"
    with pd.ExcelWriter(source) as writer:
        pd.DataFrame({"DataId": [1]}).to_excel(writer, sheet_name="Data", index=False)
        pd.DataFrame({"LookupCode": ["A"]}).to_excel(
            writer, sheet_name="Lookup", index=False
        )
    before = _identity(source)

    result = runner.invoke(
        app,
        [
            "type-plan", str(source), "--object", "Lookup",
            "--target", "parquet", "--json",
        ],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["source"]["object"] == "Lookup"
    assert payload["source"]["columns"] == 1
    assert _identity(source) == before
    assert not list(tmp_path.glob("*.statconvert-metadata.json"))


def test_type_plan_help_and_existing_commands_have_expected_boundary() -> None:
    type_help = runner.invoke(app, ["type-plan", "--help"])
    convert_help = runner.invoke(app, ["convert", "--help"])
    batch_help = runner.invoke(app, ["batch", "--help"])

    assert type_help.exit_code == 0
    assert "--target" in type_help.output
    assert "--policy" in type_help.output
    assert "--json" in type_help.output
    assert "--policy" in convert_help.output
    assert "--type-plan" in convert_help.output
    assert "--optimize-types" in convert_help.output
    assert "--policy" not in batch_help.output


def _csv(tmp_path: Path) -> Path:
    source = tmp_path / "input.csv"
    pd.DataFrame({"small": [1, 2], "text": ["a", "abcd"]}).to_csv(
        source, index=False
    )
    return source


def _identity(path: Path) -> tuple[str, int, int]:
    return (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        path.stat().st_size,
        path.stat().st_mtime_ns,
    )
