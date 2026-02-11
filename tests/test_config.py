"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest

from bor.config import (
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
    assert config.folders.inbox == "/INBOX"
    assert config.smtp.port == 587


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
    }

    config = Config.from_dict(data)
    assert config.general.max_messages == 200
    assert config.general.date_format == "%d/%m/%Y"
    assert config.folders.inbox == "/Mail/Inbox"
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

[folders]
inbox = "/MyInbox"
archive = "/MyArchive"

[smtp]
server = "mail.example.com"
port = 465

[aliases]
t = "Thanks!"
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(toml_content)
        f.flush()
        
        config = load_config(Path(f.name))
        
        assert config.general.max_messages == 100
        assert config.folders.inbox == "/MyInbox"
        assert config.smtp.server == "mail.example.com"
        assert config.smtp.port == 465
        assert config.aliases.get("t") == "Thanks!"


def test_general_config_defaults():
    """Test GeneralConfig defaults."""
    general = GeneralConfig()
    assert general.max_messages == 400
    assert general.date_format == "%Y-%m-%d %H:%M"
    assert general.short_date_format == "%m/%d"
    assert general.time_format == "%H:%M"


def test_folders_config_defaults():
    """Test FoldersConfig defaults."""
    folders = FoldersConfig()
    assert folders.inbox == "/INBOX"
    assert folders.archive == "/Archive"
    assert folders.drafts == "/Drafts"
    assert folders.sent == "/Sent"
    assert folders.trash == "/Trash"
