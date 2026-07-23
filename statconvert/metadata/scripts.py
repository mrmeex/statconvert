from __future__ import annotations

from datetime import date, datetime
import math
from numbers import Number
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from statconvert.dataset import Dataset
from statconvert.exceptions import MetadataScriptError, OutputPathError


SCRIPT_EXTENSIONS = (".r", ".do", ".sps")
_STATA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SPSS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_@#$]*$")
_STATA_FORMAT = re.compile(r"^%[-0-9.,]*[A-Za-z]+$")
_SPSS_FORMAT = re.compile(r"^[A-Za-z][A-Za-z0-9.]*$")
_SPSS_LEVELS = {
    "nominal": "NOMINAL",
    "ordinal": "ORDINAL",
    "scale": "SCALE",
}


def export_metadata_script(
    dataset: Dataset,
    input_filename: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a deterministic best-effort helper script from resolved metadata."""

    input_path = Path(input_filename)
    target = Path(output_path)
    extension = target.suffix.lower()
    if extension not in SCRIPT_EXTENSIONS:
        raise MetadataScriptError(
            f"Unsupported script output format: {target.suffix or '(none)'}",
            suggestion="Use .R, .do, or .sps.",
        )
    if target.resolve(strict=False) == input_path.resolve(strict=False):
        raise OutputPathError(
            f"Metadata helper script path would replace the input file: {target}",
            suggestion="Choose a different script output path.",
        )
    _validate_output_path(target, overwrite=overwrite)

    renderers: dict[str, Callable[[Dataset, str], str]] = {
        ".r": render_r_script,
        ".do": render_stata_script,
        ".sps": render_spss_script,
    }
    text = renderers[extension](dataset, input_path.name)
    try:
        target.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise MetadataScriptError(
            f"Could not write metadata helper script: {target}. {exc}"
        ) from exc
    return target


def render_r_script(dataset: Dataset, source_name: str = "") -> str:
    """Render a base-R helper that assumes a data frame named ``df``."""

    dataset.sync_metadata()
    metadata = dataset.get_normalized_metadata()
    lines = _header(
        comment="#",
        source_name=source_name or str(dataset.source_file or ""),
        target="R",
        provenance_source=_metadata_source(dataset),
    )
    lines.extend(
        [
            "# Load your data before running this helper script.",
            "# Replace df with the name of your data frame if needed.",
            "",
        ]
    )
    if metadata.dataset_label:
        lines.append(f'attr(df, "label") <- {_r_string(metadata.dataset_label)}')
    if metadata.notes:
        notes = ", ".join(_r_string(note) for note in metadata.notes)
        lines.append(f'attr(df, "notes") <- c({notes})')

    unsupported: list[str] = []
    for dataframe_column in dataset.dataframe.columns:
        name = str(dataframe_column)
        variable = metadata.get_variable(name)
        if variable is None:
            continue
        reference = f"df[[{_r_string(name)}]]"
        if variable.label:
            lines.append(
                f'attr({reference}, "label") <- {_r_string(variable.label)}'
            )
        if variable.value_labels:
            entries = []
            for value, label in _sorted_items(variable.value_labels):
                literal = _r_literal(value)
                if literal is None:
                    unsupported.append(
                        f"{name}: value label key {_display(value)} is not a "
                        "simple R scalar."
                    )
                    continue
                entries.append(f"{_r_string(label)} = {literal}")
            if entries:
                lines.append(
                    f'attr({reference}, "labels") <- c({", ".join(entries)})'
                )
        _append_review_metadata(
            unsupported,
            name=name,
            missing_values=variable.missing_values,
            missing_ranges=variable.missing_ranges,
            measurement_level=variable.measure,
            display_format=variable.display_format,
        )

    unsupported.append(
        "Resolved metadata provenance is informational and is not assigned "
        "to R objects."
    )
    _append_review_section(lines, unsupported, comment="#")
    return "\n".join(lines).rstrip() + "\n"


def render_stata_script(dataset: Dataset, source_name: str = "") -> str:
    """Render a Stata do-file that assumes the dataset is already loaded."""

    dataset.sync_metadata()
    metadata = dataset.get_normalized_metadata()
    lines = _header(
        comment="*",
        source_name=source_name or str(dataset.source_file or ""),
        target="Stata",
        provenance_source=_metadata_source(dataset),
    )
    lines.extend(
        [
            "* Load your dataset before running this do-file.",
            "",
        ]
    )
    unsupported: list[str] = []
    if metadata.dataset_label:
        quoted = _stata_string(metadata.dataset_label)
        if quoted is None:
            unsupported.append(
                "Dataset label contains Stata quote/macro delimiters and was "
                "not emitted."
            )
        else:
            lines.append(f"label data {quoted}")
    for note in metadata.notes:
        quoted = _stata_string(note)
        if quoted is None:
            unsupported.append(
                "A dataset note contains Stata quote/macro delimiters and was "
                "not emitted."
            )
        else:
            lines.append(f"notes: {quoted}")

    for index, dataframe_column in enumerate(dataset.dataframe.columns, start=1):
        name = str(dataframe_column)
        variable = metadata.get_variable(name)
        if variable is None:
            continue
        if not _valid_stata_name(name):
            unsupported.append(
                f"{name}: invalid Stata variable name; rename it before "
                "applying metadata."
            )
            continue
        if variable.label:
            quoted = _stata_string(variable.label)
            if quoted is None:
                unsupported.append(
                    f"{name}: variable label contains Stata quote/macro "
                    "delimiters and was skipped."
                )
            else:
                lines.append(f"label variable {name} {quoted}")
        if variable.value_labels:
            entries = []
            for value, label in _sorted_items(variable.value_labels):
                literal = _stata_numeric_literal(value)
                if literal is None:
                    unsupported.append(
                        f"{name}: value label key {_display(value)} is not "
                        "numeric and was skipped."
                    )
                    continue
                quoted = _stata_string(label)
                if quoted is None:
                    unsupported.append(
                        f"{name}: value label for {literal} contains Stata "
                        "quote/macro delimiters and was skipped."
                    )
                    continue
                entries.append(f"{literal} {quoted}")
            if entries:
                label_name = _stata_label_name(name, index)
                lines.append(
                    f"label define {label_name} {' '.join(entries)}, replace"
                )
                lines.append(f"label values {name} {label_name}")
        if variable.display_format:
            if _STATA_FORMAT.fullmatch(variable.display_format):
                lines.append(f"format {name} {variable.display_format}")
            else:
                unsupported.append(
                    f"{name}: display format {variable.display_format!r} is "
                    "not recognized as Stata-compatible."
                )
        if variable.measure:
            unsupported.append(
                f"{name}: measurement level {variable.measure!r} has no "
                "direct Stata command in this helper."
            )
        if variable.missing_values or variable.missing_ranges:
            unsupported.append(
                f"{name}: user-defined missing metadata requires manual "
                "review in Stata."
            )

    unsupported.append(
        "Resolved metadata provenance is informational and is not represented "
        "by Stata label commands."
    )
    _append_review_section(lines, unsupported, comment="*")
    return "\n".join(lines).rstrip() + "\n"


def render_spss_script(dataset: Dataset, source_name: str = "") -> str:
    """Render SPSS syntax that assumes the dataset is already active."""

    dataset.sync_metadata()
    metadata = dataset.get_normalized_metadata()
    lines = _header(
        comment="*",
        source_name=source_name or str(dataset.source_file or ""),
        target="SPSS",
        provenance_source=_metadata_source(dataset),
        terminator=".",
    )
    lines.extend(
        [
            "* Load or activate your dataset before running this syntax.",
            "",
        ]
    )
    unsupported: list[str] = []
    if metadata.dataset_label:
        unsupported.append(
            f"Dataset label: {_comment_text(metadata.dataset_label)}"
        )
    for note in metadata.notes:
        unsupported.append(f"Dataset note: {_comment_text(note)}")

    for dataframe_column in dataset.dataframe.columns:
        name = str(dataframe_column)
        variable = metadata.get_variable(name)
        if variable is None:
            continue
        if not _valid_spss_name(name):
            unsupported.append(
                f"{name}: invalid SPSS variable name; rename it before "
                "applying metadata."
            )
            continue
        if variable.label:
            lines.append(
                f"VARIABLE LABELS {name} {_spss_string(variable.label)}."
            )
        if variable.value_labels:
            entries = []
            for value, label in _sorted_items(variable.value_labels):
                literal = _spss_literal(value)
                if literal is None:
                    unsupported.append(
                        f"{name}: value label key {_display(value)} is not a "
                        "simple SPSS scalar and was skipped."
                    )
                    continue
                entries.append(f"  {literal} {_spss_string(label)}")
            if entries:
                lines.extend(
                    [
                        f"VALUE LABELS {name}",
                        *entries,
                        ".",
                    ]
                )
        if variable.missing_values:
            literals = [
                _spss_literal(value) for value in variable.missing_values
            ]
            if (
                not variable.missing_ranges
                and len(literals) <= 3
                and all(literal is not None for literal in literals)
            ):
                lines.append(
                    f"MISSING VALUES {name} ({' '.join(literals)})."
                )
            else:
                unsupported.append(
                    f"{name}: user-defined missing values require manual "
                    "review in SPSS."
                )
        if variable.missing_ranges:
            unsupported.append(
                f"{name}: missing ranges require manual review in SPSS."
            )
        if variable.measure:
            level = _SPSS_LEVELS.get(variable.measure.lower())
            if level:
                lines.append(f"VARIABLE LEVEL {name} ({level}).")
            elif variable.measure.lower() != "unknown":
                unsupported.append(
                    f"{name}: measurement level {variable.measure!r} is not "
                    "mapped to SPSS syntax."
                )
        if variable.display_format:
            if _SPSS_FORMAT.fullmatch(variable.display_format):
                lines.append(f"FORMATS {name} ({variable.display_format}).")
            else:
                unsupported.append(
                    f"{name}: display format {variable.display_format!r} is "
                    "not recognized as SPSS-compatible."
                )

    unsupported.append(
        "Resolved metadata provenance is informational and is not represented "
        "by SPSS syntax."
    )
    _append_review_section(lines, unsupported, comment="*", terminator=".")
    return "\n".join(lines).rstrip() + "\n"


def _header(
    *,
    comment: str,
    source_name: str,
    target: str,
    provenance_source: str,
    terminator: str = "",
) -> list[str]:
    source = _comment_text(Path(source_name).name) if source_name else "(unknown)"
    return [
        _comment_line(comment, "Generated by StatConvert", terminator),
        _comment_line(comment, f"Source dataset: {source}", terminator),
        _comment_line(
            comment,
            f"Resolved metadata source: {provenance_source or '(unknown)'}",
            terminator,
        ),
        _comment_line(
            comment,
            f"Target: {target} metadata helper script",
            terminator,
        ),
        _comment_line(
            comment,
            "Generated from resolved metadata; review before running",
            terminator,
        ),
        _comment_line(
            comment,
            "This helper does not modify or save a data file",
            terminator,
        ),
        "",
    ]


def _append_review_metadata(
    unsupported: list[str],
    *,
    name: str,
    missing_values: list[Any],
    missing_ranges: list[dict[str, Any]],
    measurement_level: str | None,
    display_format: str | None,
) -> None:
    if missing_values or missing_ranges:
        unsupported.append(
            f"{name}: user-defined missing metadata is not assigned by the "
            "base-R helper."
        )
    if measurement_level:
        unsupported.append(
            f"{name}: measurement level {measurement_level!r} has no base-R "
            "standard and was not assigned."
        )
    if display_format:
        unsupported.append(
            f"{name}: display format {display_format!r} is target-specific "
            "and was not assigned."
        )


def _append_review_section(
    lines: list[str],
    items: list[str],
    *,
    comment: str,
    terminator: str = "",
) -> None:
    lines.extend(
        [
            "",
            _comment_line(
                comment,
                "Unsupported or review-required metadata",
                terminator,
            ),
        ]
    )
    for item in items:
        lines.append(_comment_line(comment, f"- {item}", terminator))


def _comment_line(comment: str, value: Any, terminator: str) -> str:
    text = _comment_text(value)
    if terminator == ".":
        text = text.replace(".", "(dot)")
    return f"{comment} {text}{terminator}"


def _metadata_source(dataset: Dataset) -> str:
    provenance = dataset.metadata_provenance or {}
    return _comment_text(provenance.get("dataset") or "primary_file")


def _validate_output_path(target: Path, *, overwrite: bool) -> None:
    parent = target.parent
    if parent != Path(".") and not parent.exists():
        raise OutputPathError(
            f"Parent folder does not exist: {parent}",
            suggestion="Create the folder first.",
        )
    if parent.exists() and not parent.is_dir():
        raise OutputPathError(
            f"Parent path is not a folder: {parent}",
            suggestion="Choose a script path whose parent is a folder.",
        )
    if target.exists() and not overwrite:
        raise OutputPathError(
            f"Metadata helper script already exists: {target}",
            suggestion=(
                "Use --overwrite-script to replace it, or choose a different "
                "path."
            ),
        )


def _valid_stata_name(value: str) -> bool:
    return len(value) <= 32 and _STATA_NAME.fullmatch(value) is not None


def _valid_spss_name(value: str) -> bool:
    return len(value) <= 64 and _SPSS_NAME.fullmatch(value) is not None


def _stata_label_name(variable_name: str, position: int) -> str:
    prefix = f"scvl_{position}_"
    return f"{prefix}{variable_name}"[:32]


def _sorted_items(values: Mapping[Any, Any]) -> list[tuple[Any, Any]]:
    return sorted(
        values.items(),
        key=lambda item: (type(item[0]).__name__, _display(item[0])),
    )


def _r_string(value: Any) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _r_literal(value: Any) -> str | None:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if _is_finite_number(value):
        return _number_text(value)
    if isinstance(value, (str, date, datetime)):
        return _r_string(value.isoformat() if hasattr(value, "isoformat") else value)
    return None


def _stata_string(value: Any) -> str | None:
    text = _one_line(value)
    if "`" in text or "\"'" in text:
        return None
    return f'`"{text}"\''


def _stata_numeric_literal(value: Any) -> str | None:
    if isinstance(value, bool) or not _is_finite_number(value):
        return None
    return _number_text(value)


def _spss_string(value: Any) -> str:
    return f"'{_one_line(value).replace(chr(39), chr(39) * 2)}'"


def _spss_literal(value: Any) -> str | None:
    if isinstance(value, bool):
        return "1" if value else "0"
    if _is_finite_number(value):
        return _number_text(value)
    if isinstance(value, (str, date, datetime)):
        text = value.isoformat() if hasattr(value, "isoformat") else value
        return _spss_string(text)
    return None


def _is_finite_number(value: Any) -> bool:
    if not isinstance(value, Number):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _number_text(value: Any) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return format(numeric, ".15g")


def _display(value: Any) -> str:
    if isinstance(value, (str, date, datetime)):
        text = value.isoformat() if hasattr(value, "isoformat") else value
        return repr(_one_line(text))
    return repr(value)


def _one_line(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _comment_text(value: Any) -> str:
    return _one_line(value).replace("\t", " ")
