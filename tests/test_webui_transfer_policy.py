from __future__ import annotations

import asyncio
from pathlib import Path
import time

import httpx
import pandas as pd
import pytest


pytest.importorskip("fastapi")

from statconvert.webui.server import create_app


def _request(application, method: str, path: str, payload=None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://statconvert.local",
        ) as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(send())


def _wait(application, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = _request(application, "GET", f"/api/jobs/{job_id}")
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish: {job_id}")


def test_policy_preview_is_bounded_nonwriting_and_bypasses_output_checks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    source.write_text("small,text\n1,alpha\n2,beta\n", encoding="utf-8")
    output = tmp_path / "missing" / "output.parquet"

    response = _request(
        create_app(),
        "POST",
        "/api/workflows/plan-convert",
        {
            "input_path": str(source),
            "output_path": str(output),
            "target_format": "parquet",
            "policy": "smallest-types",
        },
    )

    payload = response.json()
    transfer = payload["details"]["transfer_plan"]
    assert response.status_code == 200
    assert payload["valid"] is True
    assert payload["details"]["writes"] is False
    assert transfer["policy"] == "smallest-types"
    assert transfer["output"] is None
    assert "truncated" in transfer
    assert "--policy smallest-types --type-plan" in payload["command"]
    assert not output.parent.exists()


def test_blocked_policy_preview_disables_execution_contract(tmp_path: Path) -> None:
    source = tmp_path / "timezone.parquet"
    pd.DataFrame(
        {"when": pd.date_range("2026-01-01", periods=2, tz="Europe/Amsterdam")}
    ).to_parquet(source, index=False)
    output = tmp_path / "output.xlsx"
    request = {
        "input_path": str(source),
        "output_path": str(output),
        "target_format": "xlsx",
        "policy": "strict",
    }
    application = create_app()

    preview = _request(
        application, "POST", "/api/workflows/plan-convert", request
    )
    created = _request(application, "POST", "/api/execute/convert", request)
    job = _wait(application, created.json()["job_id"])

    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    assert preview.json()["details"]["transfer_plan"]["status"] == "blocked"
    assert job["status"] == "failed"
    assert not output.exists()


def test_smallest_types_application_runs_only_when_explicit(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("small,exact,inexact\n1,1.5,0.1\n2,2.0,0.2\n", encoding="utf-8")
    output = tmp_path / "output.parquet"
    request = {
        "input_path": str(source),
        "output_path": str(output),
        "target_format": "parquet",
        "policy": "smallest-types",
        "optimize_types": True,
    }
    application = create_app()

    preview = _request(
        application, "POST", "/api/workflows/plan-convert", request
    )
    created = _request(application, "POST", "/api/execute/convert", request)
    job = _wait(application, created.json()["job_id"])

    written = pd.read_parquet(output)
    assert preview.status_code == 200
    assert preview.json()["details"]["optimize_types"] is True
    assert job["status"] == "succeeded"
    assert job["result"]["conversion"]["application"]["applied_count"] == 2
    assert str(written["small"].dtype) == "int8"
    assert str(written["exact"].dtype) == "float32"
    assert str(written["inexact"].dtype) == "float64"


def test_policy_streaming_and_invalid_application_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    base = {
        "input_path": str(source),
        "output_path": str(tmp_path / "output.csv"),
        "target_format": "csv",
    }
    application = create_app()

    streaming = _request(
        application,
        "POST",
        "/api/workflows/plan-convert",
        {**base, "policy": "safe", "stream": True},
    )
    analysis = _request(
        application,
        "POST",
        "/api/workflows/plan-convert",
        {**base, "policy": "analysis-ready", "optimize_types": True},
    )
    legacy = _request(
        application,
        "POST",
        "/api/workflows/plan-convert",
        {**base, "policy": "legacy-compatible"},
    )

    assert streaming.status_code == 400
    assert "cannot use streaming" in streaming.text
    assert analysis.status_code == 400
    assert "requires the smallest-types policy" in analysis.text
    assert legacy.status_code == 400
    assert "not implemented" in legacy.text


def test_report_policy_plan_and_execution_share_transfer_section(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    source.write_text("small\n1\n2\n", encoding="utf-8")
    output = tmp_path / "report.json"
    request = {
        "input_path": str(source),
        "output_path": str(output),
        "output_format": "json",
        "preset": "quick",
        "target_format": "parquet",
        "policy": "smallest-types",
    }
    application = create_app()

    preview = _request(application, "POST", "/api/workflows/plan-report", request)
    created = _request(application, "POST", "/api/execute/report", request)
    job = _wait(application, created.json()["job_id"])

    report = output.read_text(encoding="utf-8")
    assert preview.status_code == 200
    assert preview.json()["details"]["transfer_plan"]["policy"] == "smallest-types"
    assert "--target-format parquet --policy smallest-types" in preview.json()["command"]
    assert job["status"] == "succeeded"
    assert '"key": "transfer_policy"' in report


def test_frontend_policy_controls_are_explicit_and_scoped() -> None:
    root = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    convert = (root / "pages" / "ConvertPage.tsx").read_text(encoding="utf-8")
    report = (root / "pages" / "ReportPage.tsx").read_text(encoding="utf-8")
    reference = (root / "pages" / "ReferencePage.tsx").read_text(encoding="utf-8")
    batch = (root / "pages" / "BatchPage.tsx").read_text(encoding="utf-8")
    settings = (root / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
    transfer_view = (root / "components" / "TransferPlanView.tsx").read_text(
        encoding="utf-8"
    )

    assert "Current behavior / no policy" in convert
    for policy in (
        "safe",
        "strict",
        "analysis-ready",
        "preserve-metadata",
        "smallest-types",
    ):
        assert policy in convert
    assert "Preview transfer plan" in convert
    assert "Apply exact type optimization" in convert
    assert "checked={optimizeTypes}" in convert
    assert "Analysis-ready is plan-only" in convert
    assert "setPlan(null)" in convert
    assert "TransferPlanView" in convert
    assert "RawDetails" in transfer_view
    assert 'component="details"' not in transfer_view
    assert "Optional transfer target" in report
    assert "Transfer-policy section" in report
    assert "Legacy-compatible" in reference
    assert "policy" not in batch.casefold()
    assert "policy" not in settings.casefold()
