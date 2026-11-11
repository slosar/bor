"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest

from bor.config import (
    apply_config_overrides,
    Config,
    GeneralConfig,
    FoldersConfig,
    SmtpConfig,
    load_config,
)


def test_default_config():
    """Test that default config is created correctly."""
    config = Config()
    assert config.general.max_messages == 400
    assert config.general.theme == "textual-dark"
    assert config.folders.inbox == "/INBOX"
    assert config.smtp.port == 587
    assert config.attachments.force_kitty_support is False


def test_config_from_dict():
    """Test creating config from dictionary."""
    data = {
        "general": {
            "max_messages": 200,
            "date_format": "%d/%m/%Y",
        },
        "folders": {
            "inbox": "/Mail/Inbox",
        },
        "attachments": {
            "force_kitty_support": True,
        },
    }

    config = Config.from_dict(data)
    assert config.general.max_messages == 200
    assert config.general.date_format == "%d/%m/%Y"
    assert config.folders.inbox == "/Mail/Inbox"
    assert config.attachments.force_kitty_support is True
    # Default values should be preserved
    assert config.folders.archive == "/Archive"


def test_load_config_missing_file():
    """Test loading config when file doesn't exist."""
    config = load_config(Path("/nonexistent/path/bor.conf"))
    # Should return defaults
    assert config.general.max_messages == 400


def test_load_config_from_file():
    """Test loading config from a TOML file."""
    toml_content = """
[general]
max_messages = 100
theme = "nord"

[folders]
inbox = "/MyInbox"
archive = "/MyArchive"

[smtp]
server = "mail.example.com"
port = 465

[attachments]
force_kitty_support = true

[aliases]
t = "Thanks!"
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(toml_content)
        f.flush()
        
        config = load_config(Path(f.name))
        
        assert config.general.max_messages == 100
        assert config.general.theme == "nord"
        assert config.folders.inbox == "/MyInbox"
        assert config.smtp.server == "mail.example.com"
        assert config.smtp.port == 465
        assert config.attachments.force_kitty_support is True
        assert config.aliases.get("t") == "Thanks!"


def test_general_config_defaults():
    """Test GeneralConfig defaults."""
    general = GeneralConfig()
    assert general.max_messages == 400
    assert general.date_format == "%Y-%m-%d %H:%M"
    assert general.short_date_format == "%m/%d"
    assert general.time_format == "%H:%M"
    assert general.theme == "textual-dark"


def test_folders_config_defaults():
    """Test FoldersConfig defaults."""
    folders = FoldersConfig()
    assert folders.inbox == "/INBOX"
    assert folders.archive == "/Archive"
    assert folders.drafts == "/Drafts"
    assert folders.sent == "/Sent"
    assert folders.trash == "/Trash"


def test_apply_config_overrides_basic_types():
    """Test applying CLI overrides with common value types."""
    config = Config()

    apply_config_overrides(
        config,
        [
            "general.max_messages=123",
            "threading.enabled=false",
            "folders.inbox=/MyInbox",
        ],
    )

    assert config.general.max_messages == 123
    assert config.threading.enabled is False
    assert config.folders.inbox == "/MyInbox"


def test_apply_config_overrides_dict_section():
    """Test applying overrides to dictionary-backed config sections."""
    config = Config()

    apply_config_overrides(config, ["aliases.ty=Thanks!"])

    assert config.aliases["ty"] == "Thanks!"


def test_apply_config_overrides_invalid_key_errors():
    """Test invalid override key raises ValueError."""
    config = Config()

    with pytest.raises(ValueError):
        apply_config_overrides(config, ["general=100"])

    with pytest.raises(ValueError):
        apply_config_overrides(config, ["unknown.value=1"])

    with pytest.raises(ValueError):
        apply_config_overrides(config, ["general.unknown=1"])


def test_unknown_option_is_skipped_not_fatal():
    """A misspelled option must not throw away the rest of the configuration."""
    config = Config.from_dict(
        {
            "general": {"max_messages": 50, "max_mesages": 10},
            "colors": {"flagged": "red", "unread": "green"},
        }
    )

    assert config.general.max_messages == 50
    assert config.colors.unread == "green"
    assert config.warnings == [
        "Unknown config option general.max_mesages ignored",
        "Unknown config option colors.flagged ignored",
    ]


def test_unknown_and_malformed_sections_are_reported():
    config = Config.from_dict({"keybindings": {"x": "y"}, "general": 5, "aliases": {"r": "Hi"}})

    assert config.aliases == {"r": "Hi"}
    assert config.general.max_messages == 400
    assert config.warnings == [
        "Unknown config section [keybindings] ignored",
        "[general] must be a table; using defaults",
    ]


def test_warnings_is_not_a_config_section():
    config = Config.from_dict({"warnings": {"a": 1}})

    assert config.warnings == ["Unknown config section [warnings] ignored"]


def test_unparseable_file_reports_warning(tmp_path):
    path = tmp_path / "bor.conf"
    path.write_text("[general\nmax_messages = 1\n")

    config = load_config(path)

    assert config.general.max_messages == 400
    assert len(config.warnings) == 1
    assert config.warnings[0].startswith(f"Could not load {path}:")


async def test_app_shows_config_warnings():
    from unittest.mock import MagicMock, patch

    from bor.app import BorApp

    config = Config.from_dict({"general": {"theme": "no-such-theme", "bogus": 1}})
    mu = MagicMock()
    mu.find.return_value = []
    with patch("bor.app.get_config", return_value=config):
        with patch("bor.app.MuInterface", return_value=mu):
            with patch.object(BorApp, "notify") as notify:
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()

    shown = [call.args[0] for call in notify.call_args_list]
    assert "Unknown config option general.bogus ignored" in shown
    assert "Unknown theme 'no-such-theme'; using 'textual-dark'" in shown


def test_invalid_row_colors_fall_back_to_defaults():
    config = Config.from_dict({"colors": {"important": "orange", "unread": "#00ff00"}})

    assert config.colors.important == "dark_orange"
    assert config.colors.unread == "#00ff00"
    assert config.warnings == ["Invalid color 'orange' for colors.important; using 'dark_orange'"]


def test_invalid_color_override_falls_back_to_default():
    config = Config()

    apply_config_overrides(config, ["colors.unread=nocolor"])

    assert config.colors.unread == "blue"
    assert config.warnings == ["Invalid color 'nocolor' for colors.unread; using 'blue'"]
