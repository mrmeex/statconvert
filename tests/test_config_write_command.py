from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.config import load_config
from statconvert.registry import list_dataset_objects


runner = CliRunner()


def test_convert_write_config_does_not_execute_and_generated_config_runs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config_path = tmp_path / "convert.toml"
    pd.DataFrame({"id": [1, 2]}).to_csv(source, index=False)

    write_result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--write-config", str(config_path)],
    )

    assert write_result.exit_code == 0
    assert "No conversion was run" in write_result.output
    assert config_path.exists()
    assert not output.exists()
    assert load_config(config_path).command == "convert"

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert output.exists()


def test_write_config_collision_requires_explicit_overwrite_config(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config_path = tmp_path / "convert.toml"
    pd.DataFrame({"id": [1]}).to_csv(source, index=False)
    config_path.write_text("existing", encoding="utf-8")

    blocked = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(output),
            "--overwrite",
            "--write-config",
            str(config_path),
        ],
    )

    assert blocked.exit_code == 1
    assert "already exists" in blocked.output
    assert config_path.read_text(encoding="utf-8") == "existing"

    allowed = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(output),
            "--overwrite",
            "--write-config",
            str(config_path),
            "--overwrite-config",
        ],
    )
    assert allowed.exit_code == 0
    assert load_config(config_path).options["overwrite"] is True


def test_write_config_uses_create_dirs_for_config_parent(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config_path = tmp_path / "configs" / "convert.toml"

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(output),
            "--create-dirs",
            "--write-config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert config_path.exists()
    assert not output.exists()


def test_transform_write_config_preserves_pipeline_and_runs(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    config_path = tmp_path / "transform.toml"
    pd.DataFrame({"id": [1, 2], "value": [10, -1]}).to_csv(source, index=False)

    write_result = runner.invoke(
        app,
        [
            "transform",
            str(source),
            str(output),
            "--select",
            "id",
            "--select",
            "value",
            "--rename",
            "value=amount",
            "--filter",
            "amount,gte,0",
            "--write-config",
            str(config_path),
        ],
    )

    assert write_result.exit_code == 0
    assert "No transformation was run" in write_result.output
    assert not output.exists()
    config = load_config(config_path)
    assert [step["type"] for step in config.options["steps"]] == [
        "select",
        "rename",
        "filter",
    ]
    assert config.options["steps"][1]["map"] == {"value": "amount"}

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert pd.read_csv(output).to_dict("list") == {"id": [1], "amount": [10]}


def test_batch_write_config_preserves_options_and_runs(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    nested = source / "nested"
    nested.mkdir(parents=True)
    pd.DataFrame({"id": [1]}).to_csv(nested / "input.csv", index=False)
    output = tmp_path / "converted"
    config_path = tmp_path / "batch.toml"

    write_result = runner.invoke(
        app,
        [
            "batch",
            str(source),
            str(output),
            "--to",
            "csv",
            "--recursive",
            "--workers",
            "2",
            "--create-dirs",
            "--no-progress",
            "--write-config",
            str(config_path),
        ],
    )

    assert write_result.exit_code == 0
    assert "No batch conversion was run" in write_result.output
    assert not output.exists()
    config = load_config(config_path)
    assert config.options["recursive"] is True
    assert config.options["workers"] == 2
    assert config.options["to"] == "csv"

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert (output / "nested" / "input.csv").exists()


def test_batch_write_config_preserves_dry_run_without_outputs(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(source / "input.csv", index=False)
    output = tmp_path / "converted"
    config_path = tmp_path / "batch.toml"

    write_result = runner.invoke(
        app,
        [
            "batch",
            str(source),
            str(output),
            "--to",
            "csv",
            "--dry-run",
            "--create-dirs",
            "--write-config",
            str(config_path),
        ],
    )
    run_result = runner.invoke(app, ["config", "run", str(config_path)])

    assert write_result.exit_code == 0
    assert load_config(config_path).options["dry_run"] is True
    assert run_result.exit_code == 0
    assert not output.exists()


def test_batch_write_config_preserves_transform_options(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    pd.DataFrame({"id": [1], "value": [10]}).to_csv(
        source / "input.csv", index=False
    )
    output = tmp_path / "converted"
    config_path = tmp_path / "batch.toml"

    write_result = runner.invoke(
        app,
        [
            "batch",
            str(source),
            str(output),
            "--to",
            "csv",
            "--transform",
            "--select",
            "id",
            "--create-dirs",
            "--no-progress",
            "--write-config",
            str(config_path),
        ],
    )
    run_result = runner.invoke(app, ["config", "run", str(config_path)])

    assert write_result.exit_code == 0
    assert load_config(config_path).options["select"] == ["id"]
    assert run_result.exit_code == 0
    assert pd.read_csv(output / "input.csv").columns.tolist() == ["id"]


def test_compare_write_config_preserves_options_and_runs(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"id": [1], "value": [10], "ignored": ["a"]}).to_csv(
        left, index=False
    )
    pd.DataFrame({"id": [1], "value": [10], "ignored": ["b"]}).to_csv(
        right, index=False
    )
    report = tmp_path / "comparison.json"
    config_path = tmp_path / "compare.toml"

    write_result = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--key",
            "id",
            "--ignore-columns",
            "ignored",
            "--max-differences",
            "10",
            "--report",
            str(report),
            "--write-config",
            str(config_path),
        ],
    )

    assert write_result.exit_code == 0
    assert "No comparison was run" in write_result.output
    assert not report.exists()
    config = load_config(config_path)
    assert config.options["key"] == ["id"]
    assert config.options["ignore_columns"] == ["ignored"]

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert report.exists()


def test_report_write_config_does_not_generate_report_and_runs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    pd.DataFrame({"id": [1], "value": [10]}).to_csv(source, index=False)
    output = tmp_path / "reports" / "report.html"
    config_path = tmp_path / "configs" / "report.toml"

    write_result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--preset",
            "quick",
            "--create-dirs",
            "--write-config",
            str(config_path),
        ],
    )

    assert write_result.exit_code == 0
    assert "No report was generated" in write_result.output
    assert config_path.exists()
    assert not output.exists()
    assert load_config(config_path).options["preset"] == "quick"

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert output.exists()


