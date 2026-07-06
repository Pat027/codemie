# Google Docs OAuth 2.0 Implementation Plan (CORRECTED)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement per-user OAuth 2.0 authorization for Google Docs datasource with backend token management

**Architecture:** Layered - API router → OAuth service + Token service → Repository → PostgreSQL. Token refresh on-demand, encrypted at rest. Integration with GoogleDocLoader and GoogleDocDatasourceProcessor. User identity from JWT via `authenticate` dependency.

**Tech Stack:** FastAPI, SQLModel, google-auth-oauthlib, Redis (temp state), PostgreSQL (token storage), EncryptionFactory

**Corrections Applied:**
- All imports use `codemie.*` namespace (not `src.codemie.*`)
- `GoogleOAuthToken` extends `BaseModelWithSQLSupport`
- Exceptions extend `ExtendedHTTPException`
- `EncryptionFactory.get_current_encryption_service()` classmethod pattern
- `authenticate` dependency on protected endpoints
- `Depends(get_session)` for session management
- Token revocation on disconnect
- Missing datetime import fixed

---

## File Structure

**New Files:**
- `codemie/rest_api/models/google_oauth.py` - SQLModel and request/response models
- `codemie/repository/google_oauth_token_repository.py` - Token CRUD operations
- `codemie/service/google_oauth_service.py` - OAuth flow orchestration
- `codemie/service/google_oauth_token_service.py` - Token management and refresh
- `codemie/rest_api/routers/google_docs_oauth.py` - OAuth API endpoints
- `alembic/versions/<timestamp>_add_google_oauth_tokens.py` - Database migration

**Modified Files:**
- `codemie/core/exceptions.py` - Add GoogleOAuth* exceptions
- `codemie/datasource/google_doc/google_doc_datasource_processor.py` - Use OAuth tokens
- `codemie/datasource/loader/google_doc_loader.py` - Accept OAuth token
- `codemie/configs/config.py` - Add OAuth config vars
- `codemie/parsers/assistant_kb_google_doc_to_json_parser.py` - Add OAuth credentials support

**Test Files:**
- `tests/unit/service/test_google_oauth_service.py`
- `tests/unit/service/test_google_oauth_token_service.py`
- `tests/unit/repository/test_google_oauth_token_repository.py`
- `tests/integration/api/test_google_docs_oauth.py`

---

### Task 1: Database Model and Migration

**Files:**
- Create: `codemie/rest_api/models/google_oauth.py`
- Create: `alembic/versions/<timestamp>_add_google_oauth_tokens.py`
- Test: `tests/unit/repository/test_google_oauth_token_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/repository/test_google_oauth_token_repository.py
import pytest
from datetime import datetime
from codemie.rest_api.models.google_oauth import GoogleOAuthToken
from codemie.repository.google_oauth_token_repository import GoogleOAuthTokenRepository

def test_create_token_record(db_session):
    repo = GoogleOAuthTokenRepository(db_session)
    token = GoogleOAuthToken(
        user_id="user-123",
        access_token="encrypted-access",
        refresh_token="encrypted-refresh",
        expires_at=1234567890,
        scopes="https://www.googleapis.com/auth/documents.readonly",
        email="user@example.com"
    )
    created = repo.create(token)
    assert created.user_id == "user-123"
    assert created.email == "user@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/repository/test_google_oauth_token_repository.py::test_create_token_record -v`
Expected: FAIL with "No module named 'codemie.rest_api.models.google_oauth'"

- [ ] **Step 3: Write SQLModel definition**

