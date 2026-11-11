# Server Mode Logging & Verification

## Summary

Added comprehensive logging throughout the mu server integration to verify that server mode is always used when enabled and CLI fallback is minimized.

## Key Logging Points Added

### 1. Command Routing (`_run_mu_server`)
- **DEBUG**: Command received: `[mu server] Attempting to route command: {cmd}`
- **INFO**: Successful execution: `[mu server] Successfully executed '{cmd}' command via server`
- **DEBUG**: Fallback decision: `[mu server] Command '{cmd}' not supported by server, will use CLI fallback`
- **ERROR**: Server failures: `[mu server] Error executing '{cmd}': {error}. Disabling server mode.`

### 2. Database Operations
- **INFO**: Move operations: `[mu server] Moving message docid={docid} to maildir={maildir}`
- **INFO**: Add operations: `[mu server] Adding message path={path}`
- **INFO**: Remove operations: `[mu server] Removing message docid={docid}`
- **DEBUG**: DocID lookups: `[mu server] Found message docid={docid} for path={path}`

### 3. High-Level Operations (`move()` method)
- **INFO**: `[mu] Attempting server-native move for {filename} to {maildir}`
- **INFO**: Success: `[mu] Successfully moved {filename} via server`
- **INFO**: Fallback: `[mu] Server move failed or docid not found, falling back to CLI`
- **INFO**: Direct CLI path: `[mu] Using CLI-based move for {filename} to {maildir}`

### 4. Fallback Decision (`_run_mu`)
- **DEBUG**: Fallback triggered: `[mu] Server returned None for {cmd}, falling back to CLI`

## Usage

To enable logging and verify server mode is working:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now run operations - you'll see detailed server logs
from bor.mu import MuInterface
mu = MuInterface(use_server=True)
mu.find("maildir:/INBOX")
```

Or run the test script:
```bash
python test_server_logging.py
```

## Expected Behavior

When `use_server=True`:
1. All `find` and `cfind` commands should show: `[mu server] Successfully executed 'find' command via server`
2. Archive/move operations should show: `[mu server] Moving message docid=... to maildir=...`
3. NO CLI fallback messages should appear (unless server fails)

When `use_server=False`:
- No `[mu server]` messages should appear
- Commands execute directly via CLI

## Verification Points

✓ Tests: 70 passing (all tests still pass with logging)
✓ Server routing: `find` and `cfind` use server when enabled
✓ Database operations: Move uses atomic server command + docid lookup
✓ Fallback: Only triggered when command not supported by server
✓ Atomic operations: Archive/move/delete use server when available
