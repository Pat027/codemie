# QA Gate Report — mcp-schema-ref-resolution-order

**Branch**: EPMCDME-13328_mcp-schema-ref-resolution-order
**Runner**: Makefile (poetry-based, per `.ai-run/guides/quality-gates.md`)
**Started**: 2026-07-08
**Status**: PASSED (user-confirmed override on Secret Scan — see below)

## Gates

| Gate           | Status | Command | Notes |
|----------------|--------|---------|-------|
| Lint/Format    | PASS   | `make ruff` | 1 file reformatted (line-length collapse in new test), committed. `ruff check` clean. |
| Build          | PASS   | `make build` | sdist + wheel built successfully. |
| License Headers| PASS   | `make license-check` | 1878 files checked, 0 missing headers. |
| Secret Scan    | FAIL* | `make gitleaks` | 2 findings, both in files explicitly listed in `.gitignore` (`.codex/config.toml`, `.mcp.json.lock`) — pre-existing local dev config, untracked, unrelated to this diff, will never be committed. Not attributable to this change. |
| Tests          | PASS   | `make test` | 12938 passed, 115 skipped, 0 failed. |
| Coverage       | SKIPPED | (n/a) | Not requested for this task. |
| Static Analysis (Sonar) | SKIPPED | (n/a) | Not requested for this task. |

## Failure detail

Secret scan findings (both gitignored, local-only, pre-existing before this session):
```
File: .codex/config.toml:15  (RuleID: generic-api-key) — CONTEXT7_API_KEY
File: .mcp.json.lock:11      (RuleID: generic-api-key) — BRAVE_API_KEY
```
Both paths matched by `.gitignore:58` (`/.mcp.json*`) and `.gitignore:62` (`/.codex/config.toml`). Neither is tracked by git, neither is touched by this diff, and neither will ever be committed/pushed. `make gitleaks` scans the filesystem (not git history/staged content), so it flags gitignored local secrets unconditionally. This is a pre-existing local-environment condition, not introduced by this change.

## Drift signal

no — implementation matches plan.md; no spec exists for sdlc-light to drift against.
