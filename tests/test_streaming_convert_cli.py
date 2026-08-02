from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.metadata.sidecar import sidecar_path
from statconvert.registry import read_dataset


runner = CliRunner()

_SUPPORTED_PAIRS = [
    (".csv", ".csv"),
    (".csv", ".jsonl"),
    (".csv", ".ndjson"),
    (".jsonl", ".csv"),
    (".jsonl", ".jsonl"),
    (".jsonl", ".ndjson"),
    (".ndjson", ".csv"),
    (".ndjson", ".jsonl"),
    (".ndjson", ".ndjson"),
]


@pytest.mark.parametrize(("source_extension", "target_extension"), _SUPPORTED_PAIRS)
def test_convert_stream_supports_all_foundation_pairs(
    tmp_path: Path,
    source_extension: str,
    target_extension: str,
) -> None:
    source = tmp_path / f"input{source_extension}"
    target = tmp_path / f"output{target_extension}"
    expected = pd.DataFrame(
        {
            "row": range(5),
            "label": ["a", "b", "c", "d", "e"],
        }
    )
    _write_records(expected, source)

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    pd.testing.assert_frame_equal(_read_records(target), expected)
    assert "Streaming conversion completed" in result.output
    assert "Chunk size: 2" in result.output
    assert "Chunks processed: 3" in result.output
    assert "Rows processed: 5" in result.output
    assert sidecar_path(target).name in result.output
    assert sidecar_path(target).exists()


def test_stream_uses_default_chunk_size_only_when_enabled(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.jsonl"
    pd.DataFrame({"value": [1, 2]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream"],
    )

    assert result.exit_code == 0, result.output
    assert "Chunk size: 100,000" in result.output
    assert "Chunks processed: 1" in result.output


def test_chunk_size_without_stream_fails_before_output(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.csv"
    pd.DataFrame({"value": [1]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        ["convert", str(source), str(target), "--chunk-size", "2"],
    )

    assert result.exit_code == 1
    assert "--chunk-size requires --stream" in result.output
    assert not target.exists()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_invalid_chunk_size_fails_cleanly(
    tmp_path: Path,
    value: str,
) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.csv"
    pd.DataFrame({"value": [1]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            value,
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value for '--chunk-size'" in result.output
    assert not target.exists()


@pytest.mark.parametrize(
    ("source_extension", "target_extension", "json_array"),
    [
        (".json", ".csv", True),
        (".csv", ".json", True),
        (".csv", ".parquet", False),
        (".sav", ".csv", False),
        (".xlsx", ".csv", False),
    ],
)
def test_unsupported_streaming_pairs_fail_before_output(
    tmp_path: Path,
    source_extension: str,
    target_extension: str,
    json_array: bool,
) -> None:
    source = tmp_path / f"input{source_extension}"
    target = tmp_path / f"output{target_extension}"
    if source_extension == ".json":
        source.write_text('[{"value": 1}]', encoding="utf-8")
    elif source_extension == ".csv":
        pd.DataFrame({"value": [1]}).to_csv(source, index=False)
    else:
        source.write_bytes(b"placeholder")

    result = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream"],
    )

    assert result.exit_code == 1
    if json_array:
        assert "not supported for JSON array files" in result.output
        assert "Use JSONL or NDJSON" in result.output
    else:
        assert (
            f"not supported for {source_extension} -> {target_extension}"
            in result.output
        )
        assert "Run without --stream" in result.output
    assert "Traceback" not in result.output
    assert not target.exists()
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(f".{target.name}.statconvert-*.tmp*"))


def test_non_streaming_convert_keeps_existing_path_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.jsonl"
    pd.DataFrame({"value": [1, 2]}).to_csv(source, index=False)

    monkeypatch.setattr(
        "statconvert.cli.execute_streaming_convert",
        lambda *args, **kwargs: pytest.fail("streaming executor was called"),
    )
    result = runner.invoke(app, ["convert", str(source), str(target)])

    assert result.exit_code == 0, result.output
    assert "Conversion completed" in result.output
    assert "Rows converted: 2" in result.output
    assert "Streaming conversion completed" not in result.output


def test_streaming_csv_options_are_mapped_to_executor(tmp_path: Path) -> None:
    source = tmp_path / "latin1.csv"
    target = tmp_path / "output.csv"
    expected = pd.DataFrame({"city": ["Zürich"], "amount": [1.5]})
    expected.to_csv(
        source,
        index=False,
        encoding="latin1",
        sep=";",
        decimal=",",
    )

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "1",
            "--input-encoding",
            "latin1",
            "--output-encoding",
            "utf-8-sig",
            "--csv-delimiter",
            ";",
            "--csv-decimal",
            ",",
        ],
    )

    assert result.exit_code == 0, result.output
    actual = pd.read_csv(
        target,
        encoding="utf-8-sig",
        sep=";",
        decimal=",",
    )
    pd.testing.assert_frame_equal(actual, expected)


def test_streaming_output_safety_matches_normal_convert(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "missing" / "output.csv"
    pd.DataFrame({"value": [1]}).to_csv(source, index=False)

    missing_parent = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream"],
    )
    created = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream", "--create-dirs"],
    )
    blocked_existing = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream"],
    )
    overwritten = runner.invoke(
        app,
        ["convert", str(source), str(target), "--stream", "--overwrite"],
    )

    assert missing_parent.exit_code == 1
    assert "--create-dirs" in missing_parent.output
    assert created.exit_code == 0, created.output
    assert blocked_existing.exit_code == 1
    assert "--overwrite" in blocked_existing.output
    assert overwritten.exit_code == 0, overwritten.output


