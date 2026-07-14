from __future__ import annotations

from statconvert.dataset import Dataset
from statconvert.transformations.base import Transformation


class NoOpTransformation(Transformation):
    """
    Transformation that returns a copy of the input dataset.
    """

    name = "noop"
    description = "Return an unchanged copy of the dataset."


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a copied dataset without changing it.
        """

        return dataset.copy()
