from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest


pytest.importorskip("fastapi")

from statconvert.webui.server import create_app


def _request(application, method: str, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://statconvert.local",
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send())


def test_frontend_polish_contracts_are_centralized() -> None:
    source = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    picker = (source / "components" / "PathPickerField.tsx").read_text(encoding="utf-8")
    formats = (source / "lib" / "formats.ts").read_text(encoding="utf-8")
    statuses = (source / "lib" / "status.ts").read_text(encoding="utf-8")
    job_progress = (source / "components" / "JobProgress.tsx").read_text(
        encoding="utf-8"
    )
    batch_progress = (source / "components" / "BatchProgressTable.tsx").read_text(
        encoding="utf-8"
    )
    theme = (source / "theme.ts").read_text(encoding="utf-8")
    styles = (source / "styles" / "app.css").read_text(encoding="utf-8")

    assert 'label="Confirmed starting folder"' in picker
    assert 'postJson<PathBrowseResponse>("/api/files/browse"' in picker
    assert 'getJson<PathRootsResponse>("/api/files/roots")' not in picker
    assert "Locations" not in picker
    assert "<Table.Thead>" not in picker
    assert 'csv: "CSV (*.csv)"' in formats
    assert 'xlsx: "Excel (*.xlsx)"' in formats
    assert 'sav: "SPSS (*.sav)"' in formats
    assert 'dta: "Stata (*.dta)"' in formats
    assert ".sort((left, right) => left.label.localeCompare(right.label))" in formats
    for status, color in (
        ('case "running"', 'return "blue"'),
        ('case "succeeded"', 'return "green"'),
        ('case "failed"', 'return "red"'),
        ('case "cancelled"', 'return "orange"'),
    ):
        assert status in statuses
        assert color in statuses
    assert "jobStatusColor(job?.status" in job_progress
    assert "jobStatusColor(row.status)" in batch_progress
    assert '"--sc-table-header"' in theme
    assert ".result-table tbody tr:nth-of-type(even) td" in styles
    assert ".path-browser-table" not in styles


def test_format_selectors_keep_payload_values_and_use_friendly_options() -> None:
    pages = Path(__file__).resolve().parents[1] / "ui-frontend" / "src" / "pages"
    for page_name in (
        "ConvertPage.tsx",
        "BatchPage.tsx",
        "ValidatePage.tsx",
        "TransformPage.tsx",
    ):
        page = (pages / page_name).read_text(encoding="utf-8")
        assert 'import { formatOptions } from "../lib/formats"' in page
        assert "data={formats}" in page
        assert "target_format: targetFormat" in page


def test_implementation_build_labels_are_removed_but_about_keeps_version() -> None:
    source = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    about = (source / "pages" / "AboutPage.tsx").read_text(encoding="utf-8")
    normal_sources = [
        source / "App.tsx",
        source / "components" / "WorkflowHeader.tsx",
        source / "pages" / "HomePage.tsx",
        source / "pages" / "PlaceholderPage.tsx",
        source / "routes" / "navigation.ts",
    ]

    for path in normal_sources:
        text = path.read_text(encoding="utf-8")
        assert "1.0.0c" not in text
        assert "1.0.0d" not in text
        assert "1.0.0e" not in text
        assert "1.0.0f" not in text
        assert "1.0.0g5" not in text
    assert "data.version" in about

    version = _request(create_app(), "GET", "/api/version")
    assert version.status_code == 200
    assert version.json()["version"] == "1.0.1"


def test_report_and_configs_page_polish_contracts() -> None:
    source = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    report = (source / "pages" / "ReportPage.tsx").read_text(encoding="utf-8")
    configs = (source / "pages" / "ConfigsPage.tsx").read_text(encoding="utf-8")
    workflow_result = (
        source / "components" / "WorkflowResultView.tsx"
    ).read_text(encoding="utf-8")
    command_preview = (source / "components" / "CommandPreview.tsx").read_text(
        encoding="utf-8"
    )

    assert 'useState<string | null>("html")' in report
    assert "output_path: ensureOutputExtension(outputPath, outputFormat)" in report
    assert "updateGeneratedExtension(outputPath, outputFormat, value)" in report
    assert "outputExtensionWarning(outputPath, outputFormat)" in report
    assert "extensions={outputFormat ? [`.${outputFormat}`] : []}" in report
    assert "onCommit={commitOutputPath}" in report
    assert "Visual round-trip import into Transform remains deferred" not in configs
    assert 'key !== "cli_command"' in configs
    assert "rawData={result}" in configs
    config_summary = workflow_result.split('workflow === "config"', maxsplit=1)[1]
    assert "cli_command:" not in config_summary.split("return <ResultView", maxsplit=1)[0]
    assert "show_command_preview" in command_preview
