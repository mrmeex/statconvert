from rich.table import Table

from statconvert.collection import CollectionPlan, CollectionResult

from .console import console


def show_collection_plan(plan: CollectionPlan) -> None:
    """Display a manifest collection plan."""

    summary = Table(title="Planned Object Collection")
    summary.add_column("Input file", style="cyan")
    summary.add_column("Input object")
    summary.add_column("Output object", style="green")
    for item in plan.items:
        summary.add_row(
            str(item.input_file),
            item.input_object or "",
            item.output_object,
        )
    console.print(summary)

    console.print("[bold]Collection Output[/bold]")
    console.print(
        f"[cyan]Output file:[/cyan] {plan.output_file}",
        overflow="fold",
    )
    console.print(f"[cyan]Objects:[/cyan] {len(plan.items):,}")


def show_collection_result(result: CollectionResult) -> None:
    """Display a completed collection summary."""

    table = Table(title="Object Collection Result")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Output file", str(result.plan.output_file))
    table.add_row("Objects written", f"{len(result.objects):,}")
    table.add_row("Rows written", f"{result.rows:,}")
    console.print(table)
