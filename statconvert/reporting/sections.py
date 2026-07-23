from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from itertools import islice

from statconvert.dataset import Dataset
from statconvert.inspection import (
    frequency_tables,
    missing_profile,
    profile_columns,
    summarize_dataset,
    validate_dataset,
)
from statconvert.reporting.models import (
    DatasetReport,
    ReportIssue,
    ReportMetric,
    ReportSection,
    ReportTable,
)
from statconvert.reporting.exceptions import ReportError


def build_summary_section(dataset: Dataset) -> ReportSection:
    summary = summarize_dataset(dataset)
    values = asdict(summary)
    metrics = [
        ReportMetric("rows", summary.row_count, label="Rows"),
        ReportMetric("columns", summary.column_count, label="Columns"),
        ReportMetric("source_format", dataset.source_format, label="Source format"),
        ReportMetric("source_file", dataset.source_file, label="Source file"),
        ReportMetric("memory_usage", summary.memory_usage_bytes, label="Memory usage (bytes)"),
        ReportMetric("duplicate_rows", summary.duplicate_rows, label="Duplicate rows"),
        ReportMetric("total_missing_cells", summary.total_missing_cells, label="Missing cells"),
    ]
    for name in (
        "numeric_columns",
        "text_columns",
        "boolean_columns",
        "datetime_columns",
        "categorical_columns",
        "other_columns",
    ):
        metrics.append(ReportMetric(name, values[name], label=name.replace("_", " ").title()))
    return ReportSection(key="summary", title="Dataset Summary", metrics=metrics)


def build_schema_section(dataset: Dataset) -> ReportSection:
    labels = dataset.variable_labels()
    storage_types = dataset.storage_types()
    display_formats = dataset.display_formats()
    measurement_levels = dataset.measurement_levels()
    rows = []
    for index, column in enumerate(dataset.dataframe.columns):
        name = str(column)
        rows.append(
            {
                "column": name,
                "dtype": str(dataset.dataframe.iloc[:, index].dtype),
                "storage_type": storage_types.get(name),
                "display_format": display_formats.get(name),
                "measurement_level": measurement_levels.get(name),
                "variable_label": labels.get(name),
            }
        )
    columns = [
        "column", "dtype", "storage_type", "display_format",
        "measurement_level", "variable_label",
    ]
    return ReportSection(
        key="schema",
        title="Schema",
        tables=[ReportTable("schema", columns, rows)],
    )


def build_metadata_section(dataset: Dataset) -> ReportSection:
    try:
        summary = dict(dataset.metadata_summary() or {})
    except (AttributeError, TypeError, ValueError):
        summary = {}

    counts = {
        "variable_labels": int(summary["variable_labels"])
        if "variable_labels" in summary
        else len(dataset.variable_labels() or {}),
        "value_label_variables": int(summary["value_label_sets"])
        if "value_label_sets" in summary
        else len(dataset.value_labels() or {}),
        "missing_value_variables": int(summary["missing_value_sets"])
        if "missing_value_sets" in summary
        else len(dataset.missing_values() or {}),
        "storage_type_variables": len(dataset.storage_types() or {}),
        "display_format_variables": int(summary["display_formats"])
        if "display_formats" in summary
        else len(dataset.display_formats() or {}),
        "measurement_level_variables": int(
            summary["measurement_levels"]
        )
        if "measurement_levels" in summary
        else len(dataset.measurement_levels() or {}),
    }
    summary.update(counts)
    metadata = dataset.get_normalized_metadata()
    provenance = dataset.metadata_provenance or {}
    context_metrics = [
        ReportMetric(
            name="dataset_label",
            value=metadata.dataset_label,
            label="Dataset Label",
        ),
        ReportMetric(
            name="dataset_notes",
            value=list(metadata.notes),
            label="Dataset Notes",
        ),
        ReportMetric(
            name="metadata_source",
            value=provenance.get("dataset"),
            label="Metadata Source",
        ),
        ReportMetric(
            name="column_metadata_sources",
            value=dict(provenance.get("columns", {}))
            if isinstance(provenance.get("columns", {}), dict)
            else {},
            label="Column Metadata Sources",
        ),
    ]
    metrics = [
        ReportMetric(name=name, value=value, label=name.replace("_", " ").title())
        for name, value in summary.items()
    ]
    return ReportSection(
        key="metadata",
        title="Metadata",
        metrics=[*context_metrics, *metrics],
    )


def build_labels_section(
    dataset: Dataset,
    preview_values: int = 5,
) -> ReportSection:
    if preview_values < 1:
        raise ReportError("Label preview values must be at least 1.")
    variable_rows = [
        {"column": column, "label": label}
        for column, label in dataset.variable_labels().items()
    ]
    value_rows = []
    for column, mappings in dataset.value_labels().items():
        preview = "; ".join(
            f"{value}={label}"
            for value, label in islice(mappings.items(), preview_values)
        )
        value_rows.append(
            {"column": column, "value_count": len(mappings), "values_preview": preview}
        )
    return ReportSection(
        key="labels",
        title="Labels",
        tables=[
            ReportTable("variable_labels", ["column", "label"], variable_rows),
            ReportTable(
                "value_labels",
                ["column", "value_count", "values_preview"],
                value_rows,
            ),
        ],
    )


