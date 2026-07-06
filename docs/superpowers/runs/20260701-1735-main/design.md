# Google Docs OAuth 2.0 Authorization Design

**Date:** 2026-07-01  
**Work Item:** [EPMCDME-13222](https://jiraeu.epam.com/browse/EPMCDME-13222)  
**Author:** AI Assistant  
**Status:** Draft

## Overview

Replace the shared service account approach for Google Docs datasource indexing with per-user OAuth 2.0 authorization. Tokens are fully managed backend-side with automatic refresh, enabling secure per-user access and scheduled reindexing without frontend involvement.

## Goals

- Implement per-user OAuth 2.0 authorization for Google Docs datasources
- Store tokens backend-side with encryption (frontend never sees tokens)
- Automatic token refresh before expiry
- Enable scheduled/automatic reindexing without frontend intervention
- Secure token storage with CSRF protection
- Clear error handling for authorization failures

## Non-Goals

- Multi-scope support (only Google Docs read access for now)
- Token sharing across users
- Migration of existing service account datasources (new feature only)

## Architecture

### High-Level Components

```
┌─────────────┐
│  Frontend   │
└──────┬──────┘
       │ 1. POST /initiate
       ▼
┌─────────────────────┐      ┌─────────────┐
│  OAuth API Router   │─────▶│    Redis    │ (temp state)
│  /v1/google-docs/   │      └─────────────┘
│      oauth/         │
└──────┬──────────────┘
       │ 2. Redirect to Google
       ▼
┌─────────────────────┐
│   Google OAuth      │
│  Authorization      │
└──────┬──────────────┘
       │ 3. Callback
       ▼
┌─────────────────────┐      ┌──────────────────────┐
│  OAuth Callback     │─────▶│  PostgreSQL          │
│  Handler            │      │  google_oauth_tokens │
└──────┬──────────────┘      └──────────────────────┘
       │ 4. Store tokens
       │
       ▼
┌─────────────────────┐
│  Datasource         │
│  Processor          │─────▶ Get valid token
└─────────────────────┘       (auto-refresh if expired)
```

### Layer Architecture

**API Layer:**
- `src/codemie/rest_api/routers/google_docs_oauth.py` - OAuth endpoints

**Service Layer:**
- `src/codemie/service/google_oauth_service.py` - OAuth flow management
- `src/codemie/service/google_oauth_token_service.py` - Token CRUD and refresh

**Repository Layer:**
- `src/codemie/repository/google_oauth_token_repository.py` - Database access

**Model Layer:**
- `src/codemie/rest_api/models/google_oauth.py` - SQLModel definitions

## Database Schema

### New Table: `google_oauth_tokens`

```python
class GoogleOAuthToken(BaseModelWithSQLSupport, table=True):
    __tablename__ = "google_oauth_tokens"
    
    user_id: str = SQLField(primary_key=True, index=True)  # FK to User
    access_token: str = SQLField(max_length=2048)  # Encrypted
    refresh_token: str = SQLField(max_length=512)  # Encrypted
    expires_at: int  # Unix timestamp
    scopes: str  # Space-delimited, as granted by Google
    email: str = SQLField(max_length=255)  # Google account email
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)
```

**Key Design Decisions:**
- **One token set per user** (primary key on `user_id`)
- **Tokens encrypted at rest** using `EncryptionFactory`
- **No per-datasource tokens** - user authorizes once for all Google Docs datasources
- **Scopes stored as granted** by Google (no default value in schema)

**Migration:**
- Alembic migration creates table
- No data migration needed (new feature)

## API Endpoints

### POST `/v1/google-docs/oauth/initiate`

**Purpose:** Start OAuth flow  
**Auth:** Required (authenticated user)  
**Request:** None  
**Response:**
```json
{
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "state": "random-csrf-token"
}
```

**Side Effects:**
- Generates cryptographically random state token
- Stores in Redis: `codemie:google_oauth:state:{state}` → `{user_id, timestamp}` (TTL: 600s)
- Returns Google authorization URL with state parameter

**Scopes Requested:**
- `https://www.googleapis.com/auth/documents.readonly`

---

### GET `/v1/google-docs/oauth/callback`

**Purpose:** Handle Google's OAuth redirect  
**Auth:** None (public callback endpoint)  
**Query Params:** `code`, `state`, `error` (from Google)  
**Response:** HTML page with success/error message

**Flow:**
1. Validate state parameter (CSRF protection)
2. Extract `user_id` from Redis state
3. Exchange authorization code for tokens at Google's token endpoint
4. Store encrypted tokens in `google_oauth_tokens` table (upsert on `user_id`)
5. Fetch user email from Google (for display purposes)
6. Write result to Redis: `codemie:google_oauth:result:{state}` (TTL: 300s)
7. Return HTML page: "Authentication successful. You can close this window."

**Error Handling:**
- Invalid/expired state → 400 HTML page
- User denied authorization → Store error in Redis, show friendly HTML message
- Token exchange fails → Store error in Redis, show error HTML message

---

### GET `/v1/google-docs/oauth/status/{state}`

**Purpose:** Frontend polls to check OAuth completion  
**Auth:** Required  
**Response:**

```json
// Pending (202)
{"status": "pending"}

// Success (200)
{"status": "success", "email": "user@gmail.com"}

// Error (400)
{"status": "error", "message": "Authorization declined"}
```

**Security:**
- Validates `user_id` in Redis result matches authenticated user
- Returns 403 if state belongs to different user
- Deletes result from Redis after reading (one-time use)

---

### POST `/v1/google-docs/oauth/disconnect`

**Purpose:** Revoke authorization and delete tokens  
**Auth:** Required  
**Response:**
```json
{"message": "Google Docs authorization removed successfully"}
```

**Side Effects:**
1. Calls Google's revoke endpoint: `https://oauth2.googleapis.com/revoke?token={refresh_token}`
2. Deletes row from `google_oauth_tokens` table
3. Returns success even if Google revoke fails (best-effort, idempotent)

**Impact on Existing Datasources:**
- All user's Google Docs datasources will fail to reindex after disconnect
- Datasources show `AuthorizationRequired` error
- User must re-authorize to resume indexing
- Datasources are NOT automatically deleted (data remains accessible)

## Token Management

### Token Refresh Strategy

**When tokens are accessed:**

```python
def get_valid_token(user_id: str) -> str:
    token = repository.get_by_user_id(user_id)
    
    if token.expires_at <= int(time.time()):
        token = refresh_token(token)
    
    return decrypt(token.access_token)
```

**Refresh Process:**
1. Check if `expires_at <= current_time`
2. If expired, call Google token endpoint with `refresh_token`
3. Update `access_token` and `expires_at` in database
4. Return fresh `access_token`

**Token Lifetimes:**
- Access token: ~1 hour (Google's default)
- Refresh token: Long-lived (months/years, as long as used)

**No proactive refresh:** Tokens refreshed on-demand when accessed. This is simpler and handles infrequent reindexing gracefully.

### Encryption

**Encrypted Fields:**
- `access_token`
- `refresh_token`

**Implementation:**
```python
from codemie.service.encryption.encryption_factory import EncryptionFactory

enc_service = EncryptionFactory().get_current_encryption_service()
encrypted_token = enc_service.encrypt(plaintext_token)
plaintext_token = enc_service.decrypt(encrypted_token)
```

Same encryption mechanism as SharePoint OAuth tokens.

## Integration with Google Docs Datasource

### Changes to `GoogleDocDatasourceProcessor`

**Before (Service Account):**
```python
def _init_loader(self):
    return GoogleDocLoader(product_id=self.product_id)
```

**After (OAuth):**
```python
def _init_loader(self):
    token_service = GoogleOAuthTokenService()
    try:
        access_token = token_service.get_valid_token(self.user.id)
    except AuthorizationRequired:
        raise InvalidQueryException(
            "Google Docs authorization required. Please authorize at /v1/google-docs/oauth/initiate"
        )
    except AuthorizationExpired:
        raise InvalidQueryException(
            "Google authorization expired. Please reconnect your Google account."
        )
    
    return GoogleDocLoader(
        product_id=self.product_id,
        access_token=access_token
    )
```

### Changes to `GoogleDocLoader`

**Add OAuth credentials support:**

```python
class GoogleDocLoader(BaseLoader):
    def __init__(self, *, product_id: str, access_token: str):
        self.product_id = product_id
        self.access_token = access_token
        self.service = self._build_service()
    
    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(token=self.access_token)
        return build('docs', 'v1', credentials=credentials)
```

### Datasource Creation Endpoint

**Add authorization check:**

```python
@router.post("/index/knowledge_base/google_doc")
def index_google_doc(request, raw_request, background_tasks):
    user = raw_request.state.user
    
    # Check if user has authorized Google Docs
    token_service = GoogleOAuthTokenService()
    if not token_service.has_authorization(user.id):
        raise ExtendedHTTPException(
            401,
            message="Google Docs authorization required",
            details="Please authorize access at /v1/google-docs/oauth/initiate"
        )
    
    # Continue with datasource creation...
```

### Scheduled Reindexing

**Key Benefit:** Backend-managed tokens enable automatic reindexing

- Cron jobs trigger reindexing without frontend
- Token service automatically refreshes expired tokens
- If refresh fails (token revoked) → datasource shows error, notify user

## Error Handling

### Exception Hierarchy

```python
class GoogleOAuthError(ExtendedHTTPException):
    """Base exception for Google OAuth errors"""

# Authorization State Errors
class AuthorizationRequired(GoogleOAuthError):
    """User hasn't authorized or needs to re-authorize"""
    # 401: "Google Docs authorization required"

class AuthorizationExpired(GoogleOAuthError):
    """Refresh token revoked/expired by Google"""
    # 401: "Google authorization expired. Please reconnect."

# OAuth Flow Errors  
class InvalidStateError(GoogleOAuthError):
    """State parameter invalid (CSRF protection)"""
    # 400: "Invalid or expired authorization request"

class CallbackError(GoogleOAuthError):
    """Error during OAuth callback from Google"""
    # 400: User-friendly message based on Google's error code

# Token Operation Errors
class TokenRefreshFailed(GoogleOAuthError):
    """Failed to refresh access token (transient)"""
    # 502: "Failed to refresh authorization. Try again."

class TokenExchangeFailed(GoogleOAuthError):
    """Failed to exchange authorization code for tokens"""
    # 502: "Failed to complete authorization"
```

### Error Scenarios by Context

**OAuth Initiation (`/initiate`):**
- Config missing → 503: "Google OAuth not configured"

**OAuth Callback (`/callback`):**
- Invalid state → `InvalidStateError` → HTML page
- User denied → `CallbackError` with "Authorization declined" → HTML page
- Code exchange fails → `TokenExchangeFailed` → HTML page
- State expired → 400 HTML: "Authorization request expired"

**Status Check (`/status/{state}`):**
- State not found → 404: "Authorization status not found"
- Wrong user → 403: "Forbidden"
- Pending → 202: `{"status": "pending"}`

**Token Retrieval (Datasource Indexing):**
- No tokens in DB → `AuthorizationRequired`
- Token expired, refresh succeeds → transparent (no error)
- Refresh fails with `invalid_grant` → `AuthorizationExpired`
- Refresh fails with network error → `TokenRefreshFailed`

**Disconnect (`/disconnect`):**
- Always succeeds (idempotent)
- Token not found → Success anyway
- Google revoke fails → Log warning, delete locally, return success

### User-Facing Error Messages

```python
GOOGLE_ERROR_MESSAGES = {
    "access_denied": "Authorization was declined",
    "invalid_grant": "Your authorization has expired",
    "invalid_client": "Application is misconfigured. Contact administrator.",
    "invalid_scope": "Invalid permissions requested",
}
```

### Logging Strategy

**What Gets Logged:**
- OAuth events: initiate, callback success/fail, refresh, disconnect
- Include: user_id, timestamp, error type
- Google API errors: status code, error code, sanitized message

**What Never Gets Logged:**
- Access tokens
- Refresh tokens
- Authorization codes
- Client secrets

## Security

### CSRF Protection

- **State parameter:** Cryptographically random 32-byte token
- **Storage:** Redis with `{user_id, timestamp}`
- **Validation:** State must exist in Redis and not expired
- **One-time use:** Deleted after callback (using `getdel`)

### Token Security

- **Encryption at rest:** Using `EncryptionFactory.get_current_encryption_service()`
- **No logging:** Tokens never logged or exposed in responses
- **HTTPS only:** All OAuth communication over HTTPS
- **Minimal scope:** Request only `documents.readonly`

### Redirect URI Validation

- **Exact match:** Must match Google Cloud Console registration
- **Format:** `{CALLBACK_API_BASE_URL}/v1/google-docs/oauth/callback`
- **No open redirects:** Google validates this

### Authentication & Authorization

- **All endpoints require auth** (except `/callback` - redirect target)
- **User isolation:** `/status/{state}` validates state belongs to authenticated user
- **Per-user tokens:** Users can only disconnect their own tokens

### Rate Limiting

- **`/initiate`:** 10 requests/minute per user (prevent abuse)
- **`/callback`:** No rate limiting (called by Google)

### Secrets Management

- **`GOOGLE_OAUTH_CLIENT_SECRET`:** Stored in environment/secrets manager
- **Never committed:** Not in code or logs
- **Rotation:** Periodic rotation following Google's recommendations

## Configuration

### Environment Variables

```python
GOOGLE_OAUTH_CLIENT_ID: str  # From Google Cloud Console
GOOGLE_OAUTH_CLIENT_SECRET: str  # From Google Cloud Console
CALLBACK_API_BASE_URL: str  # Base URL for callback (e.g., https://api.codemie.com)
```

### Constants

```python
GOOGLE_DOCS_SCOPE = "https://www.googleapis.com/auth/documents.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

OAUTH_STATE_TTL = 600  # 10 minutes
OAUTH_RESULT_TTL = 300  # 5 minutes
```

## Testing Strategy

### Unit Tests

**GoogleOAuthService:**
- `test_initiate_creates_state_in_redis()`
- `test_initiate_returns_valid_auth_url()`
- `test_callback_validates_state()`
- `test_callback_exchanges_code_for_tokens()`
- `test_callback_stores_encrypted_tokens()`
- `test_callback_handles_user_denial()`
- `test_callback_handles_invalid_state()`
- `test_status_returns_pending_when_not_ready()`
- `test_status_returns_success_with_email()`
- `test_status_deletes_result_after_reading()`
- `test_disconnect_revokes_and_deletes_tokens()`

**GoogleOAuthTokenService:**
- `test_get_valid_token_returns_unexpired_token()`
- `test_get_valid_token_refreshes_expired_token()`
- `test_get_valid_token_raises_when_no_authorization()`
- `test_refresh_token_updates_database()`
- `test_refresh_token_handles_revoked_refresh_token()`
- `test_refresh_token_retries_on_network_error()`
- `test_has_authorization_returns_true_when_exists()`
- `test_tokens_are_encrypted_in_database()`

**GoogleDocDatasourceProcessor:**
- `test_processor_fetches_token_from_service()`
- `test_processor_raises_when_no_authorization()`
- `test_processor_raises_when_authorization_expired()`
- `test_loader_uses_oauth_credentials()`

### Integration Tests

- `test_full_oauth_flow_end_to_end()` - Mock Google OAuth
- `test_datasource_indexing_with_oauth()`
- `test_token_refresh_during_indexing()`
- `test_reindexing_uses_refreshed_token()`

### API Tests

- `test_initiate_requires_authentication()`
- `test_initiate_returns_auth_url_and_state()`
- `test_callback_accepts_authorization_code()`
- `test_callback_returns_html_page()`
- `test_status_requires_authentication()`
- `test_status_validates_user_owns_state()`
- `test_disconnect_requires_authentication()`
- `test_disconnect_is_idempotent()`

### Mock Strategy

- Mock `httpx` calls to Google OAuth endpoints
- Mock Redis client for state storage
- Mock encryption service where appropriate
- Use test database for token storage

## Implementation Tasks

1. **Database Layer**
   - Create `GoogleOAuthToken` model
   - Create Alembic migration
   - Create repository class

2. **Service Layer**
   - Implement `GoogleOAuthService` (initiate, callback, status, disconnect)
   - Implement `GoogleOAuthTokenService` (get, refresh, has_authorization)

3. **API Layer**
   - Create OAuth router (`/v1/google-docs/oauth/`)
   - Implement endpoints (initiate, callback, status, disconnect)

4. **Integration**
   - Modify `GoogleDocLoader` to accept OAuth credentials
   - Modify `GoogleDocDatasourceProcessor` to fetch tokens
   - Add authorization check to datasource creation endpoint

5. **Configuration**
   - Add environment variables
   - Document Google Cloud Console setup

6. **Testing**
   - Write unit tests
   - Write integration tests
   - Write API tests

7. **Documentation**
   - Update API documentation
   - Update user guide for authorization flow

## Open Questions

None at this time.

## Future Enhancements

- Support additional Google Workspace scopes (Drive, Sheets, etc.)
- Admin dashboard to view OAuth connection status across users
- Automatic token revocation on user deletion
- Metrics/monitoring for OAuth flow success rates
