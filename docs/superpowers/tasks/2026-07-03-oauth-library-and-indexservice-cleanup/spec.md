# OAuth Library Migration and IndexService Cleanup

**Date**: 2026-07-03  
**Branch**: EPMCDME-13222_google-docs-oauth  
**Status**: Approved

---

## Overview

Two independent improvements to the Google OAuth integration:

1. **Adopt google-auth-oauthlib library** - Replace manual httpx-based OAuth implementation with Google's official library
2. **Remove unused IndexService class** - Delete dead code that was added but never integrated

Both tasks are scoped to the Google OAuth feature only. No other parts of the system are affected.

---

## Background

### Current State

**OAuth Implementation** (`src/codemie/service/google_oauth_settings_service.py`):
- 150+ lines of manual PKCE generation, token exchange, and refresh logic
- Uses httpx.AsyncClient for direct HTTP calls to Google OAuth endpoints
- Manually constructs authorization URLs, exchanges codes, and refreshes tokens

**IndexService** (`src/codemie/service/index/index_service.py`):
- Contains unused `create_google_doc_datasource` method (lines 344-386)
- Never called anywhere in the codebase
- Datasource creation happens via `GoogleDocDatasourceProcessor` instead

### Historical Context

The branch originally used `google-auth-oauthlib.flow.Flow` (commit `5df3390ad`), then switched to manual httpx implementation when PKCE was added (commit `0c13bd979`). The original Flow-based implementation worked without async issues - methods were regular `def`, not `async def`, and OAuth callbacks are rare enough that brief sync I/O is acceptable.

---

## Task 1: Adopt google-auth-oauthlib

### Goal

Replace manual OAuth implementation with `google-auth-oauthlib.flow.Flow` to reduce maintenance burden and eliminate security-critical manual PKCE code.

### Approach

**Use synchronous Flow.fetch_token()** - Same pattern as the original implementation that worked on this branch.

- Service methods change from `async def` to regular `def`
- Use `Flow.from_client_config()` for initialization
- Use `flow.authorization_url()` with PKCE parameters for auth URL generation
- Use `flow.fetch_token(code=code, code_verifier=verifier)` for token exchange
- Extract credentials from `flow.credentials` object

### Justification for Sync

OAuth callbacks are rare user-initiated operations (~100-500ms network call, once per user authorization). The original implementation proved this works without blocking issues. FastAPI handles brief sync I/O in routes without degrading performance for typical OAuth workloads.

### Implementation Details

**Files to modify:**
1. `src/codemie/service/google_oauth_settings_service.py` - Replace manual OAuth logic with Flow
2. `src/codemie/rest_api/routers/google_oauth.py` - Update callback handler if needed
3. `pyproject.toml` - Add `google-auth-oauthlib` dependency

**Key changes:**

**Before (manual PKCE):**
```python
async def initiate_flow(self, user_id: str):
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode("utf-8").rstrip("=")
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
```

**After (Flow-based):**
```python
def initiate_flow(self, user_id: str):
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": config.google_oauth_client_id,
                "client_secret": config.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
```

**Note:** PKCE is handled automatically by Flow when `include_granted_scopes="true"` is set or when Flow detects it's appropriate for the client type.

**Token Exchange:**

**Before:**
```python
async with httpx.AsyncClient() as client:
    response = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
    )
    token_data = response.json()
```

**After:**
```python
flow = Flow.from_client_config(...)
flow.fetch_token(code=code)
credentials = flow.credentials

# Extract token data
access_token = credentials.token
refresh_token = credentials.refresh_token
expires_at = int(credentials.expiry.timestamp()) if credentials.expiry else int(time.time()) + 3600
```

### Behavioral Changes

**What stays the same:**
- Redis state storage with PKCE code_verifier
- Token encryption before database storage
- Same scopes: `openid`, `userinfo.email`, `documents.readonly`
- Same callback URL and redirect flow
- Same token refresh logic (can continue using httpx for refresh or adopt `google.auth.credentials.Credentials.refresh()`)

**What changes:**
- Method signatures: `async def` → `def`
- Internal implementation: httpx calls → Flow methods
- Error handling: HTTP status codes → Flow exceptions
- PKCE generation: manual → automatic (Flow handles it)

### Migration Strategy

1. Add `google-auth-oauthlib` to dependencies
2. Refactor `initiate_flow()` to use Flow
3. Refactor token exchange in `handle_callback()` to use Flow
4. Keep token refresh as-is initially (can migrate separately if desired)
5. Test full OAuth flow: initiate → callback → token storage → datasource creation

### Backward Compatibility

**Redis state format:** Compatible - still stores `code_verifier` in state data  
**Token storage:** Compatible - same fields stored in database (access_token, refresh_token, expires_at, email)  
**API contracts:** Compatible - same endpoints, same request/response formats

