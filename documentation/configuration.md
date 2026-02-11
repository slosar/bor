# Bor Configuration Guide

Bor uses a TOML configuration file located at `~/.config/bor.conf`.

## Configuration Sections

### [general]

General application settings.

```toml
[general]
# Maximum number of messages to display in message list
max_messages = 400

# Date format for message list (strftime format)
date_format = "%Y-%m-%d %H:%M"

# Short date format for compact view
short_date_format = "%m/%d"

# Time format for today's messages
time_format = "%H:%M"
```

### [folders]

Maildir folder paths relative to the mu root maildir.

```toml
[folders]
inbox = "/INBOX"
archive = "/Archive"
drafts = "/Drafts"
sent = "/Sent"
trash = "/Trash"
```

### [smtp]

SMTP server settings for sending email.

```toml
[smtp]
server = "smtp.example.com"
port = 587
username = "user@example.com"
# Password can be stored here or in system keyring
# password = "your-password"
use_tls = true
use_starttls = true
```

For security, it's recommended to store your password in the system keyring:

```bash
# Using Python keyring
python -c "import keyring; keyring.set_password('bor-email', 'user@example.com', 'your-password')"
```

### [identity]

Your email identity settings.

```toml
[identity]
name = "Your Name"
email = "user@example.com"
organization = "Your Organization"
signature = """
--
Your Name
Your Organization
"""
```

### [colors]

Color scheme configuration. Colors support Rich color names and modifiers.

```toml
[colors]
# Color for unread messages (default: bold cyan)
unread = "bold cyan"

# Color for flagged/important messages (default: bold yellow)
flagged = "bold yellow"

# Style for marked messages (default: reverse)
marked = "reverse"

# Header styling
header = "bold"

# Quoted text styling
quoted = "italic dim"
```

Available color names: black, red, green, yellow, blue, magenta, cyan, white.
Available modifiers: bold, dim, italic, underline, reverse.

### [sync]

External synchronization command.

```toml
[sync]
# mbsync example
command = "mbsync -a"

# offlineimap example
# command = "offlineimap"

# isync + mu index example
# command = "mbsync -a && mu index"
```

### [threading]

Threading display settings.

```toml
[threading]
enabled = true
indicator = "↳"
```

### [display]

Message list display settings.

```toml
[display]
# Available columns: date, from, to, subject, flags, size, maildir
columns = ["date", "from", "subject", "flags"]

# Column widths (0 = fill remaining space)
date_width = 12
from_width = 20
subject_width = 0
flags_width = 6

# Flag symbols
flag_unread = "●"
flag_replied = "↩"
flag_forwarded = "→"
flag_flagged = "⚑"
flag_attachment = "📎"
flag_encrypted = "🔒"
flag_signed = "✓"
```

### [html]

HTML email rendering settings.

```toml
[html]
# Renderer: html2text, rich, links, w3m
renderer = "html2text"

# Open links in browser when clicked
open_links_in_browser = true
```

### [attachments]

Attachment handling settings.

```toml
[attachments]
# Default directory for saving attachments
save_directory = "~/Downloads"

# Use kitty icat for image preview (requires kitty terminal)
use_kitty_icat = true
```

### [aliases]

Text aliases for quick insertion in compose mode. Press the letter followed by Tab to expand.

```toml
[aliases]
r = "Best regards,"
t = "Thank you for your email."
k = "Kind regards,"
s = """Sincerely,
Your Name"""
```

### [email_aliases]

Email address aliases for quick addressing. Works like `.mailrc` aliases.

```toml
[email_aliases]
john = "john.doe@example.com"
team = "alice@example.com, bob@example.com, charlie@example.com"
boss = "Jane Smith <jane.smith@example.com>"
```

## Complete Example

```toml
[general]
max_messages = 400
date_format = "%Y-%m-%d %H:%M"
short_date_format = "%m/%d"
time_format = "%H:%M"

[folders]
inbox = "/INBOX"
archive = "/Archive"
drafts = "/Drafts"
sent = "/Sent"
trash = "/Trash"

[smtp]
server = "smtp.gmail.com"
port = 587
username = "myemail@gmail.com"
use_tls = true
use_starttls = true

[identity]
name = "John Doe"
email = "myemail@gmail.com"
signature = """
--
John Doe
Software Developer
"""

[colors]
unread = "blue"
important = "orange"

[sync]
command = "mbsync -a"

[threading]
enabled = true
indicator = "↳"

[display]
columns = ["date", "from", "subject", "flags"]
flag_unread = "●"
flag_replied = "↩"
flag_attachment = "📎"

[aliases]
r = "Best regards,\nJohn"
t = "Thanks!"

[email_aliases]
work = "colleagues@company.com"
```
