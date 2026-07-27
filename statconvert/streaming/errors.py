"""Friendly errors for internal streaming workflows."""

from statconvert.exceptions import ConversionError


class StreamingNotSupportedError(ConversionError):
    """A requested streaming operation is not implemented."""


class StreamingSchemaError(ConversionError):
    """A streamed chunk does not match the established schema."""


class StreamingWriteError(ConversionError):
    """A transactional streaming write could not be completed."""
