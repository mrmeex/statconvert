from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.batch import build_batch_plan, execute_batch_plan
from statconvert.dataset import Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.registry import read_dataset, write_dataset


runner = CliRunner()


def _write_csv(path: Path, text: str = "id,name\n1,Ada\n2,Lin\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_recipe(path: Path) -> Path:
    path.write_text(
        'version = 1\nname = "Select ID"\n\n[[steps]]\n'
        'type = "select"\ncolumns = ["id"]\n',
        encoding="utf-8",
    )
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _invoke_json(*arguments: str):
    result = runner.invoke(app, ["batch", *arguments, "--json"])
    payload = json.loads(result.stdout)
    return result, payload


def test_recipe_dry_run_parses_once_without_reading_or_writing(tmp_path, monkeypatch):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()
    import statconvert.cli as cli

    original_parse = cli.parse_portable_recipe
    calls = 0

    def parse_once(path):
        nonlocal calls
        calls += 1
        return original_parse(path)

    monkeypatch.setattr(cli, "parse_portable_recipe", parse_once)
    monkeypatch.setattr(
        "statconvert.registry.read_dataset",
        lambda *args, **kwargs: pytest.fail("ordinary dry-run read a dataset"),
    )

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--dry-run",
    )

    assert result.exit_code == 0
    assert calls == 1
    assert list(output.iterdir()) == []
    item = payload["items"][0]
    assert item["read_state"] == "not_checked"
    assert item["recipe"]["syntax_status"] == "ready"
    assert item["recipe"]["compatibility_status"] == "not_checked"
    assert item["recipe"]["execution_status"] == "not_checked"


def test_recipe_full_plan_blocks_only_incompatible_item_and_writes_nothing(tmp_path):
    _write_csv(tmp_path / "input" / "good.csv")
    _write_csv(tmp_path / "input" / "bad.csv", "other\n1\n")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()

    result, payload = _invoke_json(
        str(tmp_path / "input"),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--full-plan",
    )

    assert result.exit_code == 1
    assert payload["phase"] == "full_plan"
    assert [item["status"] for item in payload["items"]] == ["blocked", "pending"]
    bad, good = payload["items"]
    assert bad["reason_code"] == "RECIPE_COMPATIBILITY_BLOCKED"
    assert bad["recipe"]["compatibility_status"] == "blocked"
    assert good["recipe"]["compatibility_status"] == "ready"
    assert good["recipe"]["execution_status"] == "simulated"
    assert good["rows_before"] == 2
    assert good["columns_before"] == 2
    assert good["columns_after"] == 1
    assert list(output.iterdir()) == []


def test_recipe_execution_continues_after_incompatible_item_and_preserves_sources(
    tmp_path,
):
    good = _write_csv(tmp_path / "input" / "good.csv")
    bad = _write_csv(tmp_path / "input" / "bad.csv", "other\n1\n")
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (good, bad)
    }
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"

    result, payload = _invoke_json(
        str(tmp_path / "input"),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--create-dirs",
    )

    assert result.exit_code == 1
    assert [item["status"] for item in payload["items"]] == ["failed", "success"]
    assert payload["items"][0]["reason_code"] == "RECIPE_COMPATIBILITY_BLOCKED"
    assert read_dataset(output / "good.parquet").columns == ["id"]
    assert not (output / "bad.parquet").exists()
    for path, expected in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == expected


def test_policy_full_plan_and_execution_use_structured_existing_plan(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    output = tmp_path / "output"
    output.mkdir()

    planned, plan_payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--policy",
        "safe",
        "--full-plan",
    )
    assert list(output.iterdir()) == []
    executed, result_payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--policy",
        "safe",
    )

    assert planned.exit_code == 0
    plan_item = plan_payload["items"][0]
    assert plan_item["read_state"] == "ready"
    assert plan_item["policy"]["policy_name"] == "safe"
    assert plan_item["policy"]["status"] in {"ready", "warnings"}
    assert sum(plan_item["policy"]["decision_counts"].values()) == 2
    assert (output / "data.parquet").exists()
    assert executed.exit_code == 0
    assert result_payload["items"][0]["policy"]["status"] in {"ready", "warnings"}


