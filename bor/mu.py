"""
Mu interface module for Bor email reader.

Provides an interface to the mu mail indexer/searcher command-line tool.
Handles searching, viewing, moving, and managing email messages.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from email import policy, utils as email_utils
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class EmailAddress:
    """Represents an email address with optional name."""
    name: str = ""
    email: str = ""

    def __str__(self) -> str:
        """Return formatted email address string with proper quoting."""
        if self.name:
            # Check if name needs quoting (contains special characters per RFC 5322)
            # Special characters that require quoting include: , ; : " < > @ [ ] \
            # Note: We don't include . or \ here since they're usually not in names
            # and might have already been processed during parsing
            needs_quoting = any(c in self.name for c in ',;:"<>@[]')
            if needs_quoting:
                # Escape any quotes in the name for the quoted string
                # First check if the name already contains backslash-escaped quotes
                # from the original parsing, and only escape unescaped quotes
                escaped_name = self.name.replace('"', '\\"')
                return f'"{escaped_name}" <{self.email}>'
            return f"{self.name} <{self.email}>"
        return self.email

    @classmethod
    def from_mu(cls, data: Union[Dict, List, str, None]) -> "EmailAddress":
        """
        Create EmailAddress from mu output format.

        Args:
            data: Email data from mu (can be dict, list, or string)

        Returns:
            EmailAddress instance
        """
        if data is None:
            return cls()
        if isinstance(data, str):
            # Try to parse "Name <email>" format
            match = re.match(r"(.+?)\s*<(.+)>", data)
            if match:
                name = match.group(1).strip()
                # Strip surrounding quotes if present (mu may include them)
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1]
                    # Unescape any escaped quotes or backslashes
                    name = name.replace('\\"', '"').replace('\\\\', '\\')
                return cls(name=name, email=match.group(2).strip())
            return cls(email=data)
        if isinstance(data, dict):
            # mu JSON uses colon-prefixed keys like :name, :email
            name = data.get(":name", data.get("name", ""))
            # Strip quotes from name if present
            if name and name.startswith('"') and name.endswith('"'):
                name = name[1:-1]
                name = name.replace('\\"', '"').replace('\\\\', '\\')
            email = data.get(":email", data.get("email", data.get(":addr", data.get("addr", ""))))
            return cls(name=name, email=email)
        if isinstance(data, list) and len(data) >= 1:
            return cls.from_mu(data[0])
        return cls()


@dataclass
class EmailMessage:
    """Represents an email message with all metadata."""
    docid: int = 0
    msgid: str = ""
    path: str = ""
    maildir: str = ""
    subject: str = ""
    date: Optional[datetime] = None
    size: int = 0
    from_addr: EmailAddress = field(default_factory=EmailAddress)
    reply_to_addr: Optional[EmailAddress] = None  # Reply-To header if present
    to_addrs: List[EmailAddress] = field(default_factory=list)
    cc_addrs: List[EmailAddress] = field(default_factory=list)
    bcc_addrs: List[EmailAddress] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    in_reply_to: str = ""
    priority: str = "normal"
    body_txt: str = ""
    body_html: str = ""
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    thread_level: int = 0  # For threading display

    @property
    def is_unread(self) -> bool:
        """Check if message is unread."""
        return "unread" in self.flags or "new" in self.flags

    @property
    def is_replied(self) -> bool:
        """Check if message has been replied to."""
        return "replied" in self.flags

    @property
    def is_forwarded(self) -> bool:
        """Check if message has been forwarded."""
        return "passed" in self.flags

    @property
    def is_flagged(self) -> bool:
        """Check if message is flagged/important."""
        return "flagged" in self.flags

    @property
    def has_attachments(self) -> bool:
        """Check if message has attachments."""
        return "attach" in self.flags or len(self.attachments) > 0

    @property
    def is_encrypted(self) -> bool:
        """Check if message is encrypted."""
        return "encrypted" in self.flags

    @property
    def is_signed(self) -> bool:
        """Check if message is signed."""
        return "signed" in self.flags

    @classmethod
    def from_mu_json(cls, data: Dict[str, Any]) -> "EmailMessage":
        """
        Create EmailMessage from mu JSON output.

        Args:
            data: Message data dictionary from mu find --format=json

        Returns:
            EmailMessage instance
        """
        # Helper to get values - mu JSON uses colon-prefixed keys like :subject
        def get(key: str, default: Any = None) -> Any:
            # Try with colon prefix first (mu's sexp-style JSON)
            val = data.get(f":{key}")
            if val is not None:
                return val
            # Fall back to without colon
            return data.get(key, default)

        msg = cls()
        msg.docid = get("docid", 0)
        msg.msgid = get("msgid", get("message-id", ""))
        msg.path = get("path", "")
        msg.maildir = get("maildir", "")
        msg.subject = get("subject", "(no subject)")
        msg.size = get("size", 0)

        # Parse date - mu returns date as [high, low, usec] array
        date_val = get("date")
        if date_val:
            if isinstance(date_val, list) and len(date_val) >= 2:
                # mu returns [high, low, usec] where timestamp = high * 65536 + low
                high, low = date_val[0], date_val[1]
                timestamp = high * 65536 + low
                msg.date = datetime.fromtimestamp(timestamp)
            elif isinstance(date_val, (int, float)):
                msg.date = datetime.fromtimestamp(date_val)
            elif isinstance(date_val, str):
                try:
                    msg.date = datetime.fromisoformat(date_val)
                except ValueError:
                    msg.date = None

        # Parse addresses
        from_data = get("from")
        if from_data:
            if isinstance(from_data, list) and len(from_data) > 0:
                msg.from_addr = EmailAddress.from_mu(from_data[0])
            else:
                msg.from_addr = EmailAddress.from_mu(from_data)

        to_data = get("to", [])
        if isinstance(to_data, list):
            msg.to_addrs = [EmailAddress.from_mu(addr) for addr in to_data]

        cc_data = get("cc", [])
        if isinstance(cc_data, list):
            msg.cc_addrs = [EmailAddress.from_mu(addr) for addr in cc_data]

        bcc_data = get("bcc", [])
        if isinstance(bcc_data, list):
            msg.bcc_addrs = [EmailAddress.from_mu(addr) for addr in bcc_data]

        # Parse flags - can be list or dict (mu returns dict like {"flagged":"seen"})
        flags = get("flags", [])
        if isinstance(flags, list):
            msg.flags = [str(f) for f in flags]
        elif isinstance(flags, dict):
            # mu returns flags as dict like {"flagged":"seen","attach":"personal"}
            msg.flags = list(flags.keys()) + list(flags.values())
        elif isinstance(flags, str):
            msg.flags = flags.split()

        # Parse tags
        tags = get("tags", [])
        if isinstance(tags, list):
            msg.tags = [str(t) for t in tags]

        # Parse threading info
        refs = get("references", [])
        if isinstance(refs, list):
            msg.references = [str(r) for r in refs]
        msg.in_reply_to = get("in-reply-to", "")

        # Parse Reply-To header
        reply_to_data = get("reply-to", [])
        if isinstance(reply_to_data, list) and reply_to_data:
            msg.reply_to_addr = EmailAddress.from_mu(reply_to_data[0])

        # Priority
        msg.priority = get("priority", "normal")

        # Thread level (for display)
        msg.thread_level = get("thread-level", 0)

        return msg


class MuInterface:
    """
    Interface to the mu mail indexer/searcher.

    Provides methods for searching, viewing, and managing email messages
    using the mu command-line tool.
    """

    def __init__(self, mu_binary: Optional[str] = None, muhome: Optional[str] = None):
        """
        Initialize the mu interface.

        Args:
            mu_binary: Path to mu binary. If None, searches in PATH.
            muhome: Path to mu home directory. If None, uses default.
        """
        self.mu_binary = mu_binary or shutil.which("mu") or "mu"
        self.muhome = muhome
        self._root_maildir: Optional[str] = None
        self._move_history: List[Tuple[str, str]] = []  # For undo

    def _run_mu(self, args: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """
        Run mu command with given arguments.

        Args:
            args: Command arguments (without 'mu')
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess instance

        Raises:
            RuntimeError: If mu command fails
        """
        cmd = [self.mu_binary]
        if self.muhome:
            cmd.append(f"--muhome={self.muhome}")
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=60
            )
            return result
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"mu command timed out: {' '.join(cmd)}")
        except FileNotFoundError:
            raise RuntimeError(f"mu binary not found: {self.mu_binary}")

    def get_root_maildir(self) -> str:
        """
        Get the root maildir path.

        Returns:
            Path to the root maildir directory.
        """
        if self._root_maildir:
            return self._root_maildir

        result = self._run_mu(["info"])
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                # mu info output format: "| maildir           | /home/anze/mail                 |"
                if "maildir" in line.lower() and "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    # parts will be ['', 'maildir', '/home/anze/mail', '']
                    for i, part in enumerate(parts):
                        if part.lower() == "maildir" and i + 1 < len(parts):
                            self._root_maildir = parts[i + 1].strip()
                            return self._root_maildir

        # Fallback to common location
        self._root_maildir = str(Path.home() / "Maildir")
        return self._root_maildir

    def find(
        self,
        query: str,
        maxnum: Optional[int] = None,
        threads: bool = False,
        sort_field: str = "date",
        descending: bool = True,
        skip_dups: bool = True,
        include_related: bool = False
    ) -> List[EmailMessage]:
        """
        Search for messages matching query.

        Args:
            query: Mu search query
            maxnum: Maximum number of results (None for unlimited)
            threads: Whether to show threaded results
            sort_field: Field to sort by (date, from, subject, etc.)
            descending: Sort in descending order
            skip_dups: Skip duplicate messages
            include_related: Include related messages

        Returns:
            List of EmailMessage objects matching the query
        """
        args = ["find", query, "--format=json"]

        if maxnum is not None:
            args.extend(["--maxnum", str(maxnum)])

        if threads:
            args.append("--threads")

        if sort_field:
            args.extend(["--sortfield", sort_field])

        if descending:
            args.append("--reverse")

        if skip_dups:
            args.append("--skip-dups")

        if include_related:
            args.append("--include-related")

        result = self._run_mu(args)

        if result.returncode != 0:
            # Empty result is not an error
            if "no matches" in result.stderr.lower():
                return []
            # Log but don't fail for non-critical errors
            return []

        messages = []
        stdout = result.stdout.strip()
        
        # mu outputs JSON as an array, try parsing as array first
        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                messages = [EmailMessage.from_mu_json(m) for m in data]
            elif isinstance(data, dict):
                # Single message
                messages = [EmailMessage.from_mu_json(data)]
        except json.JSONDecodeError:
            # Fallback: try JSON lines format (one JSON object per line)
            try:
                for line in stdout.split("\n"):
                    line = line.strip()
                    if line and line not in ('[', ']', ','):
                        data = json.loads(line.rstrip(','))
                        messages.append(EmailMessage.from_mu_json(data))
            except json.JSONDecodeError:
                pass

        # Compute thread levels from references when threading is enabled
        if threads and messages:
            self._compute_thread_levels(messages)

        return messages

    def _compute_thread_levels(self, messages: List[EmailMessage]) -> None:
        """
        Compute thread_level for each message based on references.
        
        Only shows threading when the parent message is visible in the list.
        Messages whose parents aren't visible are treated as root (level 0).
        """
        # Build a set of message-ids in our result set
        visible_msgids = set()
        for msg in messages:
            if msg.msgid:
                visible_msgids.add(msg.msgid)
        
        for msg in messages:
            if not msg.references:
                msg.thread_level = 0
            else:
                # Count how many ancestors are visible in our list
                # Walk the reference chain and count visible ones
                visible_ancestors = 0
                for ref in msg.references:
                    if ref in visible_msgids:
                        visible_ancestors += 1
                
                # Thread level is based on visible ancestors only
                msg.thread_level = min(visible_ancestors, 10)  # Cap at 10

    def find_by_msgid(self, msgid: str) -> Optional[EmailMessage]:
        """
        Find a message by its Message-ID.

        Args:
            msgid: Message-ID to search for

        Returns:
            EmailMessage if found, None otherwise
        """
        # Clean the msgid - remove angle brackets if present
        clean_msgid = msgid.strip("<>")
        query = f'msgid:"{clean_msgid}"'
        results = self.find(query, maxnum=1)
        return results[0] if results else None

    def find_thread(self, message: EmailMessage) -> List[EmailMessage]:
        """
        Find all messages in the thread containing the given message.

        Args:
            message: Message whose thread to find

        Returns:
            List of all messages in the thread
        """
        if message.msgid:
            query = f"msgid:{message.msgid} OR refs:{message.msgid}"
        else:
            # Fallback to subject-based threading
            subject = re.sub(r"^(re|fwd|fw):\s*", "", message.subject, flags=re.I)
            query = f'subject:"{subject}"'

        return self.find(query, threads=True, include_related=True)

    def view(self, path: str, mark_as_read: bool = True, msgid: str = "") -> Optional[EmailMessage]:
        """
        View a message by path.

        Args:
            path: Path to the message file
            mark_as_read: Whether to mark the message as read
            msgid: Message-ID to use if path is stale

        Returns:
            EmailMessage with full content, or None if not found
        """
        # If path doesn't exist but we have msgid, try to find the current path
        if not Path(path).exists() and msgid:
            current = self.find_by_msgid(msgid)
            if current:
                path = current.path
        
        if not Path(path).exists():
            return None

        # Use mu view for metadata
        result = self._run_mu(["view", path, "--format=sexp"])

        # Parse the email file directly for full content
        try:
            with open(path, "rb") as f:
                email_msg = BytesParser(policy=policy.default).parse(f)

            msg = EmailMessage()
            msg.path = path
            msg.subject = email_msg.get("Subject", "(no subject)")
            msg.msgid = email_msg.get("Message-ID", "")

            # Parse From
            from_header = email_msg.get("From", "")
            msg.from_addr = EmailAddress.from_mu(from_header)

            # Parse To, CC, BCC
            to_header = email_msg.get("To", "")
            if to_header:
                # Use email.utils.getaddresses to properly handle quoted names with commas
                parsed_addrs = email_utils.getaddresses([to_header])
                msg.to_addrs = [EmailAddress(name=name, email=email) 
                               for name, email in parsed_addrs if email]

            cc_header = email_msg.get("CC", "")
            if cc_header:
                # Use email.utils.getaddresses to properly handle quoted names with commas
                parsed_addrs = email_utils.getaddresses([cc_header])
                msg.cc_addrs = [EmailAddress(name=name, email=email) 
                              for name, email in parsed_addrs if email]

            bcc_header = email_msg.get("BCC", "")
            if bcc_header:
                # Use email.utils.getaddresses to properly handle quoted names with commas
                parsed_addrs = email_utils.getaddresses([bcc_header])
                msg.bcc_addrs = [EmailAddress(name=name, email=email) 
                                for name, email in parsed_addrs if email]

            # Parse Reply-To
            reply_to_header = email_msg.get("Reply-To", "")
            if reply_to_header:
                msg.reply_to_addr = EmailAddress.from_mu(reply_to_header)

            # Parse date
            date_header = email_msg.get("Date")
            if date_header:
                from email.utils import parsedate_to_datetime
                try:
                    msg.date = parsedate_to_datetime(date_header)
                except (ValueError, TypeError):
                    msg.date = None

            # Get body content
            msg.body_txt = ""
            msg.body_html = ""
            msg.attachments = []

            if email_msg.is_multipart():
                # Track MIME part index for mu extract --parts command
                # mu only counts leaf parts (non-multipart), not container parts
                part_index = 0
                for part in email_msg.walk():
                    content_type = part.get_content_type()
                    # Skip multipart containers - mu doesn't count them
                    if content_type.startswith("multipart/"):
                        continue
                    part_index += 1
                    content_disposition = part.get("Content-Disposition", "")
                    filename = part.get_filename()

                    # Detect attachments:
                    # 1. Explicit attachment disposition
                    # 2. Inline images/media with a filename (common in HTML emails)
                    # 3. Non-text parts with a filename
                    is_attachment = "attachment" in content_disposition
                    is_inline_media = (
                        "inline" in content_disposition and
                        filename and
                        not content_type.startswith("text/")
                    )
                    # Also catch parts with filename that aren't text body parts
                    has_filename_not_text = (
                        filename and
                        content_type not in ("text/plain", "text/html")
                    )

                    if is_attachment or is_inline_media or has_filename_not_text:
                        msg.attachments.append({
                            "filename": filename or "attachment",
                            "content_type": content_type,
                            "size": len(part.get_payload(decode=True) or b""),
                            "part_index": part_index,  # MIME part number for mu extract
                            "inline": "inline" in content_disposition
                        })
                    elif content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload and isinstance(payload, bytes):
                            charset = part.get_content_charset() or "utf-8"
                            try:
                                text = payload.decode(charset, errors="replace")
                            except LookupError:
                                text = payload.decode("utf-8", errors="replace")
                            # Concatenate multiple text/plain parts (e.g., body + footer)
                            if msg.body_txt:
                                msg.body_txt += "\n" + text
                            else:
                                msg.body_txt = text
                    elif content_type == "text/html":
                        payload = part.get_payload(decode=True)
                        if payload and isinstance(payload, bytes):
                            charset = part.get_content_charset() or "utf-8"
                            try:
                                html = payload.decode(charset, errors="replace")
                            except LookupError:
                                html = payload.decode("utf-8", errors="replace")
                            # Concatenate multiple text/html parts
                            if msg.body_html:
                                msg.body_html += html
                            else:
                                msg.body_html = html
            else:
                content_type = email_msg.get_content_type()
                payload = email_msg.get_payload(decode=True)
                if payload and isinstance(payload, bytes):
                    charset = email_msg.get_content_charset() or "utf-8"
                    try:
                        text = payload.decode(charset, errors="replace")
                    except LookupError:
                        text = payload.decode("utf-8", errors="replace")

                    if content_type == "text/html":
                        msg.body_html = text
                    else:
                        msg.body_txt = text

            # Mark as read if requested and update path if it changed
            if mark_as_read and self._is_new_or_unread(path):
                new_path = self.mark_read(path)
                if new_path:
                    msg.path = new_path

            return msg

        except Exception as e:
            print(f"Error parsing message: {e}")
            return None

    def _is_new_or_unread(self, path: str) -> bool:
        """Check if message path indicates new/unread status."""
        return "/new/" in path or (",S" not in path and "S" not in path.split(",")[-1])

    def mark_read(self, path: str) -> Optional[str]:
        """
        Mark a message as read.

        Args:
            path: Path to the message file

        Returns:
            New path if successful, None otherwise
        """
        return self._set_flag(path, "+S-N")

    def mark_unread(self, path: str) -> Optional[str]:
        """
        Mark a message as unread.

        Args:
            path: Path to the message file

        Returns:
            New path if successful, None otherwise
        """
        return self._set_flag(path, "-S+N")

    def mark_flagged(self, path: str, flagged: bool = True) -> Optional[str]:
        """
        Mark a message as flagged/important.

        Args:
            path: Path to the message file
            flagged: Whether to flag or unflag

        Returns:
            New path if successful, None otherwise
        """
        flag_str = "+F" if flagged else "-F"
        return self._set_flag(path, flag_str)

    def mark_replied(self, path: str) -> Optional[str]:
        """
        Mark a message as replied to.

        Args:
            path: Path to the message file

        Returns:
            New path if successful, None otherwise
        """
        return self._set_flag(path, "+R")

    def mark_forwarded(self, path: str) -> Optional[str]:
        """
        Mark a message as forwarded.

        Args:
            path: Path to the message file

        Returns:
            New path if successful, None otherwise
        """
        return self._set_flag(path, "+P")

    def _set_flag(self, path: str, flag_delta: str) -> Optional[str]:
        """
        Set flags on a message.

        Args:
            path: Path to the message file
            flag_delta: Flag delta string like "+S-N" or "-F"

        Returns:
            New path if successful, None otherwise
        """
        # Parse the current filename and maildir
        path_obj = Path(path)
        if not path_obj.exists():
            return None

        # Maildir flag format: filename:2,FLAGS
        name = path_obj.name
        dir_path = path_obj.parent

        # Handle moving from new to cur
        if dir_path.name == "new":
            new_dir = dir_path.parent / "cur"
            if not new_dir.exists():
                new_dir.mkdir(parents=True)
        else:
            new_dir = dir_path

        # Parse existing flags
        if ":2," in name:
            base, flags = name.rsplit(":2,", 1)
        else:
            base = name
            flags = ""

        # Apply flag delta
        current_flags = set(flags)
        for i in range(0, len(flag_delta), 2):
            if i + 1 < len(flag_delta):
                op = flag_delta[i]
                flag = flag_delta[i + 1]
                if op == "+":
                    current_flags.add(flag)
                elif op == "-":
                    current_flags.discard(flag)

        # Create new filename with sorted flags
        new_flags = "".join(sorted(current_flags))
        new_name = f"{base}:2,{new_flags}"
        new_path = new_dir / new_name

        try:
            path_obj.rename(new_path)
            # Update mu database with new location
            self._run_mu(["remove", str(path_obj)])
            self._run_mu(["add", str(new_path)])
            return str(new_path)
        except OSError:
            return None

    def move(self, path: str, maildir: str) -> Optional[str]:
        """
        Move a message to a different maildir.

        Args:
            path: Path to the message file
            maildir: Target maildir (relative to root, e.g., "/Archive")

        Returns:
            New path if successful, None otherwise
        """
        path_obj = Path(path)
        if not path_obj.exists():
            return None

        root = self.get_root_maildir()
        target_dir = Path(root) / maildir.lstrip("/") / "cur"

        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True)
            except OSError:
                return None

        new_path = target_dir / path_obj.name

        try:
            # Store for undo
            self._move_history.append((str(new_path), path))

            # First remove from mu database
            self._run_mu(["remove", path])
            
            # Move the file
            shutil.move(str(path_obj), str(new_path))
            
            # Add to mu database at new location
            self._run_mu(["add", str(new_path)])
            
            return str(new_path)
        except OSError:
            return None

    def undo_move(self) -> bool:
        """
        Undo the last move operation.

        Returns:
            True if successful
        """
        if not self._move_history:
            return False

        current_path, original_path = self._move_history.pop()
        current = Path(current_path)
        original = Path(original_path)

        if not current.exists():
            return False

        # Ensure original directory exists
        original.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(current), str(original))
            return True
        except OSError:
            return False

    def delete(self, path: str, permanent: bool = False) -> bool:
        """
        Delete a message.

        Args:
            path: Path to the message file
            permanent: If True, permanently delete; otherwise move to trash

        Returns:
            True if successful
        """
        if permanent:
            try:
                Path(path).unlink()
                return True
            except OSError:
                return False
        else:
            # Move to trash
            result = self.move(path, "/Trash")
            return result is not None

    def index(self, cleanup: bool = False, lazy: bool = True) -> bool:
        """
        Index the maildir.

        Args:
            cleanup: Remove messages no longer in filesystem
            lazy: Only check changed directories

        Returns:
            True if successful
        """
        args = ["index"]
        if cleanup:
            args.append("--cleanup")
        if lazy:
            args.append("--lazy-check")

        result = self._run_mu(args)
        return result.returncode == 0

    def find_contacts(
        self,
        pattern: str = "",
        personal: bool = False,
        maxnum: Optional[int] = None
    ) -> List[EmailAddress]:
        """
        Find contacts matching pattern.

        Args:
            pattern: Search pattern (regex)
            personal: Only return personal contacts
            maxnum: Maximum number of results

        Returns:
            List of EmailAddress objects
        """
        args = ["cfind", "--format=json"]

        if pattern:
            args.append(pattern)

        if personal:
            args.append("--personal")

        if maxnum:
            args.extend(["--maxnum", str(maxnum)])

        result = self._run_mu(args)

        if result.returncode != 0:
            return []

        contacts = []
        try:
            # mu cfind returns a JSON array
            data = json.loads(result.stdout)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        contacts.append(EmailAddress(
                            name=item.get("name") or "",
                            email=item.get("email") or item.get("addr") or ""
                        ))
            elif isinstance(data, dict):
                # Single contact
                contacts.append(EmailAddress(
                    name=data.get("name") or "",
                    email=data.get("email") or data.get("addr") or ""
                ))
        except json.JSONDecodeError:
            # Try newline-delimited JSON as fallback
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            contacts.append(EmailAddress(
                                name=item.get("name") or "",
                                email=item.get("email") or item.get("addr") or ""
                            ))
                    except json.JSONDecodeError:
                        # Try plain text parsing
                        contacts.append(EmailAddress.from_mu(line.strip()))

        return contacts

    def get_maildirs(self) -> List[str]:
        """
        Get list of all maildirs.

        Returns:
            List of maildir paths relative to root
        """
        root = Path(self.get_root_maildir())
        maildirs = []

        for path in root.rglob("cur"):
            maildir = "/" + str(path.parent.relative_to(root))
            maildirs.append(maildir)

        return sorted(maildirs)

    def extract_attachment(
        self,
        message_path: str,
        attachment_index: int,
        target_dir: str
    ) -> Optional[str]:
        """
        Extract an attachment from a message.

        Args:
            message_path: Path to the message file
            attachment_index: MIME part index (as shown by 'mu extract <file>')
            target_dir: Directory to save the attachment

        Returns:
            Path to extracted file, or None on error
        """
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Get list of files before extraction
        existing_files = set(f.name for f in target_path.iterdir() if f.is_file())
        
        args = ["extract", "--parts", str(attachment_index),
                "--target-dir", str(target_path),
                "--overwrite",
                message_path]

        result = self._run_mu(args)
        if result.returncode != 0:
            return None
        
        # Find the extracted file - check for new files first
        for f in target_path.iterdir():
            if f.is_file() and f.name not in existing_files:
                return str(f)
        
        # If no new file, mu probably overwrote an existing file
        # Check mu output for the filename, or return any file that matches
        # the part pattern. Since we used --overwrite, the file exists.
        # Just return any file if there's only one candidate.
        current_files = [f for f in target_path.iterdir() if f.is_file()]
        if len(current_files) == 1:
            return str(current_files[0])
        
        # Multiple files exist - we need to figure out which one was just extracted
        # mu outputs the filename on stdout when extracting
        if result.stdout:
            # Parse mu output to find the extracted filename
            # mu typically outputs: "Wrote <path>"
            for line in result.stdout.strip().split('\n'):
                if line.startswith('Wrote '):
                    extracted_path = line[6:].strip()
                    if Path(extracted_path).exists():
                        return extracted_path
        
        # Last resort: return the most recently modified file
        if current_files:
            current_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return str(current_files[0])
        
        return None

    def extract_all_attachments(self, message_path: str, target_dir: str) -> List[str]:
        """
        Extract all attachments from a message.

        Args:
            message_path: Path to the message file
            target_dir: Directory to save attachments

        Returns:
            List of saved file paths
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        
        # Track file modification times before extraction
        existing_mtimes = {f: f.stat().st_mtime for f in target.iterdir() if f.is_file()}
        
        args = ["extract", "--save-attachments", "--overwrite", 
                "--target-dir", str(target), message_path]
        result = self._run_mu(args)

        if result.returncode != 0:
            return []

        # List files that are new or modified
        saved = []
        for f in target.iterdir():
            if f.is_file():
                old_mtime = existing_mtimes.get(f)
                if old_mtime is None or f.stat().st_mtime > old_mtime:
                    saved.append(str(f))

        return saved
