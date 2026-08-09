from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config.writing import write_config


runner = CliRunner()


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_are_accepted_by_shared_read_workflows(
    tmp_path: Path,
    extension: str,
) -> None:
    source = _write_json_lines(tmp_path / f"input{extension}")
    report = tmp_path / f"report-{extension[1:]}.json"
    commands = [
        ["info", str(source)],
        ["schema", str(source)],
        ["metadata", str(source)],
        ["peek", str(source)],
        ["validate", str(source)],
        ["compare", str(source), str(source)],
        ["report", str(source), "--output", str(report)],
    ]

    for arguments in commands:
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, f"{arguments}: {result.output}"

    assert json.loads(report.read_text(encoding="utf-8"))["report"]["sections"]


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_work_in_normal_batch_both_directions(
    tmp_path: Path,
    extension: str,
) -> None:
    line_input = tmp_path / "line-input"
    line_input.mkdir()
    _write_json_lines(line_input / f"records{extension}")
    csv_output = tmp_path / "csv-output"
    to_csv = runner.invoke(
        app,
        ["batch", str(line_input), str(csv_output), "--to", "csv", "--create-dirs"],
    )

    csv_input = tmp_path / "csv-input"
    csv_input.mkdir()
    pd.DataFrame({"id": [1, 2], "value": ["a", "b"]}).to_csv(
        csv_input / "records.csv",
        index=False,
    )
    line_output = tmp_path / "line-output"
    to_lines = runner.invoke(
        app,
        [
            "batch",
            str(csv_input),
            str(line_output),
            "--to",
            extension[1:],
            "--create-dirs",
        ],
    )

    assert to_csv.exit_code == 0, to_csv.output
    assert pd.read_csv(csv_output / "records.csv")["id"].tolist() == [1, 2]
    assert to_lines.exit_code == 0, to_lines.output
    assert pd.read_json(line_output / f"records{extension}", lines=True)[
        "value"
    ].tolist() == ["a", "b"]


@pytest.mark.parametrize("extension", [".jsonl", ".ndjson"])
def test_json_lines_work_in_convert_config(
    tmp_path: Path,
    extension: str,
) -> None:
    source = _write_json_lines(tmp_path / f"config-input{extension}")
    output = tmp_path / "config-output.csv"
    config = tmp_path / f"convert-{extension[1:]}.toml"
    write_config(
        {"command": "convert", "input": str(source), "output": str(output)},
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0, result.output
    assert pd.read_csv(output).to_dict("list") == {
        "id": [1, 2],
        "value": ["a", "b"],
    }


def _write_json_lines(path: Path) -> Path:
    pd.DataFrame({"id": [1, 2], "value": ["a", "b"]}).to_json(
        path,
        orient="records",
        lines=True,
        force_ascii=False,
    )
    return path
