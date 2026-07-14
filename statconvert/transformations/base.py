from __future__ import annotations

from abc import ABC, abstractmethod

from statconvert.dataset import Dataset


class Transformation(ABC):
    """
    Base class for dataset transformations.
    """

    name: str
    description: str | None = None


    @abstractmethod
    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Apply this transformation and return a Dataset.
        """
