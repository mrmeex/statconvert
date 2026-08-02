import pytest

from statconvert.streaming import ChunkedReadOptions, ChunkedWriteOptions
from statconvert.streaming.options import validate_chunk_size


@pytest.mark.parametrize("value", [1, 1_000, 10_000_000])
def test_chunk_size_accepts_positive_integers(value: int) -> None:
    assert validate_chunk_size(value) == value
    assert ChunkedReadOptions(value).chunk_size == value
    assert ChunkedWriteOptions(value).chunk_size == value


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1000", None])
def test_chunk_size_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="chunk_size must be a positive integer"):
        validate_chunk_size(value)  # type: ignore[arg-type]