def test_collect_write_config_does_not_collect_and_generated_config_runs(
    tmp_path: Path,
) -> None:
    pd.DataFrame({"value": [1]}).to_csv(tmp_path / "data.csv", index=False)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "input_file,output_object\ndata.csv,Data\n",
        encoding="utf-8",
    )
    output = tmp_path / "outputs" / "collected.xlsx"
    config_path = tmp_path / "configs" / "collect.toml"

    write_result = runner.invoke(
        app,
        [
            "collect",
            str(manifest),
            str(output),
            "--base-dir",
            str(tmp_path),
            "--create-dirs",
            "--write-config",
            str(config_path),
        ],
    )

    assert write_result.exit_code == 0
    assert "No collection was run" in write_result.output
    assert config_path.exists()
    assert not output.exists()

    run_result = runner.invoke(app, ["config", "run", str(config_path)])
    assert run_result.exit_code == 0
    assert [item.name for item in list_dataset_objects(output)] == ["Data"]


def test_new_write_config_commands_use_explicit_collision_policy(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"id": [1]}).to_csv(left, index=False)
    pd.DataFrame({"id": [1]}).to_csv(right, index=False)
    config_path = tmp_path / "compare.toml"
    config_path.write_text("existing", encoding="utf-8")

    blocked = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--write-config",
            str(config_path),
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "compare",
            str(left),
            str(right),
            "--write-config",
            str(config_path),
            "--overwrite-config",
        ],
    )

    assert blocked.exit_code == 1
    assert "already exists" in blocked.output
    assert allowed.exit_code == 0
    assert load_config(config_path).command == "compare"
