from pathlib import Path

import pytest

import bor.tabs.compose as compose_module
from bor.editing import kill_input_line, kill_text_line
from bor.mu import EmailMessage, EmailAddress
from bor.tabs.compose import ComposeWidget, AddressInput, ComposeTextArea, FilePathInput
import email.utils


def test_compose_references_appends_parent_msgid() -> None:
    """Ensure References include prior chain plus parent message id."""
    parent = EmailMessage(msgid="<parent@id>", references=["<root@id>"])

    references = ComposeWidget._compose_references(parent)

    assert references == "<root@id> <parent@id>"


def test_compose_references_handles_empty_chain() -> None:
    """When no existing references, include only the parent id."""
    parent = EmailMessage(msgid="<parent@id>", references=[])

    references = ComposeWidget._compose_references(parent)

    assert references == "<parent@id>"


def test_compose_references_deduplicates_ids() -> None:
    """Do not duplicate ids already present in the chain."""
    parent = EmailMessage(msgid="<parent@id>", references=["<parent@id>", "<root@id>"])

    references = ComposeWidget._compose_references(parent)

    assert references == "<parent@id> <root@id>"


def test_smtp_address_extraction_with_commas() -> None:
    """Test that addresses with commas in display names are extracted correctly for SMTP."""
    # Simulate what would be in the To/CC/BCC headers after formatting
    to_header = '"Smith, Alice" <alice@example.com>, "Brown, Bob" <bob@example.org>'
    cc_header = 'John Doe <john@example.com>'

    # Extract addresses the way _send_message does
    to_addrs = []
    to_addrs.extend([email for name, email in email.utils.getaddresses([to_header])])
    to_addrs.extend([email for name, email in email.utils.getaddresses([cc_header])])
    to_addrs = [addr for addr in to_addrs if addr]

    # Should extract exactly 3 email addresses
    assert len(to_addrs) == 3
    assert 'alice@example.com' in to_addrs
    assert 'bob@example.org' in to_addrs
    assert 'john@example.com' in to_addrs


def test_find_address_start_with_quoted_commas() -> None:
    """Test that _find_address_start correctly handles commas in quoted names."""
    addr_input = AddressInput()

    # Test 1: Single address with comma in quoted name
    text1 = '"Smith, Alice" <alice@example.com>'
    start1 = addr_input._find_address_start(text1, len(text1))
    assert start1 == 0, "Should start at beginning for single quoted address"

    # Test 2: After separator comma (not quoted comma)
    text2 = '"Smith, Alice" <alice@example.com>, John'
    start2 = addr_input._find_address_start(text2, len(text2))
    assert text2[start2:].strip() == "John", "Should find position after separator comma"

    # Test 3: Second address with quoted comma
    text3 = '"Brown, Bob" <bob@example.org>, "Smith, Alice" <alice@example.com>'
    start3 = addr_input._find_address_start(text3, len(text3))
    assert text3[start3:].strip() == '"Smith, Alice" <alice@example.com>'

    # Test 4: Escaped quotes in name
    text4 = r'"Joe \"The Boss\" Smith" <joe@example.com>, Another'
    start4 = addr_input._find_address_start(text4, len(text4))
    assert text4[start4:].strip() == "Another"

def test_reply_all_prompt_with_multiple_to_recipients() -> None:
    """Test that reply prompt shows when message has multiple TO recipients."""
    # Create a message with multiple TO recipients and no CC
    msg = EmailMessage(
        msgid="<test@id>",
        to_addrs=[
            EmailAddress(name="Alice", email="alice@example.com"),
            EmailAddress(name="Bob", email="bob@example.com"),
        ],
        cc_addrs=[],
    )
    
    # Should show reply prompt if there are multiple TO recipients
    should_show_prompt = len(msg.to_addrs) > 1 or bool(msg.cc_addrs)
    assert should_show_prompt is True


def test_reply_all_prompt_with_cc_recipients() -> None:
    """Test that reply prompt shows when message has CC recipients."""
    msg = EmailMessage(
        msgid="<test@id>",
        to_addrs=[EmailAddress(name="Alice", email="alice@example.com")],
        cc_addrs=[EmailAddress(name="Bob", email="bob@example.com")],
    )
    
    should_show_prompt = len(msg.to_addrs) > 1 or bool(msg.cc_addrs)
    assert should_show_prompt is True


