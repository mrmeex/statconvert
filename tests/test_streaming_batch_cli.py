import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.metadata.sidecar import sidecar_path


runner = CliRunner()


@pytest.mark.parametrize(
    ("source_extension", "target_format"),
    [
        (".csv", "csv"),
        (".csv", "jsonl"),
        (".jsonl", "csv"),
        (".ndjson", "csv"),
    ],
)
def test_batch_stream_cli_supports_foundation_examples(
    tmp_path: Path,
    source_extension: str,
    target_format: str,
) -> None:
    source_dir = tmp_path / "input"
    source = source_dir / f"records{source_extension}"
    expected = pd.DataFrame({"value": range(5), "label": list("abcde")})
    _write_records(expected, source)
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source_dir),
            str(output),
            "--to",
            target_format,
            "--stream",
            "--chunk-size",
            "2",
            "--create-dirs",
            "--no-progress",
        ],
    )

    target = output / f"records.{target_format}"
    assert result.exit_code == 0, result.output
    pd.testing.assert_frame_equal(_read_records(target), expected)
    assert sidecar_path(target).exists()
    assert "Streaming" in result.output
    assert "Chunk size" in result.output
    assert "Streamed chunks" in result.output
    assert "Streamed rows" in result.output


def test_batch_stream_cli_json_and_report_include_metrics(tmp_path: Path) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": range(5)}), source)
    report = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "jsonl",
            "--stream",
            "--chunk-size",
            "2",
            "--create-dirs",
            "--json",
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    item = output["items"][0]
    assert output["workload"]["streaming_enabled"] is True
    assert output["workload"]["chunk_size"] == 2
    assert item["streaming"] is True
    assert item["chunks_processed"] == 3
    assert item["rows_processed"] == 5
    report_data = json.loads(report.read_text(encoding="utf-8"))
    assert report_data["summary"]["streaming"] is True
    assert report_data["summary"]["chunk_size"] == 2
    assert report_data["summary"]["total_streamed_chunks"] == 3
    assert report_data["summary"]["total_streamed_rows"] == 5
    assert report_data["items"][0]["streaming"] is True


def test_batch_stream_uses_shared_default_chunk_size(tmp_path: Path) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1, 2]}), source)

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "jsonl",
            "--stream",
            "--create-dirs",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "100,000" in result.output


def test_batch_chunk_size_without_stream_fails(tmp_path: Path) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1]}), source)
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "csv",
            "--chunk-size",
            "2",
        ],
    )

    assert result.exit_code == 1
    assert "--chunk-size requires --stream" in result.output
    assert not output.exists()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_batch_invalid_chunk_size_fails(tmp_path: Path, value: str) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1]}), source)

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "csv",
            "--stream",
            "--chunk-size",
            value,
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value for '--chunk-size'" in result.output


@pytest.mark.parametrize(
    ("source_extension", "target_format", "expected"),
    [
        (".csv", "parquet", "only CSV, JSONL, and NDJSON"),
        (".json", "jsonl", "JSON array files"),
        (".sav", "csv", "only CSV, JSONL, and NDJSON"),
        (".xlsx", "csv", "only CSV, JSONL, and NDJSON"),
    ],
)
def test_batch_stream_unsupported_item_fails_without_output(
    tmp_path: Path,
    source_extension: str,
    target_format: str,
    expected: str,
) -> None:
    source = tmp_path / "input" / f"records{source_extension}"
    source.parent.mkdir(parents=True)
    if source_extension == ".csv":
        _write_records(pd.DataFrame({"value": [1]}), source)
    elif source_extension == ".json":
        source.write_text('[{"value": 1}]', encoding="utf-8")
    else:
        source.write_bytes(b"placeholder")
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            target_format,
            "--stream",
            "--create-dirs",
            "--no-progress",
        ],
    )

    normalized_output = " ".join(result.output.split())
    assert result.exit_code == 1
    assert expected in normalized_output
    assert "run without --stream" in normalized_output.lower()
    assert not (output / f"records.{target_format}").exists()


@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [
        (
            ["--transform", "--select", "value"],
            "does not support transforms",
        ),
        (["--validate"], "does not support validation"),
        (["--object", "data"], "does not support object selection"),
        (["--write-config", "batch.toml"], "config integration is not available"),
    ],
)
def test_batch_stream_rejects_unimplemented_global_modes(
    tmp_path: Path,
    extra_args: list[str],
    expected: str,
) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1]}), source)
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "csv",
            "--stream",
            *extra_args,
        ],
    )

    assert result.exit_code == 1
    assert expected in result.output
    assert not output.exists()


def test_batch_without_stream_uses_normal_json_array_output(tmp_path: Path) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1, 2]}), source)

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "json",
            "--create-dirs",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "output" / "records.json").exists()
    assert "Streamed rows" not in result.output


def test_batch_stream_preserves_existing_target_until_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "input" / "records.csv"
    _write_records(pd.DataFrame({"value": [1, 2, 3]}), source)
    target = tmp_path / "output" / "records.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("original\n", encoding="utf-8")
    arguments = [
        "batch",
        str(source.parent),
        str(target.parent),
        "--to",
        "jsonl",
        "--stream",
        "--chunk-size",
        "2",
        "--no-progress",
    ]

    blocked = runner.invoke(app, arguments)

    assert blocked.exit_code == 1
    assert "already exists" in blocked.output
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sidecar_path(target).exists()

    replaced = runner.invoke(app, [*arguments, "--overwrite"])

    assert replaced.exit_code == 0, replaced.output
    assert len(pd.read_json(target, lines=True)) == 3
    assert sidecar_path(target).exists()


@pytest.mark.parametrize(
    "command",
    ["report", "transform", "compare", "collect"],
)
def test_batch_streaming_options_do_not_leak_to_other_commands(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--stream" not in result.output
    assert "--chunk-size" not in result.output


def _write_records(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_json(path, orient="records", lines=True)


def _read_records(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_json(path, lines=True)
