"""Internal foundations for selective streaming workflows."""

from statconvert.streaming.capabilities import (
    FormatStreamingCapability,
    StreamingSupport,
    StreamingSuitability,
    get_streaming_capability,
    list_streaming_capabilities,
)
from statconvert.streaming.chunks import (
    ChunkWriter,
    DatasetChunk,
    StreamingExecutionResult,
    StreamingProgressEvent,
)
from statconvert.streaming.errors import (
    StreamingNotSupportedError,
    StreamingSchemaError,
    StreamingWriteError,
)
from statconvert.streaming.options import ChunkedReadOptions, ChunkedWriteOptions
from statconvert.streaming.plan import (
    StreamingPlan,
    build_streaming_plan,
)
from statconvert.streaming.schema import StreamingSchemaGuard

__all__ = [
    "ChunkedReadOptions",
    "ChunkedWriteOptions",
    "ChunkWriter",
    "DatasetChunk",
    "FormatStreamingCapability",
    "StreamingNotSupportedError",
    "StreamingPlan",
    "StreamingExecutionResult",
    "StreamingProgressEvent",
    "StreamingSchemaError",
    "StreamingSchemaGuard",
    "StreamingSupport",
    "StreamingSuitability",
    "StreamingWriteError",
    "build_streaming_plan",
    "get_streaming_capability",
    "list_streaming_capabilities",
]