def test_recipe_runs_before_policy_in_full_plan(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--policy",
        "smallest-types",
        "--full-plan",
    )

    assert result.exit_code == 0
    item = payload["items"][0]
    assert item["columns_before"] == 2
    assert item["columns_after"] == 1
    assert sum(item["policy"]["decision_counts"].values()) == 1


def test_smallest_types_optimization_applies_exact_decisions_only(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    output = tmp_path / "output"

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--policy",
        "smallest-types",
        "--optimize-types",
        "--create-dirs",
    )

    assert result.exit_code == 0
    item = payload["items"][0]
    assert item["policy"]["optimization_requested"] is True
    assert item["policy"]["applied_count"] >= 1
    converted = read_dataset(output / "data.parquet")
    assert pd.api.types.is_integer_dtype(converted.dataframe["id"].dtype)
    assert source.read_text(encoding="utf-8") == "id,name\n1,Ada\n2,Lin\n"


@pytest.mark.parametrize("policy", ["analysis-ready", "smallest-types"])
def test_plan_only_policies_do_not_apply_recommendations(tmp_path, policy):
    source = _write_csv(tmp_path / "input" / "data.csv")
    output = tmp_path / "output"

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--policy",
        policy,
        "--create-dirs",
    )

    assert result.exit_code == 0
    assert payload["items"][0]["policy"]["applied_count"] == 0
    assert str(read_dataset(output / "data.parquet").dataframe["id"].dtype) == "int64"


def test_policy_blocker_fails_only_that_item_and_warnings_allow_write(tmp_path):
    _write_json(tmp_path / "input" / "bad.json", [{"mixed": 1}, {"mixed": "a"}])
    _write_json(tmp_path / "input" / "good.json", [{"mixed": 1}, {"mixed": 2}])
    strict_output = tmp_path / "strict-output"

    planned, planned_payload = _invoke_json(
        str(tmp_path / "input"),
        str(tmp_path / "planned-output"),
        "--to",
        "csv",
        "--policy",
        "strict",
        "--full-plan",
        "--create-dirs",
    )
    assert planned.exit_code == 1
    assert [item["status"] for item in planned_payload["items"]] == [
        "blocked",
        "pending",
    ]
    assert planned_payload["items"][0]["policy"]["status"] == "blocked"
    assert not (tmp_path / "planned-output").exists()

    strict, strict_payload = _invoke_json(
        str(tmp_path / "input"),
        str(strict_output),
        "--to",
        "csv",
        "--policy",
        "strict",
        "--create-dirs",
    )

    assert strict.exit_code == 1
    by_name = {Path(item["input_file"]).name: item for item in strict_payload["items"]}
    assert by_name["bad.json"]["status"] == "failed"
    assert by_name["bad.json"]["reason_code"] == "TRANSFER_POLICY_BLOCKED"
    assert by_name["bad.json"]["policy"]["status"] == "blocked"
    assert by_name["good.json"]["status"] == "success"
    assert (strict_output / "good.csv").exists()
    assert not (strict_output / "bad.csv").exists()

    warning_output = tmp_path / "warning-output"
    warning, warning_payload = _invoke_json(
        str(tmp_path / "input" / "bad.json"),
        str(warning_output / "bad.csv"),
        "--to",
        "csv",
        "--policy",
        "safe",
        "--create-dirs",
    )
    assert warning.exit_code == 0
    assert warning_payload["items"][0]["policy"]["status"] == "warnings"
    assert (warning_output / "bad.csv").exists()


def test_recipe_then_policy_optimization_executes_on_post_recipe_copy(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--policy",
        "smallest-types",
        "--optimize-types",
        "--create-dirs",
    )

    assert result.exit_code == 0
    item = payload["items"][0]
    assert item["recipe"]["execution_status"] == "success"
    assert item["policy"]["applied_count"] == 1
    converted = read_dataset(output / "data.parquet")
    assert converted.columns == ["id"]
    assert str(converted.dataframe["id"].dtype) == "int8"
    assert source.read_text(encoding="utf-8") == "id,name\n1,Ada\n2,Lin\n"


