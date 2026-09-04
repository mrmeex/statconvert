from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.batch import BatchItem, BatchPlan, BatchPlanningOptions, build_batch_plan
from statconvert.batch.reporting import batch_plan_to_dict
from statconvert.cli import app
from statconvert.ui.batch import show_batch_plan


runner = CliRunner()


def _write_csv(path: Path, values: list[int] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"value": values or [1, 2]}).to_csv(path, index=False)
    return path


def _dry_plan(
    input_path: Path,
    output_path: Path,
    *,
    overwrite: bool = False,
    create_dirs: bool = False,
    recursive: bool = False,
    preserve_structure: bool = True,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> BatchPlan:
    return build_batch_plan(
        input_path,
        output_path,
        "json",
        overwrite=overwrite,
        create_dirs=create_dirs,
        recursive=recursive,
        preserve_structure=preserve_structure,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
        mode="dry_run",
        filesystem_preflight=True,
    )


def test_batch_help_exposes_1_5_0c_features_without_batch_type_plan() -> None:
    result = runner.invoke(app, ["batch", "--help"])

    assert result.exit_code == 0
    for implemented_option in (
        "--full-plan",
        "--recipe",
        "--policy",
        "--optimize-types",
    ):
        assert implemented_option in result.output
    assert "--type-plan" not in result.output


def test_dry_run_never_reads_transforms_or_runs_transfer_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_csv(tmp_path / "input/source.csv")
    original = source.read_bytes()

    monkeypatch.setattr(
        "statconvert.registry.read_dataset",
        lambda *args, **kwargs: pytest.fail("dry-run read a dataset"),
    )
    monkeypatch.setattr(
        "statconvert.transformations.pipeline.TransformationPipeline.apply",
        lambda *args, **kwargs: pytest.fail("dry-run applied a transform"),
    )
    monkeypatch.setattr(
        "statconvert.cli.build_transfer_plan",
        lambda *args, **kwargs: pytest.fail("dry-run ran transfer planning"),
    )

    output = tmp_path / "output"
    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            "--transform",
            "--select",
            "missing",
            "--create-dirs",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not output.exists()
    assert source.read_bytes() == original
    assert list(source.parent.iterdir()) == [source]


def test_existing_output_dispositions_follow_overwrite(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/source.csv")
    output = tmp_path / "output/source.json"
    output.parent.mkdir()
    output.write_text("original", encoding="utf-8")

    blocked = _dry_plan(source.parent, output.parent)
    replacing = _dry_plan(source.parent, output.parent, overwrite=True)

    assert blocked.items[0].status == "blocked"
    assert blocked.items[0].reason_code == "OUTPUT_EXISTS"
    assert blocked.items[0].overwrite_disposition == "blocked"
    assert blocked.items[0].existing_output is True
    assert replacing.items[0].status == "pending"
    assert replacing.items[0].overwrite_disposition == "would_replace"
    assert replacing.would_replace_count == 1
    assert output.read_text(encoding="utf-8") == "original"


def test_missing_root_and_generated_subdirectory_dispositions(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    _write_csv(input_root / "nested/source.csv")

    blocked = _dry_plan(
        input_root,
        tmp_path / "missing-output",
        recursive=True,
        create_dirs=False,
    )
    creatable = _dry_plan(
        input_root,
        tmp_path / "creatable-output",
        recursive=True,
        create_dirs=True,
    )
    existing_root = tmp_path / "existing-output"
    existing_root.mkdir()
    nested_blocked = _dry_plan(
        input_root,
        existing_root,
        recursive=True,
        create_dirs=False,
    )

    assert blocked.items[0].status == "blocked"
    assert blocked.items[0].reason_code == "OUTPUT_DIRECTORY_MISSING"
    assert blocked.items[0].directory_disposition == "blocked"
    assert creatable.items[0].status == "pending"
    assert creatable.items[0].directory_disposition == "would_create"
    assert creatable.would_create_directory_count == 1
    assert nested_blocked.items[0].reason_code == "OUTPUT_DIRECTORY_MISSING"
    assert nested_blocked.items[0].directory_disposition == "blocked"
    assert not (tmp_path / "missing-output").exists()
    assert not (tmp_path / "creatable-output").exists()


def test_invalid_output_path_kinds_are_blocked(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/source.csv")
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    output_directory = tmp_path / "explicit.json"
    output_directory.mkdir()

    invalid_parent = _dry_plan(source.parent, parent_file, create_dirs=True)
    invalid_output = _dry_plan(source, output_directory, create_dirs=True)

    assert invalid_parent.items[0].reason_code == "OUTPUT_PARENT_NOT_DIRECTORY"
    assert invalid_parent.items[0].directory_disposition == "blocked"
    assert invalid_output.items[0].reason_code == "OUTPUT_PATH_IS_DIRECTORY"
    assert invalid_output.items[0].overwrite_disposition == "blocked"


def test_duplicate_and_same_path_conflicts_have_stable_flags(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    _write_csv(input_root / "a/source.csv")
    _write_csv(input_root / "b/source.csv")
    output = tmp_path / "output"

    duplicates = _dry_plan(
        input_root,
        output,
        recursive=True,
        preserve_structure=False,
        overwrite=True,
        create_dirs=True,
    )
    same_path_source = _write_csv(tmp_path / "same.json")
    same_path = _dry_plan(same_path_source, same_path_source, overwrite=True)

    assert [item.reason_code for item in duplicates.items] == [
        "DUPLICATE_OUTPUT_PATH",
        "DUPLICATE_OUTPUT_PATH",
    ]
    assert all(item.duplicate_output for item in duplicates.items)
    assert all(item.status == "blocked" for item in duplicates.items)
    assert same_path.items[0].reason_code == "INPUT_OUTPUT_SAME_PATH"
    assert same_path.items[0].same_path is True
    assert same_path.items[0].status == "blocked"


def test_skip_reasons_and_recursive_output_exclusion_are_explicit(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    _write_csv(input_root / "keep.csv")
    _write_csv(input_root / "excluded.csv")
    (input_root / "notes.unknown").write_text("notes", encoding="utf-8")
    output_root = input_root / "generated"
    _write_csv(output_root / "old.csv")

    plan = _dry_plan(
        input_root,
        output_root,
        recursive=True,
        create_dirs=True,
        patterns=["*.csv", "**/*.csv", "*.unknown"],
        exclude_patterns=["excluded.csv"],
    )

    by_name = {item.input_file.name: item for item in plan.items}
    assert by_name["excluded.csv"].reason_code == "EXCLUDED_BY_PATTERN"
    assert by_name["notes.unknown"].reason_code == "UNSUPPORTED_INPUT_FORMAT"
    assert by_name["old.csv"].reason_code == "OUTPUT_TREE_EXCLUDED"
    assert by_name["old.csv"].output_inside_input_excluded is True
    assert by_name["keep.csv"].status == "pending"


def test_include_pattern_non_match_is_retained_as_skipped(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input/source.csv")

    plan = _dry_plan(
        source.parent,
        tmp_path / "output",
        patterns=["*.sav"],
        create_dirs=True,
    )

    assert plan.total_count == 1
    assert plan.items[0].status == "skipped"
    assert plan.items[0].reason_code == "PATTERN_NOT_INCLUDED"


def test_dry_run_json_contract_is_plain_deterministic_and_complete(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    first = _write_csv(input_root / "b.csv", [1])
    second = _write_csv(input_root / "a.csv", [1, 2, 3])
    result = runner.invoke(
        app,
        [
            "batch",
            str(input_root),
            str(tmp_path / "output"),
            "--to",
            "json",
            "--create-dirs",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["phase"] == "filesystem_plan"
    assert payload["mode"] == "dry_run"
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["total_input_bytes"] == (
        first.stat().st_size + second.stat().st_size
    )
    assert payload["summary"]["reason_counts"] == {}
    assert [Path(item["input_file"]).name for item in payload["items"]] == [
        "a.csv",
        "b.csv",
    ]
    assert payload["items"][0]["input_size_bytes"] == second.stat().st_size
    assert payload["items"][0]["directory_disposition"] == "would_create"
    assert payload["items"][0]["sidecar_disposition"] == "potential_path"
    assert payload["truncation"] == {
        "item_limit": None,
        "items_omitted": 0,
        "issues_omitted": 0,
    }
    assert set(payload["checks_not_performed"]) == {
        "schema",
        "transform_recipe_compatibility",
        "transfer_policy_decisions",
        "required_metadata_sidecars",
    }
    assert "[bold]" not in result.output


def test_plan_serializer_reports_explicit_truncation_without_files() -> None:
    options = BatchPlanningOptions(
        input_path=Path("input"),
        output_path=Path("output"),
        target_extension=".json",
        mode="dry_run",
    )
    plan = BatchPlan(
        options=options,
        items=[
            BatchItem(Path(f"input/{index}.csv"), Path(f"output/{index}.json"))
            for index in range(3)
        ],
    )

    payload = batch_plan_to_dict(plan, item_limit=2)

    assert len(payload["items"]) == 2
    assert payload["truncation"] == {
        "item_limit": 2,
        "items_omitted": 1,
        "issues_omitted": 0,
    }


def test_human_plan_detail_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options = BatchPlanningOptions(
        input_path=Path("input"),
        output_path=Path("output"),
        target_extension=".json",
        mode="dry_run",
    )
    plan = BatchPlan(
        options=options,
        items=[
            BatchItem(Path(f"input/{index}.csv"), Path(f"output/{index}.json"))
            for index in range(3)
        ],
    )
    monkeypatch.setattr("statconvert.ui.batch.BATCH_PLAN_DISPLAY_ITEM_LIMIT", 2)

    show_batch_plan(plan)
    output = capsys.readouterr().out

    assert "Plan detail truncated" in output
    assert "1 item(s) omitted" in output
    assert "Not checked" in output


def test_dry_run_summary_counts_statuses_and_reasons(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    _write_csv(input_root / "good.csv")
    _write_csv(input_root / "excluded.csv")
    output_root = tmp_path / "output"
    output_root.mkdir()
    (output_root / "good.json").write_text("existing", encoding="utf-8")

    plan = _dry_plan(
        input_root,
        output_root,
        exclude_patterns=["excluded.csv"],
    )

    assert plan.summary_dict() == {
        "total": 2,
        "pending": 0,
        "skipped": 1,
        "blocked": 1,
        "would_replace": 0,
        "would_create_directories": 0,
        "path_conflicts": 1,
        "reason_counts": {"EXCLUDED_BY_PATTERN": 1, "OUTPUT_EXISTS": 1},
        "total_input_bytes": sum(path.stat().st_size for path in input_root.iterdir()),
    }
