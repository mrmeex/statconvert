from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from statconvert.contracts import load_contract, parse_contract
from statconvert.exceptions import ContractError


def test_valid_minimal_contract_parses() -> None:
    contract = parse_contract(
        {
            "contract_version": 1,
            "dataset": {},
        }
    )

    assert contract.contract_version == 1
    assert contract.dataset.require_columns is True
    assert contract.dataset.allow_extra_columns is False
    assert contract.dataset.column_order == "ignore"
    assert contract.columns == ()


def test_valid_column_contract_parses_from_toml() -> None:
    contract = parse_contract(
        tomllib.loads(
            """
contract_version = 1
name = "Orders"
description = "Expected order data"

[dataset]
require_columns = true
allow_extra_columns = false
column_order = "exact"

[[columns]]
name = "id"
required = true
storage_type = "int64"
logical_type = "integer"
nullable = false
unique = true

[[columns]]
name = "amount"
required = false
logical_type = "number"
allowed_values = [0, 10, 20]
min = 0
max = 20
regex = "^[0-9]+$"
"""
        )
    )

    assert contract.name == "Orders"
    assert contract.description == "Expected order data"
    assert contract.dataset.column_order == "exact"
    assert [column.name for column in contract.columns] == ["id", "amount"]
    assert contract.columns[0].unique is True
    assert contract.columns[1].allowed_values == (0, 10, 20)
    assert contract.columns[1].min_value == 0
    assert contract.columns[1].max_value == 20


def test_contract_model_serializes_to_toml_shaped_dict() -> None:
    contract = parse_contract(
        {
            "contract_version": 1,
            "name": "People",
            "dataset": {"column_order": "prefix"},
            "columns": [
                {
                    "name": "id",
                    "nullable": False,
                    "allowed_values": [1, 2],
                    "min": 1,
                }
            ],
        }
    )

    assert contract.to_dict() == {
        "contract_version": 1,
        "name": "People",
        "dataset": {
            "require_columns": True,
            "allow_extra_columns": False,
            "column_order": "prefix",
        },
        "columns": [
            {
                "name": "id",
                "required": True,
                "nullable": False,
                "unique": False,
                "allowed_values": [1, 2],
                "min": 1,
            }
        ],
    }


def test_duplicate_column_definitions_fail() -> None:
    with pytest.raises(ContractError, match="duplicate column definitions: id"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "columns": [
                    {"name": "id"},
                    {"name": "id"},
                ],
            }
        )


@pytest.mark.parametrize("version", [0, 2, 99])
def test_unsupported_contract_version_fails(version: int) -> None:
    with pytest.raises(ContractError, match="unsupported contract_version"):
        parse_contract(
            {
                "contract_version": version,
                "dataset": {},
            }
        )


def test_invalid_column_order_fails() -> None:
    with pytest.raises(ContractError, match="unsupported column_order"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {"column_order": "alphabetical"},
            }
        )


def test_invalid_regex_fails() -> None:
    with pytest.raises(ContractError, match="invalid regex"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "columns": [
                    {
                        "name": "code",
                        "regex": "[",
                    }
                ],
            }
        )


def test_min_greater_than_max_fails() -> None:
    with pytest.raises(ContractError, match="min greater than max"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {},
                "columns": [
                    {
                        "name": "amount",
                        "min": 10,
                        "max": 5,
                    }
                ],
            }
        )


def test_unknown_field_fails_with_context() -> None:
    with pytest.raises(ContractError, match="unknown field 'allow_extras'"):
        parse_contract(
            {
                "contract_version": 1,
                "dataset": {"allow_extras": True},
            }
        )


def test_missing_dataset_section_fails() -> None:
    with pytest.raises(ContractError, match=r"missing required section \[dataset\]"):
        parse_contract({"contract_version": 1})


def test_load_contract_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="file does not exist"):
        load_contract(tmp_path / "missing.toml")


def test_load_contract_reports_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "contract.toml"
    path.write_text("contract_version = [", encoding="utf-8")

    with pytest.raises(ContractError, match="invalid TOML"):
        load_contract(path)


def test_load_contract_adds_source_path_to_validation_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.toml"
    path.write_text(
        'contract_version = 1\n[dataset]\ncolumn_order = "bad"\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ContractError,
        match=r"Schema contract error in .*contract\.toml",
    ):
        load_contract(path)