### Testing Requirements

**Manual testing:**
1. Initiate OAuth flow - verify auth URL has correct PKCE parameters
2. Complete callback - verify tokens stored in database
3. Create Google Docs datasource - verify access_token retrieved and works
4. Token refresh - verify refresh_token refreshes successfully

**No unit tests required** - OAuth flow is integration-heavy, end-to-end testing is more valuable than mocking Flow internals.

---

## Task 2: Remove IndexService Class

### Goal

Delete unused `IndexService.create_google_doc_datasource` method to eliminate dead code and reduce maintenance burden.

### Implementation

**File to modify:**
- `src/codemie/service/index/index_service.py` - Delete lines 344-386

**What gets deleted:**
```python
class IndexService:
    @classmethod
    def create_google_doc_datasource(
        cls,
        *,
        user: User,
        name: str,
        project_name: str,
        google_doc: str,
        setting_id: str,
        description: str = "",
        project_space_visible: bool = False,
        embedding_model: Optional[str] = None,
    ) -> IndexInfo:
        # ... (43 lines of unused code)
```

**What stays:**
- `IndexStatusService` class (lines 46-342) - used in 3 files
- All helper methods and utilities in the file
- All imports (none are exclusively for IndexService)

### Verification

**Pre-deletion check:**
```bash
# Confirm zero callers
grep -r "IndexService\.create_google_doc_datasource" src/ tests/
grep -r "from.*index_service import.*IndexService[^S]" src/ tests/
```

**Post-deletion check:**
```bash
# Verify IndexStatusService still works
python -m pytest tests/codemie/service/index/test_index_service.py -v
```

### Risk Assessment

**Risk: NONE**
- Method never called
- No imports of `IndexService` exist
- Only `IndexStatusService` is imported elsewhere
- Datasource creation is handled by `GoogleDocDatasourceProcessor`

---

## Implementation Order

1. **Task 2 first** (IndexService cleanup) - 5 minutes, zero risk, immediate value
2. **Task 1 second** (OAuth library adoption) - 1-2 hours, requires end-to-end testing

---

## Success Criteria

### Task 1 (OAuth Library)
- [ ] `google-auth-oauthlib` added to pyproject.toml
- [ ] Manual PKCE code removed from google_oauth_settings_service.py
- [ ] Manual httpx token exchange removed
- [ ] Flow-based initiate_flow() implemented
- [ ] Flow-based token exchange in handle_callback() implemented
- [ ] End-to-end OAuth flow tested: initiate → callback → datasource creation
- [ ] Token refresh still works (existing or migrated)
- [ ] Code review passes

### Task 2 (IndexService)
- [ ] Lines 344-386 deleted from index_service.py
- [ ] No imports broken (verified with grep)
- [ ] IndexStatusService tests pass
- [ ] Code review passes

---

## Non-Goals

**Out of scope for this work:**
- Migrating token refresh to use `google.auth.credentials.Credentials.refresh()` (can be done separately)
- Changing token storage format (keep current encrypted database storage)
- Adding async transport wrapper (sync is proven to work)
- Modifying other OAuth features (SharePoint, Azure, etc.)
- Adding new OAuth scopes or features
- Performance optimization beyond code reduction

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Flow behavioral differences vs manual | Low | Medium | Test full OAuth flow end-to-end before merging |
| Dependency size increase (~2MB) | Certain | Low | Acceptable for maintenance benefit |
| Breaking existing OAuth sessions | Low | Medium | Redis state TTL is 10min, users can re-auth |
| Import errors from IndexService deletion | Very Low | Low | Pre-deletion grep confirms zero callers |

---

## Dependencies

**New dependency:**
```toml
google-auth-oauthlib = "^1.2.0"
```

**Existing dependencies used:**
- `google-auth` (already installed) - used by google-auth-oauthlib
- `httpx` (already installed) - can keep for token refresh if desired
- `redis` (already installed) - state storage unchanged

---

## Rollback Plan

**Task 1 (OAuth Library):**
- If Flow fails in production: revert commit, fall back to manual httpx implementation
- Users may need to re-authorize (Redis state expires in 10min anyway)
- No database migration needed (token format unchanged)

**Task 2 (IndexService):**
- If deletion breaks something: revert commit (git restore)
- Extremely unlikely given zero callers confirmed via grep

---

## Follow-up Work (Optional)

After this work completes:

1. **Migrate token refresh** to use `google.auth.credentials.Credentials.refresh()` for consistency
2. **Add logging** for OAuth flow steps (already exists, verify after migration)
3. **Documentation update** if OAuth setup guide references manual implementation
4. **Consider async wrapper** if blocking becomes an issue (unlikely given historical evidence)
