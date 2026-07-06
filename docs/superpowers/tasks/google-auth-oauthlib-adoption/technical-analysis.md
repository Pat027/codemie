# Technical Research

**Task**: oauth google-auth-oauthlib PKCE dead-code removal index-service
**Generated**: 2026-07-03T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

Assess these two independent tasks as a single work unit:

## Task 1: Adopt google-auth-oauthlib library
Replace manual httpx-based OAuth 2.0 PKCE implementation with google-auth-oauthlib Flow API.

**Context from technical analysis**:
- Current: 150+ lines of manual PKCE generation, token exchange, refresh in google_oauth_settings_service.py
- Target: Use google-auth-oauthlib.flow.Flow for standard OAuth flow
- Files to modify: 1 service file, 1 router file
- Testing: Full OAuth flow (initiate, callback, token refresh)
- Risk: Medium (security-critical code, behavioral changes possible)

## Task 2: Remove unused IndexService class
Delete IndexService.create_google_doc_datasource method (lines 344-386 of index_service.py).

**Context from technical analysis**:
- Usage: Zero callers found in codebase
- IndexStatusService (lines 46-342) remains untouched
- Datasource creation happens via GoogleDocDatasourceProcessor instead
- Risk: None (dead code removal)

---

## 2. Codebase Findings

### Existing Implementations

**Task 1 — OAuth service and router:**
- `src/codemie/service/google_oauth_settings_service.py` — 536-line service implementing the full OAuth 2.0 PKCE flow: PKCE verifier/challenge generation (`_generate_code_verifier`, `_generate_code_challenge`), authorization URL assembly via `urlencode` against `_GOOGLE_AUTH_URL`, token exchange via raw `httpx.AsyncClient.post` to `_GOOGLE_TOKEN_URL`, token refresh with a 5-minute buffer via another raw `httpx.AsyncClient.post`, user email fetch via raw `httpx.AsyncClient.get`, and Redis-backed state/result management with TTL and encryption
- `src/codemie/rest_api/routers/google_oauth.py` — FastAPI router with 3 endpoints (`/initiate`, `/callback`, `/status/{state}`); thin delegation to `GoogleOAuthSettingsService`; zero `httpx` usage; zero OAuth logic

**Task 2 — Dead code:**
- `src/codemie/service/index/index_service.py` — contains two distinct classes: `IndexStatusService` (lines 46–342, actively used) and `IndexService` (lines 344–386, zero callers); `IndexService` has a single `@classmethod` — `create_google_doc_datasource` — with no callers anywhere in `src/`

**Supporting files:**
- `src/codemie/configs/config.py` — defines `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and the computed `google_oauth_redirect_uri` property
- `src/codemie/rest_api/models/settings.py` — ORM model `Settings` and `CredentialValues` used by the OAuth service for token persistence
- `src/codemie/rest_api/routers/index.py` — imports `IndexStatusService` only; never imports `IndexService`
- `src/codemie/service/provider/datasource/provider_datasource_schema_service.py` — imports `IndexStatusService` only; never imports `IndexService`

### Architecture and Layers Affected

**Task 1:**
- REST API layer: `rest_api/routers/google_oauth.py` — endpoint signatures may change if `Flow` requires different response shapes
- Service layer: `service/google_oauth_settings_service.py` — all manual PKCE logic, httpx calls, and URL constants replaced with `google_auth_oauthlib.flow.Flow` and `google.oauth2.credentials.Credentials`
- Infrastructure: Redis client (state/result storage) — unchanged; encryption via `EncryptionFactory` — unchanged
- ORM / persistence: `CredentialValues` rows updated on token refresh — unchanged

**Task 2:**
- Service layer only: `service/index/index_service.py` lines 344–386 — remove the `IndexService` class in its entirety; `IndexStatusService` is untouched

### Integration Points

**Task 1:**
- `google_auth_oauthlib.flow.Flow.from_client_config()` — replaces manual authorization URL assembly and token exchange; requires a `client_secrets` dict constructed from `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`
- `google.oauth2.credentials.Credentials` + `google.auth.transport.requests.Request` — replaces manual `httpx` refresh call for token refresh path
- Google token endpoint (`https://oauth2.googleapis.com/token`) — currently called directly via httpx; will be called internally by the library
- Google userinfo endpoint (`https://www.googleapis.com/oauth2/v1/userinfo`) — NOT covered by `Flow`; `_fetch_user_email` must be preserved or replaced with a credentials-authenticated call
- Redis client — unchanged; state key prefix `codemie:google_oauth:state:`, result key prefix `codemie:google_oauth:result:`, `getdel` for atomic one-time consumption
- `EncryptionFactory` — unchanged; encrypts state and tokens before Redis and DB storage
- `CALLBACK_API_BASE_URL` → `google_oauth_redirect_uri` — must continue to match the redirect URI registered in Google Cloud Console

