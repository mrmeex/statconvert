import pytest

from statconvert.streaming import StreamingNotSupportedError, build_streaming_plan


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("input.csv", "output.csv"),
        ("input.csv", "output.jsonl"),
        ("input.ndjson", "output.csv"),
        ("input.jsonl", "output.ndjson"),
    ],
)
def test_foundation_pairs_are_internal_execution_candidates(
    source: str,
    target: str,
) -> None:
    plan = build_streaming_plan(source, target)

    assert plan.candidate is True
    assert plan.implemented is True
    assert "internal 0.9.0b streaming execution path" in plan.reasons[0]


def test_json_array_source_is_not_a_candidate() -> None:
    plan = build_streaming_plan("input.json", "output.csv")

    assert plan.candidate is False
    assert any("not a safe initial streaming source" in item for item in plan.reasons)


def test_deferred_pair_produces_clear_execution_error() -> None:
    plan = build_streaming_plan("input.parquet", "output.feather")

    with pytest.raises(
        StreamingNotSupportedError,
        match=r"Streaming conversion is not supported for \.parquet -> \.feather",
    ):
        plan.require_executable()
