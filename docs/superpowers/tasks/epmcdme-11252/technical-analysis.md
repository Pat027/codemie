# EPMCDME-11252 — Technical Analysis
## Stop hook: `make ruff` fails with `poetry: No such file or directory` (Error 127)

## Root Cause

The Stop hook command `cd "$CLAUDE_PROJECT_DIR" && make ruff` fails because `poetry` is not available in the WSL shell environment that Claude Code uses to run hooks on Windows 11.

## Hook Configuration

**File:** `C:\Projects\EPM-SDAI\.claude\settings.local.json`

```json
"hooks": {
  "Stop": [
    { "command": "cd \"$CLAUDE_PROJECT_DIR\" && make ruff" }
  ]
}
```

`$CLAUDE_PROJECT_DIR` is auto-injected by Claude Code and resolves to the directory `claude` was launched from — `C:\Projects\EPM-SDAI\codemie` (or `/mnt/c/Projects/EPM-SDAI/codemie` in WSL).

## Failing Makefile Target

**File:** `C:\Projects\EPM-SDAI\codemie\Makefile:30-33`

```makefile
ruff:
    poetry run ruff format     # line 31 — fails here
    poetry run ruff check --fix
    poetry run ruff check
```

All three `ruff` commands depend on `poetry run`, so none execute if `poetry` is absent.

## Reproduction Environment

**Windows 11 + VS Code + WSL** — WSL is the correct environment; it produces the exact Error 127 matching the ticket. Native Git Bash gives a different error (Error 2, Windows-style).

**Prerequisites:**
- WSL installed and running (Ubuntu/Debian-based)
- `make` installed in WSL: `sudo apt-get install -y make`
- `poetry` not installed in WSL (`which poetry` returns nothing)

**Reproduction command:**
```bash
cd /mnt/c/Projects/EPM-SDAI/codemie && make ruff
```

**Observed error:**
```
make: poetry: No such file or directory
make: *** [Makefile:31: ruff] Error 127
```

## Fix Options

**Option 1 — Install `poetry` in WSL**
```bash
curl -sSL https://install.python-poetry.org | python3 -
```
Makes the hook work as-is. Requires `poetry` to be present in every developer's WSL environment.

**Option 2 — Remove `poetry run` dependency from the Makefile `ruff` target**

Replace `poetry run ruff` with a direct `ruff` call or `uvx ruff`, removing the `poetry` dependency entirely:
```makefile
ruff:
    uvx ruff format
    uvx ruff check --fix
    uvx ruff check
```
More portable — works without `poetry` installed.
