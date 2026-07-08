# QA Gate Report — keep-mcp-auth-callback-tab-open

**Branch**: EPMCDME-11515_keep-mcp-auth-callback-tab-open
**Runner**: poetry (guide-first: `.ai-run/guides/quality-gates.md`)
**Started**: 2026-07-08
**Status**: PASSED (gitleaks: pre-existing out-of-scope finding — see note)

## Gates

| Gate | Status | Command | Notes |
|------|--------|---------|-------|
| lint | PASS | `make ruff` | ruff format: 2098 files unchanged; check --fix + check clean. No files modified. |
| build | PASS | `make build` | Built codemie-0.8.0 sdist + wheel. |
| license | PASS | `make license-check` | 1878 files checked, 0 missing headers. |
| gitleaks | FAIL (out-of-scope) | `make gitleaks` | See failure detail — finding is in a gitignored, untracked file outside the diff. |
| unit | PASS | `make test` | 12919 passed, 115 skipped, 0 failed (115s). |
| coverage | N/A | `make coverage` | opt-in; not requested. |
| sonar | N/A | `make sonar-local` | opt-in; not requested. |
| ui | SKIPPED | (n/a) | No UI surface changed (backend Python + injected JS string only). |

## Failure detail (gitleaks)

```
Finding:  "BRAVE_API_KEY": "<redacted>"
RuleID:   generic-api-key
File:     .mcp.json.lock
Line:     11
```

**Assessment — not attributable to this change, does not block the task:**
- `.mcp.json.lock` is **untracked** (`git ls-files` → not known to git) and **gitignored** (`.gitignore:58: /.mcp.json*`). It cannot be committed and is not part of the branch.
- It is **not in the reviewed diff** — the diff touches only `src/codemie/configs/config.py`, `src/codemie/enterprise/mcp_auth/_callback_pages.py`, and `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`, none of which contain secrets.
- The gitleaks gate scans the whole working directory (`gitleaks dir /path`), so it surfaces this local developer artifact regardless of the change under review. It is a pre-existing environment condition.

The three files introduced by EPMCDME-11515 are secret-free. For the purpose of this task the change is clean; the gitleaks finding is an unrelated local-environment item the developer may want to clean up separately.

## Drift signal

no