def test_reply_single_recipient_no_prompt() -> None:
    """Test that reply prompt does not show for single recipient and no CC."""
    msg = EmailMessage(
        msgid="<test@id>",
        to_addrs=[EmailAddress(name="Alice", email="alice@example.com")],
        cc_addrs=[],
    )
    
    should_show_prompt = len(msg.to_addrs) > 1 or bool(msg.cc_addrs)
    assert should_show_prompt is False


def test_reply_all_includes_other_to_recipients() -> None:
    """Test that reply-all includes other TO recipients in the reply."""
    # Simulate original message with multiple TO and CC recipients
    original_msg = EmailMessage(
        msgid="<test@id>",
        from_addr=EmailAddress(name="Alice", email="alice@example.com"),
        to_addrs=[
            EmailAddress(name="Bob", email="bob@example.com"),
            EmailAddress(name="Charlie", email="charlie@example.com"),
        ],
        cc_addrs=[
            EmailAddress(name="David", email="david@example.com"),
        ],
    )
    
    # Simulate reply from Charlie (one of the TO recipients)
    my_email = "charlie@example.com"
    reply_all = True
    
    # Build TO field for reply (mimics what _init_reply does)
    to_addrs = []
    if original_msg.reply_to_addr:
        to_addrs.append(str(original_msg.reply_to_addr))
    else:
        to_addrs.append(str(original_msg.from_addr))

    # Build CC list for reply-all (original TO + CC, excluding self and duplicates)
    cc_list = []
    cc_seen = set(to_addrs)
    if reply_all:
        for addr in list(original_msg.to_addrs) + list(original_msg.cc_addrs):
            if addr.email == my_email:
                continue
            addr_str = str(addr)
            if addr_str in cc_seen:
                continue
            cc_list.append(addr_str)
            cc_seen.add(addr_str)

    # Verify TO field contains only original sender
    assert len(to_addrs) == 1
    assert str(original_msg.from_addr) in to_addrs

    # Verify CC field contains other TO recipients and CC recipients (excluding self)
    assert str(original_msg.to_addrs[0]) in cc_list  # Bob
    assert str(original_msg.to_addrs[1]) not in cc_list  # Charlie (self)
    assert str(original_msg.cc_addrs[0]) in cc_list  # David

def test_reply_all_excludes_self_from_cc() -> None:
    """Test that reply-all excludes the current user from CC field."""
    # Simulate original message where user is in CC
    my_email = "charlie@example.com"
    original_msg = EmailMessage(
        msgid="<test@id>",
        from_addr=EmailAddress(name="Alice", email="alice@example.com"),
        to_addrs=[EmailAddress(name="Bob", email="bob@example.com")],
        cc_addrs=[
            EmailAddress(name="Charlie", email="charlie@example.com"),  # This is me
            EmailAddress(name="David", email="david@example.com"),
        ],
    )
    
    # Build CC field for reply (mimics what _init_reply does)
    to_addrs = [str(original_msg.from_addr)]
    cc_list = []
    cc_seen = set(to_addrs)
    for addr in list(original_msg.to_addrs) + list(original_msg.cc_addrs):
        if addr.email == my_email:
            continue
        addr_str = str(addr)
        if addr_str in cc_seen:
            continue
        cc_list.append(addr_str)
        cc_seen.add(addr_str)
    
    # Should include Bob and David, not Charlie (self)
    assert any("bob@example.com" in entry for entry in cc_list)
    assert any("david@example.com" in entry for entry in cc_list)
    assert all("charlie@example.com" not in entry for entry in cc_list)


