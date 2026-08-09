from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import json
from pathlib import Path
from typing import Any

from statconvert.exceptions import MetadataDiagnosticsError
from statconvert.metadata.comparison import MetadataDiffResult
from statconvert.serialization import make_json_safe


SUPPORTED_METADATA_REPORT_FORMATS = {"csv", "json", "html"}


def write_metadata_diff_report(
    result: MetadataDiffResult,
    report_file: str | Path,
    report_format: str | None = None,
) -> Path:
    path = Path(report_file)
    report_format = (report_format or path.suffix).lower().lstrip(".")
    if report_format not in SUPPORTED_METADATA_REPORT_FORMATS:
        raise MetadataDiagnosticsError(
            "Unsupported metadata report format. Use a .csv, .json or .html file."
        )
    try:
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        if report_format == "json":
            path.write_text(
                json.dumps(make_json_safe(asdict(result)), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        elif report_format == "csv":
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("column", "field", "left", "right"))
                writer.writeheader()
                for change in result.changes:
                    writer.writerow({
                        "column": change.column or "",
                        "field": change.field,
                        "left": _cell(change.left),
                        "right": _cell(change.right),
                    })
        else:
            rows = "".join(
                "<tr>" + "".join(
                    f"<td>{escape(str(_cell(value)))}</td>"
                    for value in (change.column or "", change.field, change.left, change.right)
                ) + "</tr>"
                for change in result.changes
            )
            path.write_text(
                "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                "<title>StatConvert Metadata Diff</title><style>body{font-family:Arial,sans-serif;"
                "max-width:1100px;margin:2rem auto}table{border-collapse:collapse;width:100%}"
                "th,td{border:1px solid #ccc;padding:.45rem;text-align:left}</style></head><body>"
                f"<h1>Metadata Diff</h1><p>Same metadata: {result.same_metadata}</p>"
                f"<p>Changes: {result.total_changes} (showing {result.shown_changes})</p>"
                "<table><thead><tr><th>Column</th><th>Field</th><th>Left</th><th>Right</th>"
                f"</tr></thead><tbody>{rows}</tbody></table></body></html>\n",
                encoding="utf-8",
            )
    except OSError as exc:
        raise MetadataDiagnosticsError(f"Unable to write metadata report '{path}': {exc}") from exc
    return path


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(make_json_safe(value), ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else value