def test_recipe_fail_fast_preserves_existing_meaning(tmp_path):
    _write_csv(tmp_path / "input" / "bad.csv", "other\n1\n")
    _write_csv(tmp_path / "input" / "good.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")

    result, payload = _invoke_json(
        str(tmp_path / "input"),
        str(tmp_path / "output"),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--create-dirs",
        "--fail-fast",
    )

    assert result.exit_code == 1
    assert [item["status"] for item in payload["items"]] == ["failed", "skipped"]
    assert payload["items"][1]["reason"] == "Not processed due to fail-fast"


def test_full_plan_is_deterministic_across_worker_counts(tmp_path):
    _write_csv(tmp_path / "input" / "b.csv")
    _write_csv(tmp_path / "input" / "a.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()
    base = [
        str(tmp_path / "input"),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--policy",
        "smallest-types",
        "--full-plan",
    ]

    one, one_payload = _invoke_json(*base, "--workers", "1")
    many, many_payload = _invoke_json(*base, "--workers", "3")

    assert one.exit_code == many.exit_code == 0
    one_payload["options"]["workers"] = 0
    many_payload["options"]["workers"] = 0
    one_payload["workload"]["workers"] = 0
    many_payload["workload"]["workers"] = 0
    one_payload["workload"]["memory_note"] = None
    many_payload["workload"]["memory_note"] = None
    assert one_payload == many_payload


@pytest.mark.parametrize("mode", ["recipe", "policy"])
def test_execution_order_and_outcomes_are_stable_across_workers(tmp_path, mode):
    _write_json(tmp_path / "input" / "bad.json", [{"mixed": 1}, {"mixed": "a"}])
    _write_json(tmp_path / "input" / "good.json", [{"mixed": 1}, {"mixed": 2}])
    recipe = tmp_path / "recipe.toml"
    recipe.write_text(
        'version = 1\n[[steps]]\ntype = "select"\ncolumns = ["missing"]\n',
        encoding="utf-8",
    )
    option = ["--recipe", str(recipe)] if mode == "recipe" else ["--policy", "strict"]

    payloads = []
    for workers in (1, 3):
        result, payload = _invoke_json(
            str(tmp_path / "input"),
            str(tmp_path / f"output-{workers}"),
            "--to",
            "csv",
            *option,
            "--create-dirs",
            "--workers",
            str(workers),
        )
        assert result.exit_code == 1
        payloads.append(
            [
                (
                    Path(item["input_file"]).name,
                    item["status"],
                    item["reason_code"],
                    item["recipe"]["compatibility_status"],
                    item["policy"]["status"],
                    [entry["code"] for entry in item["recipe"]["diagnostics"]],
                    [entry["code"] for entry in item["policy"]["diagnostics"]],
                )
                for item in payload["items"]
            ]
        )

    assert payloads[0] == payloads[1]


def test_full_plan_create_dirs_is_advisory_and_source_is_immutable(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "missing" / "nested"

    result, payload = _invoke_json(
        str(source.parent),
        str(output),
        "--to",
        "parquet",
        "--recipe",
        str(recipe),
        "--full-plan",
        "--create-dirs",
    )

    assert result.exit_code == 0
    assert payload["items"][0]["directory_disposition"] == "would_create"
    assert not output.exists()
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_policy_full_plan_blocks_existing_required_sidecar(tmp_path):
    metadata = DatasetMetadata(dataset_label="Survey")
    metadata.add_variable(VariableMetadata(name="id", label="Identifier"))
    source = tmp_path / "input" / "data.csv"
    source.parent.mkdir()
    write_dataset(
        Dataset(
            dataframe=pd.DataFrame({"id": [1, 2]}),
            normalized_metadata=metadata,
        ),
        source,
    )
    output = tmp_path / "output"
    output.mkdir()
    sidecar = output / "data.csv.statconvert-metadata.json"
    sidecar.write_text("existing", encoding="utf-8")

    result, payload = _invoke_json(
        str(source),
        str(output / "data.csv"),
        "--to",
        "csv",
        "--policy",
        "preserve-metadata",
        "--full-plan",
    )

    item = payload["items"][0]
    assert item["sidecar_disposition"] == "required"
    assert result.exit_code == 1
    assert item["reason_code"] == "SIDECAR_OUTPUT_EXISTS"
    executed, execution_payload = _invoke_json(
        str(source),
        str(output / "data.csv"),
        "--to",
        "csv",
        "--policy",
        "preserve-metadata",
    )
    assert executed.exit_code == 1
    assert execution_payload["items"][0]["reason_code"] == "SIDECAR_OUTPUT_EXISTS"
    assert not (output / "data.csv").exists()
    assert sidecar.read_text(encoding="utf-8") == "existing"


def test_recipe_full_plan_blocks_existing_automatic_sidecar(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output" / "data.json"
    output.parent.mkdir()
    sidecar = Path(f"{output}.statconvert-metadata.json")
    sidecar.write_text("existing", encoding="utf-8")

    result, payload = _invoke_json(
        str(source),
        str(output),
        "--to",
        "json",
        "--recipe",
        str(recipe),
        "--full-plan",
    )

    item = payload["items"][0]
    assert result.exit_code == 1
    assert item["sidecar_disposition"] == "potential_path"
    assert item["reason_code"] == "SIDECAR_OUTPUT_EXISTS"
    assert not output.exists()
    assert sidecar.read_text(encoding="utf-8") == "existing"


def test_policy_json_bounds_diagnostics_but_keeps_complete_counts(tmp_path):
    columns = {f"mixed_{index}": 1 for index in range(105)}
    second = {name: "text" for name in columns}
    source = _write_json(tmp_path / "input.json", [columns, second])
    output = tmp_path / "output"
    output.mkdir()

    result, payload = _invoke_json(
        str(source),
        str(output / "data.csv"),
        "--to",
        "csv",
        "--policy",
        "safe",
        "--full-plan",
    )

    assert result.exit_code == 0
    policy = payload["items"][0]["policy"]
    assert len(policy["diagnostics"]) == 100
    assert policy["diagnostics_omitted"] > 0
    assert policy["issue_code_counts"]["TYPE_MIXED_OBJECT_UNSAFE"] == 105
    assert payload["truncation"]["issues_omitted"] == policy["diagnostics_omitted"]
    assert "[bold]" not in result.stdout
    assert not (output / "data.csv").exists()


def test_full_plan_report_is_the_only_explicit_write(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()
    report = tmp_path / "reports" / "plan.json"

    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(output),
            "--to",
            "parquet",
            "--recipe",
            str(recipe),
            "--full-plan",
            "--report",
            str(report),
            "--json",
            "--create-dirs",
        ],
    )

    assert result.exit_code == 0
    assert list(output.iterdir()) == []
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert report_payload["phase"] == "full_plan"
    assert report_payload["items"][0]["recipe"]["compatibility_status"] == "ready"


def test_full_plan_read_and_policy_failures_have_correct_subsystems(
    tmp_path, monkeypatch
):
    source = _write_csv(tmp_path / "input" / "data.csv")
    output = tmp_path / "output"
    output.mkdir()

    monkeypatch.setattr(
        "statconvert.registry.read_dataset",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read unavailable")),
    )
    read_result, read_payload = _invoke_json(
        str(source),
        str(output / "data.csv"),
        "--to",
        "csv",
        "--policy",
        "safe",
        "--full-plan",
    )
    assert read_result.exit_code == 1
    assert read_payload["items"][0]["reason_code"] == "INPUT_READ_FAILED"
    assert read_payload["items"][0]["subsystem"] == "read"

    monkeypatch.undo()
    monkeypatch.setattr(
        "statconvert.batch.integration.build_transfer_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("planner unavailable")
        ),
    )
    policy_result, policy_payload = _invoke_json(
        str(source),
        str(output / "data.csv"),
        "--to",
        "csv",
        "--policy",
        "safe",
        "--full-plan",
    )
    assert policy_result.exit_code == 1
    assert (
        policy_payload["items"][0]["reason_code"] == "TRANSFER_POLICY_PLANNING_FAILED"
    )
    assert policy_payload["items"][0]["subsystem"] == "policy"


def test_execution_rechecks_output_immediately_before_write(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    output = tmp_path / "output"
    output.mkdir()
    plan = build_batch_plan(source.parent, output, "csv")
    target = output / "data.csv"

    def create_racing_output(item, dataset):
        target.write_text("created while item was planning", encoding="utf-8")
        return dataset

    result = execute_batch_plan(plan, item_processor=create_racing_output)

    assert result.failed_count == 1
    assert target.read_text(encoding="utf-8") == "created while item was planning"


def test_full_plan_human_output_surfaces_recipe_and_policy_state(tmp_path):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    output = tmp_path / "output"
    output.mkdir()

    result = runner.invoke(
        app,
        [
            "batch",
            str(source),
            str(output / "data.parquet"),
            "--to",
            "parquet",
            "--recipe",
            str(recipe),
            "--policy",
            "safe",
            "--full-plan",
        ],
    )

    assert result.exit_code == 0
    assert "Full plan:" in result.stdout
    assert "Recipe" in result.stdout
    assert "Policy" in result.stdout


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            ["--dry-run", "--full-plan", "--recipe", "{recipe}"],
            "either --dry-run or --full-plan",
        ),
        (["--full-plan"], "requires --recipe or --policy"),
        (["--policy", "safe", "--dry-run"], "Use --full-plan"),
        (["--recipe", "{recipe}", "--transform"], "either --recipe or --transform"),
        (["--policy", "legacy-compatible"], "not implemented"),
        (["--policy", "unknown"], "Unknown transfer policy"),
        (["--optimize-types"], "requires --policy smallest-types"),
        (
            ["--policy", "analysis-ready", "--optimize-types"],
            "requires --policy smallest-types",
        ),
        (["--recipe", "{recipe}", "--stream"], "does not support recipes"),
        (
            ["--policy", "safe", "--stream"],
            "does not support recipes or transfer policies",
        ),
    ],
)
def test_batch_recipe_policy_option_validation(tmp_path, extra, message):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    arguments = [value.format(recipe=recipe) for value in extra]
    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "parquet",
            *arguments,
        ],
    )

    assert result.exit_code == 1
    assert message.lower() in result.stdout.lower()


