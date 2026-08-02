from __future__ import annotations

import json
from pathlib import Path
import tomllib

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.contracts import (
    DataQualityRule,
    DatasetContract,
    SchemaContract,
    contract_to_toml,
    parse_contract,
    validate_contract,
)
from statconvert.dataset import Dataset
from statconvert.exceptions import ContractError


runner = CliRunner()


def test_contract_without_named_rules_remains_valid() -> None:
    contract = parse_contract(
        {
            "contract_version": 1,
            "dataset": {},
        }
    )

    assert contract.rules == ()
    assert "rules" not in contract.to_dict()


def test_schema_contract_positional_fields_remain_backward_compatible() -> None:
    contract = SchemaContract(
        1,
        DatasetContract(),
        (),
        "Existing name",
        "Existing description",
    )

    assert contract.name == "Existing name"
    assert contract.description == "Existing description"
    assert contract.rules == ()


def test_all_named_rule_types_parse() -> None:
    contract = parse_contract(
        tomllib.loads(
            """
contract_version = 1
[dataset]

[[rules]]
name = "known_status"
type = "allowed_values"
column = "status"
values = ["active", "inactive"]

[[rules]]
name = "valid_age"
type = "range"
column = "age"
min = 0
max = 120

[[rules]]
name = "valid_email"
type = "regex"
column = "email"
pattern = "^[^@]+@[^@]+$"
severity = "warning"

[[rules]]
name = "unique_person"
type = "unique"
columns = ["site_id", "person_id"]

[[rules]]
name = "minimum_rows"
type = "row_count"
min = 1

[[rules]]
name = "required_id"
type = "not_null"
column = "person_id"

[[rules]]
name = "short_code"
type = "length"
column = "code"
min = 2
max = 8
"""
        )
    )

    assert [rule.rule_type for rule in contract.rules] == [
        "allowed_values",
        "range",
        "regex",
        "unique",
        "row_count",
        "not_null",
        "length",
    ]
    assert contract.rules[2].severity == "warning"
    assert contract.rules[3].columns == ("site_id", "person_id")


def test_named_rules_serialize_to_deterministic_toml() -> None:
    contract = _contract(
        DataQualityRule(
            name="known_status",
            rule_type="allowed_values",
            column="status",
            values=("active", "inactive"),
            description="Only known workflow states.",
        )
    )

    first = contract_to_toml(contract)
    second = contract_to_toml(contract)
    reparsed = parse_contract(tomllib.loads(first))

    assert first == second
    assert "[[rules]]" in first
    assert 'name = "known_status"' in first
    assert 'type = "allowed_values"' in first
    assert reparsed.rules == contract.rules


def test_allowed_values_rule_uses_severity_source_and_bounded_samples() -> None:
    values = [f"bad-{index}" for index in range(10)]
    result = validate_contract(
        Dataset(pd.DataFrame({"status": values})),
        _contract(
            DataQualityRule(
                name="known_status",
                rule_type="allowed_values",
                severity="warning",
                column="status",
                values=("active",),
            )
        ),
    )

    issue = _issue(result, "rule_allowed_values_violation")
    assert result.valid is True
    assert issue.severity == "warning"
    assert issue.source_rule == "known_status"
    assert issue.affected_rows == 10
    assert len(issue.sample_values) == 5


def test_range_rule_validates_numeric_values() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"age": [-1, 20, 121]})),
        _contract(
            DataQualityRule(
                name="valid_age",
                rule_type="range",
                column="age",
                min_value=0,
                max_value=120,
            )
        ),
    )

    issue = _issue(result, "rule_range_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == (-1, 121)
    assert issue.source_rule == "valid_age"


def test_regex_rule_validates_strings() -> None:
    result = validate_contract(
        Dataset(
            pd.DataFrame(
                {"email": ["a@example.com", "bad-email", 10]}
            )
        ),
        _contract(
            DataQualityRule(
                name="valid_email",
                rule_type="regex",
                column="email",
                pattern=r"^[^@]+@[^@]+$",
            )
        ),
    )

    issue = _issue(result, "rule_regex_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == ("bad-email", 10)


def test_single_column_unique_rule_validates_complete_values() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 1, None, None]})),
        _contract(
            DataQualityRule(
                name="unique_id",
                rule_type="unique",
                columns=("id",),
            )
        ),
    )

    issue = _issue(result, "rule_uniqueness_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == (1.0,)


def test_composite_unique_rule_validates_complete_keys() -> None:
    result = validate_contract(
        Dataset(
            pd.DataFrame(
                {
                    "site": ["A", "A", "A", None],
                    "id": [1, 1, 2, 1],
                }
            )
        ),
        _contract(
            DataQualityRule(
                name="unique_site_id",
                rule_type="unique",
                columns=("site", "id"),
            )
        ),
    )

    issue = _issue(result, "rule_uniqueness_violation")
    assert issue.column == "site, id"
    assert issue.affected_rows == 2
    assert issue.sample_values == (("A", 1),)


def test_row_count_rule_reports_distance_from_bound() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 2]})),
        _contract(
            DataQualityRule(
                name="minimum_rows",
                rule_type="row_count",
                min_value=3,
            )
        ),
    )

    issue = _issue(result, "rule_row_count_violation")
    assert issue.column is None
    assert issue.actual == 2
    assert issue.affected_rows == 1