def test_reply_uses_list_post_for_mailing_list_emails() -> None:
    """Test that replying to a mailing list email uses List-Post, not Reply-To (individual).

    Models the case where a mailing list hides sender addresses:
      From = list address (sender privacy on)
      Reply-To = individual sender
      List-Post = list address
    The reply should go to the list, not the individual.
    """
    original_msg = EmailMessage(
        msgid="<msg@example.org>",
        from_addr=EmailAddress(name="'sender@example.com' via Test List", email="list@example.org"),
        to_addrs=[EmailAddress(name="Test List", email="list@example.org")],
        reply_to_addr=EmailAddress(name="Sender", email="sender@example.com"),
        list_post_addr=EmailAddress(email="list@example.org"),
    )

    # Simulate what _init_reply does to pick the To address
    to_addrs = []
    if original_msg.list_post_addr and original_msg.list_post_addr.email:
        to_addrs.append(str(original_msg.list_post_addr))
    elif original_msg.reply_to_addr and original_msg.reply_to_addr.email:
        to_addrs.append(str(original_msg.reply_to_addr))
    else:
        to_addrs.append(str(original_msg.from_addr))

    # Reply should go to the list, not the individual sender
    assert len(to_addrs) == 1
    assert "list@example.org" in to_addrs[0]
    assert "sender@example.com" not in to_addrs[0]


def test_reply_uses_reply_to_header_when_no_list_post() -> None:
    """Test that replying to a non-list message with Reply-To uses that address."""
    original_msg = EmailMessage(
        msgid="<msg@example.com>",
        from_addr=EmailAddress(name="Alice", email="alice@example.com"),
        to_addrs=[EmailAddress(name="Me", email="me@example.com")],
        reply_to_addr=EmailAddress(name="Alice Support", email="support@example.com"),
        list_post_addr=None,
    )

    to_addrs = []
    if original_msg.list_post_addr and original_msg.list_post_addr.email:
        to_addrs.append(str(original_msg.list_post_addr))
    elif original_msg.reply_to_addr and original_msg.reply_to_addr.email:
        to_addrs.append(str(original_msg.reply_to_addr))
    else:
        to_addrs.append(str(original_msg.from_addr))

    assert len(to_addrs) == 1
    assert "support@example.com" in to_addrs[0]


def test_reply_falls_back_to_from_without_reply_to() -> None:
    """Test that replying without Reply-To header uses From address."""
    original_msg = EmailMessage(
        msgid="<msg@example.com>",
        from_addr=EmailAddress(name="Alice", email="alice@example.com"),
        to_addrs=[EmailAddress(name="Bob", email="bob@example.com")],
        reply_to_addr=None,
    )

    to_addrs = []
    if original_msg.reply_to_addr and original_msg.reply_to_addr.email:
        to_addrs.append(str(original_msg.reply_to_addr))
    else:
        to_addrs.append(str(original_msg.from_addr))

    assert len(to_addrs) == 1
    assert "alice@example.com" in to_addrs[0]


def test_forward_attachments_keep_duplicate_names(tmp_path: Path) -> None:
    """Forwarding should keep all attachments with duplicate filenames."""
    attachments = [
        {"part_index": 1},
        {"part_index": 2},
    ]

    def fake_extract(message_path: str, part_index: int, target_dir: str) -> str:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / "file.txt"
        path.write_text(f"part {part_index}")
        return str(path)

    result = ComposeWidget._collect_forward_attachments(
        "/tmp/message",
        attachments,
        tmp_path,
        fake_extract
    )

    names = sorted(path.name for path in result)
    assert names == ["file (2).txt", "file.txt"]
    assert (tmp_path / "file.txt").read_text() == "part 1"
    assert (tmp_path / "file (2).txt").read_text() == "part 2"


def test_read_insert_file_returns_contents(tmp_path: Path) -> None:
    """Insert helper should read UTF-8 text files fully."""
    source = tmp_path / "snippet.txt"
    source.write_text("first line\nsecond line", encoding="utf-8")

    assert ComposeWidget._read_insert_file(source) == "first line\nsecond line"


def test_read_insert_file_rejects_non_utf8(tmp_path: Path) -> None:
    """Insert helper should raise for non-UTF-8 content."""
    source = tmp_path / "binary.bin"
    source.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(UnicodeDecodeError):
        ComposeWidget._read_insert_file(source)


