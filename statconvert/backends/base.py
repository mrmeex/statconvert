from abc import ABC, abstractmethod
from pathlib import Path

from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.objects import DatasetObjectInfo
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
