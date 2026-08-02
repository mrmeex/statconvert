from datetime import datetime, timezone
from pathlib import Path

import pytest

from statconvert.reporting import DatasetReport, ReportIssue
from statconvert.ui.reporting import console, show_dataset_report_written


@pytest.mark.parametrize(
    ("issues", "warnings", "errors"),
    [
        ([], "no", "no"),
        ([ReportIssue("warning", "warning", "Warning")], "yes", "no"),
        ([ReportIssue("error", "error", "Error")], "no", "yes"),
    ],
)
def test_show_dataset_report_written_handles_issue_states(issues, warnings, errors):
    report = DatasetReport(
        "Report",
        generated_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        issues=issues,
    )
    with console.capture() as capture:
        show_dataset_report_written(report, "out/report.HTML")
    output = capture.get()
    assert "Dataset report written" in output
    assert str(Path("out/report.HTML")) in output
    assert "html" in output
    assert f"Warnings │ {warnings}" in output
    assert f"Errors   │ {errors}" in output
