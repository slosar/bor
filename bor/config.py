"""
Configuration management for Bor email reader.

Handles loading and parsing of the configuration file from ~/.config/bor.conf
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "bor.conf"


@dataclass
class GeneralConfig:
    """General configuration settings."""
    max_messages: int = 400
    date_format: str = "%Y-%m-%d %H:%M"
    short_date_format: str = "%m/%d"
    time_format: str = "%H:%M"
    theme: str = "textual-dark"


@dataclass
class FoldersConfig:
    """Maildir folder paths configuration."""
    inbox: str = "/INBOX"
    archive: str = "/Archive"
    drafts: str = "/Drafts"
    sent: str = "/Sent"
    trash: str = "/Trash"


@dataclass
class SmtpConfig:
    """SMTP server configuration."""
    server: str = "smtp.example.com"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_starttls: bool = True


@dataclass
class IdentityConfig:
    """User identity configuration."""
    name: str = ""
    email: str = ""
    organization: str = ""
    signature: str = ""


@dataclass
class ColorsConfig:
    """Color scheme configuration."""
    unread: str = "blue"
    important: str = "dark_orange"
    marked: str = "reverse"
    header: str = "bold"
    quoted: str = "italic dim"


@dataclass
class SyncConfig:
    """Synchronization command configuration."""
    command: str = "mbsync -a"


@dataclass
class ThreadingConfig:
    """Threading display configuration."""
    enabled: bool = True
    indicator: str = "↳"


@dataclass
class DisplayConfig:
    """Display settings configuration."""
    columns: List[str] = field(default_factory=lambda: ["date", "from", "subject", "flags"])
    date_width: int = 12
    from_width: int = 20
    subject_width: int = 0
    flags_width: int = 6
    flag_unread: str = "●"
    flag_replied: str = "↩"
    flag_forwarded: str = "→"
    flag_flagged: str = "⚑"
    flag_attachment: str = "📎"
    flag_encrypted: str = "🔒"
    flag_signed: str = "✓"


@dataclass
class HtmlConfig:
    """HTML rendering configuration."""
    renderer: str = "html2text"
    open_links_in_browser: bool = True
    browser_tmp_dir: str = ""


@dataclass
class AttachmentsConfig:
    """Attachments handling configuration."""
    save_directory: str = "~/Downloads"
    use_kitty_icat: bool = True


@dataclass
class EditorConfig:
    """Editor configuration."""
    external: str = ""


@dataclass
class Config:
    """Main configuration container."""
    general: GeneralConfig = field(default_factory=GeneralConfig)
    folders: FoldersConfig = field(default_factory=FoldersConfig)
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    colors: ColorsConfig = field(default_factory=ColorsConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    threading: ThreadingConfig = field(default_factory=ThreadingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    html: HtmlConfig = field(default_factory=HtmlConfig)
    attachments: AttachmentsConfig = field(default_factory=AttachmentsConfig)
    editor: EditorConfig = field(default_factory=EditorConfig)
    aliases: Dict[str, str] = field(default_factory=dict)
    email_aliases: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """
        Create a Config instance from a dictionary.

        Args:
            data: Configuration dictionary (typically from TOML file)

        Returns:
            Config instance with all settings populated
        """
        config = cls()

        if "general" in data:
            config.general = GeneralConfig(**data["general"])

        if "folders" in data:
            config.folders = FoldersConfig(**data["folders"])

        if "smtp" in data:
            config.smtp = SmtpConfig(**data["smtp"])

        if "identity" in data:
            config.identity = IdentityConfig(**data["identity"])

        if "colors" in data:
            config.colors = ColorsConfig(**data["colors"])

        if "sync" in data:
            config.sync = SyncConfig(**data["sync"])

        if "threading" in data:
            config.threading = ThreadingConfig(**data["threading"])

        if "display" in data:
            config.display = DisplayConfig(**data["display"])

        if "html" in data:
            config.html = HtmlConfig(**data["html"])

        if "attachments" in data:
            config.attachments = AttachmentsConfig(**data["attachments"])

        if "editor" in data:
            config.editor = EditorConfig(**data["editor"])

        if "aliases" in data:
            config.aliases = data["aliases"]

        if "email_aliases" in data:
            config.email_aliases = data["email_aliases"]

        return config


def load_config(path: Optional[Path] = None) -> Config:
    """
    Load configuration from file.

    Args:
        path: Path to configuration file. If None, uses default path.

    Returns:
        Config instance with loaded settings, or defaults if file not found.
    """
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return Config()

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return Config.from_dict(data)
    except Exception as e:
        print(f"Warning: Could not load config from {config_path}: {e}")
        return Config()


def load_mailrc_aliases() -> Dict[str, str]:
    """
    Load email aliases from ~/.mailrc file.

    Returns:
        Dictionary mapping alias names to email addresses.
    """
    mailrc_path = Path.home() / ".mailrc"
    aliases: Dict[str, str] = {}

    if not mailrc_path.exists():
        return aliases

    try:
        with open(mailrc_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("alias "):
                    parts = line[6:].split(None, 1)
                    if len(parts) == 2:
                        aliases[parts[0]] = parts[1]
    except Exception:
        pass

    return aliases


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Loads configuration from file on first call.

    Returns:
        Global Config instance.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    """
    Reload configuration from file.

    Returns:
        Updated global Config instance.
    """
    global _config
    _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config


def _parse_override_value(raw_value: str) -> Any:
    """Parse CLI override value using TOML scalar/array syntax when possible."""
    try:
        parsed = tomllib.loads(f"value = {raw_value}")
        return parsed["value"]
    except Exception:
        return raw_value


def apply_config_overrides(config: Config, overrides: List[str]) -> Config:
    """
    Apply CLI-style overrides to a config object.

    Overrides must be in the form ``section.option=value``.
    Example: ``general.max_messages=200``.
    """
    for override in overrides:
        if "=" not in override:
            raise ValueError(f"Invalid override '{override}': expected section.option=value")

        key_path, raw_value = override.split("=", 1)
        key_path = key_path.strip()
        raw_value = raw_value.strip()

        if "." not in key_path:
            raise ValueError(
                f"Invalid override key '{key_path}': expected section.option"
            )

        section_name, option_name = key_path.split(".", 1)

        if not hasattr(config, section_name):
            raise ValueError(f"Unknown config section '{section_name}'")

        section = getattr(config, section_name)

        if isinstance(section, dict):
            section[option_name] = _parse_override_value(raw_value)
            continue

        if not hasattr(section, option_name):
            raise ValueError(f"Unknown config option '{section_name}.{option_name}'")

        parsed_value = _parse_override_value(raw_value)
        setattr(section, option_name, parsed_value)

    return config
