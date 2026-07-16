# EPMCDME-11252: Fix Stop Hook — Document Poetry Global Install Requirement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Prerequisites section to `CLAUDE.md` documenting that `poetry` must be globally installed and discoverable in non-login shell PATH, along with the diagnostic command and remediation steps.

**Architecture:** Documentation-only change. No Makefile changes, no `settings.json` changes, no source code changes. The error message from `make ruff` already communicates the problem clearly; this adds explanation so contributors know how to fix their setup rather than work around it in code.

**Tech Stack:** Markdown only

## Global Constraints

- Only `CLAUDE.md` is modified — no Makefile, no settings.json, no source files
- The diagnostic command must be POSIX-compatible (`env -i PATH="$PATH" poetry --version`)
- Remediation guidance must target non-login shell PATH (`/etc/environment` or `.profile`, not `.bashrc`)

---

### Task 1: Add Prerequisites section to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing
- Produces: `CLAUDE.md` with a Prerequisites section visible to contributors and Claude Code on session start

- [ ] **Step 1: Verify current CLAUDE.md state**

```bash
cat CLAUDE.md
```

Expected: file contains only `@AGENTS.md` with no Prerequisites section.

- [ ] **Step 2: Add the Prerequisites section**

Open `CLAUDE.md`. Replace the entire file content with:

```markdown
@AGENTS.md

## Prerequisites

Before using Claude Code in this repository, ensure your local environment
is fully set up per the [README setup guide](README.md#prerequisites--setup).

`poetry` must be installed globally and discoverable in your system PATH —
not just your interactive shell. The Stop hook runs `make ruff` in a
non-login subshell, so PATH entries added only in `.bashrc` are not picked
up.

To verify your setup:

​```bash
env -i PATH="$PATH" poetry --version
​```

If that fails, add poetry's install directory (e.g. `~/.local/bin`) to
`/etc/environment` or your shell's login profile (`.profile`, not `.bashrc`).
```

- [ ] **Step 3: Verify the file looks correct**

```bash
cat CLAUDE.md
```

Expected: `@AGENTS.md` on line 1, followed by the Prerequisites section.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "EPMCDME-11252: Document poetry global install requirement in CLAUDE.md"
```
