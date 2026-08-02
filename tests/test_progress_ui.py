from __future__ import annotations

from statconvert.ui.console import encoding_supports_unicode
from statconvert.ui.progress import spinner_name_for_encoding


def test_spinner_uses_unicode_only_for_utf_output() -> None:
    assert spinner_name_for_encoding("utf-8") == "dots"
    assert spinner_name_for_encoding("UTF_8_SIG") == "dots"
    assert spinner_name_for_encoding("cp65001") == "dots"


def test_spinner_falls_back_to_ascii_for_legacy_or_unknown_output() -> None:
    assert spinner_name_for_encoding("cp1252") == "line"
    assert spinner_name_for_encoding(None) == "line"


def test_unicode_status_symbols_follow_output_encoding() -> None:
    assert encoding_supports_unicode("utf-8") is True
    assert encoding_supports_unicode("cp1252") is False
    assert encoding_supports_unicode("not-an-encoding") is False
