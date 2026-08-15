from __future__ import annotations

from collections import Counter

from rich.panel import Panel
from rich.table import Table

from statconvert.transfer import TransferApplicationResult, TransferPlan

from .console import console


MAX_HUMAN_DECISIONS = 50
MAX_HUMAN_ISSUES = 50


def show_transfer_plan_summary(
    plan: TransferPlan,
    application: TransferApplicationResult | None = None,
) -> None:
    """Render the compact policy preflight used by writing conversions."""

    summary = plan.summary
    dispositions = Counter(item.disposition for item in plan.metadata)
    sidecar_count = dispositions.get("sidecar", 0)
    lines = [
        f"Policy: {plan.policy}",
        f"Target: {plan.target['format']} ({plan.target['extension']})",
        f"Status: {plan.status}",
        (
            "Columns: "
            f"{summary['changed_proposed_count']} proposed, "
            f"{summary['manual_count']} manual, "
            f"{summary['unchanged_count']} unchanged"
        ),
        f"Findings: {summary['error_count']} errors, {summary['warning_count']} warnings",
        f"Metadata fields requiring sidecar preservation: {sidecar_count}",
    ]
    if application is not None:
        lines.append(f"Exact type decisions applied: {application.applied_count}")
    border_style = {"ready": "green", "warnings": "yellow", "blocked": "red"}[
        plan.status
    ]
    console.print(
        Panel(
            "\n".join(lines),
            title="Transfer Policy Preflight",
            border_style=border_style,
        )
    )


def show_transfer_plan(plan: TransferPlan) -> None:
    """Render one concise bounded transfer plan through the Rich UI layer."""

    status_style = {"ready": "green", "warnings": "yellow", "blocked": "red"}[plan.status]
    summary = plan.summary
    console.print(
        Panel(
            "\n".join(
                (
                    f"Status: [{status_style}]{plan.status}[/{status_style}]",
                    f"Policy: {plan.policy}",
                    f"Target: {plan.target['format']} ({plan.target['extension']})",
                    f"Scan: full, {plan.scan['rows_scanned']:,} rows, "
                    f"{plan.scan['columns_scanned']:,} columns",
                    f"Decisions: {summary['changed_proposed_count']} proposed, "
                    f"{summary['manual_count']} manual, {summary['unchanged_count']} unchanged",
                    f"Issues: {summary['error_count']} errors, "
                    f"{summary['warning_count']} warnings",
                    "Writes: none",
                )
            ),
            title="Transfer Type Plan",
            border_style=status_style,
        )
    )

    visible_decisions = [item for item in plan.decisions if item.action != "keep"]
    if visible_decisions:
        table = Table(title="Proposed and manual decisions", expand=True)
        table.add_column("Column")
        table.add_column("Current")
        table.add_column("Proposed")
        table.add_column("Action")
        table.add_column("Reason")
        for item in visible_decisions[:MAX_HUMAN_DECISIONS]:
            table.add_row(
                item.column,
                item.current_storage_type,
                item.proposed_storage_type,
                item.action,
                item.reason_code,
            )
        console.print(table)
        omitted = len(visible_decisions) - min(len(visible_decisions), MAX_HUMAN_DECISIONS)
        if omitted:
            console.print(f"[dim]{omitted} additional decisions omitted.[/dim]")

    if plan.issues:
        table = Table(title="Transfer findings", expand=True)
        table.add_column("Severity")
        table.add_column("Code")
        table.add_column("Column/field")
        table.add_column("Message")
        for issue in plan.issues[:MAX_HUMAN_ISSUES]:
            location = issue.column or "dataset"
            if issue.field:
                location = f"{location}/{issue.field}"
            table.add_row(issue.severity, issue.code, location, issue.message)
        console.print(table)
        omitted = len(plan.issues) - min(len(plan.issues), MAX_HUMAN_ISSUES)
        if omitted:
            console.print(f"[dim]{omitted} additional findings omitted.[/dim]")

    dispositions = Counter(item.disposition for item in plan.metadata)
    console.print(
        "Metadata: "
        + ", ".join(f"{name}={count}" for name, count in sorted(dispositions.items()))
    )
