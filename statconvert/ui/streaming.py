"""Human output for opt-in streaming workflows."""

from statconvert.streaming.chunks import StreamingExecutionResult
from statconvert.streaming.validation import StreamingValidationResult
from statconvert.ui.console import console
from statconvert.ui.errors import show_success


def show_streaming_conversion_result(result: StreamingExecutionResult) -> None:
    """Display a compact deterministic streaming conversion summary."""

    show_success("Streaming conversion completed.")
    console.print(f"Input: {result.source_path}")
    console.print(f"Output: {result.output_path}")
    console.print(f"Chunk size: {result.chunk_size:,}")
    console.print(f"Chunks processed: {result.chunks_processed:,}")
    console.print(f"Rows processed: {result.rows_processed:,}")
    console.print(
        f"Sidecar: {result.sidecar_path if result.sidecar_path is not None else '-'}"
    )


def show_streaming_validation_summary(
    result: StreamingValidationResult,
    *,
    strict: bool = False,
) -> None:
    """Display compact streaming totals and validation status."""

    validation = result.contract_validation
    status = validation.status(strict=strict).replace("_", " ")
    console.print("[bold]Streaming validation[/bold]")
    console.print("Streaming enabled: yes")
    console.print(f"Chunk size: {result.chunk_size:,}")
    console.print(f"Chunks processed: {result.chunks_processed:,}")
    console.print(f"Rows processed: {result.rows_processed:,}")
    console.print(f"Rules checked: {result.rules_checked:,}")
    console.print(f"Columns checked: {result.columns_checked:,}")
    console.print(f"Validation status: {status}")
    console.print(
        f"Issues: {validation.error_count} error(s), "
        f"{validation.warning_count} warning(s), "
        f"{validation.info_count} info"
    )
