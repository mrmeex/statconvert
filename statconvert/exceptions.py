class StatConvertError(Exception):
    """Base exception with an optional concise operator suggestion."""

    def __init__(self, message: str, *, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion

    def __str__(self) -> str:
        if self.suggestion is None:
            return self.message
        return f"{self.message}\nSuggestion: {self.suggestion}"


class UnsupportedFormatError(StatConvertError, ValueError):
    """Format is not supported."""


class ConversionError(StatConvertError):
    """Conversion failed."""


class MetadataSidecarError(ConversionError):
    """A metadata sidecar or embedded payload is invalid."""


class DataDictionaryError(ConversionError):
    """A human-readable metadata dictionary could not be produced."""


class MetadataScriptError(ConversionError):
    """An external-tool metadata helper script could not be produced."""


class OutputPathError(ConversionError):
    """An output path conflicts with the selected write policy."""


class ConfigError(StatConvertError):
    """A workflow configuration is invalid or cannot be accessed."""


class ObjectSelectionError(StatConvertError):
    """A dataset object could not be selected."""


class ObjectNotFoundError(ObjectSelectionError):
    """The requested dataset object was not found."""


class AmbiguousObjectError(ObjectSelectionError):
    """A dataset object selector matched more than one object."""


class ObjectSelectionNotSupportedError(ObjectSelectionError):
    """The selected format does not expose dataset objects."""
