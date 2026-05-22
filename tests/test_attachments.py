"""Tests for attachment preview behavior."""

from bor.config import Config
from bor.tabs.attachments import _supports_kitty_graphics


def test_kitty_graphics_detected_from_term(monkeypatch):
    """Kitty graphics are enabled automatically in kitty."""
    monkeypatch.setenv("TERM", "xterm-kitty")

    assert _supports_kitty_graphics(Config()) is True


def test_kitty_graphics_disabled_for_other_terms_by_default(monkeypatch):
    """Kitty graphics stay disabled outside kitty by default."""
    monkeypatch.setenv("TERM", "xterm-256color")

    assert _supports_kitty_graphics(Config()) is False


def test_kitty_graphics_can_be_forced(monkeypatch):
    """Configuration can force Kitty graphics regardless of TERM."""
    monkeypatch.setenv("TERM", "xterm-256color")
    config = Config()
    config.attachments.force_kitty_support = True

    assert _supports_kitty_graphics(config) is True
