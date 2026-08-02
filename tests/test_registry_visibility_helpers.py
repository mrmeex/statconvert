import pytest

from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.registry import (
    get_backend_capabilities,
    get_backend_capabilities_for_extension,
    list_backends,
    list_formats,
    resolve_format_or_backend,
)


def test_list_formats_includes_common_supported_formats():

    formats = list_formats()

    assert formats[".csv"]["backend"] == "csv"
    assert formats[".sav"]["backend"] == "pyreadstat"
    assert formats[".parquet"]["backend"] == "arrow"


def test_list_backends_includes_core_backends():

    backends = list_backends()

    assert isinstance(
        backends["csv"],
        CSVBackend,
    )
    assert "excel" in backends
    assert isinstance(
        backends["pyreadstat"],
        PyReadstatBackend,
    )


def test_capabilities_lookup_works_for_backend_name():

    capabilities = get_backend_capabilities(
        "pyreadstat"
    )

    assert capabilities.supports_variable_labels is True
    assert capabilities.supports_value_labels is True


def test_capabilities_lookup_works_for_extension_with_dot():

    capabilities = get_backend_capabilities_for_extension(
        ".sav"
    )

    assert capabilities == PyReadstatBackend.capabilities


def test_capabilities_lookup_works_for_extension_without_dot():

    capabilities = get_backend_capabilities_for_extension(
        "sav"
    )

    assert capabilities == PyReadstatBackend.capabilities


def test_resolve_format_or_backend_resolves_backend_name():

    result = resolve_format_or_backend(
        "pyreadstat"
    )

    assert result["kind"] == "backend"
    assert result["backend_name"] == "pyreadstat"
    assert result["capabilities"] == PyReadstatBackend.capabilities


def test_resolve_format_or_backend_resolves_extension():

    result = resolve_format_or_backend(
        "sav"
    )

    assert result["kind"] == "format"
    assert result["extension"] == ".sav"
    assert result["format_name"] == "SPSS SAV"
    assert result["backend_name"] == "pyreadstat"


def test_unsupported_target_raises_clear_error():

    with pytest.raises(
        ValueError,
        match="Unsupported format or backend",
    ):
        resolve_format_or_backend(
            "unknown-format"
        )