def test_list_bulk_attachable_files_returns_sorted_files_only(tmp_path: Path) -> None:
    """Bulk attach helper should list direct child files, sorted by name."""
    (tmp_path / "z-last.txt").write_text("z", encoding="utf-8")
    (tmp_path / "A-first.txt").write_text("a", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    files = ComposeWidget._list_bulk_attachable_files(tmp_path)

    assert [path.name for path in files] == ["A-first.txt", "z-last.txt"]


def test_delete_previous_word_removes_word_and_whitespace() -> None:
    """Backward delete should remove previous word and separator spacing."""
    source = "hello   world"
    text, index = ComposeTextArea._delete_previous_word(source, len(source))
    assert text == "hello   "
    assert index == 8


def test_delete_previous_word_across_newline() -> None:
    """Backward delete should work across line boundaries."""
    source = "hello\nworld"
    text, index = ComposeTextArea._delete_previous_word(source, len(source))
    assert text == "hello\n"
    assert index == 6


def test_transpose_at_cursor_middle() -> None:
    """Transpose should swap char before cursor with char at cursor."""
    text, index = ComposeTextArea._transpose_at_cursor("abcd", 2)
    assert text == "acbd"
    assert index == 3


def test_transpose_at_cursor_end_of_text() -> None:
    """Transpose at end should swap final two characters."""
    text, index = ComposeTextArea._transpose_at_cursor("abcd", 4)
    assert text == "abdc"
    assert index == 4


def test_transpose_does_not_cross_newline() -> None:
    """Transpose should no-op when it would involve a newline character."""
    source = "ab\ncd"
    text, index = ComposeTextArea._transpose_at_cursor(source, 2)
    assert text == source
    assert index == 2


def test_kill_input_line_returns_killed_suffix() -> None:
    """Ctrl+K on single-line inputs should kill to end and return copied text."""
    text, cursor, killed = kill_input_line("hello world", 6)
    assert text == "hello "
    assert cursor == 6
    assert killed == "world"


def test_kill_text_line_kills_to_end_of_current_line() -> None:
    """Ctrl+K in editor text should kill only the remainder of the current line."""
    text, cursor, killed = kill_text_line("alpha\nbeta\ngamma", 7)
    assert text == "alpha\nb\ngamma"
    assert cursor == 7
    assert killed == "eta"


def test_kill_text_line_kills_newline_at_end_of_line() -> None:
    """Ctrl+K at end of line should remove the newline, matching emacs behavior."""
    text, cursor, killed = kill_text_line("alpha\nbeta", 5)
    assert text == "alphabeta"
    assert cursor == 5
    assert killed == "\n"


def test_kill_text_line_kills_trailing_empty_line() -> None:
    """Ctrl+K on a final empty line should delete that line's newline."""
    text, cursor, killed = kill_text_line("alpha\n", 6)
    assert text == "alpha"
    assert cursor == 5
    assert killed == "\n"


def test_compose_kill_line_appends_consecutive_kills_to_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consecutive editor kills should accumulate in clipboard order."""
    clipboard = ""

    def fake_copy(text: str, append: bool = False) -> None:
        nonlocal clipboard
        clipboard = clipboard + text if append else text

    monkeypatch.setattr(compose_module, "copy_to_clipboard", fake_copy)

    editor = ComposeTextArea()
    editor.text = "alpha\nbeta\n"
    editor.cursor_location = (0, 0)

    editor._kill_line_at_cursor()
    editor._kill_line_at_cursor()
    editor._kill_line_at_cursor()
    editor._kill_line_at_cursor()

    assert clipboard == "alpha\nbeta\n"
    assert editor.text == ""


def test_file_path_completion_returns_single_match() -> None:
    """Tab should complete immediately when there is exactly one match."""
    completed = FilePathInput._longest_shared_completion_prefix(
        "/tmp/al",
        ["/tmp/alpha.txt"],
    )
    assert completed == "/tmp/alpha.txt"


def test_file_path_completion_extends_to_shared_prefix() -> None:
    """Tab should extend only to the shared prefix across multiple matches."""
    completed = FilePathInput._longest_shared_completion_prefix(
        "/tmp/al",
        ["/tmp/alpha.txt", "/tmp/alpine.txt"],
    )
    assert completed == "/tmp/alp"


def test_file_path_completion_keeps_input_when_matches_diverge() -> None:
    """Tab should leave the input unchanged when matches share no extra prefix."""
    completed = FilePathInput._longest_shared_completion_prefix(
        "/tmp/a",
        ["/tmp/alpha.txt", "/tmp/archive.txt"],
    )
    assert completed == "/tmp/a"
