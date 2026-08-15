from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import re
from pathlib import Path
from typing import Any

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.registry import get_backend_name, get_file_format

from .capabilities import METADATA_FIELDS, TargetTypeCapabilities, resolve_target_capabilities
from .models import (
    ColumnTypeDecision,
    MetadataDisposition,
    TransferIssue,
    TransferPlan,
)
from .policies import apply_policy_severity, resolve_policy
from .scanning import protected_relationships, scan_column


INTEGER_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)\Z", re.ASCII)
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
FLOAT_PATTERN = re.compile(
    r"-?(?:(?:0|[1-9][0-9]*)\.[0-9]+|(?:0|[1-9][0-9]*)(?:[eE]-?[0-9]+)|"
    r"(?:0|[1-9][0-9]*)\.[0-9]+(?:[eE]-?[0-9]+))\Z",
    re.ASCII,
)


def build_transfer_plan(
    dataset: Dataset,
    *,
    source_path: str | Path,
    target: str,
    policy: str | None = None,
    object_selector: str | None = None,
) -> TransferPlan:
    """Build one complete target-aware plan without mutating or writing anything."""

    resolved_policy = resolve_policy(policy)
    target_capability = resolve_target_capabilities(target)
    metadata, metadata_issues = _plan_metadata(
        dataset,
        target_capability,
        resolved_policy,
    )

    decisions: list[ColumnTypeDecision] = []
    issues: list[TransferIssue] = [
        *metadata_issues,
        *_dataset_target_issues(dataset, target_capability, resolved_policy),
    ]
    normalized = dataset.get_normalized_metadata()
    for ordinal, raw_column in enumerate(dataset.dataframe.columns):
        column = str(raw_column)
        series = dataset.dataframe.iloc[:, ordinal]
        variable = normalized.get_variable(column)
        scan = scan_column(series, variable)
        decision = _plan_column(
            column=column,
            ordinal=ordinal,
            series=series,
            dataset=dataset,
            target=target_capability,
            policy=resolved_policy,
            scan=scan,
            variable=variable,
        )
        decisions.append(decision)
        issues.extend(decision.issues)

    issues = _stable_unique_issues(issues)
    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    status = "blocked" if error_count else "warnings" if warning_count else "ready"
    disposition_counts = dict(sorted(Counter(item.disposition for item in metadata).items()))
    summary = {
        "unchanged_count": sum(item.action == "keep" for item in decisions),
        "changed_proposed_count": sum(
            item.action in {"widen", "narrow", "semantic_convert"} for item in decisions
        ),
        "manual_count": sum(item.action == "manual" for item in decisions),
        "warning_count": warning_count,
        "error_count": error_count,
        "info_count": sum(issue.severity == "info" for issue in issues),
        "metadata_disposition_counts": disposition_counts,
    }
    source_path = Path(source_path)
    return TransferPlan(
        schema_version=1,
        source={
            "path": str(source_path),
            "object": object_selector,
            "extension": source_path.suffix.lower(),
            "format": get_file_format(str(source_path)),
            "backend": get_backend_name(str(source_path)),
            "rows": dataset.rows,
            "columns": len(dataset.columns),
        },
        target={
            "extension": target_capability.extension,
            "format": target_capability.format_name,
            "backend": target_capability.backend,
            "metadata_mode": target_capability.metadata_mode,
            "caveat": target_capability.caveat,
        },
        policy=resolved_policy,
        status=status,
        scan={
            "mode": "full",
            "full_scan": True,
            "rows_scanned": dataset.rows,
            "columns_scanned": len(dataset.columns),
        },
        summary=summary,
        decisions=tuple(decisions),
        metadata=tuple(metadata),
        issues=tuple(issues),
    )


