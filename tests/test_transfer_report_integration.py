from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from statconvert.cli import app
from statconvert.dataset import Dataset
from statconvert.reporting import build_dataset_report, build_transfer_plan_section
from statconvert.transfer import build_transfer_plan


runner = CliRunner()


def test_report_policy_requires_explicit_target(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        ["report", str(source), "--output", str(output), "--policy", "safe"],
    )

    assert result.exit_code == 1
    assert "--policy requires --target-format" in result.output
    assert not output.exists()


def test_report_policy_adds_bounded_parseable_json_section(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("small,text\n1,alpha\n2,beta\n", encoding="utf-8")
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--output",
            str(output),
            "--target-format",
            "parquet",
            "--policy",
            "smallest-types",
            "--quiet",
        ],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    sections = {section["key"]: section for section in payload["report"]["sections"]}
    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert "transfer_policy" in sections
    metrics = {item["name"]: item["value"] for item in sections["transfer_policy"]["metrics"]}
    assert metrics["policy"] == "smallest-types"
    assert metrics["target"] == ".parquet"
    assert "truncation" in metrics


def test_report_policy_section_renders_in_html_and_csv(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("value\n1\n2\n", encoding="utf-8")
    for suffix in ("html", "csv"):
        output = tmp_path / f"report.{suffix}"
        result = runner.invoke(
            app,
            [
                "report",
                str(source),
                "--output",
                str(output),
                "--target-format",
                "parquet",
                "--policy",
                "safe",
                "--quiet",
            ],
        )
        rendered = output.read_text(encoding="utf-8")
        assert result.exit_code == 0, result.output
        assert "Transfer Policy" in rendered or "transfer_policy" in rendered


def test_no_policy_report_section_list_is_unchanged() -> None:
    dataset = Dataset(pd.DataFrame({"value": [1, 2]}))
    ordinary = build_dataset_report(dataset)
    plan = build_transfer_plan(
        dataset,
        source_path="input.csv",
        target="parquet",
        policy="safe",
    )
    planned = build_dataset_report(dataset, transfer_plan=plan)

    assert [section.key for section in ordinary.sections] == [
        "summary",
        "schema",
        "metadata",
        "labels",
        "missing",
        "describe",
        "validation",
    ]
    assert [section.key for section in planned.sections[:-1]] == [
        section.key for section in ordinary.sections
    ]
    assert planned.sections[-1].key == "transfer_policy"


def test_transfer_report_section_uses_plan_bounds() -> None:
    dataset = Dataset(pd.DataFrame({f"c{i}": [i] for i in range(205)}))
    plan = build_transfer_plan(
        dataset,
        source_path="input.csv",
        target="parquet",
        policy="smallest-types",
    )

    section = build_transfer_plan_section(plan)
    metrics = {metric.name: metric.value for metric in section.metrics}

    assert len(section.tables[0].rows) <= 200
    assert len(section.tables[1].rows) <= 200
    assert metrics["truncation"]["decisions"] is True
    assert metrics["truncation"]["decisions_omitted"] == 5
