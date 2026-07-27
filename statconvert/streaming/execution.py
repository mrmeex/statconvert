"""Internal pairwise streaming conversion for the approved text formats."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from statconvert.dataset_options import DatasetReadOptions, DatasetWriteOptions
from statconvert.exceptions import ConversionError
from statconvert.registry import get_reader_for_file, get_writer_for_file
from statconvert.streaming.chunks import (
    StreamingExecutionResult,
    StreamingProgressEvent,
)
from statconvert.streaming.options import ChunkedReadOptions, ChunkedWriteOptions
from statconvert.streaming.plan import build_streaming_plan


ProgressCallback = Callable[[StreamingProgressEvent], None]


def execute_streaming_convert(
    source_path: str | Path,
    target_path: str | Path,
    *,
    chunk_size: int,
    overwrite: bool = False,
    create_dirs: bool = False,
    read_options: DatasetReadOptions | None = None,
    write_options: DatasetWriteOptions | None = None,
    on_progress: ProgressCallback | None = None,
) -> StreamingExecutionResult:
    """Run one internal CSV/JSONL/NDJSON streaming conversion."""

    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        raise ConversionError(f"Input file does not exist: {source}")

    plan = build_streaming_plan(str(source), str(target))
    plan.require_executable()

    reader = get_reader_for_file(str(source))
    writer_backend = get_writer_for_file(str(target))
    read_control = ChunkedReadOptions(chunk_size)
    write_control = ChunkedWriteOptions(chunk_size)
    read_kwargs = _read_kwargs(source.suffix.lower(), read_options)
    write_kwargs = _write_kwargs(target.suffix.lower(), write_options)

    chunks_processed = 0
    rows_processed = 0
    _emit(
        on_progress,
        StreamingProgressEvent(event_type="started"),
    )
    try:
        writer = writer_backend.open_chunk_writer(
            str(target),
            write_control,
            overwrite=overwrite,
            create_dirs=create_dirs,
            **write_kwargs,
        )
        with writer:
            for chunk in reader.iter_chunks(
                str(source),
                read_control,
                **read_kwargs,
            ):
                writer.write_chunk(chunk)
                chunks_processed += 1
                rows_processed += chunk.rows
                _emit(
                    on_progress,
                    StreamingProgressEvent(
                        event_type="chunk_completed",
                        chunk_index=chunk.index,
                        rows=chunk.rows,
                        cumulative_rows=rows_processed,
                        total_rows=chunk.total_rows,
                    ),
                )
            output_sidecar = writer.finalize()
    except Exception:
        _emit(
            on_progress,
            StreamingProgressEvent(
                event_type="failed",
                rows=rows_processed,
                cumulative_rows=rows_processed,
            ),
        )
        raise

    _emit(
        on_progress,
        StreamingProgressEvent(
            event_type="completed",
            rows=rows_processed,
            cumulative_rows=rows_processed,
        ),
    )
    return StreamingExecutionResult(
        source_path=source,
        target_path=target,
        source_extension=source.suffix.lower(),
        target_extension=target.suffix.lower(),
        chunk_size=chunk_size,
        chunks_processed=chunks_processed,
        rows_processed=rows_processed,
        completed=True,
        output_path=target,
        sidecar_path=output_sidecar,
    )


def _read_kwargs(
    extension: str,
    options: DatasetReadOptions | None,
) -> dict[str, str]:
    if options is None:
        return {}
    kwargs: dict[str, str] = {}
    if options.encoding is not None:
        kwargs["encoding"] = options.encoding
    if extension == ".csv":
        kwargs.update(options.csv_kwargs())
    return kwargs


def _write_kwargs(
    extension: str,
    options: DatasetWriteOptions | None,
) -> dict[str, str]:
    if options is None or extension != ".csv":
        return {}
    kwargs = options.csv_kwargs()
    if options.encoding is not None:
        kwargs["encoding"] = options.encoding
    return kwargs


def _emit(
    callback: ProgressCallback | None,
    event: StreamingProgressEvent,
) -> None:
    if callback is not None:
        callback(event)