def _plan_column(
    *,
    column: str,
    ordinal: int,
    series: pd.Series,
    dataset: Dataset,
    target: TargetTypeCapabilities,
    policy: str,
    scan,
    variable,
) -> ColumnTypeDecision:
    current_storage = str(series.dtype)
    column_metadata = dataset.column_metadata.get(column)
    declared_logical = (
        column_metadata.logical_type
        if column_metadata is not None and column_metadata.logical_type
        else _type_family(series, scan)
    )
    family = _type_family(series, scan)
    proposed_storage = current_storage
    proposed_logical = declared_logical
    action = "keep"
    reason_code = "TYPE_KEEP_CURRENT"
    reason = "Current representation is retained by this planning policy."
    evidence = "exact_full_scan"
    column_issues: list[TransferIssue] = []
    compatibility = "verified"
    compatibility_reason = f"{target.extension} declares support for {family}."
    protected = protected_relationships(variable)

    if scan.non_missing_count == 0:
        declared_names = getattr(dataset, "_provided_column_metadata_names", set())
        logical_known = (
            column in declared_names
            and declared_logical not in {"unknown", "object", ""}
        ) or not pd.api.types.is_object_dtype(series.dtype)
        if dataset.rows == 0:
            issue = _issue(
                "TYPE_EMPTY_NO_EVIDENCE",
                "info",
                "An empty dataset provides no value evidence for an optional type change.",
                policy,
                target.extension,
                column=column,
                category="type",
            )
            column_issues.append(issue)
            evidence = "declared_only" if logical_known else "insufficient"
        elif not logical_known:
            issue = _issue(
                "TYPE_ALL_MISSING_AMBIGUOUS",
                "warning",
                "The all-missing column has no reliable declared logical type.",
                policy,
                target.extension,
                column=column,
                category="type",
            )
            column_issues.append(issue)
            action = "manual"
            reason_code = issue.code
            reason = "An explicit logical type is required before changing this column."
            evidence = "insufficient"
        else:
            evidence = "declared_only"
    elif family == "mixed":
        issue = _issue(
            "TYPE_MIXED_OBJECT_UNSAFE",
            "warning",
            "The column contains incompatible value families and cannot be optimized safely.",
            policy,
            target.extension,
            column=column,
            category="type",
        )
        column_issues.append(issue)
        action = "manual"
        reason_code = issue.code
        reason = "Mixed object values require an explicit transformation."
        evidence = "insufficient"
        compatibility = "unverified"
        compatibility_reason = "The target behavior for mixed object values is not verified."
    elif not target.supports_family(family):
        issue = _issue(
            "TYPE_TARGET_UNSUPPORTED",
            "warning",
            f"Target {target.extension} does not declare safe support for {family} values.",
            policy,
            target.extension,
            column=column,
            category="type",
        )
        column_issues.append(issue)
        action = "manual"
        reason_code = issue.code
        reason = "No safe target representation is declared."
        compatibility = "unsupported"
        compatibility_reason = issue.message
    elif (
        family == "datetime"
        and scan.timezone_summary not in {None, "naive"}
        and not target.verified_timezone
    ):
        issue = _issue(
            "TRANSFER_TARGET_UNVERIFIED",
            "warning",
            f"Timezone-aware datetime fidelity is not verified for {target.extension}.",
            policy,
            target.extension,
            column=column,
            category="type",
        )
        column_issues.append(issue)
        reason_code = issue.code
        reason = "The current datetime is retained, but target timezone fidelity is unverified."
        compatibility = "unverified"
        compatibility_reason = issue.message
    elif policy == "analysis-ready":
        proposal = _analysis_ready_proposal(series, scan, target, protected)
        if proposal is not None:
            proposed_storage, proposed_logical, action, reason_code, reason, issue_spec = proposal
            if issue_spec is not None:
                column_issues.append(
                    _issue(*issue_spec, policy, target.extension, column=column, category="type")
                )
    elif policy == "smallest-types":
        proposal = _smallest_type_proposal(series, scan, target, protected)
        if proposal is not None:
            proposed_storage, proposed_logical, action, reason_code, reason, issue_spec = proposal
            if issue_spec is not None:
                column_issues.append(
                    _issue(*issue_spec, policy, target.extension, column=column, category="type")
                )

    promoted = tuple(apply_policy_severity(issue, policy) for issue in column_issues)
    if any(issue.severity == "error" for issue in promoted) and action == "keep":
        action = "manual"
    return ColumnTypeDecision(
        column=column,
        ordinal=ordinal,
        current_storage_type=current_storage,
        declared_logical_type=declared_logical,
        proposed_storage_type=proposed_storage,
        proposed_logical_type=proposed_logical,
        action=action,
        reason_code=reason_code,
        reason=reason,
        policy=policy,
        evidence_level=evidence,
        lossy=False,
        issues=promoted,
        scan=scan,
        metadata_impact=protected,
        target_compatibility=compatibility,
        target_compatibility_reason=compatibility_reason,
    )


def _dataset_target_issues(dataset, target, policy):
    issues = []
    if target.max_rows is not None and dataset.rows > target.max_rows:
        issues.append(
            _issue(
                "TRANSFER_TARGET_LIMIT_EXCEEDED",
                "error",
                f"Target {target.extension} supports at most {target.max_rows:,} data rows.",
                policy,
                target.extension,
            )
        )
    if target.max_columns is not None and len(dataset.columns) > target.max_columns:
        issues.append(
            _issue(
                "TRANSFER_TARGET_LIMIT_EXCEEDED",
                "error",
                f"Target {target.extension} supports at most {target.max_columns:,} columns.",
                policy,
                target.extension,
            )
        )
    return issues