```python
# codemie/rest_api/models/google_oauth.py
from datetime import datetime
from sqlmodel import Field
from codemie.rest_api.models.base import BaseModelWithSQLSupport

class GoogleOAuthToken(BaseModelWithSQLSupport, table=True):
    __tablename__ = "google_oauth_tokens"
    
    user_id: str = Field(primary_key=True, index=True, max_length=255)
    access_token: str = Field(max_length=2048)
    refresh_token: str = Field(max_length=512)
    expires_at: int
    scopes: str = Field(max_length=512)
    email: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Run test to verify SQLModel loads**

Run: `pytest tests/unit/repository/test_google_oauth_token_repository.py::test_create_token_record -v`
Expected: FAIL with "No module named 'codemie.repository.google_oauth_token_repository'"

- [ ] **Step 5: Create Alembic migration**

Run: `cd codemie && alembic revision -m "add_google_oauth_tokens"`

Edit the generated migration file:

```python
# alembic/versions/<timestamp>_add_google_oauth_tokens.py
"""add_google_oauth_tokens

Revision ID: <generated>
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.create_table(
        'google_oauth_tokens',
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('access_token', sa.String(length=2048), nullable=False),
        sa.Column('refresh_token', sa.String(length=512), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False),
        sa.Column('scopes', sa.String(length=512), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_google_oauth_tokens_user_id'), 'google_oauth_tokens', ['user_id'])

def downgrade() -> None:
    op.drop_index(op.f('ix_google_oauth_tokens_user_id'), table_name='google_oauth_tokens')
    op.drop_table('google_oauth_tokens')
```

- [ ] **Step 6: Commit**

```bash
git add codemie/rest_api/models/google_oauth.py alembic/versions/*_add_google_oauth_tokens.py tests/unit/repository/test_google_oauth_token_repository.py
git commit -m "feat(oauth): add GoogleOAuthToken model and migration"
```

---

### Task 2: Token Repository

**Files:**
- Create: `codemie/repository/google_oauth_token_repository.py`
- Test: `tests/unit/repository/test_google_oauth_token_repository.py` (extend)

- [ ] **Step 1: Extend failing test for repository CRUD**

```python
# tests/unit/repository/test_google_oauth_token_repository.py (add to existing)
def test_get_by_user_id(db_session):
    repo = GoogleOAuthTokenRepository(db_session)
    token = GoogleOAuthToken(
        user_id="user-456",
        access_token="enc-access",
        refresh_token="enc-refresh",
        expires_at=1234567890,
        scopes="https://www.googleapis.com/auth/documents.readonly",
        email="test@example.com"
    )
    repo.create(token)
    
    retrieved = repo.get_by_user_id("user-456")
    assert retrieved.user_id == "user-456"
    assert retrieved.email == "test@example.com"

def test_get_by_user_id_not_found(db_session):
    repo = GoogleOAuthTokenRepository(db_session)
    result = repo.get_by_user_id("nonexistent")
    assert result is None

def test_update_token(db_session):
    repo = GoogleOAuthTokenRepository(db_session)
    token = GoogleOAuthToken(
        user_id="user-789",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=1111111111,
        scopes="scope1",
        email="old@example.com"
    )
    repo.create(token)
    
    token.access_token = "new-access"
    token.expires_at = 2222222222
    updated = repo.update(token)
    assert updated.access_token == "new-access"
    assert updated.expires_at == 2222222222

def test_delete_token(db_session):
    repo = GoogleOAuthTokenRepository(db_session)
    token = GoogleOAuthToken(
        user_id="user-delete",
        access_token="access",
        refresh_token="refresh",
        expires_at=1234567890,
        scopes="scope",
        email="delete@example.com"
    )
    repo.create(token)
    
    repo.delete("user-delete")
    assert repo.get_by_user_id("user-delete") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/repository/test_google_oauth_token_repository.py -v`
Expected: FAIL with "GoogleOAuthTokenRepository not defined"

- [ ] **Step 3: Implement repository**

```python
# codemie/repository/google_oauth_token_repository.py
from typing import Optional
from sqlmodel import Session, select
from codemie.rest_api.models.google_oauth import GoogleOAuthToken

class GoogleOAuthTokenRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, token: GoogleOAuthToken) -> GoogleOAuthToken:
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token
    
    def get_by_user_id(self, user_id: str) -> Optional[GoogleOAuthToken]:
        statement = select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
        return self.session.exec(statement).first()
    
    def update(self, token: GoogleOAuthToken) -> GoogleOAuthToken:
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token
    
    def delete(self, user_id: str) -> None:
        token = self.get_by_user_id(user_id)
        if token:
            self.session.delete(token)
            self.session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/repository/test_google_oauth_token_repository.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/repository/google_oauth_token_repository.py tests/unit/repository/test_google_oauth_token_repository.py
git commit -m "feat(oauth): add GoogleOAuthTokenRepository with CRUD"
```

---

### Task 3: OAuth Exceptions

**Files:**
- Modify: `codemie/core/exceptions.py`
- Test: `tests/unit/exceptions/test_google_oauth_exceptions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/exceptions/test_google_oauth_exceptions.py
import pytest
from codemie.core.exceptions import (
    GoogleOAuthStateError,
    GoogleOAuthTokenError,
    GoogleOAuthRefreshError
)

def test_state_error():
    error = GoogleOAuthStateError("Invalid state")
    assert str(error) == "Invalid state"
    assert error.code == 400

def test_token_error():
    error = GoogleOAuthTokenError("Token expired")
    assert str(error) == "Token expired"
    assert error.code == 401

def test_refresh_error():
    error = GoogleOAuthRefreshError("Refresh failed")
    assert str(error) == "Refresh failed"
    assert error.code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/exceptions/test_google_oauth_exceptions.py -v`
Expected: FAIL with "cannot import name 'GoogleOAuthStateError'"

- [ ] **Step 3: Add exception classes to codemie/core/exceptions.py**

```python
# codemie/core/exceptions.py (add to existing file)

class GoogleOAuthStateError(ExtendedHTTPException):
    """CSRF state validation failed"""
    def __init__(self, message: str = "Invalid OAuth state parameter"):
        super().__init__(code=400, message=message)

class GoogleOAuthTokenError(ExtendedHTTPException):
    """Token retrieval or validation failed"""
    def __init__(self, message: str = "OAuth token error"):
        super().__init__(code=401, message=message)

class GoogleOAuthRefreshError(ExtendedHTTPException):
    """Token refresh failed"""
    def __init__(self, message: str = "Failed to refresh OAuth token"):
        super().__init__(code=401, message=message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/exceptions/test_google_oauth_exceptions.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/core/exceptions.py tests/unit/exceptions/test_google_oauth_exceptions.py
git commit -m "feat(oauth): add Google OAuth exception classes"
```

---

### Task 4: Configuration

**Files:**
- Modify: `codemie/configs/config.py`
- Test: `tests/unit/test_config.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_config.py (add to existing file)
def test_google_oauth_config_present():
    from codemie.configs.config import config
    assert hasattr(config, 'GOOGLE_OAUTH_CLIENT_ID')
    assert hasattr(config, 'GOOGLE_OAUTH_CLIENT_SECRET')
    assert hasattr(config, 'GOOGLE_OAUTH_REDIRECT_URI')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py::test_google_oauth_config_present -v`
Expected: FAIL with "Config object has no attribute 'GOOGLE_OAUTH_CLIENT_ID'"

- [ ] **Step 3: Add OAuth config fields**

```python
# codemie/configs/config.py (add to Config class)
class Config:
    # ... existing fields ...
    
    # Google OAuth 2.0
    GOOGLE_OAUTH_CLIENT_ID: str = Field(default="")
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(default="")
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(default="http://localhost:8000/v1/google-docs/oauth/callback")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py::test_google_oauth_config_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add codemie/configs/config.py tests/unit/test_config.py
git commit -m "feat(oauth): add Google OAuth config fields"
```

---

### Task 5: Token Service with Encryption

**Files:**
- Create: `codemie/service/google_oauth_token_service.py`
- Test: `tests/unit/service/test_google_oauth_token_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/service/test_google_oauth_token_service.py
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from codemie.service.google_oauth_token_service import GoogleOAuthTokenService
from codemie.rest_api.models.google_oauth import GoogleOAuthToken
from codemie.core.exceptions import GoogleOAuthTokenError

def test_store_token_encrypts_fields(mock_repo, mock_encryption_service):
    service = GoogleOAuthTokenService(mock_repo, mock_encryption_service)
    
    service.store_token(
        user_id="user-123",
        access_token="plain-access",
        refresh_token="plain-refresh",
        expires_in=3600,
        scopes="scope1 scope2",
        email="user@example.com"
    )
    
    mock_encryption_service.encrypt.assert_any_call("plain-access")
    mock_encryption_service.encrypt.assert_any_call("plain-refresh")
    assert mock_repo.create.called or mock_repo.update.called

def test_get_valid_token_not_expired(mock_repo, mock_encryption_service):
    service = GoogleOAuthTokenService(mock_repo, mock_encryption_service)
    future_expiry = int(time.time()) + 1800
    
    mock_repo.get_by_user_id.return_value = GoogleOAuthToken(
        user_id="user-123",
        access_token="encrypted-access",
        refresh_token="encrypted-refresh",
        expires_at=future_expiry,
        scopes="scope",
        email="user@example.com"
    )
    mock_encryption_service.decrypt.return_value = "decrypted-access"
    
    token = service.get_valid_token("user-123")
    assert token == "decrypted-access"
    mock_encryption_service.decrypt.assert_called_once_with("encrypted-access")

def test_get_valid_token_expired_refreshes(mock_repo, mock_encryption_service):
    service = GoogleOAuthTokenService(mock_repo, mock_encryption_service)
    past_expiry = int(time.time()) - 10
    
    mock_repo.get_by_user_id.return_value = GoogleOAuthToken(
        user_id="user-456",
        access_token="old-encrypted",
        refresh_token="encrypted-refresh",
        expires_at=past_expiry,
        scopes="scope",
        email="user@example.com"
    )
    
    with patch.object(service, '_refresh_token') as mock_refresh:
        mock_refresh.return_value = GoogleOAuthToken(
            user_id="user-456",
            access_token="new-encrypted",
            refresh_token="encrypted-refresh",
            expires_at=int(time.time()) + 3600,
            scopes="scope",
            email="user@example.com"
        )
        mock_encryption_service.decrypt.side_effect = ["decrypted-refresh", "new-decrypted"]
        
        token = service.get_valid_token("user-456")
        assert token == "new-decrypted"
        mock_refresh.assert_called_once()

def test_get_valid_token_not_found_raises(mock_repo, mock_encryption_service):
    service = GoogleOAuthTokenService(mock_repo, mock_encryption_service)
    mock_repo.get_by_user_id.return_value = None
    
    with pytest.raises(GoogleOAuthTokenError, match="No OAuth token found"):
        service.get_valid_token("nonexistent")

def test_delete_token(mock_repo, mock_encryption_service):
    service = GoogleOAuthTokenService(mock_repo, mock_encryption_service)
    service.delete_token("user-789")
    mock_repo.delete.assert_called_once_with("user-789")

@pytest.fixture
def mock_repo():
    return Mock()

@pytest.fixture
def mock_encryption_service():
    mock = Mock()
    mock.encrypt.side_effect = lambda x: f"encrypted-{x}"
    mock.decrypt.side_effect = lambda x: x.replace("encrypted-", "")
    return mock
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/service/test_google_oauth_token_service.py -v`
Expected: FAIL with "No module named 'codemie.service.google_oauth_token_service'"

- [ ] **Step 3: Implement token service**

```python
# codemie/service/google_oauth_token_service.py
import time
from datetime import datetime
from typing import Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from codemie.repository.google_oauth_token_repository import GoogleOAuthTokenRepository
from codemie.rest_api.models.google_oauth import GoogleOAuthToken
from codemie.core.exceptions import GoogleOAuthTokenError, GoogleOAuthRefreshError
from codemie.service.encryption.base_encryption_service import BaseEncryptionService
from codemie.configs import config

class GoogleOAuthTokenService:
    def __init__(self, repository: GoogleOAuthTokenRepository, encryption_service: BaseEncryptionService):
        self.repository = repository
        self.encryption = encryption_service
    
    def store_token(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        scopes: str,
        email: str
    ) -> GoogleOAuthToken:
        encrypted_access = self.encryption.encrypt(access_token)
        encrypted_refresh = self.encryption.encrypt(refresh_token)
        expires_at = int(time.time()) + expires_in
        
        existing = self.repository.get_by_user_id(user_id)
        if existing:
            existing.access_token = encrypted_access
            existing.refresh_token = encrypted_refresh
            existing.expires_at = expires_at
            existing.scopes = scopes
            existing.email = email
            existing.updated_at = datetime.utcnow()
            return self.repository.update(existing)
        else:
            token = GoogleOAuthToken(
                user_id=user_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                scopes=scopes,
                email=email
            )
            return self.repository.create(token)
    
    def get_valid_token(self, user_id: str) -> str:
        token = self.repository.get_by_user_id(user_id)
        if not token:
            raise GoogleOAuthTokenError(f"No OAuth token found for user {user_id}")
        
        if token.expires_at <= int(time.time()):
            token = self._refresh_token(token)
        
        return self.encryption.decrypt(token.access_token)
    
    def _refresh_token(self, token: GoogleOAuthToken) -> GoogleOAuthToken:
        decrypted_refresh = self.encryption.decrypt(token.refresh_token)
        credentials = Credentials(
            token=None,
            refresh_token=decrypted_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=config.GOOGLE_OAUTH_CLIENT_SECRET
        )
        
        try:
            credentials.refresh(Request())
        except Exception as e:
            raise GoogleOAuthRefreshError(f"Token refresh failed: {str(e)}")
        
        encrypted_access = self.encryption.encrypt(credentials.token)
        token.access_token = encrypted_access
        token.expires_at = int(credentials.expiry.timestamp())
        token.updated_at = datetime.utcnow()
        
        return self.repository.update(token)
    
    def delete_token(self, user_id: str) -> None:
        self.repository.delete(user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/service/test_google_oauth_token_service.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/service/google_oauth_token_service.py tests/unit/service/test_google_oauth_token_service.py
git commit -m "feat(oauth): add GoogleOAuthTokenService with encryption"
```

---

### Task 6: OAuth Flow Service

**Files:**
- Create: `codemie/service/google_oauth_service.py`
- Test: `tests/unit/service/test_google_oauth_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/service/test_google_oauth_service.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from codemie.service.google_oauth_service import GoogleOAuthService
from codemie.core.exceptions import GoogleOAuthStateError

def test_initiate_flow_returns_url_and_stores_state(mock_redis, mock_token_service):
    service = GoogleOAuthService(mock_redis, mock_token_service)
    
    with patch('codemie.service.google_oauth_service.Flow') as MockFlow:
        mock_flow = Mock()
        mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", "generated-state")
        MockFlow.from_client_config.return_value = mock_flow
        
        auth_url, state = service.initiate_flow(user_id="user-123")
        
        assert "https://accounts.google.com/o/oauth2/auth" in auth_url
        assert state == "generated-state"
        mock_redis.setex.assert_called_once()

def test_handle_callback_valid_state(mock_redis, mock_token_service):
    service = GoogleOAuthService(mock_redis, mock_token_service)
    mock_redis.get.return_value = "user-123"
    
    with patch('codemie.service.google_oauth_service.Flow') as MockFlow:
        mock_flow = Mock()
        mock_credentials = Mock()
        mock_credentials.token = "access-token"
        mock_credentials.refresh_token = "refresh-token"
        mock_credentials.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_credentials.scopes = ["scope1", "scope2"]
        mock_credentials.id_token = {"email": "user@example.com"}
        mock_flow.fetch_token.return_value = None
        mock_flow.credentials = mock_credentials
        MockFlow.from_client_config.return_value = mock_flow
        
        user_id = service.handle_callback(state="valid-state", code="auth-code")
        
        assert user_id == "user-123"
        mock_token_service.store_token.assert_called_once()
        mock_redis.delete.assert_called_once_with("oauth_state:valid-state")

def test_handle_callback_invalid_state_raises(mock_redis, mock_token_service):
    service = GoogleOAuthService(mock_redis, mock_token_service)
    mock_redis.get.return_value = None
    
    with pytest.raises(GoogleOAuthStateError, match="Invalid or expired"):
        service.handle_callback(state="invalid-state", code="auth-code")

@pytest.fixture
def mock_redis():
    return Mock()

@pytest.fixture
def mock_token_service():
    return Mock()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/service/test_google_oauth_service.py -v`
Expected: FAIL with "No module named 'codemie.service.google_oauth_service'"

- [ ] **Step 3: Implement OAuth service**

```python
# codemie/service/google_oauth_service.py
from datetime import datetime
from typing import Tuple
from google_auth_oauthlib.flow import Flow
from codemie.service.google_oauth_token_service import GoogleOAuthTokenService
from codemie.core.exceptions import GoogleOAuthStateError
from codemie.configs import config

STATE_TTL = 600  # 10 minutes

class GoogleOAuthService:
    def __init__(self, redis_client, token_service: GoogleOAuthTokenService):
        self.redis = redis_client
        self.token_service = token_service
        self.scopes = ["https://www.googleapis.com/auth/documents.readonly"]
    
    def initiate_flow(self, user_id: str) -> Tuple[str, str]:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [config.GOOGLE_OAUTH_REDIRECT_URI]
                }
            },
            scopes=self.scopes
        )
        flow.redirect_uri = config.GOOGLE_OAUTH_REDIRECT_URI
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        state_key = f"oauth_state:{state}"
        self.redis.setex(state_key, STATE_TTL, user_id)
        
        return auth_url, state
    
    def handle_callback(self, state: str, code: str) -> str:
        state_key = f"oauth_state:{state}"
        user_id = self.redis.get(state_key)
        
        if not user_id:
            raise GoogleOAuthStateError("Invalid or expired OAuth state")
        
        if isinstance(user_id, bytes):
            user_id = user_id.decode('utf-8')
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [config.GOOGLE_OAUTH_REDIRECT_URI]
                }
            },
            scopes=self.scopes,
            state=state
        )
        flow.redirect_uri = config.GOOGLE_OAUTH_REDIRECT_URI
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        expires_in = int((credentials.expiry - datetime.utcnow()).total_seconds())
        email = credentials.id_token.get("email", "") if credentials.id_token else ""
        
        self.token_service.store_token(
            user_id=user_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_in=expires_in,
            scopes=" ".join(credentials.scopes),
            email=email
        )
        
        self.redis.delete(state_key)
        
        return user_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/service/test_google_oauth_service.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/service/google_oauth_service.py tests/unit/service/test_google_oauth_service.py
git commit -m "feat(oauth): add GoogleOAuthService for OAuth flow"
```

---

### Task 7: API Router and Endpoints

**Files:**
- Create: `codemie/rest_api/routers/google_docs_oauth.py`
- Test: `tests/integration/api/test_google_docs_oauth.py`
- Modify: `codemie/rest_api/main.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/api/test_google_docs_oauth.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

def test_initiate_endpoint_authenticated(client, authenticated_user):
    with patch('codemie.rest_api.routers.google_docs_oauth.GoogleOAuthService') as MockService:
        mock_service = Mock()
        mock_service.initiate_flow.return_value = ("https://accounts.google.com/auth", "state-123")
        MockService.return_value = mock_service
        
        response = client.post(
            "/v1/google-docs/oauth/initiate",
            headers={"Authorization": f"Bearer {authenticated_user.token}"}
        )
        
        assert response.status_code == 200
        assert "authorization_url" in response.json()

def test_callback_endpoint_success(client):
    with patch('codemie.rest_api.routers.google_docs_oauth.GoogleOAuthService') as MockService:
        mock_service = Mock()
        mock_service.handle_callback.return_value = "user-123"
        MockService.return_value = mock_service
        
        response = client.get("/v1/google-docs/oauth/callback?state=valid-state&code=auth-code")
        
        assert response.status_code == 200
        assert "success" in response.text

def test_status_endpoint_authorized(client, authenticated_user, mock_token_repo):
    mock_token_repo.get_by_user_id.return_value = Mock(email="user@example.com", scopes="scope1")
    
    response = client.get(
        f"/v1/google-docs/oauth/status",
        headers={"Authorization": f"Bearer {authenticated_user.token}"}
    )
    
    assert response.status_code == 200
    assert response.json()["authorized"] is True

def test_disconnect_endpoint_with_revoke(client, authenticated_user):
    with patch('codemie.rest_api.routers.google_docs_oauth.revoke_google_token') as mock_revoke:
        mock_revoke.return_value = True
        
        response = client.delete(
            "/v1/google-docs/oauth/disconnect",
            headers={"Authorization": f"Bearer {authenticated_user.token}"}
        )
        
        assert response.status_code == 200
        mock_revoke.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/api/test_google_docs_oauth.py -v`
Expected: FAIL with "404 Not Found"

- [ ] **Step 3: Implement API router**

```python
# codemie/rest_api/routers/google_docs_oauth.py
import html
import httpx
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlmodel import Session
from codemie.service.google_oauth_service import GoogleOAuthService
from codemie.service.google_oauth_token_service import GoogleOAuthTokenService
from codemie.repository.google_oauth_token_repository import GoogleOAuthTokenRepository
from codemie.core.exceptions import GoogleOAuthStateError, GoogleOAuthTokenError
from codemie.rest_api.security.authentication import authenticate
from codemie.rest_api.security.user import User
from codemie.clients.postgres import get_session
from codemie.clients.redis import create_redis_client
from codemie.service.encryption.encryption_factory import EncryptionFactory
from codemie.configs import config, logger

router = APIRouter(prefix="/v1/google-docs/oauth", tags=["google-docs-oauth"])

def _html_page(success: bool, message: str) -> str:
    escaped = html.escape(message)
    if success:
        body = "<h2>Authentication Complete</h2>" f"<p>{escaped}</p>" "<p>You can close this window.</p>"
    else:
        body = "<h2>Authentication Failed</h2>" f"<p>{escaped}</p>" "<p>You can close this window and return to the application.</p>"
    return f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{body}</body></html>"

def get_oauth_service(session: Session = Depends(get_session)) -> GoogleOAuthService:
    redis = create_redis_client()
    repo = GoogleOAuthTokenRepository(session)
    encryption_service = EncryptionFactory.get_current_encryption_service()
    token_service = GoogleOAuthTokenService(repo, encryption_service)
    return GoogleOAuthService(redis, token_service)

def get_token_service(session: Session = Depends(get_session)) -> GoogleOAuthTokenService:
    repo = GoogleOAuthTokenRepository(session)
    encryption_service = EncryptionFactory.get_current_encryption_service()
    return GoogleOAuthTokenService(repo, encryption_service)

async def revoke_google_token(token: str) -> bool:
    """Revoke Google OAuth token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Failed to revoke Google token: {e}")
        return False

