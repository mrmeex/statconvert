from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as metadata_version
import platform

import statconvert


RUNTIME_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("pandas", "pandas"),
    ("typer", "typer"),
    ("rich", "rich"),
    ("openpyxl", "openpyxl"),
    ("xlsxwriter", "xlsxwriter"),
    ("xlrd", "xlrd"),
    ("xlwt", "xlwt"),
    ("pyreadstat", "pyreadstat"),
    ("pyarrow", "pyarrow"),
    ("pyreadr", "pyreadr"),
    ("odfpy", "odf"),
)


def get_statconvert_version() -> str:
    """Return the installed StatConvert distribution version."""

    try:
        return metadata_version("statconvert")
    except PackageNotFoundError:
        return getattr(statconvert, "__version__", "unknown")


def get_runtime_dependency_status() -> list[tuple[str, str]]:
    """Return display names and installed versions for runtime dependencies."""

    return [
        (package_name, _dependency_status(package_name, module_name))
        for package_name, module_name in RUNTIME_DEPENDENCIES
    ]


def _dependency_status(package_name: str, module_name: str) -> str:
    try:
        return metadata_version(package_name)
    except PackageNotFoundError:
        try:
            import_module(module_name)
        except ImportError:
            return "not installed"
        return "installed"


def format_version_status() -> str:
    """Format plain-text application and runtime dependency status."""

    lines = [
        f"StatConvert: {get_statconvert_version()}",
        f"Python: {platform.python_version()}",
    ]
    lines.extend(
        f"{package_name}: {status}"
        for package_name, status in get_runtime_dependency_status()
    )
    return "\n".join(lines)