**Task 2:**
- No integration points — dead class with no callers

### Patterns and Conventions

- Service files are feature-scoped under `src/codemie/service/`; service constructors instantiate `EncryptionFactory().get_current_encryption_service()` directly
- All protected endpoints use the `authenticate` dependency from `src/codemie/rest_api/security/authentication.py`; tokens must never be logged
- Redis keys use namespaced prefixes; `getdel` used for atomic one-time state consumption
- OAuth library dependency: `google-auth = "^2.32.0"` is declared in `pyproject.toml`; `google-auth-oauthlib` is **not declared** — it must be added
- Scope list: `openid`, `userinfo.email`, `documents.readonly`
- Import namespace is `codemie.*` (not `src.codemie.*`)
- Exceptions extend `ExtendedHTTPException`; three custom exception classes exist: `GoogleOAuthStateError` (400), `GoogleOAuthTokenError` (401), `GoogleOAuthRefreshError` (401)

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/integration/google-docs-integration.md` — mandates keeping Google Docs ingestion inside `datasource/google_doc/` and `datasource/loader/`; prohibits hardcoding Google API clients in feature code; the `google-auth-oauthlib` flow must stay in the service layer
- `.ai-run/guides/development/security-patterns.md` — requires all auth flows to use the central `authenticate` dependency; forbids logging tokens or API keys
- `.ai-run/guides/architecture/service-layer-patterns.md` — services coordinate repositories and providers; avoid passing `Request` into business logic; feature-scoped service files under `src/codemie/service/`
- `.ai-run/guides/data/repository-patterns.md` — repositories own all data access; services must go through repositories, not raw storage

### Architectural Decisions

From `docs/superpowers/plans/2026-07-01-google-docs-oauth.md`:
- Use `google_auth_oauthlib.flow.Flow` for the OAuth flow in the service layer
- Use `google.oauth2.credentials.Credentials` + `google.auth.transport.requests.Request` for token refresh
- State stored in Redis with 10-minute TTL, consumed atomically on callback
- Tokens encrypted at rest via `EncryptionFactory.get_current_encryption_service()`
- Exception classes: `GoogleOAuthStateError` (400), `GoogleOAuthTokenError` (401), `GoogleOAuthRefreshError` (401)
- `GoogleOAuthToken` SQLModel extends `BaseModelWithSQLSupport`, stored in `google_oauth_tokens` table
- All protected endpoints use `authenticate` dependency; user identity from JWT only
- Token revocation at Google on disconnect via `POST https://oauth2.googleapis.com/revoke`

### Derived Conventions

- The live service (`google_oauth_settings_service.py`) currently has no `TODO`, `HACK`, `NOTE`, or `DECISION` comments — the implementation is clean but entirely manual
- The existing test suite for the service (`test_google_oauth_service.py`) already mocks `google_auth_oauthlib.flow.Flow.from_client_config`, indicating the test suite was written anticipating the library adoption; tests will not need to be rebuilt from scratch
- `IndexService` (lines 344–386) is a standalone class at the end of the file — deletion is a clean cut with no import side effects

---

## 4. Testing Landscape

### Existing Coverage

