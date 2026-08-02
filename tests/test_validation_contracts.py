from __future__ import annotations

import copy
import json

import pandas as pd

from statconvert.contracts import (
    ColumnContract,
    DatasetContract,
    SchemaContract,
    validate_contract,
)
from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata


def test_matching_dataset_is_valid() -> None:
    dataset = _dataset()
    contract = _contract(
        ColumnContract(
            name="id",
            storage_type="int64",
            logical_type="integer",
            nullable=False,
            unique=True,
            min_value=1,
        ),
        ColumnContract(
            name="status",
            logical_type="string",
            allowed_values=("active", "inactive"),
            regex="^[a-z]+$",
        ),
    )

    result = validate_contract(dataset, contract)

    assert result.valid is True
    assert result.issues == ()


def test_missing_required_column_produces_result() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1]})),
        _contract(
            ColumnContract(name="id"),
            ColumnContract(name="name"),
        ),
    )

    issue = _issue(result, "missing_column")
    assert issue.column == "name"
    assert issue.source_rule == "column.required"


def test_require_columns_false_skips_missing_column_check() -> None:
    contract = SchemaContract(
        contract_version=1,
        dataset=DatasetContract(
            require_columns=False,
            allow_extra_columns=True,
        ),
        columns=(ColumnContract(name="missing"),),
    )

    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1]})),
        contract,
    )

    assert not _has_issue(result, "missing_column")


def test_extra_column_produces_result_when_not_allowed() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1], "extra": [2]})),
        _contract(ColumnContract(name="id")),
    )

    issue = _issue(result, "unexpected_column")
    assert issue.column == "extra"
    assert issue.source_rule == "dataset.allow_extra_columns"


def test_exact_column_order_mismatch_produces_result() -> None:
    contract = SchemaContract(
        contract_version=1,
        dataset=DatasetContract(column_order="exact"),
        columns=(
            ColumnContract(name="id"),
            ColumnContract(name="status"),
        ),
    )

    result = validate_contract(
        Dataset(
            pd.DataFrame(
                {
                    "status": ["active"],
                    "id": [1],
                }
            )
        ),
        contract,
    )

    issue = _issue(result, "column_order_mismatch")
    assert issue.expected == ["id", "status"]
    assert issue.actual == ["status", "id"]


def test_prefix_column_order_accepts_extra_trailing_columns() -> None:
    contract = SchemaContract(
        contract_version=1,
        dataset=DatasetContract(
            allow_extra_columns=True,
            column_order="prefix",
        ),
        columns=(
            ColumnContract(name="id"),
            ColumnContract(name="status"),
        ),
    )

    result = validate_contract(
        Dataset(
            pd.DataFrame(
                {
                    "id": [1],
                    "status": ["active"],
                    "notes": ["ok"],
                }
            )
        ),
        contract,
    )

    assert result.valid is True


def test_storage_and_logical_type_mismatches_produce_results() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 2]})),
        _contract(
            ColumnContract(
                name="id",
                storage_type="float64",
                logical_type="string",
            )
        ),
    )

    assert _has_issue(result, "storage_type_mismatch")
    assert _has_issue(result, "logical_type_mismatch")


def test_number_logical_type_accepts_integer_and_float_columns() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 2], "score": [1.5, 2.5]})),
        _contract(
            ColumnContract(name="id", logical_type="number"),
            ColumnContract(name="score", logical_type="number"),
        ),
    )

    assert not _has_issue(result, "logical_type_mismatch")


def test_nullable_violation_produces_affected_row_count() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1.0, None, 3.0]})),
        _contract(ColumnContract(name="id", nullable=False)),
    )

    issue = _issue(result, "nullable_violation")
    assert issue.affected_rows == 1
    assert issue.actual == 1


