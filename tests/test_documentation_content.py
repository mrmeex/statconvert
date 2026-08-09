from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_FILES = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "pyproject.toml",
    *(PROJECT_ROOT / "docs").rglob("*.md"),
)

PROHIBITED_PATTERNS = {
    "removed report format": re.compile(r"\bpd" + r"f\b", re.IGNORECASE),
    "removed container distribution": re.compile(
        r"\bdock" + r"er\b", re.IGNORECASE
    ),
    "removed package-index publishing": re.compile(
        r"\bpyp" + r"i\b", re.IGNORECASE
    ),
    "removed bundled application": re.compile(
        r"\bstandalone\s+execut" + r"able\b", re.IGNORECASE
    ),
}
R_WORKSPACE_PATTERN = re.compile(r"\b(?:rdata|rda)\b", re.IGNORECASE)
OUTPUT_PATTERN = re.compile(
    r"\b(?:output|outputs|write|writes|writing|destination|target|targets)\b",
    re.IGNORECASE,
)


def test_public_documentation_excludes_removed_topics() -> None:
    failures: list[str] = []

    for path in DOCUMENTATION_FILES:
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(PROJECT_ROOT)

        for label, pattern in PROHIBITED_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{relative_path}: {label}")

        for paragraph in re.split(r"\n\s*\n", text):
            normalized = " ".join(paragraph.split())
            if (
                R_WORKSPACE_PATTERN.search(normalized)
                and "multi-object" in normalized.casefold()
                and OUTPUT_PATTERN.search(normalized)
            ):
                failures.append(
                    f"{relative_path}: removed R workspace output roadmap topic"
                )
                break

    assert not failures, "\n".join(failures)


def test_public_docs_describe_metadata_release_boundaries() -> None:
    public_docs = "\n".join(
        (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/formats.md",
            "docs/user-guide.md",
            "docs/ui.md",
            "docs/examples.md",
        )
    )

    assert "--diagnose" in public_docs
    assert "--validate-sidecar" in public_docs
    assert "metadata-diff" in public_docs
    assert "--patch" in public_docs
    assert "--dry-run" in public_docs
    assert "native metadata are never" in public_docs
    assert "Missing values/ranges, display formats" in public_docs
    assert "Container editing is currently refused" in public_docs
    assert "database files, ORC" in public_docs