- `tests/codemie/service/test_google_oauth_service.py` — unit tests for a `GoogleOAuthService` class (mocks `google_auth_oauthlib.flow.Flow.from_client_config`); covers `initiate_flow`, `handle_callback` success and error paths, `None` expiry fallback, Redis state cleanup on exceptions. **Note**: this test file targets a class named `GoogleOAuthService`, not `GoogleOAuthSettingsService` — the class under test for Task 1 is `GoogleOAuthSettingsService`; this discrepancy must be resolved
- `tests/codemie/rest_api/routers/test_google_docs_oauth.py` — router integration tests covering 4 endpoints (initiate, callback, status, disconnect); patches `GoogleOAuthService`, `GoogleOAuthTokenRepository`, `GoogleOAuthTokenService`, `EncryptionFactory`, Redis, httpx; tests XSS escaping and security headers. **Note**: covers `google_docs_oauth.py` router, not the current `google_oauth.py` router
- `tests/codemie/service/index/test_index_service.py` — tests for `IndexStatusService` only; covers `get_index_info_list` and `get_users`; no test for `IndexService.create_google_doc_datasource`
- `tests/unit/exceptions/test_google_oauth_exceptions.py` — unit tests for all three custom OAuth exception classes
- `tests/unit/repository/test_google_oauth_token_repository.py` — CRUD tests for `GoogleOAuthTokenRepository` against in-memory SQLite
- `tests/unit/service/test_google_oauth_token_service.py` — unit tests for `GoogleOAuthTokenService`: encrypt-on-store, decrypt-on-retrieve, expired token refresh, not-found exception, delete delegation

### Testing Framework and Patterns

- pytest `^8.3.1` with pytest-asyncio `^0.23.7`, pytest-cov, pytest-env, pytest-mock, pytest-httpx
- `unittest.mock.MagicMock` / `Mock` for all collaborators; `patch` and `patch.object` as context managers
- `@pytest.fixture` (function-scope) for Redis, token service, repo, encryption service, and user mocks
- `db_session` fixture in `tests/unit/repository/conftest.py`: in-memory SQLite via `sqlmodel` + `StaticPool`
- Global `autouse=True` session-scoped `mock_database_engine` patches `PostgresClient.get_engine` for all tests
- `FastAPI.TestClient` (sync) for router tests with `dependency_overrides` to inject test `User`
- `side_effect` for exception simulation and `encrypt`/`decrypt` lambda transforms

### Coverage Gaps

- `GoogleOAuthSettingsService` (the actual Task 1 target) — **no test file exists**; the existing `test_google_oauth_service.py` targets a different class name (`GoogleOAuthService`)
- `google_oauth.py` router (Task 1 router) — no test file; `test_google_docs_oauth.py` covers the old `google_docs_oauth.py` router only
- PKCE code verifier/challenge generation — no unit tests for these private methods anywhere
- `IndexService.create_google_doc_datasource` — zero test coverage (task 2 dead code; no tests needed for deletion)
- Raw `httpx`-based token revocation in the disconnect endpoint — tested via mock patch only; no isolation tests

---

## 5. Configuration and Environment

### Environment Variables

- `GOOGLE_OAUTH_CLIENT_ID` — OAuth 2.0 Client ID; required for `Flow.from_client_config()` `client_secrets` dict
- `GOOGLE_OAUTH_CLIENT_SECRET` — OAuth 2.0 Client Secret; required for `Flow.from_client_config()` `client_secrets` dict and currently used in raw httpx token exchange and refresh calls
- `CALLBACK_API_BASE_URL` — used to compute `google_oauth_redirect_uri` (`{CALLBACK_API_BASE_URL}/v1/google-oauth/callback`); must match redirect URI registered in Google Cloud Console; passed as `redirect_uri` to `Flow`

### Configuration Files

- `src/codemie/configs/config.py` — defines all Google OAuth settings; `GOOGLE_OAUTH_CLIENT_ID` at line ~380, `GOOGLE_OAUTH_CLIENT_SECRET` at line ~381, `google_oauth_redirect_uri` computed property at line ~842
- `.env` — local dev overrides; contains real values for `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`

### Feature Flags and Deployment Concerns

