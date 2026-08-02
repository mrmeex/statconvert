from __future__ import annotations

from datetime import datetime
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest
from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.cli import app
from statconvert.serialization import make_json_safe
from statconvert.ui.output import to_json_text


runner = CliRunner()
RICH_LIKE_VALUES = [
    "[red]secret[/red]",
    "[bold]important[/bold]",
    "[not-a-real-tag]",
    "ANSI \x1b[31mred\x1b[0m",
    "Unicode é Ö 中文 🧪",
]


def test_to_json_text_preserves_literal_strings_and_common_scalars() -> None:
    timestamp = datetime(2026, 7, 13, 12, 30)
    text = to_json_text(
        {
            "values": RICH_LIKE_VALUES,
            "path": Path("a/b"),
            "timestamp": timestamp,
            "missing": float("nan"),
        }
    )

    payload = json.loads(text)
    assert payload["values"] == RICH_LIKE_VALUES
    assert payload["path"] == str(Path("a/b"))
    assert payload["timestamp"] == timestamp.isoformat()
    assert payload["missing"] is None
    assert "Unicode é Ö 中文 🧪" in text


def test_emit_json_uses_utf8_when_stdout_starts_with_legacy_encoding() -> None:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from statconvert.ui.output import emit_json; "
                "emit_json({'x': 'Unicode é Ö 中文 🧪'})"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=False,
        capture_output=True,
    )

    output = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert json.loads(output)["x"] == "Unicode é Ö 中文 🧪"


def test_make_json_safe_normalizes_scalar_keys_and_missing_values() -> None:
    payload = make_json_safe(
        {
            pd.Timestamp("2026-07-13"): pd.NaT,
            pd.NA: float("nan"),
        }
    )

    assert payload == {"2026-07-13T00:00:00": None, "null": None}


def test_frequencies_json_preserves_rich_like_values_and_unicode(tmp_path: Path) -> None:
    input_file = _write_rich_values_csv(tmp_path / "rich-values.csv")

    result = runner.invoke(
        app,
        ["frequencies", str(input_file), "--columns", "text", "--json"],
    )

    payload = json.loads(result.output)
    emitted_values = [item["value"] for item in payload[0]["items"]]
    assert result.exit_code == 0
    assert set(emitted_values) == set(RICH_LIKE_VALUES)
    assert "[red]secret[/red]" in result.output
    assert "[bold]important[/bold]" in result.output
    assert "Unicode é Ö 中文 🧪" in result.output


def test_frequencies_json_with_logging_stays_clean(tmp_path: Path) -> None:
    input_file = _write_rich_values_csv(tmp_path / "rich-values.csv")
    log_file = tmp_path / "frequencies-json.log"

    result = runner.invoke(
        app,
        [
            "frequencies",
            str(input_file),
            "--columns",
            "text",
            "--json",
            "--log",
            str(log_file),
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload[0]["items"][0]["value"] in RICH_LIKE_VALUES
    assert "Command started" not in result.output
    assert log_file.exists()
    assert "Frequency result:" in log_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("command", "extra_arguments", "expected_type"),
    [
        ("summary", [], dict),
        ("describe", ["--columns", "text"], list),
        ("missing", [], list),
        ("validate", [], list),
    ],
)
def test_inspection_json_commands_emit_valid_plain_json(
    tmp_path: Path,
    command: str,
    extra_arguments: list[str],
    expected_type: type[object],
) -> None:
    input_file = _write_rich_values_csv(tmp_path / f"{command}.csv")

    result = runner.invoke(
        app,
        [command, str(input_file), *extra_arguments, "--json"],
    )

    assert result.exit_code == 0
    assert isinstance(json.loads(result.output), expected_type)


def test_compare_and_report_json_stdout_remain_valid(tmp_path: Path) -> None:
    input_file = _write_rich_values_csv(tmp_path / "left.csv")
    right_file = _write_rich_values_csv(tmp_path / "right.csv")
    report_file = tmp_path / "report.html"

    compare_result = runner.invoke(
        app,
        ["compare", str(input_file), str(right_file), "--json"],
    )
    report_result = runner.invoke(
        app,
        [
            "report",
            str(input_file),
            "--output",
            str(report_file),
            "--json",
        ],
    )

    assert compare_result.exit_code == 0
    assert json.loads(compare_result.output)["values"]["same_values"] is True
    assert report_result.exit_code == 0
    assert json.loads(report_result.output)["format"] == "html"
    assert report_file.exists()


def test_cli_has_no_direct_json_dumps_or_rich_json_printing() -> None:
    source = inspect.getsource(cli_module)

    assert "json.dumps" not in source
    assert "console.print(json.dumps" not in source


def _write_rich_values_csv(path: Path) -> Path:
    pd.DataFrame(
        {
            "id": range(1, len(RICH_LIKE_VALUES) + 1),
            "text": RICH_LIKE_VALUES,
            "value": [10, 20, 30, 40, 50],
        }
    ).to_csv(path, index=False)
    return path
