from __future__ import annotations

import asyncio
from pathlib import Path
import time
import tomllib

import httpx
import pandas as pd
import pytest


pytest.importorskip("fastapi")

from fastapi import FastAPI

from statconvert.transformations.language import expression_function_specs
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
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = _request(application, "GET", f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish: {job_id}")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    pd.DataFrame(
        {"old": [1, 2, 3], "status": ["A", "I", "A"], "unused": [9, 8, 7]}
    ).to_csv(path, index=False)
    return path


def _payload(source: Path, output: Path) -> dict[str, object]:
    return {
        "input_path": str(source),
        "output_path": str(output),
        "target_format": "csv",
        "overwrite": False,
        "create_dirs": True,
        "preview_limit": 2,
        "steps": [
            {"type": "drop", "columns": ["unused"]},
            {"type": "rename", "map": {"old": "value"}},
            {
                "type": "derive",
                "column": "double_value",
                "expression": "value * 2",
            },
            {"type": "filter", "expression": "status == 'A'"},
            {"type": "recode", "column": "status", "map": {"A": "Active"}},
        ],
    }


def test_function_api_matches_active_registry() -> None:
    response = _request(create_app(), "GET", "/api/transform/functions")
    payload = response.json()["data"]

    assert response.status_code == 200
    assert payload["count"] == 43
    assert {item["name"] for item in payload["functions"]} == {
        spec.name for spec in expression_function_specs()
    }
    replace = next(item for item in payload["functions"] if item["name"] == "replace")
    assert replace["signature"] == "replace(value, old, new)"
    assert replace["arguments"]
    assert replace["return_type"] == "string"
    assert replace["deferred"] is False


def test_expression_validation_is_pure_and_structured() -> None:
    application = create_app()
    valid = _request(
        application,
        "POST",
        "/api/transform/validate-expression",
        {"expression": "lower(name) == 'alice'", "purpose": "filter"},
    ).json()["data"]
    invalid = _request(
        application,
        "POST",
        "/api/transform/validate-expression",
        {"expression": "open('secret')", "purpose": "derive"},
    ).json()["data"]

    assert valid["valid"] is True
    assert valid["referenced_columns"] == ["name"]
    assert valid["functions"] == ["lower"]
    assert valid["source_spans"] == "half-open"
    assert invalid["valid"] is False
    assert invalid["errors"][0]["code"] == "unknown_function"
    assert invalid["errors"][0]["start"] == 0
    assert invalid["errors"][0]["end"] == 4


def test_plan_projects_columns_and_canonical_toml(
    source: Path,
    tmp_path: Path,
) -> None:
    response = _request(
        create_app(),
        "POST",
        "/api/transform/plan",
        _payload(source, tmp_path / "nested" / "output.csv"),
    )
    payload = response.json()
    plan = payload["details"]["plan"]

    assert response.status_code == 200
    assert payload["valid"] is True
    assert plan["initial_columns"] == ["old", "status", "unused"]
    assert plan["steps"][1]["input_columns"] == ["old", "status"]
    assert plan["steps"][1]["output_columns"] == ["value", "status"]
    assert plan["final_columns"] == ["value", "status", "double_value"]
    assert payload["command"] == "statconvert config run <saved-transform-recipe.toml>"
    parsed = tomllib.loads(payload["details"]["toml"])
    assert [step["type"] for step in parsed["steps"]] == [
        "drop",
        "rename",
        "derive",
        "filter",
        "recode",
    ]


def test_plan_reports_downstream_invalid_reference(
    source: Path,
    tmp_path: Path,
) -> None:
    payload = _payload(source, tmp_path / "output.csv")
    payload["steps"] = [
        {"type": "rename", "map": {"old": "value"}},
        {"type": "derive", "column": "bad", "expression": "old + 1"},
    ]
    response = _request(create_app(), "POST", "/api/transform/plan", payload)
    plan = response.json()["details"]["plan"]

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert plan["steps"][1]["status"] == "invalid"
    assert plan["errors"][0]["code"] == "transform_unknown_referenced_column"
    assert plan["errors"][0]["referenced_column"] == "old"


def test_preview_returns_before_after_without_writing(
    source: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output.csv"
    response = _request(
        create_app(),
        "POST",
        "/api/transform/preview-recipe",
        _payload(source, output),
    )
    preview = response.json()["data"]

    assert response.status_code == 200
    assert preview["valid"] is True
    assert len(preview["before_rows"]) == 2
    assert preview["preview_rows"] == 1
    assert preview["sample_output_rows"] == [
        {"value": 1, "status": "Active", "double_value": 2}
    ]
    assert not output.exists()


def test_background_execution_preserves_output_safety(
    source: Path,
    tmp_path: Path,
) -> None:
    application = create_app()
    output = tmp_path / "nested" / "output.csv"
    payload = _payload(source, output)
    created = _request(application, "POST", "/api/execute/transform", payload)
    job = _wait_for_job(application, created.json()["job_id"])

    assert job["status"] == "succeeded"
    assert job["result"]["rows"] == 2
    assert pd.read_csv(output).to_dict("list") == {
        "value": [1, 3],
        "status": ["Active", "Active"],
        "double_value": [2, 6],
    }

    collision = _request(application, "POST", "/api/execute/transform", payload)
    assert collision.status_code == 400
    assert collision.json()["error"]["code"] == "web_ui_request_error"
    assert "already exists" in collision.json()["error"]["message"]
    assert "Traceback" not in collision.text


def test_transform_applies_selected_extension_when_output_has_none(
    source: Path,
    tmp_path: Path,
) -> None:
    application = create_app()
    output_without_suffix = tmp_path / "nested" / "output"
    payload = _payload(source, output_without_suffix)

    plan = _request(application, "POST", "/api/transform/plan", payload)
    assert plan.status_code == 200
    assert plan.json()["details"]["output_path"] == f"{output_without_suffix}.csv"
    assert tomllib.loads(plan.json()["details"]["toml"])["output"] == (
        f"{output_without_suffix}.csv"
    )

    created = _request(application, "POST", "/api/execute/transform", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["output_path"] == f"{output_without_suffix}.csv"
    assert (tmp_path / "nested" / "output.csv").is_file()
