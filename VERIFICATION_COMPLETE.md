# Server Mode Verification - Complete Implementation

## What Was Added

Comprehensive logging throughout the mu server integration to verify that:
1. **Server mode is actually being used** when enabled
2. **CLI fallback is minimized** - only used for unsupported commands
3. **Archive/move operations work correctly** with atomic server commands
4. **All database operations** stay coordinated between server and filesystem

## Key Changes to `/home/anze/Dropbox/work/bor/bor/mu.py`

### 1. Added Logging Import
```python
import logging
logger = logging.getLogger(__name__)
```

### 2. Command Routing Logging

In `_run_mu_server()` method:
- **DEBUG**: When command enters: `[mu server] Attempting to route command: {cmd}`
- **INFO**: When server handles: `[mu server] Successfully executed '{cmd}' command via server`
- **DEBUG**: When falling back: `[mu server] Command '{cmd}' not supported by server, will use CLI fallback`
- **ERROR**: When server fails: `[mu server] Error executing '{cmd}': {error}. Disabling server mode.`

### 3. Database Operation Logging

In server methods (`_server_move_message`, `_server_add_message`, `_server_remove_message`):
- **INFO**: Operation attempts: `[mu server] Moving/Adding/Removing message ...`
- **INFO**: Success confirmations: `[mu server] Successfully moved/added/removed message ...`
- **ERROR**: Operation failures: `[mu server] {Operation} error: {message}`
- **DEBUG**: DocID lookups: `[mu server] Found message docid={docid} for path={path}`

### 4. High-Level Operation Logging

In `move()` method:
- **INFO**: Attempting server: `[mu] Attempting server-native move for {filename}`
- **INFO**: Server succeeded: `[mu] Successfully moved {filename} via server`
- **INFO**: Server failed/fallback: `[mu] Server move failed or docid not found, falling back to CLI`
- **INFO**: Direct CLI path: `[mu] Using CLI-based move for {filename} to {maildir}`

### 5. Fallback Decision Logging

In `_run_mu()` method:
- **DEBUG**: When server returns None: `[mu] Server returned None for {cmd}, falling back to CLI`

## How to Use the Logging

### Enable Debug Logging
```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from bor.mu import MuInterface
mu = MuInterface(use_server=True)
```

### Check Log Output
- Look for `[mu server]` prefix = Server-mode operations
- Look for `[mu]` prefix (without `server`) = General operations or CLI fallback
- `INFO` level = High-level operation completion
- `DEBUG` level = Detailed routing decisions
- `ERROR` level = Failures that disable server mode

## Verification Commands

### 1. Test Server Command Routing
```bash
python test_command_routing.py
```
Output shows which commands use server vs CLI fallback.

### 2. Test Server Logging
```bash
python test_server_logging.py
```
Output demonstrates logging when operations complete.

### 3. Run Full Test Suite
```bash
pytest -q
```
✓ All 70 tests passing

## Expected Behavior

### With `use_server=True` (Default)
1. `find` queries → `[mu server] Successfully executed 'find' command via server`
2. Archive/move → `[mu server] Moving message docid=... to maildir=...`
3. NO CLI fallback messages should appear unless:
   - Server completely fails (then `[mu server] Error ...`)
   - Command not supported (then `[mu server] Command ... not supported by server`)

### With `use_server=False`
1. No `[mu server]` messages
2. All commands go directly to CLI
3. Operations take longer (spawning processes each time)

## Commands Status

### Handled by Server (No CLI Fallback)
- ✓ `find` - Query messages
- ✓ `cfind` - Search contacts
- ✓ `move` - Via atomic server command (when using `_server_move_message()`)
- ✓ `add` - Via server (when using `_server_add_message()`)
- ✓ `remove` - Via server (when using `_server_remove_message()`)

### Falling Back to CLI
- `index` - Not in `_run_mu_server()` yet (rarely used in GUI)
- `mkdir` - Not in `_run_mu_server()` yet
- Other operations

## Archive Operation Flow (with Logging)

1. User clicks Archive on message
2. `move()` called with path and target maildir
3. Logs: `[mu] Attempting server-native move for {filename} to {maildir}`
4. Gets docid via server query
5. Logs: `[mu server] Found message docid={docid} for path={path}`
6. Uses atomic server `(move :docid ... :maildir ...)` command
7. Logs: `[mu server] Successfully moved message docid={docid}`
8. Logs: `[mu] Successfully moved {filename} via server`
9. Message is now in Archive folder with server index synchronized

## Troubleshooting

### No `[mu server]` Messages Appearing
- Check if `use_server=True` in config
- Check if mu server is actually running: `pgrep -f "mu server"`
- Enable DEBUG logging: `logging.basicConfig(level=logging.DEBUG)`

### Server Mode Not Working
- Check logs for `[mu server] Error executing ...`
- Logs will show `[mu server] ... Disabling server mode.`
- Server will fall back to CLI automatically

### Archive Messages Disappearing
- Check logs show `[mu server] Moving message ...` 
- If server move fails, logs show error and CLI fallback is used
- All operations are logged for debugging

## Summary

✓ Comprehensive logging added throughout server mode
✓ Can easily verify server is being used
✓ CLI fallback is transparent and logged
✓ Archive/move operations use atomic server commands
✓ All 70 tests passing
✓ No regressions in functionality
