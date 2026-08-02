from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def test_config_help_lists_commands() -> None:
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    assert "init" in result.output
    assert "validate" in result.output
    assert "run" in result.output


def test_config_init_and_validate(tmp_path: Path) -> None:
    path = tmp_path / "batch.toml"

    init_result = runner.invoke(
        app,
        ["config", "init", "batch", "--output", str(path)],
    )
    validate_result = runner.invoke(app, ["config", "validate", str(path)])

    assert init_result.exit_code == 0
    assert "Created batch config" in init_result.output
    assert path.exists()
    assert validate_result.exit_code == 0
    assert "Config is valid for command 'batch'" in validate_result.output


def test_config_init_requires_create_dirs(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "batch.toml"

    result = runner.invoke(
        app,
        ["config", "init", "batch", "--output", str(path)],
    )

    assert result.exit_code == 1
    assert "Use --create-dirs" in result.output


def test_config_init_fails_if_output_exists(tmp_path: Path) -> None:
    path = tmp_path / "batch.toml"
    path.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        ["config", "init", "batch", "--output", str(path)],
    )

    assert result.exit_code == 1
    assert "already exists" in result.output


def test_config_init_overwrite_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "batch.toml"
    path.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "config",
            "init",
            "batch",
            "--output",
            str(path),
            "--overwrite",
        ],
    )

    assert result.exit_code == 0
    assert 'command = "batch"' in path.read_text(encoding="utf-8")


def test_config_validate_invalid_file_is_nonzero(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('command = "batch"\nworkerz = 2\n', encoding="utf-8")

    result = runner.invoke(app, ["config", "validate", str(path)])

    assert result.exit_code == 1
    assert "Config error" in result.output


def test_config_run_dispatches_validated_compare_config(tmp_path: Path) -> None:
    path = tmp_path / "compare.toml"
    init_result = runner.invoke(
        app,
        ["config", "init", "compare", "--output", str(path)],
    )
    assert init_result.exit_code == 0

    result = runner.invoke(app, ["config", "run", str(path)])

    assert result.exit_code == 1
    assert "Unsupported file format" not in result.output
    assert "No such file or directory" in result.output
