# Final Plan Corrections Needed Before Implementation

## Status
Plan is 95% correct. Two minor pattern adjustments needed that implementer can handle inline:

## 1. Session Management Pattern (Task 7 - Router)

**Current (incorrect):**
```python
def get_oauth_service(session: Session = Depends(get_session)) -> GoogleOAuthService:
    redis = create_redis_client()
    repo = GoogleOAuthTokenRepository(session)
    ...
    return GoogleOAuthService(redis, token_service)

@router.post("/initiate")
async def initiate_oauth(
    user: User = Depends(authenticate),
    oauth_service: GoogleOAuthService = Depends(get_oauth_service)
):
```

**Correct pattern (from cost_centers.py, sharepoint_oauth.py):**
```python
@router.post("/initiate")
async def initiate_oauth(
    user: User = Depends(authenticate)
):
    with get_session() as session:
        redis = create_redis_client()
        repo = GoogleOAuthTokenRepository(session)
        encryption_service = EncryptionFactory.get_current_encryption_service()
        token_service = GoogleOAuthTokenService(repo, encryption_service)
        oauth_service = GoogleOAuthService(redis, token_service)
        
        auth_url, state = oauth_service.initiate_flow(user.id)
        return InitiateResponse(authorization_url=auth_url)
```

**Action:** Remove `get_oauth_service()` and `get_token_service()` dependency functions. Initialize services inline in each endpoint using `with get_session() as session:`.

## 2. File Paths - `src/` Prefix

**Current:** Plan says create `codemie/rest_api/models/google_oauth.py`

**Correct:** Create `src/codemie/rest_api/models/google_oauth.py`

**Note:** Import paths remain correct as `from codemie.rest_api.models.google_oauth import ...` because `src/` is in PYTHONPATH. Only the file creation paths need the `src/` prefix.

**Action:** When creating files, use `src/codemie/...` paths, not `codemie/...` paths.

## All Other Corrections Applied ✅

- ✅ Import paths use `codemie.*` (not `src.codemie.*`)
- ✅ `BaseModelWithSQLSupport` from `codemie.rest_api.models.base`
- ✅ Exceptions extend `ExtendedHTTPException` with `code=` parameter
- ✅ `EncryptionFactory` from `codemie.service.encryption.encryption_factory`
- ✅ `BaseEncryptionService` from `codemie.service.encryption.base_encryption_service`
- ✅ `create_redis_client()` from `codemie.clients.redis`
- ✅ `authenticate` dependency on protected endpoints
- ✅ Token revocation on disconnect
- ✅ datetime import fixed

## Implementation Note

These two remaining issues are minor and follow established project patterns. The implementer (subagent-driven-development or executing-plans) can apply these corrections inline during Task 7 execution. The plan is ready for approval and implementation.