def test_uniqueness_violation_produces_samples() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 1, 2]})),
        _contract(ColumnContract(name="id", unique=True)),
    )

    issue = _issue(result, "uniqueness_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == (1,)


def test_allowed_values_violation_produces_samples() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"status": ["active", "other", None]})),
        _contract(
            ColumnContract(
                name="status",
                allowed_values=("active", "inactive"),
            )
        ),
    )

    issue = _issue(result, "allowed_values_violation")
    assert issue.affected_rows == 1
    assert issue.sample_values == ("other",)


def test_numeric_range_violation_produces_samples() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"amount": [-1, 50, 101]})),
        _contract(
            ColumnContract(
                name="amount",
                min_value=0,
                max_value=100,
            )
        ),
    )

    issue = _issue(result, "range_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == (-1, 101)


def test_range_rule_on_non_numeric_column_fails_cleanly() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"amount": ["1", "2"]})),
        _contract(ColumnContract(name="amount", min_value=0)),
    )

    issue = _issue(result, "range_violation")
    assert issue.actual == "string"
    assert issue.affected_rows is None


def test_regex_violation_produces_samples() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"code": ["AB-12", "bad", 10]})),
        _contract(
            ColumnContract(
                name="code",
                regex=r"^[A-Z]{2}-\d{2}$",
            )
        ),
    )

    issue = _issue(result, "regex_violation")
    assert issue.affected_rows == 2
    assert issue.sample_values == ("bad", 10)


def test_result_serializes_cleanly_to_json() -> None:
    result = validate_contract(
        Dataset(pd.DataFrame({"id": [1, 1]})),
        SchemaContract(
            contract_version=1,
            name="Identifiers",
            dataset=DatasetContract(),
            columns=(ColumnContract(name="id", unique=True),),
        ),
    )

    serialized = result.to_dict()
    encoded = json.dumps(serialized, allow_nan=False)

    assert serialized["contract_name"] == "Identifiers"
    assert serialized["valid"] is False
    assert serialized["summary"]["errors"] == 1
    assert '"uniqueness_violation"' in encoded


def test_validation_does_not_modify_dataset() -> None:
    dataset = _dataset()
    dataframe_before = dataset.dataframe.copy(deep=True)
    metadata_before = copy.deepcopy(dataset.normalized_metadata)
    column_metadata_before = copy.deepcopy(dataset.column_metadata)

    validate_contract(
        dataset,
        _contract(
            ColumnContract(name="id", unique=True),
            ColumnContract(name="status", regex="^[a-z]+$"),
        ),
    )

    pd.testing.assert_frame_equal(dataset.dataframe, dataframe_before)
    assert dataset.normalized_metadata == metadata_before
    assert dataset.column_metadata == column_metadata_before


def test_resolved_metadata_participates_in_type_checks() -> None:
    metadata = DatasetMetadata()
    metadata.add_variable(
        VariableMetadata(
            name="id",
            storage_type="int32",
        )
    )
    dataset = Dataset(
        dataframe=pd.DataFrame({"id": [1, 2]}),
        normalized_metadata=metadata,
        column_metadata={
            "id": ColumnMetadata(
                name="id",
                physical_type="int32",
                logical_type="identifier",
            )
        },
        metadata_provenance={
            "dataset": "automatic_sidecar",
            "columns": {"id": "automatic_sidecar"},
        },
    )

    result = validate_contract(
        dataset,
        _contract(
            ColumnContract(
                name="id",
                storage_type="int32",
                logical_type="identifier",
            )
        ),
    )

    assert result.valid is True
    assert dataset.metadata_provenance["columns"]["id"] == "automatic_sidecar"


def _dataset() -> Dataset:
    return Dataset(
        pd.DataFrame(
            {
                "id": [1, 2],
                "status": ["active", "inactive"],
            }
        )
    )


def _contract(*columns: ColumnContract) -> SchemaContract:
    return SchemaContract(
        contract_version=1,
        dataset=DatasetContract(),
        columns=tuple(columns),
    )


def _has_issue(result, code: str) -> bool:
    return any(issue.code == code for issue in result.issues)


def _issue(result, code: str):
    return next(issue for issue in result.issues if issue.code == code)
