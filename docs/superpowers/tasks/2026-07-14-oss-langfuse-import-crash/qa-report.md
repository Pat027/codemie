# QA Gate Report — oss-langfuse-import-crash

**Branch**: EPMCDME-13525_fix-oss-langfuse-import-crash
**Runner**: poetry (Tests gate executed inside Docker container `codemie-oss-test` due to a corrupted local venv unrelated to this ticket)
**HEAD**: d5a1a0d9904b49a098c0391b6c9cab75871d0edd
**Status**: BLOCKED (mechanically) — but see "Attribution" below; nothing in this ticket's own diff fails any gate

## Gates

| Gate | Status | Command | Notes |
|---|---|---|---|
| Lint And Format | **PASS** | `make ruff` | Initial run found a real formatting issue in the new test file (multi-line `raise AssertionError(...)`); fixed with `poetry run ruff format`, committed as `d5a1a0d99`. Full-repo re-run: "2104 files left unchanged", "All checks passed!" (format + check). |
| Build | **PASS** | `make build` | Built `codemie-0.8.0.tar.gz` and `codemie-0.8.0-py3-none-any.whl` cleanly. |
| License Headers | **PASS** | `make license-check` | "Checked 1883 files, 0 missing license headers" (full repo); also verified scoped to the 2 files this ticket touches. |
| Secret Scan | **FAIL** (pre-existing, out of scope) | `make gitleaks` | 1 leak found: `AZURE_OPENAI_API_KEY` in `.env` line 1 (rule `generic-api-key`). `.env` was already modified/dirty at session start, is explicitly out of this ticket's scope, and was never touched by this change. Gitleaks' `dir` scan mode scans the live filesystem, not the diff, so it flags this regardless of what this ticket changed. Not fixed — redacting a live local `.env` value is outside this ticket's scope and risks disrupting the user's local environment. |
| Tests | **FAIL** (mechanically, on full `tests/`) / **PASS** (scoped to this ticket) | `make test` (via `docker exec -w /app codemie-oss-test python -m pytest tests/`) | Full run: 64 failed, 12901 passed, 129 skipped, 29 errors. All 8 tests this ticket owns pass cleanly: `test_workflow_evaluation_service.py` (7) and `test_workflow_evaluation_service_import.py` (1), both natural-order collection, zero failures. See "Attribution" below — none of the 64 failures / 29 errors are caused by this ticket's diff. |
| Coverage | **SKIPPED** | `make coverage` | Not requested by the user or task. |
| Static Analysis | **SKIPPED** | `make sonar-local` | No Sonar token/config/network access confirmed available in this session. |
| Full Verification | **SKIPPED** | `make verify` | Composite of ruff + license + gitleaks + test, all already run individually above with identical inputs; re-running would just reproduce the same results. |

## Attribution of the 64 failed / 29 errors (Tests gate)

Every failing/erroring test was traced to one of two causes, **neither originating in this ticket's diff** (which is limited to `src/codemie/service/workflow_evaluation_service.py` + 2 test files):

1. **44 FAILED** — `tests/enterprise/mcp_auth/*` (30+4+3+3+2+1+1) — require the optional `codemie_enterprise` package, not installed in this OSS-only container (`codemie-oss-test`). Confirmed directly: other tests in the same run fail with `ModuleNotFoundError: No module named 'codemie_enterprise'`.
2. **2 FAILED** — `test_toolkit_service_auth_resolver.py` — same `ModuleNotFoundError: No module named 'codemie_enterprise'`.
3. **2 FAILED** — `test_svn_loader.py::test_rar_archive_is_unsupported`, `test_git_loader.py::test_is_unsupported_mime_type_returns_true_for_rar` — pre-existing mime-detection gap (`_is_unsupported_mime_type("archive.rar")` returns `None` instead of `True`), unrelated to any file in this ticket's scope.
4. **16 FAILED + 29 ERROR** — `test_sharepoint_oauth.py`, `test_populate_credentials.py`, `test_credential_preservation.py` — caused by a **pre-existing, uncommitted, unrelated** working-tree refactor of `src/codemie/rest_api/routers/google_oauth.py` and `sharepoint_oauth.py` (converting module-level singletons `oauth_service`/`_pkce_service` to lazy `_get_oauth_service()`/`_get_pkce_service()` getters). This refactor was already dirty in the working tree before this session started (per initial `git status`) and is explicitly out of this ticket's scope; it was never touched or committed by this ticket's work.

Sum check: 44 + 2 + 2 = 48 FAILED (enterprise/mime) + 16 FAILED (oauth) = **64 FAILED** total ✓. 29 ERROR (oauth) = **29 ERROR** total ✓. Fully accounted for.

## Failure detail (Secret Scan)

```
Finding:     AZURE_OPENAI_API_KEY="REDACTED"
RuleID:      generic-api-key
Entropy:     4.226410
File:        .env
Line:        1
```

## Drift signal

no — implementation matches spec.md and plan.md; `workflow_evaluation_service.py` guards the `ExperimentItem` import under `TYPE_CHECKING` exactly as specified, with no deviation.
