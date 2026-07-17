from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.objects import DatasetObjectInfo, NamedDataset
from statconvert.dataset import Dataset
from statconvert.exceptions import ObjectSelectionNotSupportedError


class Backend(ABC):
    """
    Abstract base class for all file format backends.
    """

    #: Short backend name (e.g. "excel", "csv", "pyreadstat")
    name: str

    #: Declarative backend capabilities.
    capabilities = BackendCapabilities()

    def supports_object_selection(self) -> bool:
        """Return whether this backend can select dataset objects."""

        return self.capabilities.object_selection

    def list_objects(self, path: Path) -> list[DatasetObjectInfo]:
        """List readable dataset objects, if implemented by the backend."""

        return []

    def read_object(
        self,
        path: Path,
        object_selector: str,
    ) -> Dataset:
        """Read one selected object or reject selection by default."""

        extension = path.suffix.lower() or "this format"
        raise ObjectSelectionNotSupportedError(
            f"Object selection is not supported for {extension} files."
        )

    def validate_object_names(
        self,
        names: Sequence[str],
        filename: str,
    ) -> None:
        """Validate names for a multi-object output or reject it by default."""

        extension = Path(filename).suffix.lower() or "this format"
        raise ObjectSelectionNotSupportedError(
            f"Writing multiple dataset objects is not supported for {extension}."
        )

    def write_objects(
        self,
        objects: Sequence[NamedDataset],
        filename: str,
        **kwargs,
    ) -> None:
        """Write named datasets to one output container or reject by default."""

        extension = Path(filename).suffix.lower() or "this format"
        raise ObjectSelectionNotSupportedError(
            f"Writing multiple dataset objects is not supported for {extension}."
        )

    @abstractmethod
    def read(
        self,
        filename: str,
        **kwargs
    ) -> Dataset:
        """
        Read a file and return a Dataset.
        """
        raise NotImplementedError

    @abstractmethod
    def write(
        self,
        dataset: Dataset,
        filename: str,
        **kwargs
    ) -> None:
        """
        Write a Dataset to a file.
        """
        raise NotImplementedError
