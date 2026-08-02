from __future__ import annotations

import asyncio
from pathlib import Path
import time

import httpx
import pandas as pd
import pytest


pytest.importorskip("fastapi")

from fastapi import FastAPI

from statconvert.registry import list_backends, list_formats
from statconvert.webui.server import create_app


def _request(
    application: FastAPI,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://statconvert.local",
        ) as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(send())


def _wait_for_job(application: FastAPI, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = _request(application, "GET", f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish: {job_id}")


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame({"id": [1, 2], "score": [10, 20]}).to_csv(left, index=False)
    pd.DataFrame({"id": [1, 2], "score": [10, 21]}).to_csv(right, index=False)
    return left, right


def test_config_init_load_validate_export_and_run(tmp_path: Path) -> None:
    application = create_app()
    config_path = tmp_path / "convert.toml"
    source = tmp_path / "input.csv"
    output = tmp_path / "output.json"
    pd.DataFrame({"value": [1, 2]}).to_csv(source, index=False)

    starter = _request(
        application,
        "POST",
        "/api/config/init",
        {"command": "compare"},
    )
    assert starter.status_code == 200
    assert starter.json()["data"]["toml"].startswith('command = "compare"')
    assert "statconvert config init compare" in starter.json()["data"]["cli_command"]

    toml_text = (
        'command = "convert"\n'
        f'input = "{str(source).replace(chr(92), chr(92) * 2)}"\n'
        f'output = "{str(output).replace(chr(92), chr(92) * 2)}"\n'
    )
    exported = _request(
        application,
        "POST",
        "/api/config/export",
        {"output_path": str(config_path), "toml_text": toml_text},
    )
    assert exported.status_code == 200
    assert config_path.is_file()

    loaded = _request(
        application,
        "POST",
        "/api/config/load",
        {"config_path": str(config_path)},
    )
    assert loaded.status_code == 200
    assert loaded.json()["data"]["command"] == "convert"

    validated = _request(
        application,
        "POST",
        "/api/config/validate",
        {"toml_text": toml_text},
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["valid"] is True

    created = _request(
        application,
        "POST",
        "/api/config/run",
        {"config_path": str(config_path)},
    )
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert output.is_file()


def test_invalid_and_mixed_config_errors_are_structured() -> None:
    application = create_app()
    malformed = _request(
        application,
        "POST",
        "/api/config/validate",
        {"toml_text": 'command = "convert"\ninvalid = ['},
    )
    assert malformed.status_code == 400
    assert "Traceback" not in malformed.text

    mixed = _request(
        application,
        "POST",
        "/api/config/validate",
        {
            "toml_text": (
                'command = "transform"\ninput = "in.csv"\noutput = "out.csv"\n'
                'select = ["id"]\n[[steps]]\ntype = "drop"\ncolumns = ["x"]\n'
            )
        },
    )
    assert mixed.status_code == 400
    assert "legacy" in mixed.json()["error"]["message"].lower()
    assert "Traceback" not in mixed.text


def test_compare_plan_execute_and_bounded_differences(
    pair: tuple[Path, Path],
) -> None:
    application = create_app()
    left, right = pair
    payload = {
        "left_path": str(left),
        "right_path": str(right),
        "key_columns": ["id"],
        "max_differences": 1,
    }
    plan = _request(application, "POST", "/api/workflows/plan-compare", payload)
    assert plan.status_code == 200
    assert "--key id" in plan.json()["command"]

    created = _request(application, "POST", "/api/execute/compare", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["is_identical"] is False
    comparison = job["result"]["comparison"]
    assert comparison["summary"]["detailed_differences_shown"] == 1
    assert set(comparison) >= {
        "summary",
        "shape",
        "columns",
        "schema",
        "metadata",
        "values",
        "differences",
    }


def test_report_plan_execute_and_output_safety(pair: tuple[Path, Path], tmp_path: Path) -> None:
    application = create_app()
    output = tmp_path / "report.json"
    payload = {
        "input_path": str(pair[0]),
        "output_path": str(output),
        "preset": "quick",
        "max_table_rows": 10,
    }
    plan = _request(application, "POST", "/api/workflows/plan-report", payload)
    assert plan.status_code == 200
    assert "statconvert report" in plan.json()["command"]

    created = _request(application, "POST", "/api/execute/report", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert output.is_file()
    assert job["result"]["format"] == "json"

    collision = _request(application, "POST", "/api/execute/report", payload)
    assert collision.status_code == 400
    assert "already exists" in collision.json()["error"]["message"]


def test_collect_plan_execute_and_output_safety(pair: tuple[Path, Path], tmp_path: Path) -> None:
    application = create_app()
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "input_file,output_object\nleft.csv,Left\nright.csv,Right\n",
        encoding="utf-8",
    )
    output = tmp_path / "collection.xlsx"
    payload = {
        "manifest_path": str(manifest),
        "output_path": str(output),
        "create_dirs": False,
    }
    plan = _request(application, "POST", "/api/workflows/plan-collect", payload)
    assert plan.status_code == 200
    assert plan.json()["details"]["objects"] == 2
    assert "statconvert collect" in plan.json()["command"]

    created = _request(application, "POST", "/api/execute/collect", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["objects"] == 2
    assert output.is_file()

    collision = _request(application, "POST", "/api/execute/collect", payload)
    assert collision.status_code == 400
    assert "already exists" in collision.json()["error"]["message"]


def test_collect_manifest_example_and_safe_starter(tmp_path: Path) -> None:
    application = create_app()
    example = _request(application, "GET", "/api/collect/manifest-example")

    assert example.status_code == 200
    example_data = example.json()["data"]
    assert example_data["required_columns"] == ["input_file"]
    assert example_data["csv"].startswith(
        "input_file,input_object,output_object\n"
    )

    output = tmp_path / "nested" / "objects.csv"
    created = _request(
        application,
        "POST",
        "/api/collect/create-manifest",
        {
            "output_path": str(output),
            "create_dirs": True,
            "overwrite": False,
        },
    )
    assert created.status_code == 200
    assert created.json()["data"]["output_path"] == str(output)
    assert created.json()["data"]["rows"] == 2
    assert output.read_text(encoding="utf-8").splitlines()[1] == "data.csv,,Data"

    collision = _request(
        application,
        "POST",
        "/api/collect/create-manifest",
        {"output_path": str(output)},
    )
    assert collision.status_code == 400
    assert "already exists" in collision.json()["error"]["message"]

    wrong_extension = _request(
        application,
        "POST",
        "/api/collect/create-manifest",
        {"output_path": str(tmp_path / "objects.txt")},
    )
    assert wrong_extension.status_code == 400
    assert ".csv extension" in wrong_extension.json()["error"]["message"]


def test_g4_frontend_run_state_and_structured_compare_contract() -> None:
    source = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    pages = source / "pages"
    compare = (pages / "ComparePage.tsx").read_text(encoding="utf-8")
    report = (pages / "ReportPage.tsx").read_text(encoding="utf-8")
    collect = (pages / "CollectPage.tsx").read_text(encoding="utf-8")
    configs = (pages / "ConfigsPage.tsx").read_text(encoding="utf-8")
    compare_result = (source / "components" / "CompareResultView.tsx").read_text(
        encoding="utf-8"
    )

    for page in (compare, report, collect):
        assert "setJobId(null)" in page
        assert "setPlan(null)" in page
    assert "setResult(null)" in configs
    assert "setJobId(null)" in configs
    for section in (
        "Comparison Summary",
        "Inputs",
        "Shape",
        "Columns",
        "Schema",
        "Metadata",
        "Values",
    ):
        assert section in compare_result
    assert "<RawDetails data={data}" in compare_result
    assert "Show manifest example" in collect
    assert "Create starter manifest" in collect
    assert "/api/collect/create-manifest" in collect


def test_g5_raw_details_summaries_and_plan_cleanup_contract() -> None:
    source = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    components = source / "components"
    pages = source / "pages"
    raw_details = (components / "RawDetails.tsx").read_text(encoding="utf-8")
    result_view = (components / "ResultView.tsx").read_text(encoding="utf-8")
    workflow_result = (components / "WorkflowResultView.tsx").read_text(encoding="utf-8")
    job_progress = (components / "JobProgress.tsx").read_text(encoding="utf-8")

    assert 'component="details"' in raw_details
    assert "Raw details" in raw_details
    assert "open=" not in raw_details
    assert "<RawDetails" in result_view
    assert "<WorkflowResultView" in job_progress
    for workflow in ("convert", "transform", "report", "collect", "config"):
        assert f'workflow === "{workflow}"' in workflow_result

    for page_name in ("ConvertPage.tsx", "ValidatePage.tsx"):
        page = (pages / page_name).read_text(encoding="utf-8")
        assert "setJobId(null)" in page
        assert "setPlan(null)" in page


def test_reference_routes_follow_live_registries() -> None:
    application = create_app()
    formats = _request(application, "GET", "/api/reference/formats").json()["data"]
    backends = _request(application, "GET", "/api/reference/backends").json()["data"]
    capabilities = _request(
        application,
        "GET",
        "/api/reference/capabilities",
    ).json()["data"]

    assert formats["count"] == len(list_formats())
    assert {row["extension"] for row in formats["rows"]} == set(list_formats())
    assert formats["command"] == "statconvert formats"
    assert backends["count"] == len(list_backends())
    assert {row["backend"] for row in backends["rows"]} == set(list_backends())
    assert backends["command"] == "statconvert backends"
    assert capabilities["count"] == len(list_formats())
    assert all("supports_streaming" in row for row in capabilities["rows"])
    assert capabilities["command"] == "statconvert capabilities"
