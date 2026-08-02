from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tomllib

import typer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_LOGGING_DIR = PROJECT_ROOT / "statconvert" / "logging"
LICENSE_EXPRESSION = "AGPL-3.0-or-later"
CURRENT_RELEASED_VERSION = "1.0.0"
BASE_RUNTIME_DEPENDENCY_COUNT = 11
REQUIRED_DOCS_DEPENDENCIES = {
    "mkdocs>=1.6,<2",
    "mkdocs-material>=9.6,<10",
}
REQUIRED_PUBLIC_DOCS = {
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "docs/index.md",
    "docs/cli.md",
    "docs/formats.md",
    "docs/examples.md",
    "docs/user-guide.md",
    "docs/ui.md",
    "docs/license.md",
}


def _run_python(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the current Python interpreter from the canonical project root."""

    return subprocess.run(
        [sys.executable, *arguments],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_stdlib_logging_path(output: str) -> None:
    """Assert that an import resolved outside StatConvert's logging package."""

    logging_path = Path(output.strip()).resolve()
    package_logging_path = PACKAGE_LOGGING_DIR.resolve()

    assert logging_path.name == "__init__.py"
    assert logging_path.parent.name == "logging"
    assert str(package_logging_path).casefold() not in str(logging_path).casefold()


def test_stdlib_logging_imports_before_statconvert() -> None:
    result = _run_python(
        "-c",
        "import logging; print(logging.__file__)",
    )

    assert result.returncode == 0, result.stderr
    _assert_stdlib_logging_path(result.stdout)


def test_stdlib_logging_imports_after_statconvert() -> None:
    result = _run_python(
        "-c",
        "import statconvert; import logging; print(logging.__file__)",
    )

    assert result.returncode == 0, result.stderr
    _assert_stdlib_logging_path(result.stdout)


def test_statconvert_package_imports() -> None:
    import statconvert

    package_path = Path(statconvert.__file__).resolve()

    assert package_path.parent == PROJECT_ROOT / "statconvert"


def test_cli_module_imports() -> None:
    import statconvert.cli

    assert statconvert.cli.__name__ == "statconvert.cli"


def test_cli_module_exposes_typer_app() -> None:
    from statconvert import cli

    assert isinstance(cli.app, typer.Typer)


def test_python_module_entry_point_shows_help() -> None:
    result = _run_python(
        "-m",
        "statconvert",
        "--help",
    )

    assert result.returncode == 0, result.stderr
    assert "Universal statistical data converter" in result.stdout
    assert "convert" in result.stdout


def test_python_module_entry_point_shows_version_status() -> None:
    result = _run_python(
        "-m",
        "statconvert",
        "--version",
    )

    assert result.returncode == 0, result.stderr
    assert "StatConvert:" in result.stdout
    assert "Python:" in result.stdout
    assert "pandas:" in result.stdout


def test_project_version_matches_current_release() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["version"] == CURRENT_RELEASED_VERSION


def test_pytest_starts_from_canonical_project_root() -> None:
    result = _run_python(
        "-m",
        "pytest",
        "--version",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("pytest ")


def test_pyproject_declares_package_and_console_entry_point() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["name"] == "statconvert"
    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert pyproject["project"]["scripts"]["statconvert"] == "statconvert.cli:app"
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "statconvert*"
    ]
    assert set(pyproject["project"]["optional-dependencies"]) == {"ui"}
    assert pyproject["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert pyproject["tool"]["pytest"]["ini_options"]["pythonpath"] == ["."]


def test_ui_dependencies_are_optional_and_packaged_assets_are_declared() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    project = pyproject["project"]
    ui_dependencies = set(project["optional-dependencies"]["ui"])

    assert len(project["dependencies"]) == BASE_RUNTIME_DEPENDENCY_COUNT
    assert ui_dependencies == {
        "fastapi>=0.141,<1",
        "uvicorn>=0.52,<1",
    }
    assert ui_dependencies.isdisjoint(project["dependencies"])
    assert pyproject["tool"]["setuptools"]["package-data"]["statconvert.webui"] == [
        "static/*",
        "static/assets/*",
    ]


def test_bundled_webui_assets_exist() -> None:
    static_dir = PROJECT_ROOT / "statconvert" / "webui" / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    assets = list((static_dir / "assets").iterdir())

    assert "StatConvert" in index_html
    assert any(asset.suffix == ".js" for asset in assets)
    assert any(asset.suffix == ".css" for asset in assets)


def test_project_declares_agpl_license_metadata() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["license"] == LICENSE_EXPRESSION
    assert pyproject["project"]["license-files"] == ["LICENSE"]
    assert "setuptools>=77" in pyproject["build-system"]["requires"]


def test_official_agpl_license_text_is_present() -> None:
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 19 November 2007" in license_text
    assert "Copyright (C) 2007 Free Software Foundation, Inc." in license_text
    assert "13. Remote Network Interaction; Use with the GNU General Public License." in (
        license_text
    )
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert "How to Apply These Terms to Your New Programs" in license_text


def test_license_documentation_uses_spdx_expression() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    license_guide = (PROJECT_ROOT / "docs" / "license.md").read_text(
        encoding="utf-8"
    )

    assert LICENSE_EXPRESSION in readme
    assert "[LICENSE](LICENSE)" in readme
    assert LICENSE_EXPRESSION in license_guide
    assert "LICENSE" in license_guide
    assert "License to be determined" not in readme


def test_advertised_format_dependencies_are_normal_runtime_dependencies() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    declared_names = {
        requirement.split(">=", maxsplit=1)[0].casefold()
        for requirement in pyproject["project"]["dependencies"]
    }

    assert declared_names == {
        "pandas",
        "typer",
        "rich",
        "openpyxl",
        "xlsxwriter",
        "xlrd",
        "xlwt",
        "pyreadstat",
        "pyarrow",
        "pyreadr",
        "odfpy",
    }


def test_build_tool_is_a_development_dependency() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    development_dependencies = pyproject["dependency-groups"]["dev"]

    assert any(requirement.startswith("build>=") for requirement in development_dependencies)
    assert not any(
        requirement.startswith("build>=")
        for requirement in pyproject["project"]["dependencies"]
    )


def test_docs_dependency_group_supports_public_pages_workflow() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    dependency_groups = pyproject["dependency-groups"]

    assert "docs" in dependency_groups
    assert REQUIRED_DOCS_DEPENDENCIES <= set(dependency_groups["docs"])
    assert not (
        REQUIRED_DOCS_DEPENDENCIES & set(pyproject["project"]["dependencies"])
    )


def test_ui_guide_is_public_safe_and_integrated() -> None:
    guide = (PROJECT_ROOT / "docs" / "ui.md").read_text(encoding="utf-8")
    user_guide = (PROJECT_ROOT / "docs" / "user-guide.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "## Install the UI",
        "## Local-only operation and privacy",
        "## Inspect",
        "## Convert",
        "## Batch Convert",
        "## Validate",
        "## Transform",
        "## Configs",
        "## Compare",
        "## Report",
        "## Collect",
        "## Settings",
        "## Troubleshooting",
    ):
        assert heading in guide
    assert 'python -m pip install "statconvert[ui]"' in guide
    assert "input_file,input_object,output_object" in guide
    assert "D:" + "\\Projects" not in guide
    assert "statconvert" + "-dev" not in guide
    assert "[Browser UI Guide](ui.md)" in user_guide


def test_required_public_documentation_is_present() -> None:
    for relative_path in REQUIRED_PUBLIC_DOCS:
        assert (PROJECT_ROOT / relative_path).is_file(), relative_path