def test_malformed_json_lines_cleans_output_and_preserves_existing_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "broken.jsonl"
    target = tmp_path / "output.csv"
    source.write_text('{"a": 1}\n{"a":\n', encoding="utf-8")
    target.write_text("original\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "1",
            "--overwrite",
        ],
    )

    assert result.exit_code == 1
    assert "Failed reading chunked JSON Lines file" in result.output
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp*"))


def test_schema_drift_cleans_output_and_preserves_existing_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drift.jsonl"
    target = tmp_path / "output.csv"
    source.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
    target.write_text("original\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "1",
            "--overwrite",
        ],
    )

    assert result.exit_code == 1
    assert "Streaming schema drift" in result.output
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()
    assert not list(tmp_path.glob(".output.csv.statconvert-*.tmp*"))


def test_source_sidecar_metadata_survives_cli_streaming(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.ndjson"
    dataframe = pd.DataFrame({"value": [1, 2, 3]})
    dataframe.to_csv(source, index=False)
    dataset = Dataset(
        dataframe,
        source_format="csv",
        source_file=str(source),
    )
    dataset.get_normalized_metadata().variables["value"].label = "CLI label"
    dataset.sync_metadata()
    dataset.write_sidecar(source)

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert read_dataset(target).variable_labels() == {"value": "CLI label"}


def test_streaming_conversion_writes_compact_log_summary(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.jsonl"
    log_file = tmp_path / "streaming.log"
    pd.DataFrame({"value": [1, 2, 3]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(target),
            "--stream",
            "--chunk-size",
            "2",
            "--log",
            str(log_file),
        ],
    )

    contents = log_file.read_text(encoding="utf-8")
    assert result.exit_code == 0, result.output
    assert "Streaming conversion result:" in contents
    assert "chunks=2" in contents
    assert "rows=3" in contents


@pytest.mark.parametrize(
    "arguments",
    [
        ["--stream", "--validate"],
        ["--stream", "--strict-validation"],
        ["--stream", "--object", "Data"],
        ["--stream", "--all-objects"],
        ["--stream", "--write-config", "convert.toml"],
    ],
)
def test_streaming_rejects_unimplemented_convert_integrations(
    tmp_path: Path,
    arguments: list[str],
) -> None:
    source = tmp_path / "input.csv"
    target = tmp_path / "output.csv"
    pd.DataFrame({"value": [1]}).to_csv(source, index=False)

    result = runner.invoke(
        app,
        ["convert", str(source), str(target), *arguments],
    )

    assert result.exit_code == 1
    assert "does not support" in result.output or "not supported" in result.output
    assert not target.exists()


@pytest.mark.parametrize(
    "command",
    ["report", "transform", "compare", "collect"],
)
def test_streaming_options_are_absent_from_unrelated_commands(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--stream" not in result.output
    assert "--chunk-size" not in result.output


def _write_records(dataframe: pd.DataFrame, path: Path) -> None:
    if path.suffix.lower() == ".csv":
        dataframe.to_csv(path, index=False)
    else:
        dataframe.to_json(path, orient="records", lines=True)


def _read_records(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_json(path, lines=True)
