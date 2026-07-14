from __future__ import annotations

from statconvert.dataset import Dataset
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


class TransformationPipeline:
    """
    Ordered collection of dataset transformations.
    """

    def __init__(
        self,
        transformations: list[Transformation] | None = None
    ) -> None:
        """
        Create a transformation pipeline.
        """

        self.transformations = list(
            transformations or []
        )


    def add(
        self,
        transformation: Transformation
    ) -> None:
        """
        Add a transformation to the end of the pipeline.
        """

        self.transformations.append(
            transformation
        )


    def extend(
        self,
        transformations: list[Transformation]
    ) -> None:
        """
        Add multiple transformations to the end of the pipeline.
        """

        self.transformations.extend(
            transformations
        )


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Apply all transformations in order.
        """

        if self.is_empty():
            return dataset

        transformed = dataset

        for transformation in self.transformations:
            name = getattr(
                transformation,
                "name",
                transformation.__class__.__name__,
            )

            try:
                transformed = transformation.apply(
                    transformed
                )

            except Exception as exc:
                raise TransformationError(
                    f"Transformation '{name}' failed: {exc}"
                ) from exc

            if not isinstance(
                transformed,
                Dataset
            ):
                raise TransformationError(
                    f"Transformation '{name}' failed: "
                    "apply() must return a Dataset."
                )

        return transformed


    def is_empty(self) -> bool:
        """
        Return whether the pipeline has no transformations.
        """

        return len(
            self.transformations
        ) == 0


    def __len__(
        self
    ) -> int:
        """
        Return the number of transformations in the pipeline.
        """

        return len(
            self.transformations
        )
