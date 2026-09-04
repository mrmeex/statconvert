from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.batch import (
    BATCH_REPORT_ITEM_LIMIT,
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_PENDING,
    REPORT_COLUMNS,
    BatchDiagnostic,
    BatchError,
    BatchItem,
    BatchPlan,
    BatchPlanningOptions,
    infer_report_format,
    validate_batch_report_path,
    write_batch_plan_report,
)
from statconvert.cli import app


runner = CliRunner()


def test_html_and_htm_report_formats_are_supported(tmp_path: Path) -> None:
    assert infer_report_format(tmp_path / "report.HTML") == "html"
    assert infer_report_format(tmp_path / "report.htm") == "html"


def test_report_parent_requires_create_dirs(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    report = tmp_path / "missing" / "report.json"

    with pytest.raises(BatchError, match="directory does not exist"):
        write_batch_plan_report(plan, report)

    assert not report.parent.exists()
    write_batch_plan_report(plan, report, create_dirs=True)
    assert report.exists()


def test_report_parent_path_as_file_is_blocked(tmp_path: Path) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("sentinel", encoding="utf-8")

    with pytest.raises(BatchError, match="parent is not a directory"):
        write_batch_plan_report(_plan(tmp_path), parent / "report.json")


def test_existing_report_requires_overwrite_and_replaces_atomically(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"
    report.write_text("sentinel", encoding="utf-8")

    with pytest.raises(BatchError, match="already exists"):
        write_batch_plan_report(_plan(tmp_path), report)
    assert report.read_text(encoding="utf-8") == "sentinel"

    write_batch_plan_report(_plan(tmp_path), report, overwrite=True)
    assert json.loads(report.read_text(encoding="utf-8"))["type"] == "plan"
    assert not list(tmp_path.glob(".report.json.*.tmp"))


@pytest.mark.parametrize("conflict", ["source", "output", "sidecar"])
def test_report_path_conflicts_are_blocked(tmp_path: Path, conflict: str) -> None:
    item = _item(tmp_path)
    item.potential_sidecar_path = tmp_path / "output" / "one.json.statconvert.json"
    candidates = {
        "source": item.input_file,
        "output": item.output_file,
        "sidecar": item.potential_sidecar_path,
    }
    plan = _plan(tmp_path, [item])

    with pytest.raises(
        BatchError, match="selected source|primary output|metadata sidecar"
    ):
        validate_batch_report_path(
            plan,
            candidates[conflict],
            report_format="json",
            create_dirs=True,
        )


def test_html_report_is_escaped_phase_aware_and_has_advanced_summaries(
    tmp_path: Path,
) -> None:
    item = _item(tmp_path, name="unsafe<&.csv")
    options = _options(tmp_path)
    options.phase = "full_plan"
    options.mode = "full_plan"
    options.recipe_path = tmp_path / "clean.toml"
    options.policy = "smallest-types"
    options.optimize_types = True
    plan = BatchPlan(options=options, items=[item])
    item.status = BATCH_STATUS_BLOCKED
    item.reason_code = "RECIPE<&BLOCKED"
    item.reason = "unsafe <message> & value"
    item.recipe.requested = True
    item.recipe.recipe_name = "Clean <recipe>"
    item.recipe.compatibility_status = "blocked"
    item.recipe.error_count = 1
    item.recipe.diagnostics = [BatchDiagnostic("R<&", "diagnostic <unsafe>", "error")]
    item.policy.requested = True
    item.policy.policy_name = "smallest-types"
    item.policy.status = "warnings"
    item.policy.decision_counts = {"keep": 1}
    item.policy.issue_counts = {"warning": 1}
    item.policy.optimization_requested = True
    item.policy.applied_count = 1
    report = tmp_path / "report.html"

    write_batch_plan_report(plan, report)

    html = report.read_text(encoding="utf-8")
    assert "StatConvert batch report" in html
    assert "Full-plan read pending datasets" in html
    assert "Recipe summary" in html
    assert "Policy summary" in html
    assert "Optimization summary" in html
    assert "Bounded diagnostics" in html
    assert "unsafe &lt;message&gt; &amp; value" in html
    assert "unsafe <message>" not in html
    assert "diagnostic &lt;unsafe&gt;" in html
    assert "row-level source data" in html


def test_filesystem_plan_html_explains_not_checked_areas(tmp_path: Path) -> None:
    options = _options(tmp_path)
    options.mode = "dry_run"
    report = tmp_path / "dry-run.html"

    write_batch_plan_report(BatchPlan(options=options, items=[_item(tmp_path)]), report)

    html = report.read_text(encoding="utf-8")
    assert "did not read datasets" in html
    assert "recipe compatibility" in html
    assert "transfer-policy decisions" in html


def test_json_report_keeps_nested_fields_and_caps_item_details(tmp_path: Path) -> None:
    items = [
        _item(tmp_path, name=f"item-{index}.csv")
        for index in range(BATCH_REPORT_ITEM_LIMIT + 1)
    ]
    items[-1].recipe.diagnostics = [BatchDiagnostic("LAST", "omitted", "error")]
    report = tmp_path / "report.json"

    write_batch_plan_report(_plan(tmp_path, items), report)

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == BATCH_REPORT_ITEM_LIMIT + 1
    assert len(payload["items"]) == BATCH_REPORT_ITEM_LIMIT
    assert payload["truncation"]["items_omitted"] == 1
    assert payload["truncation"]["issues_omitted"] == 1
    assert isinstance(payload["items"][0]["recipe"], dict)
    assert isinstance(payload["items"][0]["policy"], dict)


def test_csv_contract_is_flat_stable_and_has_complete_counts(tmp_path: Path) -> None:
    item = _item(tmp_path)
    item.recipe.requested = True
    item.recipe.recipe_name = "clean"
    item.policy.requested = True
    item.policy.policy_name = "safe"
    item.policy.decision_counts = {"keep": 2}
    item.policy.issue_counts = {"warning": 1}
    item.policy.issue_code_counts = {"POLICY_WARNING": 1}
    report = tmp_path / "report.csv"

    write_batch_plan_report(_plan(tmp_path, [item]), report)

    with report.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        row = next(reader)
    assert tuple(reader.fieldnames or ()) == REPORT_COLUMNS
    assert row["phase"] == "filesystem_plan"
    assert row["recipe_requested"] == "True"
    assert row["policy_name"] == "safe"
    assert row["policy_decision_count"] == "2"
    assert row["optimization_requested"] == "False"
    assert row["report_total_items"] == "1"
    assert "recipe" not in reader.fieldnames
    assert "policy" not in reader.fieldnames


def test_cli_preflights_report_before_execution(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output = tmp_path / "output"
    report = tmp_path / "missing" / "result.html"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert "Use --create-dirs" in result.output
    assert not output.exists()
    assert not report.exists()


def test_cli_dry_run_without_report_writes_nothing(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            "--dry-run",
            "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert not output.exists()
    assert {path.name for path in tmp_path.iterdir()} == {"input"}


def test_cli_dry_run_writes_explicit_html_report_only(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output = tmp_path / "output"
    report = tmp_path / "reports" / "dry-run.html"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            "--dry-run",
            "--report",
            str(report),
            "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert report.exists()
    assert "did not read datasets" in report.read_text(encoding="utf-8")
    assert not output.exists()


@pytest.mark.parametrize("advanced", ["recipe", "policy"])
def test_cli_full_plan_writes_phase_aware_html_without_data_outputs(
    tmp_path: Path, advanced: str
) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output = tmp_path / "output"
    report = tmp_path / f"{advanced}.html"
    options: list[str]
    if advanced == "recipe":
        recipe = tmp_path / "clean.toml"
        recipe.write_text(
            'version = 1\nname = "Clean"\n\n[[steps]]\n'
            'type = "select"\ncolumns = ["id"]\n',
            encoding="utf-8",
        )
        options = ["--recipe", str(recipe)]
    else:
        options = ["--policy", "safe"]

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            *options,
            "--full-plan",
            "--report",
            str(report),
            "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    html = report.read_text(encoding="utf-8")
    assert f"{advanced.title()} summary" in html
    assert "Full-plan read pending datasets" in html
    assert not output.exists()


def test_cli_execution_writes_html_report(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output = tmp_path / "output"
    report = tmp_path / "execution.html"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "json",
            "--report",
            str(report),
            "--create-dirs",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert (output / "one.json").exists()
    assert "execution" in report.read_text(encoding="utf-8")


def test_cli_report_collision_with_primary_output_blocks_before_execution(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "input" / "one.csv")
    output_file = tmp_path / "one.json"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source),
            str(output_file),
            "--to",
            "json",
            "--report",
            str(output_file),
            "--report-format",
            "html",
        ],
    )

    assert result.exit_code == 1
    assert "planned primary output" in result.output
    assert not output_file.exists()


def test_cli_report_order_is_stable_across_worker_counts(tmp_path: Path) -> None:
    source_dir = tmp_path / "input"
    for name in ("c.csv", "a.csv", "b.csv"):
        _write_csv(source_dir / name)
    report_one = tmp_path / "one.csv"
    report_many = tmp_path / "many.csv"

    for workers, report in ((1, report_one), (3, report_many)):
        result = runner.invoke(
            app,
            [
                "batch",
                str(source_dir),
                str(tmp_path / f"output-{workers}"),
                "--to",
                "json",
                "--dry-run",
                "--workers",
                str(workers),
                "--report",
                str(report),
                "--create-dirs",
            ],
        )
        assert result.exit_code == 0

    def input_names(path: Path) -> list[str]:
        with path.open(encoding="utf-8", newline="") as source:
            return [Path(row["input_file"]).name for row in csv.DictReader(source)]

    assert (
        input_names(report_one)
        == input_names(report_many)
        == ["a.csv", "b.csv", "c.csv"]
    )


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": [1, 2]}).to_csv(path, index=False)
    return path


def _item(tmp_path: Path, *, name: str = "one.csv") -> BatchItem:
    return BatchItem(
        input_file=tmp_path / "input" / name,
        output_file=tmp_path / "output" / f"{Path(name).stem}.json",
        relative_path=Path(name),
        input_extension=".csv",
        output_extension=".json",
        status=BATCH_STATUS_PENDING,
    )


def _options(tmp_path: Path) -> BatchPlanningOptions:
    return BatchPlanningOptions(
        input_path=tmp_path / "input",
        output_path=tmp_path / "output",
        target_extension=".json",
    )


def _plan(tmp_path: Path, items: list[BatchItem] | None = None) -> BatchPlan:
    return BatchPlan(options=_options(tmp_path), items=items or [_item(tmp_path)])
