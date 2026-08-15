from __future__ import annotations

import asyncio
from pathlib import Path
import re

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
    transform = (source / "pages" / "TransformPage.tsx").read_text(encoding="utf-8")
    reference = (source / "pages" / "ReferencePage.tsx").read_text(encoding="utf-8")

    assert 'label="Confirmed starting folder"' in picker
    assert 'postJson<PathBrowseResponse>("/api/files/browse"' in picker
    assert 'getJson<PathRootsResponse>("/api/files/roots")' not in picker
    assert "Locations" not in picker
    assert "<Table.Thead>" not in picker
    assert 'csv: "CSV (*.csv)"' in formats
    assert 'xlsx: "Excel Workbook (*.xlsx)"' in formats
    assert 'sav: "SPSS SAV (*.sav)"' in formats
    assert 'dta: "Stata (*.dta)"' in formats
    assert 'xpt: "SAS XPORT (*.xpt)"' in formats
    assert 'jsonl: "JSON Lines (*.jsonl)"' in formats
    assert 'ndjson: "Newline-delimited JSON (*.ndjson)"' in formats
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
    assert "allowSaveSelection" in picker
    assert 'open("file")' in picker and 'open("save_file")' in picker
    assert 'extensions={[".toml"]} allowSaveSelection' in transform
    assert 'setFullPreview(null); try' in transform
    assert 'setPreview(null); try' in transform
    assert "steps.length > 0 && steps.every(complete)" in transform
    assert (
        'disabled={!canPlan || Boolean(extensionWarning)}>Full impact preview'
        in transform
    )
    assert transform.index("<JobProgress jobId={jobId} />") < transform.index("<BeforeAfterPreview preview={preview} />")
    assert 'className="result-table reference-table"' in reference
    assert '.reference-table [data-column="caveat"]' in styles


def test_format_selectors_keep_payload_values_and_use_friendly_options() -> None:
    root = Path(__file__).resolve().parents[1]
    format_source = (root / "ui-frontend" / "src" / "lib" / "formats.ts").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"export const writableFormatValues = (\[.*?\]) as const;",
        format_source,
        re.DOTALL,
    )
    assert match is not None
    selector_values = set(re.findall(r'"([a-z0-9]+)"', match.group(1)))

    from statconvert.registry import list_formats

    writable_registry_values = {
        extension.lstrip(".")
        for extension, info in list_formats().items()
        if info["can_write"]
    }
    assert selector_values == writable_registry_values
    assert {"por", "sas7bdat", "zsav"}.isdisjoint(selector_values)

    pages = Path(__file__).resolve().parents[1] / "ui-frontend" / "src" / "pages"
    for page_name in (
        "ConvertPage.tsx",
        "BatchPage.tsx",
        "ValidatePage.tsx",
        "TransformPage.tsx",
    ):
        page = (pages / page_name).read_text(encoding="utf-8")
        assert 'import { writableFormatOptions } from "../lib/formats"' in page
        assert "data={formats}" in page
        assert "target_format: targetFormat" in page
        assert "const formats = writableFormatOptions" in page


def test_json_family_reference_streaming_capabilities_are_truthful() -> None:
    response = _request(create_app(), "GET", "/api/reference/capabilities")
    rows = {
        row["extension"]: row
        for row in response.json()["data"]["rows"]
    }

    assert response.status_code == 200
    assert rows[".json"]["supports_streaming"] is False
    assert rows[".jsonl"]["supports_streaming"] is True
    assert rows[".ndjson"]["supports_streaming"] is True


def test_reference_formats_are_friendly_sorted_and_describe_metadata() -> None:
    response = _request(create_app(), "GET", "/api/reference/formats")
    rows = response.json()["data"]["rows"]

    assert response.status_code == 200
    assert [(row["name"].casefold(), row["extension"]) for row in rows] == sorted(
        (row["name"].casefold(), row["extension"]) for row in rows
    )
    assert all(row["metadata_mode"] for row in rows)
    assert all(row["caveat"] for row in rows)
    by_extension = {row["extension"]: row for row in rows}
    assert by_extension[".parquet"]["metadata_mode"] == "embedded + sidecar"
    assert by_extension[".sav"]["metadata_mode"] == "native, limited"
    assert by_extension[".csv"]["metadata_mode"] == "sidecar"
    assert by_extension[".zsav"]["caveat"].endswith("write .sav instead.")
    assert by_extension[".por"]["caveat"].endswith("write .sav instead.")
    assert by_extension[".sas7bdat"]["caveat"].endswith(
        "write .xpt for SAS interchange."
    )
    assert "formulas and styling are not preserved" in by_extension[".xlsx"][
        "caveat"
    ]
    assert "nested flattening is unsupported" in by_extension[".json"]["caveat"]
    assert "sidecar overrides embedded" in by_extension[".parquet"]["caveat"]


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
    assert version.json()["version"] == "1.4.1"


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
