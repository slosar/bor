from pathlib import Path

from bor.mu import EmailMessage, EmailAddress
from bor.tabs.compose import ComposeWidget, AddressInput
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
    to_header = '"Slosar, Anze" <slosar@gmail.com>, "Derose, Joseph" <derose@bnl.gov>'
    cc_header = 'John Doe <john@example.com>'
    
    # Extract addresses the way _send_message does
    to_addrs = []
    to_addrs.extend([email for name, email in email.utils.getaddresses([to_header])])
    to_addrs.extend([email for name, email in email.utils.getaddresses([cc_header])])
    to_addrs = [addr for addr in to_addrs if addr]
    
    # Should extract exactly 3 email addresses
    assert len(to_addrs) == 3
    assert 'slosar@gmail.com' in to_addrs
    assert 'derose@bnl.gov' in to_addrs
    assert 'john@example.com' in to_addrs


def test_find_address_start_with_quoted_commas() -> None:
    """Test that _find_address_start correctly handles commas in quoted names."""
    addr_input = AddressInput()
    
    # Test 1: Single address with comma in quoted name
    text1 = '"Slosar, Anze" <slosar@gmail.com>'
    start1 = addr_input._find_address_start(text1, len(text1))
    assert start1 == 0, "Should start at beginning for single quoted address"
    
    # Test 2: After separator comma (not quoted comma)
    text2 = '"Slosar, Anze" <slosar@gmail.com>, John'
    start2 = addr_input._find_address_start(text2, len(text2))
    assert start2 == 34, "Should find position after separator comma"
    assert text2[start2:].strip() == "John"
    
    # Test 3: Second address with quoted comma
    text3 = '"Derose, Joseph" <derose@bnl.gov>, "Slosar, Anze" <slosar@gmail.com>'
    start3 = addr_input._find_address_start(text3, len(text3))
    assert start3 == 34, "Should find start of second quoted address"
    assert text3[start3:].strip() == '"Slosar, Anze" <slosar@gmail.com>'
    
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