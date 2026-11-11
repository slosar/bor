"""Blocking mu and SMTP work must never run on the UI (main) thread.

Textual runs the whole interface on one asyncio loop; a mu subprocess, a MIME
parse or a network round trip on it freezes the app, keyboard included.
"""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.widgets import DataTable

from bor.config import Config
from tests.test_app_integration import MockEmailMessage, create_mock_messages

# Calls that spawn mu, parse a whole message, or touch the network. (File
# renames for flags and moves are cheap and allowed on the UI thread.)
BLOCKING_MU_CALLS = (
    "find",
    "find_thread",
    "find_contacts",
    "view",
    "index",
    "extract_attachment",
    "extract_all_attachments",
)


def _on_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def _recording_mu(tmp_path: Path, calls: list) -> MagicMock:
    """Mock mu that records (method, ran_on_main_thread) for every blocking call."""
    messages = create_mock_messages(3)
    attachment = {"filename": "notes.txt", "content_type": "text/plain", "part_index": 2}

    def view(path, *args, **kwargs):
        return MockEmailMessage(path=path, to_addrs=[], attachments=[attachment])

    def extract(message_path, part_index, target_dir):
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        out = Path(target_dir) / "notes.txt"
        out.write_text("hello")
        return str(out)

    results = {
        "find": lambda *a, **k: list(messages),
        "find_thread": lambda *a, **k: messages[:2],
        "find_contacts": lambda *a, **k: [],
        "view": view,
        "index": lambda *a, **k: True,
        "extract_attachment": extract,
        "extract_all_attachments": lambda *a, **k: [],
        "get_root_maildir": lambda *a, **k: str(tmp_path / "Mail"),
    }

    mu = MagicMock()
    for name, result in results.items():

        def side_effect(*args, _name=name, _result=result, **kwargs):
            calls.append((_name, _on_main_thread()))
            return _result(*args, **kwargs)

        getattr(mu, name).side_effect = side_effect
    return mu


async def test_blocking_work_stays_off_the_ui_thread(tmp_path: Path) -> None:
    calls: list = []
    smtp_threads: list = []
    mu = _recording_mu(tmp_path, calls)

    class FakeSMTP:
        def __init__(self, *args, **kwargs) -> None:
            smtp_threads.append(_on_main_thread())

        def starttls(self) -> None:
            pass

        def login(self, *args) -> None:
            pass

        def sendmail(self, *args) -> None:
            smtp_threads.append(_on_main_thread())

        def quit(self) -> None:
            pass

    config = Config()
    config.sync.command = "true"
    with patch("bor.app.get_config", return_value=config):
        with patch("bor.app.MuInterface", return_value=mu):
            with patch("bor.tabs.compose.smtplib.SMTP", FakeSMTP):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:

                    async def settle() -> None:
                        await pilot.pause()
                        await app.workers.wait_for_complete()
                        await pilot.pause()

                    await settle()

                    # Reply and forward from the index (forward extracts attachments)
                    for key in ("r", "f"):
                        await pilot.press(key)
                        await settle()
                        await pilot.press("ctrl+l", "x", "y")
                        await settle()

                    # Refresh and thread view
                    await pilot.press("ctrl+r")
                    await settle()
                    await pilot.press("ctrl+t")
                    await settle()

                    # Address completion falling back to mu cfind, then send
                    await pilot.press("c")
                    await settle()
                    await pilot.press(*"zzz")
                    await pilot.press("tab")
                    await settle()
                    app.focused.value = "to@example.com"
                    await pilot.press("ctrl+l", "l")
                    await settle()

                    # Attachments: preview, open, save, save all. (Popen is
                    # patched only here: it is the global subprocess.Popen,
                    # which the sync step below needs for real.)
                    app.open_attachments(
                        MockEmailMessage(
                            attachments=[
                                {
                                    "filename": "notes.txt",
                                    "content_type": "text/plain",
                                    "part_index": 2,
                                }
                            ]
                        )
                    )
                    await settle()
                    with patch("bor.tabs.attachments.subprocess.Popen"):
                        for key in ("1", "enter", "s", "S"):
                            await pilot.press(key)
                            await settle()

                    # Sync re-indexes after the command succeeds
                    app.open_sync()
                    await settle()
                    assert app.query_one(DataTable)

    called = {name for name, _ in calls}
    assert set(BLOCKING_MU_CALLS) <= called, called
    on_ui_thread = [name for name, on_main in calls if on_main and name in BLOCKING_MU_CALLS]
    assert on_ui_thread == []
    assert smtp_threads and not any(smtp_threads)
    # The root-maildir lookup (`mu info`) is warmed up off the UI thread
    assert calls[[name for name, _ in calls].index("get_root_maildir")] == ("get_root_maildir", False)
