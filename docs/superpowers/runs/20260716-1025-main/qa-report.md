# QA Report — EPMCDME-13552

**Run**: 20260716-1025-main  
**Branch**: EPMCDME-13552_github-get-params  
**Phase**: 8  
**Date**: 2026-07-16

---

## Gate Results

| Gate | Command | Result | Notes |
|------|---------|--------|-------|
| Lint/Format | `make ruff` | PASS | 2141 files unchanged, all checks pass |
| Tests | `make test` | DRIFT | 45 pre-existing failures; in-scope: 29/29 pass |
| License Headers | `make license-check` | PASS | 1916 files, 0 missing headers |

---

## Test Drift Detail

**Total**: 13027 passed, 45 failed, 116 skipped in 174s

**Failing scope**: `tests/enterprise/mcp_auth/test_post_auth_401_bridge.py` (44 tests) and `tests/enterprise/mcp_auth/test_private_network_allowlist_bridge.py` (1 test)

**Pre-existing confirmation**: `git diff main..HEAD -- tests/enterprise/mcp_auth/` returns no output — our diff makes zero changes to this module. The `test_post_auth_401_bridge.py` file was last modified by MCP auth commits (EPMCDME-11515) unrelated to EPMCDME-13552.

**In-scope gate (GitHub tests)**: 29/29 PASS — all `tests/codemie_tools/core/vcs/github/` tests pass, including the two new regression tests added by this ticket.

**Drift verdict**: Not caused by this change. Pre-existing on `main`.

---

## Summary

- No regressions introduced by EPMCDME-13552.
- All in-scope tests pass.
- Pre-existing test failures in `enterprise/mcp_auth` are baseline drift on `main` and out of scope for this ticket.
- License headers: compliant.
- Ruff: clean.
