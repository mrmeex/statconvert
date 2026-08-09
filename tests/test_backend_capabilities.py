from statconvert.backends.arrow_backend import ArrowBackend
from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.csv_backend import CSVBackend
from statconvert.backends.excel_backend import ExcelBackend
from statconvert.backends.json_backend import JsonBackend
from statconvert.backends.ods_backend import ODSBackend
from statconvert.backends.pyreadstat_backend import PyReadstatBackend
from statconvert.backends.r_backend import RBackend
from statconvert.registry import (
    get_backend_capabilities_for_file,
    list_backend_capabilities,
)


def test_backend_capabilities_default_values():

    capabilities = BackendCapabilities()

    assert capabilities.can_read is True
    assert capabilities.can_write is True
    assert capabilities.supports_variable_labels is False
    assert capabilities.supports_compression is False
    assert capabilities.preserves_index is False
    assert capabilities.is_container is False
    assert capabilities.object_selection is False
    assert capabilities.object_kind is None
    assert capabilities.multi_object_write is False
    assert capabilities.output_object_kind is None


def test_supports_any_metadata_false_by_default():

    assert BackendCapabilities().supports_any_metadata() is False


def test_supports_any_metadata_true_when_metadata_flag_is_true():

    capabilities = BackendCapabilities(
        supports_variable_labels=True
    )

    assert capabilities.supports_any_metadata() is True


def test_capability_summaries_are_deterministic():

    capabilities = BackendCapabilities(
        supports_variable_labels=True,
        supports_compression=True,
        supports_multiple_sheets=True,
    )

    assert capabilities.metadata_summary() == {
        "variable_labels": True,
        "value_labels": False,
        "missing_values": False,
        "display_formats": False,
        "measurement_levels": False,
        "custom_metadata": False,
    }
    assert capabilities.storage_summary() == {
        "compression": True,
        "streaming": False,
        "preserves_index": False,
    }
    assert capabilities.table_summary() == {
        "multiple_tables": False,
        "multiple_sheets": True,
    }
    assert capabilities.object_summary() == {
        "is_container": False,
        "object_selection": False,
        "object_kind": None,
        "multi_object_write": False,
        "output_object_kind": None,
    }


def test_each_backend_exposes_capabilities_attribute():

    backends = [
        Backend,
        ArrowBackend,
        CSVBackend,
        ExcelBackend,
        JsonBackend,
        ODSBackend,
        PyReadstatBackend,
        RBackend,
    ]

    for backend in backends:
        assert isinstance(
            backend.capabilities,
            BackendCapabilities
        )


def test_pyreadstat_capabilities_show_label_support():

    capabilities = PyReadstatBackend.capabilities

    assert capabilities.supports_variable_labels is True
    assert capabilities.supports_value_labels is True
    assert capabilities.supports_missing_values is True
    assert capabilities.supports_any_metadata() is True


def test_csv_capabilities_do_not_show_metadata_support():

    capabilities = CSVBackend.capabilities

    assert capabilities.supports_any_metadata() is False
    assert capabilities.supports_variable_labels is False
    assert capabilities.supports_value_labels is False


def test_arrow_capabilities_describe_namespaced_metadata_behavior():
    capabilities = ArrowBackend.capabilities

    assert capabilities.supports_custom_metadata is True
    assert capabilities.supports_any_metadata() is True


def test_registry_get_backend_capabilities_for_sav_file():

    capabilities = get_backend_capabilities_for_file(
        "example.sav"
    )

    assert capabilities == PyReadstatBackend.capabilities
    assert capabilities.supports_variable_labels is True


def test_registry_refines_csv_backend_capabilities_for_streaming():

    capabilities = get_backend_capabilities_for_file(
        "example.csv"
    )

    assert capabilities.supports_any_metadata() is False
    assert capabilities.supports_streaming is True
    assert CSVBackend.capabilities.supports_streaming is False


def test_list_backend_capabilities_returns_registered_backends():

    capabilities = list_backend_capabilities()

    assert capabilities["csv"] == CSVBackend.capabilities
    assert capabilities["pyreadstat"] == PyReadstatBackend.capabilities
