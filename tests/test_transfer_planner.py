from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.serialization import to_json_text
from statconvert.transfer import (
    SUPPORTED_POLICIES,
    TARGET_CAPABILITIES,
    TransferPlanningError,
    build_transfer_plan,
    resolve_policy,
    resolve_target_capabilities,
)


@pytest.mark.parametrize("policy", SUPPORTED_POLICIES)
def test_all_selected_policies_build_plans(policy: str) -> None:
    plan = _plan(pd.DataFrame({"value": [1, 2]}), policy=policy)

    assert plan.policy == policy
    assert plan.scan == {
        "mode": "full",
        "full_scan": True,
        "rows_scanned": 2,
        "columns_scanned": 1,
    }


def test_type_plan_policy_resolution_defaults_only_when_called() -> None:
    assert resolve_policy(None) == "safe"
    assert resolve_policy("safe") == "safe"


@pytest.mark.parametrize("policy", ["legacy-compatible", "unknown"])
def test_deferred_and_unknown_policies_are_rejected(policy: str) -> None:
    with pytest.raises(TransferPlanningError):
        resolve_policy(policy)


def test_strict_promotes_mixed_object_target_uncertainty() -> None:
    dataframe = pd.DataFrame({"mixed": pd.Series([1, "a"], dtype="object")})

    safe = _plan(dataframe, policy="safe")
    strict = _plan(dataframe, policy="strict")

    assert safe.status == "warnings"
    assert _issue(safe, "TYPE_MIXED_OBJECT_UNSAFE").severity == "warning"
    assert strict.status == "blocked"
    assert _issue(strict, "TYPE_MIXED_OBJECT_UNSAFE").severity == "error"


def test_smallest_types_selects_smallest_signed_integer() -> None:
    plan = _plan(pd.DataFrame({"value": [-5, 12]}), policy="smallest-types")
    decision = plan.decisions[0]

    assert decision.action == "narrow"
    assert decision.proposed_storage_type == "int8"
    assert decision.reason_code == "TYPE_NARROW_SAFE"


def test_nullable_integer_scan_and_narrowing_preserve_nullable_type() -> None:
    series = pd.Series([1, None, 100], dtype="Int64")
    decision = _plan(
        pd.DataFrame({"value": series}), policy="smallest-types"
    ).decisions[0]

    assert decision.scan.minimum == 1
    assert decision.scan.maximum == 100
    assert decision.scan.missing_count == 1
    assert decision.proposed_storage_type == "Int8"


def test_unsigned_is_not_selected_even_when_arrow_supports_it() -> None:
    decision = _plan(
        pd.DataFrame({"value": [0, 200]}), policy="smallest-types"
    ).decisions[0]

    assert decision.proposed_storage_type == "int16"
    assert not decision.proposed_storage_type.lower().startswith("u")


def test_float32_is_proposed_only_for_exact_values() -> None:
    exact = _plan(
        pd.DataFrame({"value": [1.5, -0.0, 2.0]}), policy="smallest-types"
    ).decisions[0]
    inexact = _plan(
        pd.DataFrame({"value": [0.1, 2.0]}), policy="smallest-types"
    ).decisions[0]

    assert exact.scan.float32_exactness is True
    assert exact.proposed_storage_type == "float32"
    assert exact.action == "narrow"
    assert inexact.scan.float32_exactness is False
    assert inexact.action == "keep"
    assert inexact.reason_code == "TYPE_FLOAT32_INEXACT"


def test_non_finite_float_scan_preserves_missingness_and_avoids_json_non_finite_bounds() -> None:
    decision = _plan(
        pd.DataFrame({"value": [float("inf"), float("-inf"), float("nan")]}),
        policy="smallest-types",
    ).decisions[0]

    assert decision.scan.non_missing_count == 2
    assert decision.scan.missing_count == 1
    assert decision.scan.minimum is None
    assert decision.scan.maximum is None
    assert decision.scan.float32_exactness is True


def test_string_scan_counts_empty_string_as_non_missing() -> None:
    decision = _plan(
        pd.DataFrame({"text": pd.Series(["", "abcd", None], dtype="string")})
    ).decisions[0]

    assert decision.scan.non_missing_count == 2
    assert decision.scan.missing_count == 1
    assert decision.scan.max_string_length == 4
    assert decision.scan.string_length_unit == "unicode_code_points"


