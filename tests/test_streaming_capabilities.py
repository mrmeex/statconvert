import json

import pytest

from statconvert.registry import supported_extensions
from statconvert.streaming import (
    StreamingSupport,
    StreamingSuitability,
    get_streaming_capability,
    list_streaming_capabilities,
)


def test_streaming_audit_covers_every_registered_format() -> None:
    assert set(list_streaming_capabilities()) == set(supported_extensions())


def test_csv_and_line_delimited_json_are_conservative_first_targets() -> None:
    for extension in (".csv", ".jsonl", ".ndjson"):
        capability = get_streaming_capability(extension)
        assert capability.chunked_read is StreamingSupport.SUPPORTED_NOW
        assert capability.chunked_write is StreamingSupport.SUPPORTED_NOW
        assert capability.safe_initial_use is StreamingSuitability.YES


def test_json_array_is_not_an_initial_streaming_source() -> None:
    capability = get_streaming_capability("records.json")

    assert capability.chunked_read is StreamingSupport.UNSUPPORTED
    assert capability.safe_initial_use is StreamingSuitability.NO


def test_only_foundation_formats_claim_internal_streaming_support_now() -> None:
    supported = {
        capability.extension
        for capability in list_streaming_capabilities().values()
        if capability.chunked_read is StreamingSupport.SUPPORTED_NOW
        or capability.chunked_write is StreamingSupport.SUPPORTED_NOW
    }

    assert supported == {".csv", ".jsonl", ".ndjson"}


def test_capability_serializes_to_plain_json() -> None:
    capability = get_streaming_capability("CSV")

    payload = capability.to_dict()

    assert payload["chunked_read"] == "supported_now"
    assert payload["safe_initial_use"] == "yes"
    assert json.loads(json.dumps(payload)) == payload


def test_unknown_streaming_format_fails_clearly() -> None:
    with pytest.raises(ValueError, match=r"Unsupported streaming format: \.dbf"):
        get_streaming_capability("example.dbf")


def test_relative_path_below_dot_prefixed_directory_is_normalized() -> None:
    capability = get_streaming_capability(r".temporary\input.csv")

    assert capability.extension == ".csv"
