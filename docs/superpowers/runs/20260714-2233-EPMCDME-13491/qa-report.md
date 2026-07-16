# QA Gate Report — 20260714-2233-EPMCDME-13491

**Branch**: EPMCDME-13491_local-auth-bearer-jwt-fix
**Runner**: custom (guide-first — `.ai-run/guides/quality-gates.md` / Makefile targets)
**Started**: 2026-07-14T21:05:00Z
**Status**: BLOCKED (all blocking findings pre-exist the run or are environmental; none attributable to this branch's diff — see attribution)

## Gates

| Gate | Status | Duration | Command | Notes |
|------|--------|----------|---------|-------|
| lint | PASS | 1s | `make ruff` | format + fix + check all clean; user's dirty files verified ruff-clean beforehand (not modified by gate) |
| build | PASS | 4s | `make build` | codemie-0.8.0 wheel built |
| license | PASS | 1s | `make license-check` | 1916 files, 0 missing headers |
| secrets | FAIL (pre-existing) | 16s | `make gitleaks` | 1 finding: `.env:generic-api-key:1` — in the user's LOCAL uncommitted `.env` modification only. This branch's commits never touch `.env`; the finding cannot ship via the MR. |
| unit | FAIL (pre-existing/env) | 144s | `make test` | 12969 passed, 62 failed, 29 errors, 129 skipped. Attribution below. |
| affected | PASS | 16s | `poetry run pytest tests/codemie/rest_api/security/test_persistent_user_provider.py` | 13/13 pass (incl. 3 new tests) |
| coverage | N/A | — | `make coverage` | not requested (guide Skip-if) |
| sonar | SKIPPED | — | `make sonar-local` | credentials/config not verified available (guide Skip-if) |
| ui | SKIPPED | — | (n/a) | no UI surface changed — green outcome |

## Failure detail / attribution

**Unit gate (62 failed + 29 errors) — none in the run's diff scope:**

1. **45 failures/errors in `tests/codemie/service/google_oauth/*` and `tests/codemie/rest_api/routers/test_sharepoint_oauth.py`** — caused by the user's UNCOMMITTED working-tree refactor of `google_oauth.py`/`sharepoint_oauth.py` (lazy-singleton: module globals `oauth_service`/`_pkce_service` are now `None` at import, so `patch.object(...)` raises `AttributeError: None does not have the attribute '_redis'` / `'_generate_code_verifier'`). Branch guard decision was proceed-dirty; these files are not part of this branch's commits.
2. **~45 failures in `tests/enterprise/mcp_auth/*` and `test_toolkit_service_auth_resolver.py`** — `ModuleNotFoundError: No module named 'codemie_enterprise'`: the enterprise package is not installed in this local environment. Environmental, unrelated to the diff.
3. **Auth-area confirmation**: `tests/codemie/rest_api/security/` + `test_local_auth_router.py` → 146 passed, 1 failed, 3 skipped. The single failure (`test_local_idp.py::test_authenticate_db_success_with_user_management_enabled`) is an order-dependent pre-existing flake: it PASSES inside the full `make test` run, fails only in isolation, exercises `LocalIdp` (untouched by this run), and its behavior is driven by `ENV=local` in the user's local `.env`.

**Secrets gate**: the flagged key exists only in the local working-tree `.env` (lines 1-2 modified locally vs HEAD). `git log` confirms this branch adds no `.env` change.

**Environment note**: the local py3.13 poetry env could not satisfy the lock (`tree_sitter_languages` has no cp313 wheels); a py3.12 env was created (`poetry env use python3.12` + install) to run the gates — matching the project's historical test environment (cp312 pycache).

## Drift signal

no
