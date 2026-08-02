from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from statconvert.config import (
    SUPPORTED_COMMANDS,
    config_from_options,
    create_template,
    load_config,
    to_toml,
    write_config,
)
from statconvert.exceptions import ConfigError


def test_valid_toml_loads(tmp_path: Path) -> None:
    path = tmp_path / "workflow.toml"
    path.write_text(
        'command = "batch"\ninput = "in"\noutput = "out"\nto = "csv"\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.command == "batch"
    assert config.options["to"] == "csv"


def test_missing_file_fails_friendly(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file does not exist"):
        load_config(tmp_path / "missing.toml")


def test_invalid_toml_fails_friendly(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('command = "batch"\nworkers = [', encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(path)


@pytest.mark.parametrize("command", SUPPORTED_COMMANDS)
def test_generated_templates_round_trip(command: str) -> None:
    template = create_template(command)

    parsed = tomllib.loads(to_toml(template))

    assert parsed == template.to_dict()


def test_toml_writer_escapes_strings_and_map_keys() -> None:
    config = config_from_options(
        "transform",
        input='input "quoted".csv',
        output="line\nbreak.csv",
        rename={"old key": 'new "value"'},
    )

    parsed = tomllib.loads(to_toml(config))

    assert parsed["input"] == 'input "quoted".csv'
    assert parsed["output"] == "line\nbreak.csv"
    assert parsed["steps"][0]["map"] == {"old key": 'new "value"'}


def test_toml_output_order_is_deterministic() -> None:
    first = config_from_options(
        "batch",
        workers=2,
        to="csv",
        output="out",
        input="in",
    )
    second = config_from_options(
        "batch",
        input="in",
        output="out",
        to="csv",
        workers=2,
    )

    assert to_toml(first) == to_toml(second)


def test_none_options_are_omitted() -> None:
    config = config_from_options(
        "convert",
        input="in.csv",
        output="out.csv",
        object=None,
    )

    assert "object" not in config.options


def test_cli_option_names_are_serialized_to_config_fields() -> None:
    config = config_from_options(
        "batch",
        input_path="in",
        output_path="out",
        to_format="csv",
        object_selector=None,
        validate_inputs=True,
        workers=1,
    )

    assert config.to_dict() == {
        "command": "batch",
        "input": "in",
        "output": "out",
        "to": "csv",
        "validate": True,
        "workers": 1,
    }


def test_inline_map_keys_are_written_in_deterministic_order() -> None:
    config = config_from_options(
        "transform",
        input="in.csv",
        output="out.csv",
        rename={"z": "last", "a": "first"},
    )

    text = to_toml(config)
    assert "[[steps]]" in text
    assert '[steps.map]\na = "first"\nz = "last"' in text


def test_write_config_honors_output_safety(tmp_path: Path) -> None:
    path = tmp_path / "workflow.toml"
    write_config(create_template("convert"), path)

    with pytest.raises(Exception, match="already exists"):
        write_config(create_template("convert"), path)

    write_config(create_template("batch"), path, overwrite=True)
    assert load_config(path).command == "batch"
