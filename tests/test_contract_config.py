from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config, validate_config, write_config
from statconvert.exceptions import ConfigError


runner = CliRunner()


def test_validate_config_accepts_schema_contract_workflows() -> None:
    validate_workflow = validate_config(
        {
            "command": "validate",
            "input": "input.csv",
            "schema_contract": "schema.toml",
            "json": True,
        }
    )
    report_workflow = validate_config(
        {
            "command": "report",
            "input": "input.csv",
            "output": "report.json",
            "schema_contract": "schema.toml",
        }
    )

    assert validate_workflow.options["schema_contract"] == "schema.toml"
    assert report_workflow.options["schema_contract"] == "schema.toml"


@pytest.mark.parametrize("command", ["validate", "report"])
def test_config_rejects_non_string_schema_contract(command: str) -> None:
    raw: dict[str, object] = {
        "command": command,
        "input": "input.csv",
        "schema_contract": 123,
    }
    if command == "report":
        raw["output"] = "report.json"

    with pytest.raises(
        ConfigError,
        match="'schema_contract' must be a string",
    ):
        validate_config(raw)


def test_report_config_rejects_contract_without_validation_section() -> None:
    with pytest.raises(
        ConfigError,
        match="'schema_contract' cannot be used with 'no_validation'",
    ):
        validate_config(
            {
                "command": "report",
                "input": "input.csv",
                "output": "report.json",
                "schema_contract": "schema.toml",
                "no_validation": True,
            }
        )


def test_config_run_validate_with_contract_preserves_json_and_exit(
    tmp_path: Path,
) -> None:
    source, contract = _write_failure_case(tmp_path)
    config = tmp_path / "validate.toml"
    write_config(
        {
            "command": "validate",
            "input": str(source),
            "schema_contract": str(contract),
            "json": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert isinstance(payload["validation"], list)
    assert payload["schema_contract"]["status"] == "failed"
    assert payload["schema_contract"]["issues"][0]["source_rule"] == "required_id"


def test_config_run_report_with_contract_is_observational(
    tmp_path: Path,
) -> None:
    source, contract = _write_failure_case(tmp_path)
    output = tmp_path / "report.json"
    config = tmp_path / "report.toml"
    write_config(
        {
            "command": "report",
            "input": str(source),
            "output": str(output),
            "schema_contract": str(contract),
            "quiet": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])
    payload = json.loads(output.read_text(encoding="utf-8"))
    sections = {
        section["key"]: section
        for section in payload["report"]["sections"]
    }

    assert result.exit_code == 0
    assert sections["schema_contract"]["issues"][0]["code"] == (
        "rule_not_null_violation"
    )


@pytest.mark.parametrize("invalid_contents", [None, "[dataset\n"])
def test_config_run_validate_fails_friendly_for_invalid_contract(
    tmp_path: Path,
    invalid_contents: str | None,
) -> None:
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [1]}).to_csv(source, index=False)
    contract = tmp_path / "schema.toml"
    if invalid_contents is not None:
        contract.write_text(invalid_contents, encoding="utf-8")
    config = tmp_path / "validate.toml"
    write_config(
        {
            "command": "validate",
            "input": str(source),
            "schema_contract": str(contract),
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 1
    expected = (
        "does not exist"
        if invalid_contents is None
        else "contains invalid TOML"
    )
    assert expected in result.output
    assert "Traceback" not in result.output


def test_validate_write_config_preserves_schema_contract(
    tmp_path: Path,
) -> None:
    source, contract = _write_passing_case(tmp_path)
    config = tmp_path / "validate.toml"

    written = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--schema-contract",
            str(contract),
            "--json",
            "--write-config",
            str(config),
        ],
    )
    run = runner.invoke(app, ["config", "run", str(config)])

    assert written.exit_code == 0
    assert "No validation was run" in written.output
    assert load_config(config).options["schema_contract"] == str(contract)
    assert run.exit_code == 0
    assert json.loads(run.stdout)["schema_contract"]["valid"] is True


def test_report_write_config_preserves_schema_contract(
    tmp_path: Path,
) -> None:
    source, contract = _write_passing_case(tmp_path)
    output = tmp_path / "report.json"
    config = tmp_path / "report.toml"

    written = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--schema-contract",
            str(contract),
            "--quiet",
            "--write-config",
            str(config),
        ],
    )
    assert not output.exists()
    run = runner.invoke(app, ["config", "run", str(config)])

    assert written.exit_code == 0
    assert load_config(config).options["schema_contract"] == str(contract)
    assert run.exit_code == 0
    assert output.exists()


def test_config_init_supports_validate_template(tmp_path: Path) -> None:
    config = tmp_path / "validate.toml"

    result = runner.invoke(
        app,
        ["config", "init", "validate", "--output", str(config)],
    )

    assert result.exit_code == 0
    model = load_config(config)
    assert model.command == "validate"
    assert model.options["schema_contract"] == "./schema.toml"


def test_schema_command_remains_outside_workflow_configs() -> None:
    with pytest.raises(ConfigError, match="unsupported command 'schema'"):
        validate_config(
            {
                "command": "schema",
                "input": "input.csv",
                "export_contract": "schema.toml",
            }
        )


def _write_failure_case(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [1, None]}).to_csv(source, index=False)
    contract = tmp_path / "schema.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true
[[rules]]
name = "required_id"
type = "not_null"
column = "id"
severity = "error"
""".lstrip(),
        encoding="utf-8",
    )
    return source, contract


def _write_passing_case(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [1, 2]}).to_csv(source, index=False)
    contract = tmp_path / "schema.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = false
[[columns]]
name = "id"
nullable = false
""".lstrip(),
        encoding="utf-8",
    )
    return source, contract