@pytest.mark.parametrize(
    "direct_option",
    [
        ["--select", "id"],
        ["--drop", "name"],
        ["--rename", "id=key"],
        ["--type", "id=string"],
        ["--type-errors", "coerce"],
        ["--datetime-format", "%Y-%m-%d"],
        ["--filter", "id,eq,1"],
        ["--filter-mode", "or"],
        ["--recode", "id:1=2"],
        ["--recode-default", "0"],
        ["--no-update-value-labels"],
        ["--ignore-missing-columns"],
        ["--no-reset-index"],
    ],
)
def test_recipe_rejects_every_direct_transform_option(tmp_path, direct_option):
    source = _write_csv(tmp_path / "input" / "data.csv")
    recipe = _write_recipe(tmp_path / "recipe.toml")
    result = runner.invoke(
        app,
        [
            "batch",
            str(source.parent),
            str(tmp_path / "output"),
            "--to",
            "parquet",
            "--recipe",
            str(recipe),
            *direct_option,
        ],
    )

    assert result.exit_code == 1
    assert "cannot be combined with direct batch transform options" in result.stdout


def test_batch_help_has_integration_options_but_no_type_plan():
    result = runner.invoke(app, ["batch", "--help"])

    assert result.exit_code == 0
    for option in ("--recipe", "--full-plan", "--policy", "--optimize-types"):
        assert option in result.stdout
    assert "--type-plan" not in result.stdout