def test_analysis_ready_boolean_is_exact_and_plan_only() -> None:
    decision = _plan(
        pd.DataFrame({"flag": pd.Series(["TRUE", "false", None], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "semantic_convert"
    assert decision.proposed_storage_type == "boolean"
    assert decision.lossy is False


def test_analysis_ready_does_not_trim_boolean_strings() -> None:
    decision = _plan(
        pd.DataFrame({"flag": pd.Series(["true", " false"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "keep"


def test_analysis_ready_exact_integer_strings_are_proposed() -> None:
    decision = _plan(
        pd.DataFrame({"count": pd.Series(["-2", "10"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "semantic_convert"
    assert decision.proposed_storage_type == "int8"
    assert decision.proposed_logical_type == "integer"


def test_leading_zero_identifier_is_not_converted() -> None:
    decision = _plan(
        pd.DataFrame({"id": pd.Series(["001", "002"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "keep"
    assert decision.proposed_logical_type == "string"


def test_analysis_ready_unsigned_requires_verified_target_support() -> None:
    dataframe = pd.DataFrame(
        {"value": pd.Series(["18446744073709551615"], dtype="string")}
    )
    arrow = _plan(dataframe, target="parquet", policy="analysis-ready").decisions[0]
    csv = _plan(dataframe, target="csv", policy="analysis-ready").decisions[0]

    assert arrow.proposed_storage_type == "uint64"
    assert arrow.action == "semantic_convert"
    assert csv.action == "manual"
    assert csv.reason_code == "TYPE_TARGET_UNSUPPORTED"


def test_strict_iso_date_is_recommended_without_locale_guessing() -> None:
    exact = _plan(
        pd.DataFrame({"date": pd.Series(["2026-01-02", "2026-12-31"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]
    locale = _plan(
        pd.DataFrame({"date": pd.Series(["02/01/2026", "31/12/2026"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert exact.action == "semantic_convert"
    assert exact.proposed_logical_type == "date"
    assert locale.action == "keep"


def test_float_like_strings_remain_manual() -> None:
    decision = _plan(
        pd.DataFrame({"number": pd.Series(["1.25", "2.5"], dtype="string")}),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "manual"
    assert decision.reason_code == "TYPE_FLOAT_STRING_MANUAL"


def test_uniform_iso_datetime_strings_are_recognized_but_manual() -> None:
    decision = _plan(
        pd.DataFrame(
            {
                "when": pd.Series(
                    ["2026-01-01T10:00:00+00:00", "2026-01-02T11:30:00+00:00"],
                    dtype="string",
                )
            }
        ),
        policy="analysis-ready",
    ).decisions[0]

    assert decision.action == "manual"
    assert decision.reason_code == "TYPE_DATETIME_STRING_MANUAL"


def test_numeric_zero_one_with_value_labels_is_not_boolean() -> None:
    dataset = _labelled_dataset()
    plan = build_transfer_plan(
        dataset,
        source_path="labelled.sav",
        target="parquet",
        policy="analysis-ready",
    )

    assert plan.decisions[0].action == "keep"
    assert plan.decisions[0].metadata_impact["value_labels"] == 2


def test_value_labels_and_user_missing_definitions_block_narrowing() -> None:
    dataset = _labelled_dataset()
    dataset.normalized_metadata.variables["code"].missing_values = [-99]
    dataset.normalized_metadata.variables["code"].missing_ranges = [
        {"lo": -999, "hi": -900}
    ]
    plan = build_transfer_plan(
        dataset,
        source_path="labelled.sav",
        target="parquet",
        policy="smallest-types",
    )
    decision = plan.decisions[0]

    assert decision.action == "keep"
    assert decision.metadata_impact == {
        "value_labels": 2,
        "missing_values": 1,
        "missing_ranges": 1,
        "protected": True,
    }


def test_all_missing_without_declared_type_is_manual() -> None:
    decision = _plan(
        pd.DataFrame({"unknown": pd.Series([None, None], dtype="object")})
    ).decisions[0]

    assert decision.action == "manual"
    assert decision.reason_code == "TYPE_ALL_MISSING_AMBIGUOUS"


def test_mixed_object_scan_reports_only_bounded_family_counts() -> None:
    decision = _plan(
        pd.DataFrame({"mixed": pd.Series([1, "a", b"b"], dtype="object")})
    ).decisions[0]

    assert decision.scan.value_family_counts == {"bytes": 1, "integer": 1, "string": 1}
    assert decision.scan.value_family_count_truncated == 0


def test_all_missing_with_declared_type_keeps_declaration() -> None:
    dataset = Dataset(
        pd.DataFrame({"known": pd.Series([None, None], dtype="object")}),
        column_metadata={
            "known": ColumnMetadata(
                name="known", physical_type="string", logical_type="string"
            )
        },
    )
    decision = build_transfer_plan(
        dataset, source_path="known.csv", target="parquet"
    ).decisions[0]

    assert decision.action == "keep"
    assert decision.evidence_level == "declared_only"


def test_empty_dataset_column_has_no_value_evidence() -> None:
    decision = _plan(pd.DataFrame({"value": pd.Series([], dtype="int64")})).decisions[0]

    assert decision.action == "keep"
    assert decision.scan.rows_scanned == 0
    assert any(issue.code == "TYPE_EMPTY_NO_EVIDENCE" for issue in decision.issues)


def test_timezone_aware_datetime_is_reported_and_not_narrowed() -> None:
    series = pd.Series(pd.date_range("2026-01-01", periods=2, tz="UTC"))
    decision = _plan(
        pd.DataFrame({"when": series}), policy="smallest-types"
    ).decisions[0]

    assert decision.scan.timezone_summary == "aware:UTC"
    assert decision.scan.date_only_compatible is True
    assert decision.action == "keep"


def test_timezone_fidelity_is_unverified_for_spreadsheet_and_strict_blocks() -> None:
    dataframe = pd.DataFrame(
        {"when": pd.Series(pd.date_range("2026-01-01", periods=2, tz="UTC"))}
    )
    safe = _plan(dataframe, target="xlsx", policy="safe")
    strict = _plan(dataframe, target="xlsx", policy="strict")

    assert _issue(safe, "TRANSFER_TARGET_UNVERIFIED").severity == "warning"
    assert strict.status == "blocked"
    assert _issue(strict, "TRANSFER_TARGET_UNVERIFIED").severity == "error"


def test_naive_midnight_datetime_can_be_planned_as_date() -> None:
    decision = _plan(
        pd.DataFrame({"when": pd.to_datetime(["2026-01-01", "2026-01-02"])}),
        policy="smallest-types",
    ).decisions[0]

    assert decision.action == "narrow"
    assert decision.proposed_logical_type == "date"


def test_categorical_evidence_preserves_order() -> None:
    series = pd.Series(pd.Categorical(["low", "high"], categories=["low", "high"], ordered=True))
    decision = _plan(pd.DataFrame({"level": series}), policy="smallest-types").decisions[0]

    assert decision.action == "keep"
    assert decision.scan.category_count == 2
    assert decision.scan.category_ordered is True


def test_planning_does_not_mutate_source_dataset() -> None:
    dataset = _labelled_dataset()
    dataframe_before = dataset.dataframe.copy(deep=True)
    metadata_before = copy.deepcopy(dataset.normalized_metadata)
    columns_before = copy.deepcopy(dataset.column_metadata)

    build_transfer_plan(
        dataset, source_path="source.sav", target="parquet", policy="smallest-types"
    )

    pd.testing.assert_frame_equal(dataset.dataframe, dataframe_before)
    assert dataset.normalized_metadata == metadata_before
    assert dataset.column_metadata == columns_before


def test_transfer_plan_is_deeply_immutable_and_json_copies_are_independent() -> None:
    plan = _plan(
        pd.DataFrame({"value": pd.Series([1, 2], dtype="int64")}),
        policy="smallest-types",
    )

    with pytest.raises(TypeError):
        plan.summary["error_count"] = 99
    with pytest.raises(TypeError):
        plan.summary["metadata_disposition_counts"]["embedded"] = 99
    with pytest.raises(TypeError):
        plan.decisions[0].metadata_impact["protected"] = True
    with pytest.raises(TypeError):
        plan.decisions[0].scan.value_family_counts["integer"] = 99

    payload = plan.to_dict()
    payload["summary"]["error_count"] = 99
    payload["decisions"][0]["metadata_impact"]["protected"] = True

    assert plan.summary["error_count"] == 0
    assert plan.decisions[0].metadata_impact["protected"] is False


def test_csv_metadata_is_explicitly_sidecar_only() -> None:
    plan = _plan(pd.DataFrame({"value": [1]}), target="csv")

    storage = next(item for item in plan.metadata if item.field == "storage_type")
    assert storage.disposition == "sidecar"
    assert any(issue.code == "METADATA_SIDECAR_REQUIRED" for issue in plan.issues)


def test_safe_normalized_raw_metadata_is_planned_without_exposing_values() -> None:
    dataset = Dataset(
        pd.DataFrame({"value": [1]}),
        metadata={"backend_option": "private-value"},
    )
    plan = build_transfer_plan(dataset, source_path="source.csv", target="parquet")
    item = next(item for item in plan.metadata if item.field == "raw_metadata")
    payload = to_json_text(plan.to_dict())

    assert item.disposition == "embedded"
    assert "private-value" not in payload


@pytest.mark.parametrize("target", ["parquet", "feather"])
def test_arrow_metadata_is_embedded_and_sidecar_mode(target: str) -> None:
    plan = _plan(pd.DataFrame({"value": [1]}), target=target)
    storage = next(item for item in plan.metadata if item.field == "storage_type")

    assert plan.target["metadata_mode"] == "embedded + sidecar"
    assert storage.disposition == "embedded"
    assert "sidecar" in storage.message


@pytest.mark.parametrize(
    ("target", "field", "expected"),
    [
        ("sav", "variable_label", "native"),
        ("dta", "variable_label", "native"),
        ("xpt", "value_labels", "unsupported"),
    ],
)
def test_statistical_metadata_declarations_are_conservative(
    target: str, field: str, expected: str
) -> None:
    dataset = _labelled_dataset()
    dataset.normalized_metadata.variables["code"].label = "Code"
    plan = build_transfer_plan(
        dataset, source_path="source.sav", target=target, policy="safe"
    )
    item = next(
        item for item in plan.metadata if item.column == "code" and item.field == field
    )

    assert item.disposition == expected


def test_preserve_metadata_blocks_meaningful_unsupported_field() -> None:
    dataset = _labelled_dataset()
    dataset.normalized_metadata.variables["code"].role = "input"
    plan = build_transfer_plan(
        dataset,
        source_path="source.sav",
        target="xpt",
        policy="preserve-metadata",
    )

    assert plan.status == "blocked"
    assert _issue(plan, "METADATA_TARGET_UNSUPPORTED").severity == "error"


@pytest.mark.parametrize("target", ["zsav", "por", "sas7bdat"])
def test_read_only_targets_are_rejected(target: str) -> None:
    with pytest.raises(TransferPlanningError, match="not writable"):
        resolve_target_capabilities(target)


def test_unknown_target_is_rejected_and_unknown_is_not_safe() -> None:
    with pytest.raises(TransferPlanningError, match="Unsupported target"):
        resolve_target_capabilities("madeup")


def test_every_registered_writable_target_has_a_conservative_declaration() -> None:
    assert set(TARGET_CAPABILITIES) == {
        ".csv", ".xlsx", ".xls", ".ods", ".json", ".jsonl", ".ndjson",
        ".parquet", ".feather", ".rds", ".rdata", ".rda", ".sav", ".dta", ".xpt",
    }
    assert ".orc" not in TARGET_CAPABILITIES
    assert ".db" not in TARGET_CAPABILITIES
    assert ".sqlite" not in TARGET_CAPABILITIES


def test_xls_hard_column_limit_blocks_plan_before_any_write() -> None:
    dataframe = pd.DataFrame({f"column_{index}": [index] for index in range(257)})
    plan = _plan(dataframe, target="xls")

    assert plan.status == "blocked"
    assert _issue(plan, "TRANSFER_TARGET_LIMIT_EXCEEDED").severity == "error"


def test_plan_json_is_deterministic_bounded_and_rich_free() -> None:
    dataframe = pd.DataFrame({f"column_{index}": [index] for index in range(205)})
    plan = _plan(dataframe)
    first = to_json_text(plan.to_dict())
    second = to_json_text(plan.to_dict())
    parsed = json.loads(first)

    assert first == second
    assert parsed["schema_version"] == 1
    assert parsed["truncated"]["decisions"] is True
    assert parsed["truncated"]["decisions_omitted"] == 5
    assert "\x1b[" not in first
    assert "[bold" not in first


def _plan(dataframe: pd.DataFrame, *, target: str = "parquet", policy: str = "safe"):
    return build_transfer_plan(
        Dataset(dataframe),
        source_path="source.csv",
        target=target,
        policy=policy,
    )


def _issue(plan, code: str):
    return next(issue for issue in plan.issues if issue.code == code)


def _labelled_dataset() -> Dataset:
    metadata = DatasetMetadata(source_format="sav", source_backend="pyreadstat")
    metadata.add_variable(
        VariableMetadata(
            name="code",
            value_labels={0: "No", 1: "Yes"},
            storage_type="int64",
        )
    )
    return Dataset(
        pd.DataFrame({"code": [0, 1]}),
        source_format="sav",
        normalized_metadata=metadata,
        column_metadata={
            "code": ColumnMetadata(
                name="code",
                physical_type="int64",
                logical_type="category",
                value_labels={0: "No", 1: "Yes"},
            )
        },
    )
