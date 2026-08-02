from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.cli import app
from statconvert.config import load_config
from statconvert.contracts import (
    contract_issue_rows,
    contract_validation_summary,
    validate_schema_contract_file,
)
from statconvert.reporting import build_schema_contract_section
from statconvert.registry import read_dataset


runner = CliRunner()


def test_contract_reporting_helpers_reuse_detailed_result(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    validation = validate_schema_contract_file(
        read_dataset(str(source)),
        contract,
    )

    summary = contract_validation_summary(validation)
    rows = contract_issue_rows(validation)

    assert summary == {
        "contract_path": str(contract),
        "status": "failed",
        "issue_count": 2,
        "error_count": 1,
        "warning_count": 1,
        "info_count": 0,
        "checked_rule_count": 2,
        "checked_column_count": 2,
    }
    assert rows[0]["source_rule"] == "known_status"
    assert rows[0]["affected_rows"] == 6
    assert len(rows[0]["samples"]) == 5
    assert rows[1]["severity"] == "warning"


def test_contract_report_section_contains_summary_and_issue_details(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    validation = validate_schema_contract_file(
        read_dataset(str(source)),
        contract,
    )

    section = build_schema_contract_section(validation)
    metrics = {metric.name: metric.value for metric in section.metrics}
    row = section.tables[0].rows[0]

    assert section.key == "schema_contract"
    assert section.title == "Schema Contract Validation"
    assert metrics["status"] == "failed"
    assert metrics["checked_rule_count"] == 2
    assert row["code"] == "rule_allowed_values_violation"
    assert row["source_rule"] == "known_status"
    assert row["expected"] == ["active"]
    assert len(row["samples"]) == 5


def test_warning_contract_report_status_respects_strict_policy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    pd.DataFrame({"email": ["bad"]}).to_csv(source, index=False)
    contract = tmp_path / "warning.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true
[[rules]]
name = "valid_email"
type = "regex"
column = "email"
pattern = "^[^@]+@[^@]+$"
severity = "warning"
""".lstrip(),
        encoding="utf-8",
    )
    validation = validate_schema_contract_file(
        read_dataset(str(source)),
        contract,
    )

    normal = contract_validation_summary(validation)
    strict = contract_validation_summary(validation, strict=True)

    assert normal["status"] == "passed_with_warnings"
    assert strict["status"] == "failed"


def test_report_json_includes_contract_summary_and_details(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--quiet",
        ],
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    section = _section(payload, "schema_contract")
    metrics = {
        metric["name"]: metric["value"]
        for metric in section["metrics"]
    }
    rows = section["tables"][0]["rows"]

    assert result.exit_code == 0
    assert payload["summary"]["has_errors"] is True
    assert metrics["contract_path"] == str(contract)
    assert metrics["status"] == "failed"
    assert metrics["issue_count"] == 2
    assert metrics["checked_rule_count"] == 2
    assert rows[0]["source_rule"] == "known_status"
    assert rows[0]["samples"] == [
        "bad-0",
        "bad-1",
        "bad-2",
        "bad-3",
        "bad-4",
    ]


def test_report_csv_contains_one_detailed_table_row_per_contract_issue(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.csv"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--quiet",
        ],
    )
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    issue_rows = [
        row
        for row in rows
        if row["section"] == "schema_contract"
        and row["item_type"] == "table"
        and row["table"] == "schema_contract_issues"
    ]
    details = [json.loads(row["value"]) for row in issue_rows]

    assert result.exit_code == 0
    assert len(issue_rows) == 2
    assert details[0]["source_rule"] == "known_status"
    assert details[0]["affected_rows"] == 6
    assert len(details[0]["samples"]) == 5
    assert details[1]["severity"] == "warning"


def test_report_html_contains_contract_summary_and_issue_details(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--quiet",
        ],
    )
    html = output.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Schema Contract Validation" in html
    assert "known_status" in html
    assert "rule_allowed_values_violation" in html
    assert "Affected_Rows" not in html
    assert "affected_rows" in html
    assert "bad-0" in html


def test_report_without_contract_keeps_existing_sections(
    tmp_path: Path,
) -> None:
    source, _ = _write_rule_case(tmp_path)
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        ["report", str(source), "--output", str(output), "--quiet"],
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    keys = [
        section["key"]
        for section in payload["report"]["sections"]
    ]

    assert result.exit_code == 0
    assert keys == [
        "summary",
        "schema",
        "metadata",
        "labels",
        "missing",
        "describe",
        "validation",
    ]


def test_report_contract_is_evaluated_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.json"
    original = cli_module.validate_schema_contract_file
    calls = 0

    def counting_validation(dataset, path):
        nonlocal calls
        calls += 1
        return original(dataset, path)

    monkeypatch.setattr(
        cli_module,
        "validate_schema_contract_file",
        counting_validation,
    )

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert calls == 1


def test_report_invalid_contract_fails_before_writing(
    tmp_path: Path,
) -> None:
    source, _ = _write_rule_case(tmp_path)
    contract = tmp_path / "invalid.toml"
    contract.write_text("[dataset\n", encoding="utf-8")
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    assert "Schema contract contains invalid TOML" in result.output
    assert not output.exists()


def test_report_contract_requires_validation_section(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--no-validation",
        ],
    )

    assert result.exit_code == 1
    assert "requires the report validation section" in result.output
    assert not output.exists()


def test_report_contract_write_config_preserves_option(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)
    output = tmp_path / "report.json"
    config = tmp_path / "report.toml"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--write-config",
            str(config),
        ],
    )

    assert result.exit_code == 0
    assert not output.exists()
    assert config.exists()
    assert load_config(config).options["schema_contract"] == str(contract)


def test_validate_contract_json_includes_report_summary_fields(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--json",
        ],
    )
    contract_payload = json.loads(result.output)["schema_contract"]

    assert result.exit_code == 1
    assert contract_payload["status"] == "failed"
    assert contract_payload["checked_rule_count"] == 2
    assert contract_payload["checked_column_count"] == 2
    assert contract_payload["issue_count"] == 2


def test_validate_terminal_includes_contract_summary_counts(
    tmp_path: Path,
) -> None:
    source, contract = _write_rule_case(tmp_path)

    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
        ],
    )

    assert result.exit_code == 1
    assert "Summary: 1 error(s), 1 warning(s), 0 info" in result.output
    assert "2 named rule(s)" in result.output
    assert "column(s)" in result.output


def test_report_help_owns_schema_contract_option() -> None:
    report_help = runner.invoke(app, ["report", "--help"])

    assert report_help.exit_code == 0
    assert "--schema-contract" in report_help.output


def _write_rule_case(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "rules.csv"
    pd.DataFrame(
        {
            "status": [f"bad-{index}" for index in range(6)],
            "email": ["ok@example.com", "bad", "a@b", "c@d", "e@f", "g@h"],
        }
    ).to_csv(source, index=False)
    contract = tmp_path / "rules.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true

[[rules]]
name = "known_status"
type = "allowed_values"
column = "status"
values = ["active"]
severity = "error"

[[rules]]
name = "valid_email"
type = "regex"
column = "email"
pattern = "^[^@]+@[^@]+$"
severity = "warning"
""".lstrip(),
        encoding="utf-8",
    )
    return source, contract


def _section(payload: dict, key: str) -> dict:
    return next(
        section
        for section in payload["report"]["sections"]
        if section["key"] == key
    )
