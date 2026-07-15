class StatConvertError(Exception):
    """Base exception."""


class UnsupportedFormatError(StatConvertError):
    """Format is not supported."""


class ConversionError(StatConvertError):
    """Conversion failed."""


class OutputPathError(ConversionError):
    """An output path conflicts with the selected write policy."""


class ObjectSelectionError(StatConvertError):
    """A dataset object could not be selected."""


class ObjectNotFoundError(ObjectSelectionError):
    """The requested dataset object was not found."""


class AmbiguousObjectError(ObjectSelectionError):
    """A dataset object selector matched more than one object."""


class ObjectSelectionNotSupportedError(ObjectSelectionError):
    """The selected format does not expose dataset objects."""
