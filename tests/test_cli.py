"""Tests for Bor command-line options."""

from unittest.mock import patch

from bor.app import main


def test_cli_version_prints_and_exits(capsys):
    """--version should print the version and avoid launching the TUI."""
    with patch("bor.app.BorApp") as app_cls:
        code = main(["--version"])

    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "0.7-dev"
    app_cls.assert_not_called()


def test_cli_set_override_applies_config_before_app_init():
    """--set override should be visible when BorApp initializes."""
    captured = {}

    class FakeApp:
        def __init__(self):
            from bor.config import get_config

            captured["max_messages"] = get_config().general.max_messages

        def run(self):
            return None

    with patch("bor.app.BorApp", FakeApp):
        code = main(["--set", "general.max_messages=77"])

    assert code == 0
    assert captured["max_messages"] == 77


def test_cli_theme_override_applies_before_app_init():
    """--set general.theme should be visible when BorApp initializes."""
    captured = {}

    class FakeApp:
        def __init__(self):
            from bor.config import get_config

            captured["theme"] = get_config().general.theme

        def run(self):
            return None

    with patch("bor.app.BorApp", FakeApp):
        code = main(["--set", "general.theme=nord"])

    assert code == 0
    assert captured["theme"] == "nord"
