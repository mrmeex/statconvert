from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyreadr

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.objects import DatasetObjectInfo, resolve_object_selector
from statconvert.dataset import Dataset
from statconvert.error_suggestions import format_cli_path
from statconvert.exceptions import (
    ConversionError,
    ObjectNotFoundError,
    ObjectSelectionError,
    ObjectSelectionNotSupportedError,
)
from statconvert.metadata import build_basic_metadata
from statconvert.metadata.sidecar import read_sidecar, restore_metadata


@dataclass(frozen=True)
class _RWorkspaceObject:
    """Associate public object information with a pyreadr result value."""

    info: DatasetObjectInfo
    key: Any
    value: Any


class RBackend(Backend):
    """R reader/writer backend for RDS and R workspace files."""

    name = "r"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
        supports_multiple_tables=True,
        supports_custom_metadata=False,
        is_container=True,
        object_selection=True,
        object_kind="r_object",
    )

    def list_objects(self, path: Path) -> list[DatasetObjectInfo]:
        """List named objects exposed by an RData or RDA workspace."""

        extension = self._extension(str(path))
        if extension == ".rds":
            raise ObjectSelectionNotSupportedError(
                "This format does not expose multiple dataset objects."
            )

        descriptors = self._list_object_descriptors(str(path))
        try:
            result = self._read_result(str(path), {})
        except ConversionError:
            if not descriptors:
                raise
            result = {}

        return [
            workspace_object.info
            for workspace_object in self._workspace_objects(result, descriptors)
        ]

    def read_object(
        self,
        path: Path,
        object_selector: str,
    ) -> Dataset:
        """Read one selected R workspace object."""

        return self.read(
            str(path),
            object_selector=object_selector,
        )

    def read(
        self,
        filename: str,
        **kwargs,
    ) -> Dataset:
        """Read an R file into a Dataset."""

        extension = self._extension(filename)
        object_selector = kwargs.pop("object_selector", None)
        object_name = kwargs.pop("object_name", None)
        selector = self._coalesce_object_selector(
            object_selector,
            object_name,
        )
        if extension == ".rds" and selector is not None:
            raise ObjectSelectionNotSupportedError(
                "Object selection is not supported for .rds files."
            )

        options = self._supported_options(
            kwargs,
            {
                "use_objects",
                "timezone",
            },
        )
        result = self._read_result(filename, options)

        if extension == ".rds":
            dataframe, selected_object = self._select_rds_dataframe(result)
            object_names = [self._object_name(name) for name in result]
        else:
            descriptors = self._list_object_descriptors(filename)
            workspace_objects = self._workspace_objects(result, descriptors)
            dataframe, selected_object = self._select_workspace_dataframe(
                workspace_objects,
                selector,
                filename,
            )
            object_names = [item.info.name for item in workspace_objects]

        try:
            sidecar = read_sidecar(filename)
            column_metadata = sidecar.columns if sidecar is not None else {}
            dataframe = self._dataframe_for_read(dataframe, column_metadata)
        except Exception as exc:
            raise ConversionError(f"Failed reading R file: {exc}") from exc

        metadata = {
            "backend": self.name,
            "file_type": extension,
            "r_objects": object_names,
            "selected_object": self._object_name(selected_object),
            "object_count": len(object_names),
        }
        restored = restore_metadata(
            dataframe=dataframe,
            filename=filename,
            automatic_payload=sidecar,
            base_metadata=build_basic_metadata(
                dataframe=dataframe,
                source_format=extension.lstrip("."),
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )

        return Dataset(
            dataframe=dataframe,
            metadata=metadata,
            source_format=extension.lstrip("."),
            source_file=str(filename),
            normalized_metadata=restored.metadata,
            column_metadata=restored.column_metadata,
            metadata_provenance=restored.provenance,
        )

    def write(
        self,
        dataset: Dataset,
        filename: str,
        **kwargs,
    ) -> None:
        """Write Dataset to an R file."""

        try:
            extension = self._extension(filename)
            object_name = kwargs.pop("object_name", "data")
            options = self._supported_options(
                kwargs,
                {
                    "dateformat",
                    "datetimeformat",
                    "compress",
                    "compresslevel",
                },
            )
            dataframe = self._dataframe_for_write(dataset)

            if extension == ".rds":
                pyreadr.write_rds(filename, dataframe, **options)
            elif extension in {".rdata", ".rda"}:
                pyreadr.write_rdata(
                    filename,
                    dataframe,
                    df_name=object_name,
                    **options,
                )
            else:
                raise ValueError(f"Unsupported R format: {extension}")

            dataset.write_sidecar(filename)
        except Exception as exc:
            raise ConversionError(f"Failed writing R file: {exc}") from exc

    def _read_result(
        self,
        filename: str,
        options: dict[str, Any],
    ) -> Mapping[Any, Any]:
        """Read objects through pyreadr with a stable project exception."""

        try:
            return pyreadr.read_r(filename, **options)
        except Exception as exc:
            raise ConversionError(f"Failed reading R file: {exc}") from exc

    def _list_object_descriptors(
        self,
        filename: str,
    ) -> list[Mapping[str, Any]]:
        """Return best-effort pyreadr descriptors for unsupported objects."""

        try:
            descriptors = pyreadr.list_objects(filename)
        except Exception:
            return []

        return [
            descriptor
            for descriptor in descriptors
            if isinstance(descriptor, Mapping)
        ]

    def _workspace_objects(
        self,
        result: Mapping[Any, Any],
        descriptors: Sequence[Mapping[str, Any]],
    ) -> list[_RWorkspaceObject]:
        """Combine readable results and best-effort workspace descriptors."""

        workspace_objects: list[_RWorkspaceObject] = []
        used_keys: list[Any] = []

        for descriptor in descriptors:
            descriptor_name = descriptor.get("object_name")
            found, key, value = self._find_result_object(result, descriptor_name)
            if found:
                used_keys.append(key)
            workspace_objects.append(
                self._workspace_object(
                    name=descriptor_name,
                    key=key if found else descriptor_name,
                    value=value if found else None,
                    index=len(workspace_objects),
                    descriptor_columns=descriptor.get("columns"),
                    exposed=found,
                )
            )

        for key, value in result.items():
            if key in used_keys:
                continue
            workspace_objects.append(
                self._workspace_object(
                    name=key,
                    key=key,
                    value=value,
                    index=len(workspace_objects),
                    descriptor_columns=None,
                    exposed=True,
                )
            )

        return workspace_objects

    def _workspace_object(
        self,
        *,
        name: Any,
        key: Any,
        value: Any,
        index: int,
        descriptor_columns: Any,
        exposed: bool,
    ) -> _RWorkspaceObject:
        """Build one object record and classify tabular support."""

        if isinstance(value, pd.DataFrame):
            info = DatasetObjectInfo(
                name=self._object_name(name),
                index=index,
                kind="r_object",
                rows=len(value.index),
                columns=len(value.columns),
            )
        else:
            columns = (
                len(descriptor_columns)
                if isinstance(descriptor_columns, (list, tuple))
                else None
            )
            if exposed:
                message = f"Unsupported R object type: {type(value).__name__}."
            else:
                message = (
                    "This R object is not exposed as a readable pandas "
                    "DataFrame by pyreadr."
                )
            info = DatasetObjectInfo(
                name=self._object_name(name),
                index=index,
                kind="r_object",
                columns=columns,
                supported=False,
                message=message,
            )

        return _RWorkspaceObject(info=info, key=key, value=value)

    def _find_result_object(
        self,
        result: Mapping[Any, Any],
        descriptor_name: Any,
    ) -> tuple[bool, Any, Any]:
        """Find a descriptor's corresponding pyreadr result entry."""

        for key, value in result.items():
            if key == descriptor_name:
                return True, key, value
        for key, value in result.items():
            if self._object_name(key) == self._object_name(descriptor_name):
                return True, key, value
        return False, descriptor_name, None

    def _select_workspace_dataframe(
        self,
        workspace_objects: list[_RWorkspaceObject],
        selector: str | None,
        filename: str,
    ) -> tuple[pd.DataFrame, Any]:
        """Resolve one supported DataFrame from an R workspace."""

        supported = [item.info for item in workspace_objects if item.info.supported]
        all_objects = [item.info for item in workspace_objects]

        if selector is None:
            if not supported:
                raise ObjectNotFoundError(
                    "No supported tabular R objects were found in "
                    f"{Path(filename).name}."
                )
            selected = resolve_object_selector(
                supported,
                None,
                path=filename,
                object_label="Object",
            )
        else:
            selected = self._resolve_named_object_first(
                all_objects,
                selector,
                filename,
            )

        if not selected.supported:
            available = ", ".join(info.name for info in supported) or "none"
            detail = f" {selected.message}" if selected.message else ""
            raise ObjectSelectionError(
                f"Object '{selected.name}' is not a supported tabular dataset "
                f"object.{detail} Available supported objects: {available}.",
                suggestion=(
                    f"Run `statconvert objects {format_cli_path(filename)}` and select "
                    "a supported object."
                ),
            )

        workspace_object = workspace_objects[selected.index or 0]
        if not isinstance(workspace_object.value, pd.DataFrame):
            raise ObjectSelectionError(
                f"Object '{selected.name}' is not a supported tabular dataset object.",
                suggestion=(
                    f"Run `statconvert objects {format_cli_path(filename)}` and select "
                    "a supported object."
                ),
            )
        return workspace_object.value, workspace_object.key

    def _resolve_named_object_first(
        self,
        objects: list[DatasetObjectInfo],
        selector: str,
        filename: str,
    ) -> DatasetObjectInfo:
        """Prefer an exact R object name before considering an index."""

        exact_name_matches = [info for info in objects if info.name == selector]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]
        return resolve_object_selector(
            objects,
            selector,
            path=filename,
            object_label="Object",
        )

    def _select_rds_dataframe(
        self,
        result: Mapping[Any, Any],
    ) -> tuple[pd.DataFrame, Any]:
        """Select the single tabular value exposed by an RDS file."""

        for name, value in result.items():
            if isinstance(value, pd.DataFrame):
                return value, name
        raise ConversionError("No tabular R object found.")

    def _coalesce_object_selector(
        self,
        object_selector: str | None,
        object_name: str | None,
    ) -> str | None:
        """Accept the new selector while preserving the older backend keyword."""

        if object_selector is not None and object_name is not None:
            raise ObjectSelectionError(
                "Use object_selector or object_name, not both."
            )
        return object_selector if object_selector is not None else object_name

    def _extension(self, filename: str) -> str:
        """Return normalized R file extension."""

        extension = Path(filename).suffix.lower()
        if extension not in {".rds", ".rdata", ".rda"}:
            raise ValueError(f"Unsupported R format: {extension}")
        return extension

    def _dataframe_for_write(self, dataset: Dataset) -> pd.DataFrame:
        """Return a DataFrame without preserving the pandas index."""

        return dataset.dataframe.reset_index(drop=True)

    def _dataframe_for_read(
        self,
        dataframe: pd.DataFrame,
        column_metadata: dict,
    ) -> pd.DataFrame:
        """Return a DataFrame normalized for StatConvert."""

        dataframe = dataframe.reset_index(drop=True)
        for name, metadata in column_metadata.items():
            if name not in dataframe.columns:
                continue
            if metadata.logical_type == "integer":
                dataframe[name] = self._as_integer_series(dataframe[name])
        return dataframe

    def _as_integer_series(self, series):
        """Convert whole-number series to integer dtype when possible."""

        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.isna().sum() > series.isna().sum():
            return series

        non_missing = numeric.dropna()
        if not (non_missing % 1 == 0).all():
            return series
        if numeric.isna().any():
            return numeric.astype("Int64")
        return numeric.astype("int64")

    def _object_name(self, name: Any) -> str:
        """Return a readable R object name for metadata."""

        if name is None or name == "":
            return "<unnamed>"
        return str(name)

    def _supported_options(
        self,
        kwargs: dict[str, Any],
        supported_names: set[str],
    ) -> dict[str, Any]:
        """Keep only kwargs supported by pyreadr for this operation."""

        return {
            name: value
            for name, value in kwargs.items()
            if name in supported_names
        }