def _analysis_ready_proposal(series, scan, target, protected):
    values = series.loc[~series.isna()].tolist()
    family = _type_family(series, scan)
    if protected["protected"]:
        return None
    if family == "string" and values:
        if all(_ascii_boolean(value) for value in values) and target.supports_family("boolean"):
            nullable = scan.missing_count > 0
            return (
                "boolean" if nullable else "bool",
                "boolean",
                "semantic_convert",
                "TYPE_SEMANTIC_BOOLEAN_SAFE",
                "Every non-missing string is exactly true/false under ASCII case folding.",
                None,
            )
        if all(_exact_integer_string(value) for value in values) and target.supports_family("integer"):
            integers = [int(value) for value in values]
            dtype = _integer_target_dtype(
                min(integers),
                max(integers),
                scan.missing_count > 0,
                target,
            )
            if dtype is None:
                return (
                    str(series.dtype),
                    "string",
                    "manual",
                    "TYPE_TARGET_UNSUPPORTED",
                    "The exact integers exceed verified target integer representations.",
                    (
                        "TYPE_TARGET_UNSUPPORTED",
                        "warning",
                        "Integer-like strings exceed verified target integer representations.",
                    ),
                )
            return (
                dtype,
                "integer",
                "semantic_convert",
                "TYPE_SEMANTIC_INTEGER_SAFE",
                "Every non-missing string round-trips through the locale-neutral integer grammar.",
                None,
            )
        if all(_exact_date_string(value) for value in values) and target.supports_family("date"):
            return (
                "date",
                "date",
                "semantic_convert",
                "TYPE_SEMANTIC_DATE_SAFE",
                "Every non-missing string is a strict round-tripping YYYY-MM-DD date.",
                None,
            )
        if _uniform_iso_datetime_strings(values):
            return (
                str(series.dtype),
                "string",
                "manual",
                "TYPE_DATETIME_STRING_MANUAL",
                "Uniform ISO datetime strings remain a manual recommendation in 1.4.0b.",
                (
                    "TYPE_DATETIME_STRING_MANUAL",
                    "warning",
                    "ISO datetime inference is recognized but intentionally not automated yet.",
                ),
            )
        if all(isinstance(value, str) and FLOAT_PATTERN.fullmatch(value) for value in values):
            return (
                str(series.dtype),
                "string",
                "manual",
                "TYPE_FLOAT_STRING_MANUAL",
                "Locale-neutral float-like strings remain a manual recommendation.",
                (
                    "TYPE_FLOAT_STRING_MANUAL",
                    "warning",
                    "Float-like strings are not converted automatically because textual formatting may be meaningful.",
                ),
            )
    if family == "float" and scan.integer_exactness and target.supports_family("integer"):
        dtype = _integer_target_dtype(
            int(scan.minimum),
            int(scan.maximum),
            scan.missing_count > 0,
            target,
        )
        if dtype is None:
            return (
                str(series.dtype),
                "float",
                "manual",
                "TYPE_TARGET_UNSUPPORTED",
                "Integral floats exceed verified target integer representations.",
                (
                    "TYPE_TARGET_UNSUPPORTED",
                    "warning",
                    "Integral float values exceed verified target integer representations.",
                ),
            )
        return (
            dtype,
            "integer",
            "semantic_convert",
            "TYPE_FLOAT_INTEGER_SAFE",
            "Every finite non-missing float is exactly integral.",
            None,
        )
    if (
        family == "datetime"
        and scan.date_only_compatible
        and scan.timezone_summary in {None, "naive"}
        and target.supports_family("date")
    ):
        return (
            "date",
            "date",
            "semantic_convert",
            "TYPE_DATETIME_DATE_SAFE",
            "Every non-missing datetime is naive and exactly midnight.",
            None,
        )
    return None


