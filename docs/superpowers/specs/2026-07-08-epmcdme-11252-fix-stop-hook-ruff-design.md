# EPMCDME-11252: Fix Stop Hook — Document Poetry Global Install Requirement

## Problem

The Claude Code Stop hook (`cd "$CLAUDE_PROJECT_DIR" && make ruff`) fails on environments where `poetry` is not in the PATH of non-login subshells:

```
make: poetry: No such file or directory
make: *** [Makefile:31: ruff] Error 127
```

The root cause is a developer setup problem, not a code problem. `poetry` is by design a globally installed tool and is expected to be discoverable in any shell, including non-login subshells. The hook runs in a non-login subshell, so PATH entries added only in `.bashrc` are not picked up.

## Decision

The fix belongs in documentation, not in the Makefile. Adding PATH fallbacks or graceful-degradation guards to the Makefile would:

- Silently hide a broken developer setup instead of surfacing it
- Create inconsistency — other `poetry`-dependent Makefile targets (`test`, `build`, `install`, `license`, `run`) would still fail
- Work around a misunderstanding rather than correct it

The correct signal to a developer is: "your setup is incomplete — fix it." The error message from `make ruff` (`poetry: No such file or directory`) already communicates this clearly. The fix is to explain, in `CLAUDE.md`, exactly what is expected and how to verify and repair it.

Machine-specific workarounds (e.g. WSL PATH prefix) belong in `settings.local.json`, which is never committed.

## Fix

Add a `Prerequisites` section to `CLAUDE.md` documenting the poetry global-install requirement and the diagnostic command.

### CLAUDE.md

```markdown
## Prerequisites

Before using Claude Code in this repository, ensure your local environment
is fully set up per the [README setup guide](README.md#prerequisites--setup).

`poetry` must be installed globally and discoverable in your system PATH —
not just your interactive shell. The Stop hook runs `make ruff` in a
non-login subshell, so PATH entries added only in `.bashrc` are not picked
up.

To verify your setup:

```bash
env -i PATH="$PATH" poetry --version
```

If that fails, add poetry's install directory (e.g. `~/.local/bin`) to
`/etc/environment` or your shell's login profile (`.profile`, not `.bashrc`).
```

No Makefile changes. No `settings.json` changes.

## Behaviour

| Scenario | Before | After |
|---|---|---|
| poetry correctly installed globally | hook works | hook works (unchanged) |
| poetry in `.bashrc` only (broken setup) | Error 127 — contributor confused | Error 127 — contributor reads CLAUDE.md and fixes setup |

## Acceptance Criteria Mapping

| AC | Satisfied by |
|---|---|
| Root cause documented so contributors can fix their setup | CLAUDE.md Prerequisites section with diagnostic command and remediation steps |
| No regression to shared hook or Makefile | Diff is CLAUDE.md only — Makefile and settings.json unchanged |

## Out of Scope

- Makefile changes — no guard, no fallback, no PATH patching in the shared config
- `settings.json` changes — the shared hook stays clean (`cd "$CLAUDE_PROJECT_DIR" && make ruff`)
- Other `poetry run` targets (`install`, `test`, `build`, `license`, `run`) — unchanged
- CI pipeline — unaffected; poetry is available in CI
