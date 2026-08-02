from pathlib import Path

from typer.testing import CliRunner

from statconvert.cli import app


runner = CliRunner()


def _write_csv(path: Path, value: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"name,value\nAlice,{value}\n", encoding="utf-8")
    return path


def test_convert_requires_overwrite_for_existing_output(tmp_path):
    source = _write_csv(tmp_path / "input.csv")
    output = tmp_path / "output.json"
    output.write_text("original", encoding="utf-8")

    blocked = runner.invoke(app, ["convert", str(source), str(output)])
    allowed = runner.invoke(
        app,
        ["convert", str(source), str(output), "--overwrite"],
    )

    assert blocked.exit_code == 1
    assert "Output file already exists" in blocked.output
    assert "--overwrite" in blocked.output
    assert "Traceback" not in blocked.output
    assert allowed.exit_code == 0
    assert output.read_text(encoding="utf-8") != "original"


def test_convert_requires_create_dirs_for_missing_parent(tmp_path):
    source = _write_csv(tmp_path / "input.csv")
    output = tmp_path / "new" / "output.json"

    blocked = runner.invoke(app, ["convert", str(source), str(output)])
    allowed = runner.invoke(
        app,
        ["convert", str(source), str(output), "--create-dirs"],
    )

    assert blocked.exit_code == 1
    assert "Output directory does not exist" in blocked.output
    assert "--create-dirs" in blocked.output
    assert "Traceback" not in blocked.output
    assert allowed.exit_code == 0
    assert output.exists()


def test_convert_existing_source_directory_needs_no_create_dirs(tmp_path):
    source = _write_csv(tmp_path / "input.csv")
    output = tmp_path / "output.json"

    result = runner.invoke(app, ["convert", str(source), str(output)])

    assert result.exit_code == 0
    assert output.exists()


def test_transform_output_policy_and_dry_run_safety(tmp_path):
    source = _write_csv(tmp_path / "input.csv")
    missing_output = tmp_path / "new" / "output.csv"
    dry_run = runner.invoke(
        app,
        ["transform", str(source), str(missing_output), "--dry-run"],
    )
    dry_run_created_directory = (tmp_path / "new").exists()
    blocked = runner.invoke(
        app,
        ["transform", str(source), str(missing_output)],
    )
    created = runner.invoke(
        app,
        ["transform", str(source), str(missing_output), "--create-dirs"],
    )
    original = missing_output.read_bytes()
    existing_dry_run = runner.invoke(
        app,
        ["transform", str(source), str(missing_output), "--dry-run"],
    )
    dry_run_changed_output = missing_output.read_bytes() != original
    overwritten = runner.invoke(
        app,
        ["transform", str(source), str(missing_output), "--overwrite"],
    )

    assert dry_run.exit_code == 0
    assert not dry_run_created_directory
    assert blocked.exit_code == 1
    assert "--create-dirs" in blocked.output
    assert created.exit_code == 0
    assert existing_dry_run.exit_code == 0
    assert not dry_run_changed_output
    assert overwritten.exit_code == 0


def test_batch_root_directory_policy_and_dry_run(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv")
    output_dir = tmp_path / "output"

    blocked = runner.invoke(
        app,
        ["batch", str(input_dir), str(output_dir), "--to", "json"],
    )
    dry_run = runner.invoke(
        app,
        [
            "batch", str(input_dir), str(output_dir), "--to", "json",
            "--create-dirs", "--dry-run",
        ],
    )
    dry_run_created_directory = output_dir.exists()
    created = runner.invoke(
        app,
        [
            "batch", str(input_dir), str(output_dir), "--to", "json",
            "--create-dirs",
        ],
    )

    assert blocked.exit_code == 1
    assert "--create-dirs" in blocked.output
    assert dry_run.exit_code == 0
    assert not dry_run_created_directory
    assert created.exit_code == 0
    assert (output_dir / "one.json").exists()


def test_batch_preserve_structure_creates_generated_subfolders(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "nested" / "one.csv")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "batch", str(input_dir), str(output_dir), "--to", "json",
            "--recursive",
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "nested" / "one.json").exists()


def test_batch_existing_item_requires_overwrite(tmp_path):
    input_dir = tmp_path / "input"
    _write_csv(input_dir / "one.csv", value=2)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output = output_dir / "one.json"
    output.write_text("original", encoding="utf-8")

    blocked = runner.invoke(
        app,
        ["batch", str(input_dir), str(output_dir), "--to", "json"],
    )
    allowed = runner.invoke(
        app,
        [
            "batch", str(input_dir), str(output_dir), "--to", "json",
            "--overwrite",
        ],
    )

    assert blocked.exit_code == 1
    assert "--overwrite" in blocked.output
    assert allowed.exit_code == 0
    assert output.read_text(encoding="utf-8") != "original"


def test_report_output_policy(tmp_path):
    source = _write_csv(tmp_path / "input.csv")
    output = tmp_path / "reports" / "report.html"

    missing = runner.invoke(
        app,
        ["report", str(source), "--output", str(output), "--quiet"],
    )
    created = runner.invoke(
        app,
        [
            "report", str(source), "--output", str(output),
            "--create-dirs", "--quiet",
        ],
    )
    original = output.read_bytes()
    conflict = runner.invoke(
        app,
        ["report", str(source), "--output", str(output), "--quiet"],
    )
    conflict_changed_output = output.read_bytes() != original
    overwritten = runner.invoke(
        app,
        [
            "report", str(source), "--output", str(output),
            "--overwrite", "--quiet",
        ],
    )

    assert missing.exit_code == 1
    assert "--create-dirs" in missing.output
    assert created.exit_code == 0
    assert conflict.exit_code == 1
    assert "--overwrite" in conflict.output
    assert not conflict_changed_output
    assert overwritten.exit_code == 0


def test_output_options_are_limited_to_writing_commands():
    for command in ("convert", "transform", "batch", "report"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "--overwrite" in result.output
        assert "--create-dirs" in result.output

    for command in ("peek", "info", "validate", "compare", "formats"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "--create-dirs" not in result.output