def _smallest_type_proposal(series, scan, target, protected):
    family = _type_family(series, scan)
    if family == "integer" and scan.minimum is not None and scan.maximum is not None:
        lower, upper = _protected_numeric_bounds(scan.minimum, scan.maximum, series, protected)
        if not target.verified_integer_widths:
            return (
                str(series.dtype),
                "integer",
                "keep",
                "TYPE_NO_UNIQUE_SMALLEST",
                "The target has no verified stable integer-width ordering.",
                (
                    "TYPE_NO_UNIQUE_SMALLEST",
                    "info",
                    "No unique smallest integer storage type is verified for this target.",
                ),
            )
        proposed = _smallest_signed_dtype(int(lower), int(upper), scan.missing_count > 0)
        if _dtype_width(proposed) < _dtype_width(str(series.dtype)):
            return (
                proposed,
                "integer",
                "narrow",
                "TYPE_NARROW_SAFE",
                "Full-scan bounds and protected metadata fit the proposed signed integer type.",
                None,
            )
    if family == "float" and str(series.dtype).lower() in {"float64", "float64[pyarrow]"}:
        if target.verified_float32 and scan.float32_exactness:
            return (
                "float32",
                "float",
                "narrow",
                "TYPE_NARROW_SAFE",
                "Every non-missing float round-trips exactly through float32, including signed zero.",
                None,
            )
        if target.verified_float32 and scan.float32_exactness is False:
            return (
                str(series.dtype),
                "float",
                "keep",
                "TYPE_FLOAT32_INEXACT",
                "float32 would change at least one value or signed zero.",
                (
                    "TYPE_FLOAT32_INEXACT",
                    "warning",
                    "float32 narrowing is not exact; the current float type is retained.",
                ),
            )
    if (
        family == "datetime"
        and scan.date_only_compatible
        and scan.timezone_summary in {None, "naive"}
        and target.supports_family("date")
    ):
        return (
            "date",
            "date",
            "narrow",
            "TYPE_NARROW_SAFE",
            "Every non-missing datetime is naive and exactly midnight.",
            None,
        )
    return None


def _plan_metadata(dataset, target, policy):
    dispositions: list[MetadataDisposition] = []
    issues: list[TransferIssue] = []
    metadata = dataset.get_normalized_metadata()
    dataset_values = {
        "dataset_label": metadata.dataset_label,
        "notes": metadata.notes,
        "raw_metadata": metadata.raw_metadata,
    }
    for field in ("dataset_label", "notes", "raw_metadata"):
        meaningful = bool(dataset_values[field])
        if field == "raw_metadata" and not (
            target.embedded_metadata_fields or target.sidecar_metadata_fields
        ):
            meaningful = False
        item, issue = _metadata_disposition(
            scope="dataset",
            field=field,
            meaningful=meaningful,
            target=target,
            policy=policy,
        )
        dispositions.append(item)
        if issue is not None:
            issues.append(issue)

    for raw_column in dataset.dataframe.columns:
        column = str(raw_column)
        variable = metadata.get_variable(column)
        compatibility = dataset.column_metadata.get(column)
        values = {
            "variable_label": variable.label if variable else None,
            "value_labels": variable.value_labels if variable else None,
            "missing_values": variable.missing_values if variable else None,
            "missing_ranges": variable.missing_ranges if variable else None,
            "storage_type": variable.storage_type if variable else None,
            "logical_type": compatibility.logical_type if compatibility else None,
            "display_format": variable.display_format if variable else None,
            "display_width": variable.display_width if variable else None,
            "measurement_level": variable.measure if variable else None,
            "role": variable.role if variable else None,
            "width": variable.width if variable else None,
            "decimals": variable.decimals if variable else None,
        }
        for field in METADATA_FIELDS:
            if field in {"dataset_label", "notes", "raw_metadata"}:
                continue
            meaningful = values.get(field) not in (None, "", [], {})
            item, issue = _metadata_disposition(
                scope="column",
                field=field,
                meaningful=meaningful,
                target=target,
                policy=policy,
                column=column,
            )
            dispositions.append(item)
            if issue is not None:
                issues.append(issue)
    return dispositions, [apply_policy_severity(issue, policy) for issue in issues]


