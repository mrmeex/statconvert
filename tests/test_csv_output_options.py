from __future__ import annotations

import json

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def test_convert_writes_semicolon_delimited_csv(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        ["convert", str(input_file), str(output_file), "--csv-delimiter", ";"],
    )

    assert result.exit_code == 0
    assert output_file.read_text(encoding="utf-8").splitlines()[0] == "value;name"


def test_convert_writes_csv_with_decimal_comma(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        ["convert", str(input_file), str(output_file), "--csv-decimal", ","],
    )

    assert result.exit_code == 0
    assert '"1,5",Ada' in output_file.read_text(encoding="utf-8")


def test_convert_writes_utf8_sig_csv_with_output_encoding(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--output-encoding",
            "utf-8-sig",
        ],
    )

    assert result.exit_code == 0
    assert output_file.read_bytes().startswith(b"\xef\xbb\xbf")


def test_transform_writes_semicolon_delimited_csv(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        ["transform", str(input_file), str(output_file), "--csv-delimiter", ";"],
    )

    assert result.exit_code == 0
    assert output_file.read_text(encoding="utf-8").splitlines()[0] == "value;name"


def test_convert_reads_latin1_semicolon_csv(tmp_path) -> None:
    input_file = _write_latin1_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.xlsx"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--input-encoding",
            "latin1",
            "--csv-delimiter",
            ";",
            "--csv-decimal",
            ",",
        ],
    )

    assert result.exit_code == 0
    assert pd.read_excel(output_file).to_dict(orient="records") == [
        {"value": 1.5, "name": "André"}
    ]


def test_convert_csv_uses_different_input_and_output_encodings(tmp_path) -> None:
    input_file = _write_latin1_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
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

    assert result.exit_code == 0
    assert output_file.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "André" in output_file.read_text(encoding="utf-8-sig")


def test_unsupported_input_encoding_warns_and_continues(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--input-encoding",
            "cp1252",
        ],
    )

    assert result.exit_code == 0
    assert "--input-encoding" in result.output
    assert "xlsx" in result.output
    assert "ignored" in result.output
    assert output_file.exists()


def test_unsupported_output_encoding_warns_and_continues(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.parquet"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--output-encoding",
            "cp1252",
        ],
    )

    assert result.exit_code == 0
    assert "--output-encoding" in result.output
    assert "parquet" in result.output
    assert "ignored" in result.output
    assert output_file.exists()


def test_invalid_supported_input_encoding_fails_cleanly(tmp_path) -> None:
    input_file = _write_latin1_csv(tmp_path / "input.csv")
    output_file = tmp_path / "output.xlsx"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--input-encoding",
            "not-a-real-encoding",
            "--csv-delimiter",
            ";",
        ],
    )

    assert result.exit_code == 1
    assert "unknown encoding" in result.output.lower()
    assert not output_file.exists()


def test_transform_writes_utf8_sig_csv(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        [
            "transform",
            str(input_file),
            str(output_file),
            "--output-encoding",
            "utf-8-sig",
        ],
    )

    assert result.exit_code == 0
    assert output_file.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        (
            "--csv-delimiter",
            "||",
            "Invalid CSV delimiter: delimiter must be exactly one character.",
        ),
        (
            "--csv-decimal",
            "..",
            (
                "Invalid CSV decimal separator: decimal separator must be exactly "
                "one character."
            ),
        ),
    ],
)
def test_convert_rejects_invalid_csv_separator_early(
    tmp_path,
    option,
    value,
    message,
) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        ["convert", str(input_file), str(output_file), option, value],
    )

    assert result.exit_code == 1
    assert message.split(":", maxsplit=1)[0] in result.output
    assert not output_file.exists()


def test_convert_rejects_equal_csv_separators_early(tmp_path) -> None:
    input_file = _write_xlsx(tmp_path / "input.xlsx")
    output_file = tmp_path / "output.csv"

    result = runner.invoke(
        app,
        [
            "convert",
            str(input_file),
            str(output_file),
            "--csv-delimiter",
            ";",
            "--csv-decimal",
            ";",
        ],
    )

    assert result.exit_code == 1
    assert (
        "CSV delimiter and decimal separator cannot be the same character."
        in result.output
    )
    assert not output_file.exists()


def test_batch_writes_csv_with_selected_delimiter_and_decimal(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_xlsx(input_dir / "data.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--csv-delimiter",
            ";",
            "--csv-decimal",
            ",",
                "--json",
                "--create-dirs",
        ],
    )

    output_file = output_dir / "data.csv"
    assert result.exit_code == 0
    assert json.loads(result.output)["items"][0]["status"] == "success"
    assert output_file.read_text(encoding="utf-8").splitlines()[:2] == [
        "value;name",
        "1,5;Ada",
    ]


def test_batch_writes_utf8_sig_csv(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_xlsx(input_dir / "data.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--output-encoding",
            "utf-8-sig",
                "--no-progress",
                "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "data.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_batch_rejects_invalid_delimiter_before_planning(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_xlsx(input_dir / "data.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "csv",
            "--csv-delimiter",
            "||",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Invalid CSV delimiter: delimiter must be exactly one character."
        in result.output
    )
    assert not output_dir.exists()


def test_batch_to_non_csv_ignores_csv_specific_options(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_xlsx(input_dir / "data.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "json",
            "--csv-delimiter",
            ";",
                "--json",
                "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["items"][0]["status"] == "success"
    assert json.loads((output_dir / "data.json").read_text(encoding="utf-8"))


def test_batch_json_keeps_unsupported_encoding_warning_on_stderr(tmp_path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_xlsx(input_dir / "data.xlsx")

    result = runner.invoke(
        app,
        [
            "batch",
            str(input_dir),
            str(output_dir),
            "--to",
            "parquet",
            "--output-encoding",
            "cp1252",
                "--json",
                "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["status"] == "success"
    assert "--output-encoding" in result.stderr
    assert "parquet" in result.stderr
    assert "ignored" in result.stderr


@pytest.mark.parametrize("command", ["convert", "transform", "batch"])
def test_datafile_writing_command_help_includes_csv_options(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--input-encoding" in result.output
    assert "--output-encoding" in result.output
    assert "--csv-delimiter" in result.output
    assert "--csv-decimal" in result.output


@pytest.mark.parametrize(
    "command",
    [
        "peek",
        "info",
        "schema",
        "labels",
        "metadata",
        "summary",
        "describe",
        "frequencies",
        "missing",
        "validate",
        "report",
        "compare",
        "objects",
        "formats",
        "backends",
        "capabilities",
    ],
)
def test_read_only_command_help_excludes_csv_options(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code == 0
    assert "--input-encoding" not in result.output
    assert "--output-encoding" not in result.output
    assert "--csv-delimiter" not in result.output
    assert "--csv-decimal" not in result.output


def _write_xlsx(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "value": [1.5, 2.75],
            "name": ["Ada", "Grace"],
        }
    ).to_excel(path, index=False)
    return path


def _write_latin1_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("value;name\r\n1,5;André\r\n".encode("latin1"))
    return path
