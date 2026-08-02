from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import write_config
from statconvert.registry import list_dataset_objects


runner = CliRunner()


def test_config_run_convert_executes_existing_workflow(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    pd.DataFrame({"id": [1, 2], "value": [10, 20]}).to_csv(source, index=False)
    config = tmp_path / "convert.toml"
    write_config(
        {
            "command": "convert",
            "input": str(source),
            "output": str(output),
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert pd.read_csv(output).to_dict("list") == {
        "id": [1, 2],
        "value": [10, 20],
    }


def test_config_run_convert_preserves_csv_options_and_create_dirs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    source.write_text("id;value\n1;1,5\n", encoding="utf-8")
    output = tmp_path / "nested" / "output.csv"
    config = tmp_path / "convert.toml"
    write_config(
        {
            "command": "convert",
            "input": str(source),
            "output": str(output),
            "create_dirs": True,
            "csv_delimiter": ";",
            "csv_decimal": ",",
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert pd.read_csv(output, sep=";", decimal=",")["value"].tolist() == [1.5]


def test_config_run_convert_respects_output_collision(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    pd.DataFrame({"id": [1]}).to_csv(source, index=False)
    output.write_text("existing", encoding="utf-8")
    config = tmp_path / "convert.toml"
    write_config(
        {
            "command": "convert",
            "input": str(source),
            "output": str(output),
            "overwrite": False,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert output.read_text(encoding="utf-8") == "existing"


def test_config_run_transform_applies_existing_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    pd.DataFrame(
        {"id": [1, 2], "value": [10, -1], "unused": ["a", "b"]}
    ).to_csv(source, index=False)
    config = tmp_path / "transform.toml"
    write_config(
        {
            "command": "transform",
            "input": str(source),
            "output": str(output),
            "select": ["id", "value"],
            "rename": {"value": "amount"},
            "filter": ["amount,gte,0"],
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert pd.read_csv(output).to_dict("list") == {"id": [1], "amount": [10]}


def test_config_run_transform_invalid_expression_fails_friendly(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    pd.DataFrame({"id": [1]}).to_csv(source, index=False)
    config = tmp_path / "transform.toml"
    write_config(
        {
            "command": "transform",
            "input": str(source),
            "output": str(output),
            "filter": ["invalid"],
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 1
    assert "Invalid filter" in result.output
    assert not output.exists()


def test_config_run_batch_executes_with_workers_and_recursive(
    tmp_path: Path,
) -> None:
    source = tmp_path / "incoming"
    nested = source / "nested"
    nested.mkdir(parents=True)
    pd.DataFrame({"id": [1]}).to_csv(nested / "input.csv", index=False)
    output = tmp_path / "converted"
    config = tmp_path / "batch.toml"
    write_config(
        {
            "command": "batch",
            "input": str(source),
            "output": str(output),
            "to": "csv",
            "recursive": True,
            "workers": 2,
            "create_dirs": True,
            "no_progress": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert (output / "nested" / "input.csv").exists()
    assert "Workers" in result.output
    assert "2" in result.output


def test_config_run_batch_dry_run_is_read_free_and_writes_no_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(source / "input.csv", index=False)
    output = tmp_path / "converted"
    config = tmp_path / "batch.toml"
    write_config(
        {
            "command": "batch",
            "input": str(source),
            "output": str(output),
            "to": "csv",
            "dry_run": True,
            "create_dirs": True,
        },
        config,
    )

    def fail_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run must not read datasets")

    monkeypatch.setattr("statconvert.registry.read_dataset", fail_read)
    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert "Batch Plan Summary" in result.output
    assert not output.exists()


def test_config_run_batch_json_remains_parseable(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(source / "input.csv", index=False)
    config = tmp_path / "batch.toml"
    write_config(
        {
            "command": "batch",
            "input": str(source),
            "output": str(tmp_path / "converted"),
            "to": "csv",
            "dry_run": True,
            "json": True,
            "create_dirs": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workload"]["workers"] == 1


def test_config_run_batch_execution_json_has_no_human_progress(
    tmp_path: Path,
) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(source / "input.csv", index=False)
    config = tmp_path / "batch.toml"
    write_config(
        {
            "command": "batch",
            "input": str(source),
            "output": str(tmp_path / "converted"),
            "to": "csv",
            "workers": 2,
            "json": True,
            "create_dirs": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["status"] == "success"
    assert payload["workload"]["workers"] == 2
    assert "Batch Workload" not in result.stdout
    assert "Worker 1" not in result.stdout


def test_config_run_batch_uses_live_workload_and_worker_status(
    tmp_path: Path,
) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(source / "one.csv", index=False)
    pd.DataFrame({"id": [2]}).to_csv(source / "two.csv", index=False)
    config = tmp_path / "batch.toml"
    write_config(
        {
            "command": "batch",
            "input": str(source),
            "output": str(tmp_path / "converted"),
            "to": "csv",
            "workers": 2,
            "create_dirs": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert "Batch Workload" in result.output
    assert "Worker 1" in result.output
    assert "Worker 2" in result.output
    assert "Batch Result Summary" in result.output


def test_config_run_compare_supports_key_ignore_and_tolerance(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame(
        {"id": [1, 2], "value": [10.0, 20.0], "exported_at": ["a", "a"]}
    ).to_csv(left, index=False)
    pd.DataFrame(
        {"id": [2, 1], "value": [20.0005, 10.0], "exported_at": ["b", "b"]}
    ).to_csv(right, index=False)
    config = tmp_path / "compare.toml"
    write_config(
        {
            "command": "compare",
            "left": str(left),
            "right": str(right),
            "key": ["id"],
            "ignore_columns": ["exported_at"],
            "numeric_tolerance": 0.001,
            "max_differences": 10,
            "json": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["equal"] is True
    assert payload["options"]["key_columns"] == ["id"]
    assert payload["options"]["ignore_columns"] == ["exported_at"]


def test_config_run_compare_preserves_difference_exit_and_report(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"id": [1], "value": [10]}).to_csv(left, index=False)
    pd.DataFrame({"id": [1], "value": [20]}).to_csv(right, index=False)
    report = tmp_path / "comparison.json"
    config = tmp_path / "compare.toml"
    write_config(
        {
            "command": "compare",
            "left": str(left),
            "right": str(right),
            "key": ["id"],
            "max_differences": 1,
            "report": str(report),
            "report_format": "json",
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 1
    assert report.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["differences"]


def test_config_run_report_writes_preset_with_create_dirs(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [1, 2], "value": [10, 20]}).to_csv(source, index=False)
    output = tmp_path / "reports" / "report.json"
    config = tmp_path / "report.toml"
    write_config(
        {
            "command": "report",
            "input": str(source),
            "output": str(output),
            "preset": "quick",
            "create_dirs": True,
            "quiet": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [section["key"] for section in payload["report"]["sections"]] == [
        "summary",
        "schema",
        "missing",
        "validation",
    ]


def test_config_run_report_respects_output_collision(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "report.html"
    pd.DataFrame({"id": [1]}).to_csv(source, index=False)
    output.write_text("existing", encoding="utf-8")
    config = tmp_path / "report.toml"
    write_config(
        {"command": "report", "input": str(source), "output": str(output)},
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert output.read_text(encoding="utf-8") == "existing"


def test_config_run_collect_writes_manifest_objects(tmp_path: Path) -> None:
    pd.DataFrame({"value": [1, 2]}).to_csv(tmp_path / "one.csv", index=False)
    pd.DataFrame({"value": [3]}).to_csv(tmp_path / "two.csv", index=False)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "input_file,output_object\none.csv,One\ntwo.csv,Two\n",
        encoding="utf-8",
    )
    output = tmp_path / "collected.xlsx"
    config = tmp_path / "collect.toml"
    write_config(
        {
            "command": "collect",
            "manifest": str(manifest),
            "output": str(output),
            "base_dir": str(tmp_path),
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert [item.name for item in list_dataset_objects(output)] == ["One", "Two"]


def test_config_run_collect_dry_run_writes_nothing(tmp_path: Path) -> None:
    pd.DataFrame({"value": [1]}).to_csv(tmp_path / "data.csv", index=False)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("input_file\ndata.csv\n", encoding="utf-8")
    output = tmp_path / "missing" / "collected.xlsx"
    config = tmp_path / "collect.toml"
    write_config(
        {
            "command": "collect",
            "manifest": str(manifest),
            "output": str(output),
            "dry_run": True,
        },
        config,
    )

    result = runner.invoke(app, ["config", "run", str(config)])

    assert result.exit_code == 0
    assert "Planned Object Collection" in result.output
    assert not output.exists()
    assert not output.parent.exists()