def _metadata_disposition(*, scope, field, meaningful, target, policy, column=None):
    if not meaningful:
        return (
            MetadataDisposition(
                scope=scope,
                field=field,
                disposition="not_applicable",
                severity="info",
                message="No meaningful resolved value is present.",
                column=column,
            ),
            None,
        )
    if field in target.native_metadata_fields:
        return (
            MetadataDisposition(
                scope=scope,
                field=field,
                disposition="native",
                severity="info",
                message="The target declares limited native support for this field.",
                column=column,
            ),
            None,
        )
    if field in target.embedded_metadata_fields:
        return (
            MetadataDisposition(
                scope=scope,
                field=field,
                disposition="embedded",
                severity="info",
                message="The field is embedded and also carried by the canonical sibling sidecar.",
                column=column,
            ),
            None,
        )
    if field in target.sidecar_metadata_fields:
        severity = "info" if policy == "preserve-metadata" else "warning"
        issue = _issue(
            "METADATA_SIDECAR_REQUIRED",
            severity,
            "Meaningful metadata requires the standardized sibling sidecar for this target.",
            policy,
            target.extension,
            column=column,
            field=field,
            category="metadata",
        )
        return (
            MetadataDisposition(
                scope=scope,
                field=field,
                disposition="sidecar",
                severity=severity,
                issue_code=issue.code,
                message="Preserved through a StatConvert sidecar, not native target fidelity.",
                column=column,
            ),
            issue,
        )
    if field in {"storage_type", "logical_type"}:
        return (
            MetadataDisposition(
                scope=scope,
                field=field,
                disposition="derived",
                severity="info",
                message="The target representation derives this field from written values and formats.",
                column=column,
            ),
            None,
        )
    issue = _issue(
        "METADATA_TARGET_UNSUPPORTED",
        "warning",
        "Meaningful metadata has no declared native, embedded, or sidecar preservation channel.",
        policy,
        target.extension,
        column=column,
        field=field,
        category="metadata",
    )
    issue = apply_policy_severity(issue, policy)
    return (
        MetadataDisposition(
            scope=scope,
            field=field,
            disposition="unsupported",
            severity=issue.severity,
            issue_code=issue.code,
            message=issue.message,
            column=column,
        ),
        issue,
    )


def _type_family(series, scan) -> str:
    dtype = series.dtype
    if isinstance(dtype, pd.CategoricalDtype):
        return "category"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    families = set(scan.value_family_counts)
    if not families:
        return "unknown"
    if len(families) == 1:
        return next(iter(families))
    return "mixed"


def _smallest_signed_dtype(minimum: int, maximum: int, nullable: bool) -> str:
    for bits, lower, upper in (
        (8, -(2**7), 2**7 - 1),
        (16, -(2**15), 2**15 - 1),
        (32, -(2**31), 2**31 - 1),
        (64, -(2**63), 2**63 - 1),
    ):
        if lower <= minimum and maximum <= upper:
            return f"Int{bits}" if nullable else f"int{bits}"
    return "Int64" if nullable else "int64"


def _integer_target_dtype(
    minimum: int,
    maximum: int,
    nullable: bool,
    target: TargetTypeCapabilities,
) -> str | None:
    if -(2**63) <= minimum and maximum <= 2**63 - 1:
        return _smallest_signed_dtype(minimum, maximum, nullable)
    if target.verified_unsigned and 0 <= minimum and maximum <= 2**64 - 1:
        return "UInt64" if nullable else "uint64"
    return None


def _dtype_width(dtype: str) -> int:
    match = re.search(r"(8|16|32|64)", dtype)
    return int(match.group(1)) if match else 10_000


def _protected_numeric_bounds(minimum, maximum, series, protected):
    if not protected["protected"]:
        return minimum, maximum
    # Exact metadata values are intentionally not exposed, but Dataset metadata has already
    # been considered when deciding that the relationship is protected. Keep the current
    # width until a later applier can validate target-native sentinel/key representation.
    width = _dtype_width(str(series.dtype))
    lower = -(2 ** (width - 1)) if width in {8, 16, 32, 64} else minimum
    upper = 2 ** (width - 1) - 1 if width in {8, 16, 32, 64} else maximum
    return min(minimum, lower), max(maximum, upper)


def _ascii_boolean(value: Any) -> bool:
    return isinstance(value, str) and value.isascii() and value.lower() in {"true", "false"}


def _exact_integer_string(value: Any) -> bool:
    if not isinstance(value, str) or INTEGER_PATTERN.fullmatch(value) is None or value == "-0":
        return False
    return str(int(value)) == value


def _exact_date_string(value: Any) -> bool:
    if not isinstance(value, str) or DATE_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value


def _uniform_iso_datetime_strings(values: list[Any]) -> bool:
    parsed: list[datetime] = []
    for value in values:
        if not isinstance(value, str) or "T" not in value or value != value.strip():
            return False
        try:
            item = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        parsed.append(item)
    if not parsed:
        return False
    awareness = {
        item.tzinfo is not None and item.utcoffset() is not None for item in parsed
    }
    if len(awareness) != 1:
        return False
    if awareness == {True}:
        return len({item.utcoffset() for item in parsed}) == 1
    return True


def _issue(code, severity, message, policy, target, *, column=None, field=None, category="transfer"):
    issue = TransferIssue(
        code=code,
        severity=severity,
        message=message,
        column=column,
        field=field,
        policy=policy,
        target=target,
        category=category,
    )
    return apply_policy_severity(issue, policy)


def _stable_unique_issues(issues):
    result = []
    seen = set()
    for issue in issues:
        key = (issue.code, issue.severity, issue.column, issue.field, issue.message)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result