class InitiateResponse(BaseModel):
    authorization_url: str

class StatusResponse(BaseModel):
    authorized: bool
    email: str | None = None
    scopes: str | None = None

class DisconnectResponse(BaseModel):
    success: bool
    message: str

@router.post("/initiate", response_model=InitiateResponse)
async def initiate_oauth(
    user: User = Depends(authenticate),
    oauth_service: GoogleOAuthService = Depends(get_oauth_service)
):
    try:
        auth_url, state = oauth_service.initiate_flow(user.id)
        return InitiateResponse(authorization_url=auth_url)
    except Exception as e:
        logger.error(f"OAuth initiate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
async def oauth_callback(
    state: str = Query(...),
    code: str = Query(...),
    oauth_service: GoogleOAuthService = Depends(get_oauth_service)
):
    try:
        user_id = oauth_service.handle_callback(state, code)
        return HTMLResponse(content=_html_page(True, f"Authorization successful for user {user_id}"))
    except GoogleOAuthStateError as e:
        return HTMLResponse(content=_html_page(False, str(e)), code=400)
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return HTMLResponse(content=_html_page(False, "Authorization failed"), status_code=500)

@router.get("/status", response_model=StatusResponse)
async def check_oauth_status(
    user: User = Depends(authenticate),
    token_service: GoogleOAuthTokenService = Depends(get_token_service)
):
    token = token_service.repository.get_by_user_id(user.id)
    if token:
        return StatusResponse(authorized=True, email=token.email, scopes=token.scopes)
    return StatusResponse(authorized=False)

@router.delete("/disconnect", response_model=DisconnectResponse)
async def disconnect_oauth(
    user: User = Depends(authenticate),
    token_service: GoogleOAuthTokenService = Depends(get_token_service)
):
    try:
        # Get token before deletion for revocation
        token_record = token_service.repository.get_by_user_id(user.id)
        if token_record:
            access_token = token_service.encryption.decrypt(token_record.access_token)
            await revoke_google_token(access_token)
        
        token_service.delete_token(user.id)
        return DisconnectResponse(success=True, message=f"OAuth disconnected for user {user.id}")
    except Exception as e:
        logger.error(f"OAuth disconnect failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/api/test_google_docs_oauth.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Register router in main app**

```python
# codemie/rest_api/main.py (add to existing imports and router registration)
from codemie.rest_api.routers import google_docs_oauth

app.include_router(google_docs_oauth.router)
```

- [ ] **Step 6: Commit**

```bash
git add codemie/rest_api/routers/google_docs_oauth.py tests/integration/api/test_google_docs_oauth.py codemie/rest_api/main.py
git commit -m "feat(oauth): add Google Docs OAuth API endpoints with authentication"
```

---

### Task 8: Update GoogleDocLoader for OAuth

**Files:**
- Modify: `codemie/datasource/loader/google_doc_loader.py`
- Test: `tests/unit/datasource/loader/test_google_doc_loader.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/datasource/loader/test_google_doc_loader.py
import pytest
from unittest.mock import Mock, patch
from codemie.datasource.loader.google_doc_loader import GoogleDocLoader

def test_loader_with_oauth_token():
    with patch('codemie.datasource.loader.google_doc_loader.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        loader = GoogleDocLoader(document_ids=["doc1"], access_token="oauth-token")
        
        mock_build.assert_called_once()
        call_args = mock_build.call_args
        assert call_args[0] == ("docs", "v1")
        assert "credentials" in call_args[1]

def test_loader_without_token_uses_default():
    with patch('codemie.datasource.loader.google_doc_loader.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        loader = GoogleDocLoader(document_ids=["doc2"])
        
        mock_build.assert_called_once_with("docs", "v1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datasource/loader/test_google_doc_loader.py -v`
Expected: FAIL with "TypeError: GoogleDocLoader() got an unexpected keyword argument 'access_token'"

- [ ] **Step 3: Modify GoogleDocLoader to accept access_token**

```python
# codemie/datasource/loader/google_doc_loader.py
from typing import Optional, List
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GoogleDocLoader:
    def __init__(self, document_ids: List[str], access_token: Optional[str] = None):
        self.document_ids = document_ids
        
        if access_token:
            credentials = Credentials(token=access_token)
            self.service = build("docs", "v1", credentials=credentials)
        else:
            self.service = build("docs", "v1")
    
    def load(self):
        # ... existing load implementation ...
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/datasource/loader/test_google_doc_loader.py -v`
Expected: PASS (all 2 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/datasource/loader/google_doc_loader.py tests/unit/datasource/loader/test_google_doc_loader.py
git commit -m "feat(oauth): add OAuth token support to GoogleDocLoader"
```

---

### Task 9: Update GoogleDocDatasourceProcessor

**Files:**
- Modify: `codemie/datasource/google_doc/google_doc_datasource_processor.py`
- Test: `tests/unit/datasource/test_google_doc_datasource_processor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/datasource/test_google_doc_datasource_processor.py
import pytest
from unittest.mock import Mock, patch
from codemie.datasource.google_doc.google_doc_datasource_processor import GoogleDocDatasourceProcessor

def test_processor_fetches_oauth_token_for_user():
    with patch('codemie.datasource.google_doc.google_doc_datasource_processor.EncryptionFactory') as MockFactory:
        with patch('codemie.datasource.google_doc.google_doc_datasource_processor.GoogleOAuthTokenService') as MockTokenService:
            mock_encryption = Mock()
            MockFactory.get_current_encryption_service.return_value = mock_encryption
            
            mock_token_service = Mock()
            MockTokenService.return_value = mock_token_service
            mock_token_service.get_valid_token.return_value = "valid-access-token"
            
            processor = GoogleDocDatasourceProcessor(datasource_id="ds-123", user_id="user-456")
            
            with patch('codemie.datasource.google_doc.google_doc_datasource_processor.GoogleDocLoader') as MockLoader:
                processor.process()
                
                MockLoader.assert_called_once()
                call_kwargs = MockLoader.call_args[1]
                assert call_kwargs["access_token"] == "valid-access-token"

def test_check_google_doc_with_oauth():
    with patch('codemie.datasource.loader.google_doc_loader.GoogleDocLoader') as MockLoader:
        mock_loader = Mock()
        MockLoader.return_value = mock_loader
        mock_loader.load.return_value = [Mock(metadata={"title": "Test Doc"})]
        
        with patch('codemie.datasource.google_doc.google_doc_datasource_processor.EncryptionFactory') as MockFactory:
            with patch('codemie.datasource.google_doc.google_doc_datasource_processor.GoogleOAuthTokenService') as MockTokenService:
                mock_encryption = Mock()
                MockFactory.get_current_encryption_service.return_value = mock_encryption
                
                mock_token_service = Mock()
                MockTokenService.return_value = mock_token_service
                mock_token_service.get_valid_token.return_value = "oauth-token"
                
                result = GoogleDocDatasourceProcessor.check_google_doc(
                    document_id="doc-123",
                    user_id="user-789"
                )
                
                assert result is True
                mock_token_service.get_valid_token.assert_called_once_with("user-789")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datasource/test_google_doc_datasource_processor.py -v`
Expected: FAIL with "TypeError: process() missing required keyword argument 'access_token'"

- [ ] **Step 3: Modify processor to fetch and use OAuth tokens**

```python
# codemie/datasource/google_doc/google_doc_datasource_processor.py
from typing import Optional
from sqlmodel import Session
from codemie.datasource.loader.google_doc_loader import GoogleDocLoader
from codemie.service.google_oauth_token_service import GoogleOAuthTokenService
from codemie.repository.google_oauth_token_repository import GoogleOAuthTokenRepository
from codemie.service.encryption.encryption_factory import EncryptionFactory
from codemie.clients.postgres import get_session

class GoogleDocDatasourceProcessor:
    def __init__(self, datasource_id: str, user_id: str, session: Optional[Session] = None):
        self.datasource_id = datasource_id
        self.user_id = user_id
        self.session = session or next(get_session())
        self._token_service = None
    
    @property
    def token_service(self) -> GoogleOAuthTokenService:
        if not self._token_service:
            repo = GoogleOAuthTokenRepository(self.session)
            encryption_service = EncryptionFactory.get_current_encryption_service()
            self._token_service = GoogleOAuthTokenService(repo, encryption_service)
        return self._token_service
    
    def process(self):
        access_token = self.token_service.get_valid_token(self.user_id)
        
        loader = GoogleDocLoader(
            document_ids=self._get_document_ids(),
            access_token=access_token
        )
        
        documents = loader.load()
        # ... existing processing logic ...
    
    @classmethod
    def check_google_doc(cls, document_id: str, user_id: str) -> bool:
        try:
            session = next(get_session())
            repo = GoogleOAuthTokenRepository(session)
            encryption_service = EncryptionFactory.get_current_encryption_service()
            token_service = GoogleOAuthTokenService(repo, encryption_service)
            
            access_token = token_service.get_valid_token(user_id)
            
            loader = GoogleDocLoader(document_ids=[document_id], access_token=access_token)
            documents = loader.load()
            return len(documents) > 0
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/datasource/test_google_doc_datasource_processor.py -v`
Expected: PASS (all 2 tests)

- [ ] **Step 5: Commit**

```bash
git add codemie/datasource/google_doc/google_doc_datasource_processor.py tests/unit/datasource/test_google_doc_datasource_processor.py
git commit -m "feat(oauth): integrate OAuth token fetch in GoogleDocDatasourceProcessor"
```

---

### Task 10: Update AssistantKBGoogleDocToJsonParser

**Files:**
- Modify: `codemie/parsers/assistant_kb_google_doc_to_json_parser.py`
- Test: `tests/unit/parsers/test_assistant_kb_google_doc_to_json_parser.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/parsers/test_assistant_kb_google_doc_to_json_parser.py
import pytest
from unittest.mock import Mock, patch
from codemie.parsers.assistant_kb_google_doc_to_json_parser import AssistantKBGoogleDocToJsonParser

def test_parser_passes_oauth_credentials_to_build():
    with patch('codemie.parsers.assistant_kb_google_doc_to_json_parser.build') as mock_build:
        with patch('codemie.parsers.assistant_kb_google_doc_to_json_parser.EncryptionFactory') as MockFactory:
            with patch('codemie.parsers.assistant_kb_google_doc_to_json_parser.GoogleOAuthTokenService') as MockTokenService:
                mock_encryption = Mock()
                MockFactory.get_current_encryption_service.return_value = mock_encryption
                
                mock_token_service = Mock()
                MockTokenService.return_value = mock_token_service
                mock_token_service.get_valid_token.return_value = "oauth-access"
                
                parser = AssistantKBGoogleDocToJsonParser(user_id="user-123")
                parser.parse_doc(document_id="doc-456")
                
                mock_build.assert_called_once()
                call_kwargs = mock_build.call_args[1]
                assert "credentials" in call_kwargs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/parsers/test_assistant_kb_google_doc_to_json_parser.py -v`
Expected: FAIL with "AssertionError: expected 'credentials' in call_args"

- [ ] **Step 3: Modify parser to use OAuth credentials**

```python
# codemie/parsers/assistant_kb_google_doc_to_json_parser.py
from typing import Optional
from sqlmodel import Session
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from codemie.service.google_oauth_token_service import GoogleOAuthTokenService
from codemie.repository.google_oauth_token_repository import GoogleOAuthTokenRepository
from codemie.service.encryption.encryption_factory import EncryptionFactory
from codemie.clients.postgres import get_session

class AssistantKBGoogleDocToJsonParser:
    def __init__(self, user_id: str, session: Optional[Session] = None):
        self.user_id = user_id
        self.session = session or next(get_session())
        self._token_service = None
    
    @property
    def token_service(self) -> GoogleOAuthTokenService:
        if not self._token_service:
            repo = GoogleOAuthTokenRepository(self.session)
            encryption_service = EncryptionFactory.get_current_encryption_service()
            self._token_service = GoogleOAuthTokenService(repo, encryption_service)
        return self._token_service
    
    def parse_doc(self, document_id: str):
        access_token = self.token_service.get_valid_token(self.user_id)
        credentials = Credentials(token=access_token)
        
        service = build("docs", "v1", credentials=credentials)
        # ... existing parsing logic ...
    
    def check_document_accessible(self, document_id: str) -> bool:
        try:
            access_token = self.token_service.get_valid_token(self.user_id)
            credentials = Credentials(token=access_token)
            service = build("docs", "v1", credentials=credentials)
            # ... existing check logic ...
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/parsers/test_assistant_kb_google_doc_to_json_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add codemie/parsers/assistant_kb_google_doc_to_json_parser.py tests/unit/parsers/test_assistant_kb_google_doc_to_json_parser.py
git commit -m "feat(oauth): add OAuth credential support to AssistantKBGoogleDocToJsonParser"
```

---

### Task 11: Environment Variables Documentation

**Files:**
- Create: `docs/google-docs-oauth-setup.md`

- [ ] **Step 1: Write setup documentation**

```markdown
# docs/google-docs-oauth-setup.md
# Google Docs OAuth 2.0 Setup

## Required Environment Variables

Add the following to your `.env` file:

```bash
GOOGLE_OAUTH_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=<your-client-secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/v1/google-docs/oauth/callback
```

## Obtaining OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Navigate to **APIs & Services** > **Credentials**
4. Click **Create Credentials** > **OAuth 2.0 Client ID**
5. Select **Web application** as application type
6. Add authorized redirect URIs:
   - Development: `http://localhost:8000/v1/google-docs/oauth/callback`
   - Production: `https://your-domain.com/v1/google-docs/oauth/callback`
7. Copy the **Client ID** and **Client Secret**

## Required Scopes

- `https://www.googleapis.com/auth/documents.readonly`

## Database Migration

Run the migration to create the `google_oauth_tokens` table:

```bash
cd codemie
alembic upgrade head
```

## Testing OAuth Flow

1. Start the backend server
2. POST to `/v1/google-docs/oauth/initiate` with JWT auth header
3. Open the returned `authorization_url` in a browser
4. Authorize the app
5. Verify the callback stores tokens in the database

## Token Storage

Tokens are encrypted at rest using `EncryptionFactory.get_current_encryption_service()`. Access tokens are automatically refreshed when expired.

## Security Notes

- All endpoints except `/callback` require JWT authentication via `authenticate` dependency
- User ID comes from authenticated JWT, not request body
- Tokens are revoked at Google on disconnect
- CSRF protection via state parameter with 10-minute TTL in Redis
```

- [ ] **Step 2: Commit**

```bash
git add docs/google-docs-oauth-setup.md
git commit -m "docs(oauth): add Google Docs OAuth setup guide"
```

---

### Task 12: Run Database Migration

**Files:**
- Run: `alembic upgrade head`

- [ ] **Step 1: Apply migration to local database**

Run: `cd codemie && alembic upgrade head`
Expected: Migration applied successfully, `google_oauth_tokens` table created

- [ ] **Step 2: Verify table exists**

Run: `psql -d codemie -c "\dt google_oauth_tokens"`
Expected: Table `google_oauth_tokens` is listed

- [ ] **Step 3: Commit marker (no files changed)**

```bash
git commit --allow-empty -m "chore(oauth): database migration applied locally"
```

---

## Execution Handoff

Plan complete and saved. All reviewer feedback addressed:

✅ Import paths corrected (`codemie.*` not `src.codemie.*`)
✅ Exceptions extend `ExtendedHTTPException`
✅ `GoogleOAuthToken` extends `BaseModelWithSQLSupport`
✅ `EncryptionFactory.get_current_encryption_service()` classmethod used
✅ `authenticate` dependency on protected endpoints
✅ `Depends(get_session)` for session management
✅ Token revocation on disconnect
✅ Missing `datetime` import fixed

**Execution options:**

1. **Subagent-Driven** (recommended) - Fresh subagent per task, review between tasks
2. **Inline Execution** - Execute in this session via executing-plans

Which approach?
