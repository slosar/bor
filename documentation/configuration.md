# Bor Configuration Guide

Bor uses a TOML configuration file located at `~/.config/bor.conf`.
A different file can be given with `bor --config PATH`, and individual options
can be overridden on the command line with `bor --set section.option=value`
(repeatable; values use TOML syntax, e.g. `--set general.max_messages=200`).

Unknown sections are ignored, but an unknown or misspelled option inside a known
section makes the whole file fail to load: Bor prints a warning at startup and
falls back to the built-in defaults for everything.

## Configuration Sections

### [general]

General application settings.

```toml
[general]
# Maximum number of messages to display in message list
max_messages = 400

# Message list date column (strftime formats):
# messages from earlier years
date_format = "%Y-%m-%d %H:%M"

# messages from earlier this year
short_date_format = "%m/%d"

# today's messages
time_format = "%H:%M"

# Textual UI theme
theme = "textual-dark"
```

`theme` accepts any registered Textual theme (for example `textual-dark`, `textual-light`, `nord`, `gruvbox`, `dracula`).

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

`use_starttls = true` connects in plain text and upgrades with STARTTLS (usually
port 587); it takes precedence over `use_tls`. With `use_starttls = false`,
`use_tls = true` uses implicit TLS (SMTPS, usually port 465), and setting both to
false sends unencrypted. Bor logs in only when `username` is set and a password
is found; there is no interactive password prompt.

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

`email` is also used to leave yourself out of reply-all recipients and to detect
replies to your own sent messages. `organization` is accepted but not currently
used (no `Organization:` header is added).

### [colors]

Message list colors. Values are Rich styles: a color name (`blue`,
`dark_orange`, `orange1`, ...), a hex color (`"#ff8c00"`), optionally with
modifiers such as `italic` or `underline`. Rows are always drawn bold.

```toml
[colors]
# Unread messages (default: "blue")
unread = "blue"

# Flagged messages; takes precedence over unread (default: "dark_orange")
important = "dark_orange"
```

The options `marked`, `header` and `quoted` are also accepted but currently have
no effect (marked messages are shown with `display.flag_marked` instead). Note
the key is `important`, not `flagged`: an unknown key here makes the whole
configuration fail to load.

### [sync]

External synchronization command.

```toml
[sync]
# mbsync example
command = "mbsync -a"

# offlineimap example
# command = "offlineimap"

# Several commands need an explicit shell
# command = "sh -c 'mbsync work && mbsync personal'"
```

The command is split with shell-style quoting and run directly, **not through a
shell**, so `&&`, pipes, redirection and `~`/variable expansion only work inside
an explicit `sh -c '...'`. There is no need to run `mu index` yourself: after a
successful sync Bor runs `mu index`, refreshes the message list and closes the
Sync tab.

### [threading]

Threading display settings.

```toml
[threading]
enabled = true
indicator = "↳"
```

`enabled` sets the initial state (toggle with `T`). `indicator` is accepted but
currently unused: threads are drawn with `├`, `└` and `│` tree lines.

### [display]

Message list display settings.

```toml
[display]
# Column widths
date_width = 12
from_width = 20
flags_width = 6

# Flag symbols
flag_unread = "●"
flag_replied = "↩"
flag_forwarded = "→"
flag_flagged = "⚑"
flag_attachment = "📎"
flag_marked = "𝐌"
flag_encrypted = "🔒"
flag_signed = "✓"
```

The column layout is fixed (flags, date, from, subject; the subject takes the
remaining width). The options `columns` and `subject_width` are accepted but
currently ignored, as are `flag_encrypted` and `flag_signed`, which are not
shown in the flags column.

### [html]

HTML email rendering settings.

```toml
[html]
# Directory for temporary HTML files created by "view in browser" (V key).
# Defaults to the system temp directory when unset.
# Useful when the system temp dir (/tmp) is restricted by browser security policies.
# browser_tmp_dir = "~/tmp/bor"
```

HTML-only messages are converted to text with `html2text` when it is installed
(`pip install bormail[html]`), otherwise with a simple built-in tag stripper.
The options `renderer` and `open_links_in_browser` are accepted but currently
ignored.

### [attachments]

Attachment handling settings.

```toml
[attachments]
# Default directory for saving attachments
save_directory = "~/Downloads"

# Preview images inline with the kitty graphics protocol (requires kitty)
use_kitty_icat = true

# Force kitty graphics support even when TERM is not xterm-kitty
force_kitty_support = false
```

Non-PNG images are converted for preview with Pillow (`pip install bormail[images]`)
or, failing that, ImageMagick's `convert`.

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

Email address aliases for quick addressing. Works like `.mailrc` aliases;
`alias name address` lines from `~/.mailrc` are merged in and win on conflicts.

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
theme = "textual-dark"

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
important = "orange1"

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

[html]
# browser_tmp_dir = "~/tmp/bor"

[aliases]
r = "Best regards,\nJohn"
t = "Thanks!"

[email_aliases]
work = "colleagues@company.com"
```

## Environment Variables

These are diagnostics rather than everyday settings; none of them have a config
file equivalent.

| Variable | Effect |
|----------|--------|
| `BOR_NO_GC_TUNING` | Set to `1` to stop Bor from freezing the startup object graph and raising the garbage-collection thresholds after the inbox loads. The tuning trades a small amount of resident memory for shorter pauses; disable it when investigating memory growth, since the frozen generation is never rescanned. |
| `BORPROF_LOG` | Path for the UI latency profiler's log (default `/tmp/borprof.jsonl`). See `python -m bor.profiling` in [architecture.md](architecture.md#profiling). |
