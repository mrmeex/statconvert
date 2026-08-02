from importlib.metadata import PackageNotFoundError

from typer.testing import CliRunner

from statconvert.cli import app
import statconvert.version as version_module


runner = CliRunner()


def test_version_command_reports_application_python_and_dependencies() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    expected_labels = (
        "StatConvert",
        "Python",
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
    )

    assert [line.split(":", maxsplit=1)[0] for line in result.output.splitlines()] == [
        *expected_labels
    ]


def test_version_command_is_plain_text() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.output
    assert "[bold" not in result.output
    assert "[green" not in result.output


def test_help_still_lists_version_option() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--version" in result.output


def test_missing_dependency_is_reported_without_import_error(monkeypatch) -> None:
    def missing_metadata(package_name: str) -> str:
        raise PackageNotFoundError(package_name)

    def missing_import(module_name: str):
        raise ModuleNotFoundError(module_name)

    monkeypatch.setattr(version_module, "metadata_version", missing_metadata)
    monkeypatch.setattr(version_module, "import_module", missing_import)

    statuses = dict(version_module.get_runtime_dependency_status())

    assert statuses["pyreadstat"] == "not installed"


def test_dependency_without_metadata_is_reported_as_installed(monkeypatch) -> None:
    def missing_metadata(package_name: str) -> str:
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(version_module, "metadata_version", missing_metadata)
    monkeypatch.setattr(version_module, "import_module", lambda module_name: object())

    statuses = dict(version_module.get_runtime_dependency_status())

    assert statuses["odfpy"] == "installed"
