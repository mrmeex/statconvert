from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event
import time

import httpx
import pandas as pd
import pytest


pytest.importorskip("fastapi")

from fastapi import FastAPI

from statconvert.webui.server import create_app


def _request(
    application: FastAPI,
    method: str,
    path: str,
    *,
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


def _post(
    application: FastAPI,
    path: str,
    payload: dict[str, object],
) -> httpx.Response:
    return _request(application, "POST", path, payload=payload)


def _wait_for_job(application: FastAPI, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = _request(application, "GET", f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish: {job_id}")


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "people.csv"
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "group": ["a", "a", "b"],
            "score": [10.5, None, 8.0],
        }
    ).to_csv(path, index=False)
    return path


def test_path_and_all_inspection_routes_are_bounded(
    csv_file: Path,
) -> None:
    application = create_app()
    dataset_payload = {"path": str(csv_file), "object_selector": None}

    path_response = _post(
        application,
        "/api/files/inspect-path",
        {"path": str(csv_file)},
    )
    assert path_response.status_code == 200
    assert path_response.json()["data"]["readable"] is True

    objects = _post(
        application,
        "/api/inspect/objects",
        {"path": str(csv_file), "recursive": False},
    )
    assert objects.status_code == 200
    assert len(objects.json()["data"]["files"]) == 1

    info = _post(application, "/api/inspect/info", dataset_payload)
    assert info.json()["data"]["rows"] == 3
    assert info.json()["data"]["columns"] == 3
    assert [row["name"] for row in info.json()["data"]["column_details"]] == [
        "id",
        "group",
        "score",
    ]

    peek = _post(
        application,
        "/api/inspect/peek",
        {**dataset_payload, "rows": 2},
    )
    assert peek.json()["data"]["returned_rows"] == 2
    assert "statconvert peek" in peek.json()["command"]

    schema = _post(application, "/api/inspect/schema", dataset_payload)
    assert schema.json()["data"]["total_columns"] == 3

    labels = _post(application, "/api/inspect/labels", dataset_payload)
    assert "variable_labels" in labels.json()["data"]

    metadata = _post(application, "/api/inspect/metadata", dataset_payload)
    assert metadata.json()["data"]["total_variables"] == 3
    assert "summary" in metadata.json()["data"]

    summary = _post(application, "/api/inspect/summary", dataset_payload)
    assert summary.json()["data"]["row_count"] == 3

    describe = _post(
        application,
        "/api/inspect/describe",
        {**dataset_payload, "columns": ["score"]},
    )
    assert describe.json()["data"]["profiles"][0]["name"] == "score"
    assert describe.json()["data"]["column_profiles"][0]["name"] == "score"
    assert describe.json()["data"]["numeric_statistics"][0]["column"] == "score"
    assert describe.json()["data"]["categorical_statistics"] == []

    frequencies = _post(
        application,
        "/api/inspect/frequencies",
        {
            **dataset_payload,
            "columns": ["group"],
            "top": 10,
            "include_missing": False,
            "max_unique": 100,
        },
    )
    assert frequencies.json()["data"]["tables"][0]["items"][0]["count"] == 2

    missing = _post(
        application,
        "/api/inspect/missing",
        {**dataset_payload, "columns": ["score"]},
    )
    assert missing.json()["data"]["profiles"][0]["missing_count"] == 1


@pytest.mark.parametrize(
    ("format_name", "suffix"),
    [("r", ".R"), ("spss", ".sps"), ("stata", ".do")],
)
def test_metadata_script_export_uses_existing_exporter(
    csv_file: Path,
    tmp_path: Path,
    format_name: str,
    suffix: str,
) -> None:
    output = tmp_path / f"metadata{suffix}"
    response = _post(
        create_app(),
        "/api/inspect/metadata/export-script",
        {
            "path": str(csv_file),
            "object_selector": None,
            "output_path": str(output),
            "format": format_name,
            "overwrite": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "output_path": str(output),
        "format": format_name,
    }
    assert f"--export-script {output}" in response.json()["command"]
    assert output.is_file()
    assert "Generated by StatConvert" in output.read_text(encoding="utf-8")


def test_metadata_script_export_rejects_mismatched_extension(
    csv_file: Path,
    tmp_path: Path,
) -> None:
    response = _post(
        create_app(),
        "/api/inspect/metadata/export-script",
        {
            "path": str(csv_file),
            "output_path": str(tmp_path / "metadata.txt"),
            "format": "stata",
        },
    )

    assert response.status_code == 400
    assert ".do extension" in response.json()["error"]["message"]


def test_convert_plan_and_background_execution(
    csv_file: Path,
    tmp_path: Path,
) -> None:
    application = create_app()
    output = tmp_path / "people.json"
    payload = {
        "input_path": str(csv_file),
        "output_path": str(output),
        "target_format": "json",
        "overwrite": False,
        "create_dirs": False,
        "stream": False,
    }

    plan = _post(application, "/api/workflows/plan-convert", payload)
    assert plan.status_code == 200
    assert plan.json()["valid"] is True
    assert "statconvert convert" in plan.json()["command"]

    created = _post(application, "/api/execute/convert", payload)
    assert created.status_code == 200
    job = _wait_for_job(application, created.json()["job_id"])

    assert job["status"] == "succeeded"
    assert job["result"]["conversion"]["rows"] == 3
    assert output.is_file()

    events = _request(
        application,
        "GET",
        f"/api/jobs/{created.json()['job_id']}/events",
    )
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert '"kind": "succeeded"' in events.text

    terminal_cancel = _request(
        application,
        "POST",
        f"/api/jobs/{created.json()['job_id']}/cancel",
    )
    assert terminal_cancel.json()["status"] == "succeeded"


def test_convert_applies_selected_extension_when_output_has_none(
    csv_file: Path,
    tmp_path: Path,
) -> None:
    application = create_app()
    output_without_suffix = tmp_path / "people"
    payload = {
        "input_path": str(csv_file),
        "output_path": str(output_without_suffix),
        "target_format": "json",
    }

    plan = _post(application, "/api/workflows/plan-convert", payload)
    assert plan.status_code == 200
    assert plan.json()["details"]["output_path"] == f"{output_without_suffix}.json"

    created = _post(application, "/api/execute/convert", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["conversion"]["output_path"] == f"{output_without_suffix}.json"
    assert (tmp_path / "people.json").is_file()


def test_convert_preserves_explicit_mismatched_extension_and_reports_it(
    csv_file: Path,
    tmp_path: Path,
) -> None:
    explicit = tmp_path / "people.csv"
    response = _post(
        create_app(),
        "/api/workflows/plan-convert",
        {
            "input_path": str(csv_file),
            "output_path": str(explicit),
            "target_format": "parquet",
        },
    )

    assert response.status_code == 400
    assert "does not match output path" in response.json()["error"]["message"]
    assert not (tmp_path / "people.parquet").exists()


def test_batch_plan_and_background_execution(tmp_path: Path) -> None:
    application = create_app()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    pd.DataFrame({"x": [1]}).to_csv(input_dir / "a.csv", index=False)
    pd.DataFrame({"x": [2]}).to_csv(input_dir / "b.csv", index=False)
    payload = {
        "input_path": str(input_dir),
        "output_path": str(output_dir),
        "target_format": "json",
        "recursive": False,
        "overwrite": False,
        "create_dirs": True,
        "stream": False,
    }

    plan = _post(application, "/api/workflows/plan-batch", payload)
    assert plan.status_code == 200
    assert plan.json()["details"]["counts"]["pending"] == 2

    created = _post(application, "/api/execute/batch", payload)
    job = _wait_for_job(application, created.json()["job_id"])

    assert job["status"] == "succeeded"
    assert job["result"]["summary"]["success"] == 2
    assert (output_dir / "a.json").is_file()
    assert (output_dir / "b.json").is_file()


def test_batch_workers_are_opt_in_and_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from statconvert.webui import services

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    pd.DataFrame({"x": [1]}).to_csv(input_dir / "a.csv", index=False)
    base = {
        "input_path": str(input_dir),
        "output_path": str(tmp_path / "output"),
        "target_format": "json",
        "create_dirs": True,
    }
    application = create_app()

    automatic = _post(application, "/api/workflows/plan-batch", base)
    assert automatic.status_code == 200
    assert "--workers" not in automatic.json()["command"]
    assert automatic.json()["details"]["workers_automatic"] is True

    explicit = _post(
        application,
        "/api/workflows/plan-batch",
        {**base, "workers": 2},
    )
    assert explicit.status_code == 200
    assert "--workers 2" in explicit.json()["command"]
    assert explicit.json()["details"]["workers"] == 2

    captured_workers: list[object] = []
    original_execute = services.execute_batch_plan

    def capture_workers(plan, **kwargs):
        captured_workers.append(kwargs.get("workers", "omitted"))
        return original_execute(plan, **kwargs)

    monkeypatch.setattr(services, "execute_batch_plan", capture_workers)
    automatic_created = _post(
        application,
        "/api/execute/batch",
        {**base, "output_path": str(tmp_path / "automatic-output")},
    )
    assert (
        _wait_for_job(application, automatic_created.json()["job_id"])["status"]
        == "succeeded"
    )
    created = _post(application, "/api/execute/batch", {**base, "workers": 2})
    assert _wait_for_job(application, created.json()["job_id"])["status"] == "succeeded"
    assert captured_workers == ["omitted", 2]

    invalid = _post(
        application,
        "/api/workflows/plan-batch",
        {**base, "workers": 0},
    )
    assert invalid.status_code == 422


def test_active_job_lookup_returns_data_or_none() -> None:
    application = create_app()
    response = _request(application, "GET", "/api/jobs/active?workflow=batch")
    assert response.status_code == 200
    assert response.json() == {"data": None}


def test_g3_frontend_defaults_and_batch_state_contract() -> None:
    pages = Path(__file__).resolve().parents[1] / "ui-frontend" / "src" / "pages"
    convert = (pages / "ConvertPage.tsx").read_text(encoding="utf-8")
    batch = (pages / "BatchPage.tsx").read_text(encoding="utf-8")
    transform = (pages / "TransformPage.tsx").read_text(encoding="utf-8")

    assert 'useState<string | null>("parquet")' in convert
    assert 'useState<string | null>("parquet")' in batch
    assert 'useState<string | null>("parquet")' in transform
    assert 'workers === "" ? null : Number(workers)' in batch
    assert 'getActiveJob("batch")' in batch
    assert "let batchSessionJobId" in batch
    assert "setPlan(null)" in batch
    assert "activeJob || !plan?.valid" in batch


def test_second_ui_batch_is_rejected_until_active_job_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from statconvert.webui.api import routes

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    pd.DataFrame({"x": [1]}).to_csv(input_dir / "a.csv", index=False)
    payload = {
        "input_path": str(input_dir),
        "output_path": str(tmp_path / "output"),
        "target_format": "json",
        "create_dirs": True,
    }
    started = Event()
    release = Event()

    def blocking_execute(request, context):
        del request, context
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    monkeypatch.setattr(routes, "execute_batch", blocking_execute)
    application = create_app()
    first = _post(application, "/api/execute/batch", payload)
    assert first.status_code == 200
    assert started.wait(timeout=2)

    active = _request(application, "GET", "/api/jobs/active?workflow=batch")
    assert active.status_code == 200
    assert active.json()["data"]["job_id"] == first.json()["job_id"]

    second = _post(application, "/api/execute/batch", payload)
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "active_job_error"
    assert "already running" in second.json()["error"]["message"]

    release.set()
    assert _wait_for_job(application, first.json()["job_id"])["status"] == "succeeded"


def _write_xlsx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"value": [1]}).to_excel(writer, sheet_name="Data", index=False)
        pd.DataFrame({"value": [2]}).to_excel(writer, sheet_name="Lookup", index=False)


def _write_xls(path: Path) -> None:
    xlwt = pytest.importorskip("xlwt")
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlwt.Workbook()
    for name, value in (("Data", 1), ("Lookup", 2)):
        sheet = workbook.add_sheet(name)
        sheet.write(0, 0, "value")
        sheet.write(1, 0, value)
    workbook.save(str(path))


@pytest.mark.parametrize("suffix,writer", [(".xlsx", _write_xlsx), (".xls", _write_xls)])
def test_batch_container_choice_and_recursive_all_objects(
    tmp_path: Path,
    suffix: str,
    writer,
) -> None:
    application = create_app()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    writer(input_dir / "a" / f"book{suffix}")
    writer(input_dir / "b" / f"book{suffix}")
    base_payload = {
        "input_path": str(input_dir),
        "output_path": str(output_dir),
        "target_format": "csv",
        "recursive": True,
        "overwrite": False,
        "create_dirs": True,
        "preserve_structure": True,
        "stream": False,
    }

    automatic = _post(application, "/api/workflows/plan-batch", base_payload)
    assert automatic.status_code == 200
    assert automatic.json()["valid"] is False
    assert automatic.json()["details"]["object_choice_required"] is True

    payload = {**base_payload, "object_mode": "all"}
    plan = _post(application, "/api/workflows/plan-batch", payload)
    assert plan.status_code == 200
    assert plan.json()["valid"] is True
    assert "--all-objects" in plan.json()["command"]

    created = _post(application, "/api/execute/batch", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["summary"]["success"] == 4
    assert (output_dir / "a" / "book__Data.csv").is_file()
    assert (output_dir / "b" / "book__Lookup.csv").is_file()
    event_kinds = [event["kind"] for event in job["events"]]
    assert "batch_items_initialized" in event_kinds
    assert event_kinds.count("item_started") == 4
    assert event_kinds.count("item_finished") == 4


def test_batch_specific_object_command_warns_about_global_selector(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_xlsx(input_dir / "book.xlsx")
    response = _post(
        create_app(),
        "/api/workflows/plan-batch",
        {
            "input_path": str(input_dir),
            "output_path": str(tmp_path / "output"),
            "target_format": "csv",
            "create_dirs": True,
            "object_mode": "specific",
            "object_selector": "Data",
        },
    )
    assert response.status_code == 200
    assert "--object Data" in response.json()["command"]
    assert "applied to every input file" in response.json()["warnings"][0]


def test_local_path_browser_stays_under_confirmed_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / "data.csv").write_text("x\n1\n", encoding="utf-8")
    application = create_app(host="127.0.0.1")

    response = _post(
        application,
        "/api/files/browse",
        {
            "root_path": str(root),
            "directory": str(child),
            "selection": "file",
            "extensions": [".csv"],
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["parent"] == str(root.resolve())
    assert [entry["name"] for entry in response.json()["data"]["entries"]] == [
        "data.csv"
    ]

    outside = _post(
        application,
        "/api/files/browse",
        {
            "root_path": str(root),
            "directory": str(tmp_path),
            "selection": "directory",
            "extensions": [],
        },
    )
    assert outside.status_code == 400
    assert "outside the confirmed root" in outside.json()["error"]["message"]

    non_loopback = _post(
        create_app(host="0.0.0.0"),
        "/api/files/browse",
        {
            "root_path": str(root),
            "directory": str(root),
            "selection": "directory",
            "extensions": [],
        },
    )
    assert non_loopback.status_code == 400
    assert "local-only" in non_loopback.json()["error"]["message"]


def test_validate_normal_and_streaming_contract_requirement(
    csv_file: Path,
    tmp_path: Path,
) -> None:
    application = create_app()
    payload = {
        "path": str(csv_file),
        "strict": False,
        "stream": False,
    }
    plan = _post(application, "/api/workflows/plan-validate", payload)
    assert plan.status_code == 200

    created = _post(application, "/api/execute/validate", payload)
    job = _wait_for_job(application, created.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["passed"] is True

    missing_contract = _post(
        application,
        "/api/workflows/plan-validate",
        {**payload, "stream": True, "chunk_size": 2},
    )
    assert missing_contract.status_code == 400
    assert missing_contract.json()["error"]["code"] == "web_ui_request_error"
    assert "requires a schema contract" in missing_contract.json()["error"]["message"]

    contract = tmp_path / "contract.toml"
    contract.write_text(
        """
contract_version = 1
[dataset]
allow_extra_columns = true

[[columns]]
name = "id"
""".lstrip(),
        encoding="utf-8",
    )
    streaming_payload = {
        **payload,
        "stream": True,
        "chunk_size": 2,
        "schema_contract": str(contract),
    }
    created = _post(application, "/api/execute/validate", streaming_payload)
    streaming_job = _wait_for_job(application, created.json()["job_id"])

    assert streaming_job["status"] == "succeeded"
    assert streaming_job["result"]["streaming"]["chunks_processed"] == 2


def test_validate_job_returns_structured_issues(tmp_path: Path) -> None:
    path = tmp_path / "constant.csv"
    pd.DataFrame({"constant": [1, 1, 1], "empty": [None, None, None]}).to_csv(
        path,
        index=False,
    )
    application = create_app()
    created = _post(
        application,
        "/api/execute/validate",
        {"path": str(path), "strict": False, "stream": False},
    )
    job = _wait_for_job(application, created.json()["job_id"])

    assert job["status"] == "succeeded"
    assert job["result"]["issues"]
    assert set(job["result"]["issues"][0]) >= {
        "severity",
        "code",
        "column",
        "message",
    }


def test_g2_frontend_uses_specialized_inspect_and_validation_tables() -> None:
    root = Path(__file__).resolve().parents[1] / "ui-frontend" / "src"
    inspect_page = (root / "pages" / "InspectPage.tsx").read_text(encoding="utf-8")
    inspect_result = (root / "components" / "InspectResultView.tsx").read_text(
        encoding="utf-8"
    )
    result_view = (root / "components" / "ResultView.tsx").read_text(
        encoding="utf-8"
    )
    picker = (root / "components" / "PathPickerField.tsx").read_text(
        encoding="utf-8"
    )

    assert 'allowDirectorySelection={activeTab === "objects"}' in inspect_page
    assert "Browse file" in picker and "Browse folder" in picker
    assert "Metadata summary" in inspect_result
    assert "Column profiles" in inspect_result
    assert "Numeric statistics" in inspect_result
    assert "Categorical statistics" in inspect_result
    assert 'megabytes < 100' in inspect_result
    assert 'return `${megabytes.toFixed(1)} MB`' in inspect_result
    assert 'return `${(megabytes / 1024).toFixed(1)} GB`' in inspect_result
    assert "Not available" in inspect_result
    missing_order = inspect_result.index('{ key: "column", label: "Column" }')
    label_order = inspect_result.index('{ key: "label", label: "Label" }', missing_order)
    count_order = inspect_result.index(
        '{ key: "missing_count", label: "Missing" }',
        label_order,
    )
    assert missing_order < label_order < count_order
    assert "Validation issues" in result_view
    assert "No validation issues found." in result_view


def test_structured_errors_and_unknown_jobs(csv_file: Path) -> None:
    application = create_app()

    missing = _post(
        application,
        "/api/inspect/info",
        {"path": f"{csv_file}.missing"},
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "web_ui_request_error"
    assert "Traceback" not in missing.text

    invalid = _post(application, "/api/inspect/peek", {"path": str(csv_file), "rows": 0})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "request_validation_error"

    unknown = _request(application, "GET", "/api/jobs/not-a-job")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "job_not_found"