def test_not_null_rule_validates_missing_values() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, None, 3]})),
        _contract(
            DataQualityRule(
                name="required_id_values",
                rule_type="not_null",
                column="id",
            )
        ),
    )

    issue = _issue(result, "rule_not_null_violation")
    assert issue.affected_rows == 1
    assert issue.source_rule == "required_id_values"


def test_length_rule_validates_strings_and_non_strings() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"code": ["A", "VALID", 10]})),
        _contract(
            DataQualityRule(
                name="code_length",
                rule_type="length",
                column="code",
                min_value=2,
                max_value=5,
            )
        ),
    )

    issue = _issue(result, "rule_length_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == ("A", 10)


def test_missing_referenced_columns_produce_one_rule_issue() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1]})),
        _contract(
            DataQualityRule(
                name="unique_missing_key",
                rule_type="unique",
                columns=("site", "person"),
            )
        ),
    )

    assert len(result.issues) == 1
    issue = _issue(result, "rule_missing_column")
    assert issue.column == "site, person"
    assert issue.actual == ["site", "person"]
    assert issue.source_rule == "unique_missing_key"


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (
            {"name": "bad", "type": "expression"},
            "unsupported type 'expression'",
        ),
        (
            {
                "name": "bad",
                "type": "regex",
                "column": "code",
                "pattern": "[",
            },
            "invalid pattern",
        ),
        (
            {
                "name": "bad",
                "type": "range",
                "column": "age",
                "min": 10,
                "max": 1,
            },
            "min greater than max",
        ),
        (
            {
                "name": "bad",
                "type": "row_count",
                "min": -1,
            },
            "non-negative integer",
        ),
        (
            {
                "name": "bad",
                "type": "allowed_values",
                "column": "status",
            },
            "missing required field 'values'",
        ),
        (
            {
                "name": "bad",
                "type": "unique",
                "columns": [],
            },
            "must not be empty",
        ),
        (
            {
                "name": "bad",
                "type": "not_null",
                "column": "id",
                "values": [1],
            },
            "unknown field 'values'",
        ),
    ],
)
def test_invalid_rule_definitions_fail_friendly(
    rule: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ContractError, match=message):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "rules": [rule],
            }
        )


def test_duplicate_rule_names_fail() -> None:
    with pytest.raises(ContractError, match="duplicate rule names: duplicate"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "rules": [
                    {
                        "name": "duplicate",
                        "type": "row_count",
                        "min": 1,
                    },
                    {
                        "name": "duplicate",
                        "type": "row_count",
                        "max": 10,
                    },
                ],
            }
        )


def test_invalid_rule_severity_fails() -> None:
    with pytest.raises(ContractError, match="unsupported severity 'fatal'"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "rules": [
                    {
                        "name": "minimum_rows",
                        "type": "row_count",
                        "min": 1,
                        "severity": "fatal",
                    }
                ],
            }
        )


def test_named_rule_warning_uses_existing_strict_exit_policy(
    tmp_path: Path,
) -> None:
    source, contract = _write_warning_cli_case(tmp_path)
    command = [
        "validate",
        str(source),
        "--schema-contract",
        str(contract),
    ]

    normal = runner.invoke(app, command)
    strict = runner.invoke(app, [*command, "--strict"])

    assert normal.exit_code == 0
    assert strict.exit_code == 1
    assert "rule_allowed_values_violation" in normal.output
    assert "Source rule: known_status" in normal.output
    assert "passed with warnings" in normal.output
    assert "Schema contract validation: failed" in strict.output
    assert "warning" in normal.output


def test_named_rule_json_contains_source_severity_and_samples(
    tmp_path: Path,
) -> None:
    source, contract = _write_warning_cli_case(tmp_path)

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
    payload = json.loads(result.output)
    issue = payload["schema_contract"]["issues"][0]

    assert result.exit_code == 0
    assert issue["code"] == "rule_allowed_values_violation"
    assert issue["severity"] == "warning"
    assert issue["source_rule"] == "known_status"
    assert issue["sample_values"] == ["unknown"]


def test_exported_starter_contract_does_not_add_named_rules(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "schema.toml"
    pd.DataFrame({"id": [1, 2]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "schema",
            str(source),
            "--export-contract",
            str(output),
        ],
    )
    parsed = tomllib.loads(output.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "rules" not in parsed


def _contract(*rules: DataQualityRule) -> SchemaContract:
    return SchemaContract(
        contract_version=1,
        dataset=DatasetContract(allow_extra_columns=True),
        rules=tuple(rules),
    )


def _issue(result, code: str):
    return next(issue for issue in result.issues if issue.code == code)


def _write_warning_cli_case(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "status.csv"
    pd.DataFrame({"status": ["active", "unknown"]}).to_csv(
        source,
        index=False,
    )
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
severity = "warning"
""".lstrip(),
        encoding="utf-8",
    )
    return source, contract