- `google-auth-oauthlib` is absent from `pyproject.toml`; only `google-auth = "^2.32.0"` is declared; must run `poetry add google-auth-oauthlib` before any import of `google_auth_oauthlib.flow` will work in any environment
- The `client_secrets` dict format expected by `Flow.from_client_config()` must be assembled from the existing `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` env vars — no new env vars required
- Redis must remain available in all environments; OAuth state TTL is 10 minutes
- No `.env.example` exists at the repo root; if created, it must include `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `CALLBACK_API_BASE_URL`

---

## 6. Risk Indicators

- **Dependency not declared**: `google-auth-oauthlib` is absent from `pyproject.toml`; it must be added via `poetry add google-auth-oauthlib` before the migration can run; this affects all environments including CI
- **Test class name mismatch**: `tests/codemie/service/test_google_oauth_service.py` mocks `GoogleOAuthService`, but the live class is `GoogleOAuthSettingsService` — either the test targets a renamed class or a stale test file; must reconcile before claiming test coverage
- **Router test targeting wrong file**: `test_google_docs_oauth.py` covers `google_docs_oauth.py` (deleted per git status); the current router `google_oauth.py` has no direct test file — test coverage for the router is effectively zero post-rename
- **No test coverage for `GoogleOAuthSettingsService`**: the primary service being modified in Task 1 has no dedicated test file; new tests must be written as part of the migration
- **Userinfo fetch not covered by `Flow`**: `_fetch_user_email` uses a raw `httpx.AsyncClient.get` to `_GOOGLE_USERINFO_URL`; `google-auth-oauthlib.Flow` does not replace this call; it must be preserved or reworked using `google.oauth2.credentials.Credentials` with an authorized session
- **Security-critical code path**: PKCE and token exchange are security-critical; behavioral differences between the manual implementation and `Flow` (e.g., PKCE parameter names, state handling, error response shapes) must be explicitly validated
- **`httpx` vs `google-auth` transport mismatch**: `google-auth-oauthlib` uses `google.auth.transport.requests.Request` (synchronous, `requests`-based) for token refresh; the current service is fully async (`httpx.AsyncClient`); mixing sync transport in an async service requires care to avoid blocking the event loop
- **`IndexService` class has 19 cross-file grep hits**: Thread C noted "19 files across `src/` reference `IndexService`" — this must be verified; if any of those are import statements (even unused imports), they must be cleaned up along with the class deletion; Thread A confirmed only `IndexStatusService` is actually imported, but the count discrepancy should be confirmed before merging

---

## 7. Summary for Complexity Assessment

**Task 1 (google-auth-oauthlib adoption)** touches three architectural layers: the Service layer (`google_oauth_settings_service.py`, 536 lines), the REST API Router layer (`google_oauth.py`), and the Infrastructure/Transport layer (replacing `httpx` calls with `google_auth_oauthlib.flow.Flow` and `google.oauth2.credentials.Credentials`). The file change surface is moderate — one primary service file and one router file — but the service file contains 150+ lines of hand-rolled security logic that must be replaced cleanly. A new dependency (`google-auth-oauthlib`) must be added to `pyproject.toml`, and the async/sync transport mismatch between `httpx.AsyncClient` (current) and `google.auth.transport.requests.Request` (library default) is a non-trivial integration concern that could introduce event-loop blocking if not handled with `asyncio.run_in_executor` or `google.auth.transport.aiohttp`.

**Task 2 (IndexService dead code removal)** touches only the Service layer and is a clean deletion: `IndexService` at lines 344–386 of `index_service.py` has zero callers, zero test coverage, and is structurally isolated from `IndexStatusService`. The change surface is a single file, single class, ~43 lines. No router, no test, no config, no migration is affected. This task carries no meaningful risk.

**Test coverage posture** is the primary risk for Task 1. The service class being modified (`GoogleOAuthSettingsService`) has no dedicated test file. Existing test infrastructure (`test_google_oauth_service.py`, `test_google_docs_oauth.py`) appears to have been written against an earlier or differently-named class structure and will require reconciliation. The testing framework is mature (pytest + pytest-asyncio + pytest-httpx), and patterns for mocking `google_auth_oauthlib.flow.Flow` are already established in `test_google_oauth_service.py`, so new tests can follow existing patterns. Overall complexity for Task 1 is medium-high due to security sensitivity, the missing test file, the transport async/sync mismatch, and the need to preserve the userinfo fetch independently of `Flow`. Task 2 is trivially low complexity.
