from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

import statconvert.cli as cli_module
from statconvert.cli import app


runner = CliRunner()


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    path.write_text("small,exact,inexact\n1,1.5,0.1\n2,2.0,0.2\n3,3.25,0.3\n", encoding="utf-8")
    return path


def _convert(tmp_path: Path, *options: str):
    source = _source(tmp_path)
    output = tmp_path / "output.parquet"
    result = runner.invoke(app, ["convert", str(source), str(output), *options])
    return result, source, output


def test_convert_supported_policies_write_through_existing_path(tmp_path: Path) -> None:
    for policy in (
        "safe",
        "strict",
        "analysis-ready",
        "preserve-metadata",
        "smallest-types",
    ):
        case = tmp_path / policy
        case.mkdir()
        result, _, output = _convert(case, "--policy", policy)
        assert result.exit_code == 0, result.output
        assert output.exists()
        assert "Transfer Policy Preflight" in result.output


def test_convert_type_plan_is_nonwriting_and_ignores_output_collision(tmp_path: Path) -> None:
    source = _source(tmp_path)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    source_mtime = source.stat().st_mtime_ns
    output = tmp_path / "missing-parent" / "output.parquet"
    existing = tmp_path / "existing.parquet"
    existing.write_bytes(b"unchanged")

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(output),
            "--policy",
            "smallest-types",
            "--type-plan",
        ],
    )
    collision = runner.invoke(
        app,
        [
            "convert",
            str(source),
            str(existing),
            "--policy",
            "safe",
            "--type-plan",
        ],
    )

    assert result.exit_code == 0, result.output
    assert collision.exit_code == 0, collision.output
    assert "Writes: none" in result.output
    assert not output.parent.exists()
    assert existing.read_bytes() == b"unchanged"
    assert not list(tmp_path.rglob("*.statconvert.json"))
    assert not list(tmp_path.rglob("*report*"))
    assert not list(tmp_path.rglob("*config*"))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert source.stat().st_mtime_ns == source_mtime


def test_convert_optimize_types_applies_only_exact_decisions(tmp_path: Path) -> None:
    result, _, output = _convert(
        tmp_path,
        "--policy",
        "smallest-types",
        "--optimize-types",
    )

    written = pd.read_parquet(output)
    assert result.exit_code == 0, result.output
    assert str(written["small"].dtype) == "int8"
    assert str(written["exact"].dtype) == "float32"
    assert str(written["inexact"].dtype) == "float64"
    assert "Exact type decisions applied: 2" in result.output


def test_convert_rejects_invalid_transfer_option_combinations(tmp_path: Path) -> None:
    cases = [
        (["--type-plan"], "--type-plan requires --policy"),
        (["--optimize-types"], "requires --policy smallest-types"),
        (
            ["--policy", "analysis-ready", "--optimize-types"],
            "requires --policy smallest-types",
        ),
        (["--policy", "legacy-compatible"], "not implemented"),
        (["--policy", "unknown"], "Unknown transfer policy"),
        (
            ["--policy", "safe", "--stream"],
            "requires full-dataset planning",
        ),
        (["--policy", "safe", "--all-objects"], "single-dataset conversion"),
    ]
    for index, (options, message) in enumerate(cases):
        case = tmp_path / str(index)
        case.mkdir()
        result, _, output = _convert(case, *options)
        assert result.exit_code == 1
        assert message in result.output
        assert not output.exists()


def test_no_policy_convert_still_uses_legacy_entrypoint(monkeypatch, tmp_path: Path) -> None:
    called = {"legacy": 0, "policy": 0}
    source = _source(tmp_path)
    output = tmp_path / "output.parquet"

    def legacy(**kwargs):
        called["legacy"] += 1
        return cli_module._read_dataset(str(source))

    def policy_path(**kwargs):
        called["policy"] += 1
        raise AssertionError("policy path used")

    monkeypatch.setattr(cli_module, "convert_file", legacy)
    monkeypatch.setattr(cli_module, "transform_with_policy", policy_path)
    result = runner.invoke(app, ["convert", str(source), str(output)])

    assert result.exit_code == 0, result.output
    assert called == {"legacy": 1, "policy": 0}


def test_strict_blocked_plan_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "timezone.parquet"
    pd.DataFrame(
        {"when": pd.date_range("2026-01-01", periods=2, tz="Europe/Amsterdam")}
    ).to_parquet(source, index=False)
    output = tmp_path / "output.xlsx"

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--policy", "strict"],
    )

    assert result.exit_code == 1
    assert "blocked" in result.output.lower()
    assert not output.exists()


def test_policy_conversion_rejects_read_only_target(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "output.zsav"

    result = runner.invoke(
        app,
        ["convert", str(source), str(output), "--policy", "safe"],
    )

    assert result.exit_code == 1
    assert "writing .zsav is not supported" in result.output.lower()
    assert not output.exists()