def build_missing_section(dataset: Dataset) -> ReportSection:
    rows = [
        {
            "column": profile.column,
            "missing_count": profile.missing_count,
            "missing_percent": profile.missing_percent,
            "metadata_missing_values": profile.metadata_missing_values,
        }
        for profile in missing_profile(dataset)
    ]
    return ReportSection(
        key="missing",
        title="Missing Values",
        tables=[ReportTable(
            "missing_values",
            ["column", "missing_count", "missing_percent", "metadata_missing_values"],
            rows,
        )],
    )


def build_describe_section(
    dataset: Dataset,
    columns: list[str] | None = None,
) -> ReportSection:
    rows = []
    for profile in profile_columns(dataset, columns=columns):
        numeric = profile.numeric
        categorical = profile.categorical
        rows.append(
            {
                "column": profile.name,
                "dtype": profile.storage_type,
                "non_missing": profile.non_missing_count,
                "missing": profile.missing_count,
                "missing_percent": profile.missing_percent,
                "unique": profile.unique_count,
                "min": numeric.min if numeric else None,
                "max": numeric.max if numeric else None,
                "mean": numeric.mean if numeric else None,
                "median": numeric.median if numeric else None,
                "std": numeric.std if numeric else None,
                "top": categorical.top_value if categorical else None,
                "top_count": categorical.top_count if categorical else None,
            }
        )
    table_columns = [
        "column", "dtype", "non_missing", "missing", "missing_percent", "unique",
        "min", "max", "mean", "median", "std", "top", "top_count",
    ]
    return ReportSection(
        key="describe",
        title="Descriptive Profiles",
        tables=[ReportTable("column_profiles", table_columns, rows)],
    )


def build_frequencies_section(
    dataset: Dataset,
    columns: list[str] | None = None,
    top: int = 20,
    include_missing: bool = False,
    max_unique: int | None = None,
) -> ReportSection:
    rows = []
    for table in frequency_tables(
        dataset,
        columns=columns,
        top=top,
        include_missing=include_missing,
        max_unique=max_unique,
    ):
        rows.extend(
            {
                "column": table.column,
                "value": item.value,
                "count": item.count,
                "percent": item.percent,
            }
            for item in table.items
        )
    return ReportSection(
        key="frequencies",
        title="Frequencies",
        tables=[ReportTable("frequencies", ["column", "value", "count", "percent"], rows)],
    )


def build_validation_section(
    dataset: Dataset,
    target_format: str | None = None,
    strict: bool = False,
) -> ReportSection:
    issues = [
        ReportIssue(issue.severity, issue.code, issue.message, issue.column)
        for issue in validate_dataset(dataset, target_format=target_format, strict=strict)
    ]
    counts = {
        "errors": sum(issue.severity == "error" for issue in issues),
        "warnings": sum(issue.severity == "warning" for issue in issues),
        "info": sum(issue.severity == "info" for issue in issues),
    }
    rows = [
        {"severity": issue.severity, "code": issue.code, "column": issue.column, "message": issue.message}
        for issue in issues
    ]
    return ReportSection(
        key="validation",
        title="Validation",
        metrics=[ReportMetric(name, count, label=name.title()) for name, count in counts.items()],
        tables=[ReportTable("validation_issues", ["severity", "code", "column", "message"], rows)],
        issues=issues,
    )


def build_dataset_report(
    dataset: Dataset,
    title: str | None = None,
    include_summary: bool = True,
    include_schema: bool = True,
    include_metadata: bool = True,
    include_labels: bool = True,
    include_missing: bool = True,
    include_describe: bool = True,
    include_frequencies: bool = False,
    include_validation: bool = True,
    columns: list[str] | None = None,
    frequency_top: int = 20,
    frequency_include_missing: bool = False,
    frequency_max_unique: int | None = None,
    validation_target_format: str | None = None,
    strict_validation: bool = False,
    label_preview_values: int = 5,
) -> DatasetReport:
    sections: list[ReportSection] = []
    if include_summary:
        sections.append(build_summary_section(dataset))
    if include_schema:
        sections.append(build_schema_section(dataset))
    if include_metadata:
        sections.append(build_metadata_section(dataset))
    if include_labels:
        sections.append(
            build_labels_section(
                dataset,
                preview_values=label_preview_values,
            )
        )
    if include_missing:
        sections.append(build_missing_section(dataset))
    if include_describe:
        sections.append(build_describe_section(dataset, columns=columns))
    if include_frequencies:
        sections.append(build_frequencies_section(
            dataset,
            columns=columns,
            top=frequency_top,
            include_missing=frequency_include_missing,
            max_unique=frequency_max_unique,
        ))
    if include_validation:
        sections.append(build_validation_section(
            dataset,
            target_format=validation_target_format,
            strict=strict_validation,
        ))

    issues = [issue for section in sections for issue in section.issues]
    return DatasetReport(
        title=title or "Dataset Report",
        source_file=dataset.source_file,
        source_format=dataset.source_format,
        generated_at=datetime.now(timezone.utc),
        sections=sections,
        issues=issues,
    )
