# EPMCDME-13491 Local Auth Bearer JWT Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Authorization: Bearer <local JWT>` authenticate correctly in ENV=local persistent user-management mode by removing the Authorization-header fallback from the dev-header shortcut.

**Architecture:** Single guarded block change in `PersistentUserProvider.authenticate_and_load_user`: the ENV=local dev shortcut honors only the dedicated `user-id` header; Bearer/any Authorization values fall through to the normal auth branches (`validate_local_jwt` for IDP_PROVIDER=local, IDP otherwise). Spec: `docs/superpowers/runs/20260714-2233-EPMCDME-13491/design.md`.

**Tech Stack:** Python 3.12, FastAPI, pytest + unittest.mock (existing patterns in the target test file), Poetry.

## Global Constraints

- Commit messages: `EPMCDME-13491: <Description>` (git-workflow guide).
- All Python files keep the Apache 2.0 license header.
- Lint gate: `make ruff` must pass (removing the now-unused `AUTHORIZATION_HEADER` import is required).
- Production behavior (`ENV != "local"`) must be untouched — only the `config.ENV == "local"` block changes.

---

### Task 1: Remove Authorization fallback from dev shortcut (test-first)

**Test-first: yes — new regression tests fail against the current fallback: (1) Bearer JWT in ENV=local is consumed as dev user-id instead of reaching validate_local_jwt; (2) bare user-id in Authorization still triggers dev auth. Both must fail before the fix and pass after.**

**Files:**
- Modify: `src/codemie/rest_api/security/user_providers/persistent.py:25,101-107`
- Test: `tests/codemie/rest_api/security/test_persistent_user_provider.py` (append to `TestPersistentUserProvider`)

**Interfaces:**
- Consumes: existing fixtures `provider`, `mock_request`; patch targets `codemie.rest_api.security.user_providers.persistent.config`, `...persistent.authentication_service`, `codemie.rest_api.security.jwt_local.validate_local_jwt`.
- Produces: no new public interfaces; `authenticate_and_load_user` signature unchanged.

- [ ] **Step 1: Write the failing tests**

Append inside `class TestPersistentUserProvider` in `tests/codemie/rest_api/security/test_persistent_user_provider.py`:

```python
    @pytest.mark.asyncio
    @patch("codemie.rest_api.security.user_providers.persistent.authentication_service")
    @patch("codemie.rest_api.security.jwt_local.validate_local_jwt")
    @patch("codemie.rest_api.security.user_providers.persistent.config")
    async def test_bearer_jwt_in_local_env_uses_local_jwt_validation(
        self, mock_config, mock_validate_jwt, mock_auth_service, provider, mock_request
    ):
        """EPMCDME-13491: Bearer JWT in ENV=local must reach validate_local_jwt,
        not be consumed by the dev-header shortcut as a dev user-id."""
        # Arrange
        mock_config.ENV = "local"
        mock_config.IDP_PROVIDER = "local"
        mock_config.AUTH_COOKIE_NAME = "auth_token"

        jwt_token = "local.jwt.token"
        user_id = "uuid-user-13491"

        mock_request.headers.get.side_effect = lambda key: (
            f"Bearer {jwt_token}" if key == "Authorization" else None
        )
        mock_request.cookies.get.return_value = None

        mock_validate_jwt.return_value = {"sub": user_id, "iss": "codemie-local"}

        expected_user = User(
            id=user_id,
            email="local@example.com",
            name="Local JWT User",
            auth_token=jwt_token,
            is_admin=False,
            project_names=[],
            knowledge_bases=[],
        )
        mock_auth_service.authenticate_dev_header = AsyncMock()
        mock_auth_service.authenticate_persistent_user = AsyncMock(return_value=expected_user)

        mock_idp = MagicMock()

        # Act
        result = await provider.authenticate_and_load_user(mock_request, mock_idp)

        # Assert
        assert result == expected_user
        mock_auth_service.authenticate_dev_header.assert_not_called()
        mock_validate_jwt.assert_called_once_with(jwt_token)
        mock_auth_service.authenticate_persistent_user.assert_called_once_with(
            user_id=user_id, idp_user=None, auth_token=jwt_token
        )

    @pytest.mark.asyncio
    @patch("codemie.rest_api.security.user_providers.persistent.authentication_service")
    @patch("codemie.rest_api.security.jwt_local.validate_local_jwt")
    @patch("codemie.rest_api.security.user_providers.persistent.config")
    async def test_bare_authorization_value_no_longer_triggers_dev_auth(
        self, mock_config, mock_validate_jwt, mock_auth_service, provider, mock_request
    ):
        """EPMCDME-13491: a bare user-id in the Authorization header (legacy dev
        convention) must not trigger dev auth; without a Bearer token or cookie
        the request fails with 401 from _extract_local_auth_token."""
        # Arrange
        mock_config.ENV = "local"
        mock_config.IDP_PROVIDER = "local"
        mock_config.AUTH_COOKIE_NAME = "auth_token"

        mock_request.headers.get.side_effect = lambda key: (
            "bob" if key == "Authorization" else None
        )
        mock_request.cookies.get.return_value = None

        mock_auth_service.authenticate_dev_header = AsyncMock()

        mock_idp = MagicMock()

        # Act & Assert
        with pytest.raises(ExtendedHTTPException) as exc_info:
            await provider.authenticate_and_load_user(mock_request, mock_idp)

        assert exc_info.value.code == 401
        mock_auth_service.authenticate_dev_header.assert_not_called()
        mock_validate_jwt.assert_not_called()

    @pytest.mark.asyncio
    @patch("codemie.rest_api.security.user_providers.persistent.authentication_service")
    @patch("codemie.rest_api.security.jwt_local.validate_local_jwt")
    @patch("codemie.rest_api.security.user_providers.persistent.config")
    async def test_dev_header_wins_over_bearer_jwt_in_local_env(
        self, mock_config, mock_validate_jwt, mock_auth_service, provider, mock_request
    ):
        """When both user-id and a Bearer JWT are present in ENV=local, the
        dedicated dev header takes precedence (unchanged behavior)."""
        # Arrange
        mock_config.ENV = "local"
        mock_config.IDP_PROVIDER = "local"
        mock_config.AUTH_COOKIE_NAME = "auth_token"

        dev_user_id = "alice"
        mock_request.headers.get.side_effect = lambda key: (
            dev_user_id if key == "user-id" else "Bearer some.jwt.token" if key == "Authorization" else None
        )
        mock_request.cookies.get.return_value = None

        expected_user = User(
            id=dev_user_id,
            email="alice@example.com",
            name="Dev User",
            auth_token="dev-token",
            is_admin=False,
            project_names=[],
            knowledge_bases=[],
        )
        mock_auth_service.authenticate_dev_header = AsyncMock(return_value=expected_user)

        mock_idp = MagicMock()

        # Act
        result = await provider.authenticate_and_load_user(mock_request, mock_idp)

        # Assert
        assert result == expected_user
        mock_auth_service.authenticate_dev_header.assert_called_once_with(dev_user_id)
        mock_validate_jwt.assert_not_called()
```

- [ ] **Step 2: Run the new tests to verify the two regression tests fail**

Run: `poetry run pytest tests/codemie/rest_api/security/test_persistent_user_provider.py -v -k "bearer_jwt_in_local_env or bare_authorization or dev_header_wins"`

Expected:
- `test_bearer_jwt_in_local_env_uses_local_jwt_validation` — **FAIL** (dev shortcut consumes the Bearer value; `authenticate_dev_header` called)
- `test_bare_authorization_value_no_longer_triggers_dev_auth` — **FAIL** (dev auth called with "bob"; no 401)
- `test_dev_header_wins_over_bearer_jwt_in_local_env` — PASS (characterization; precedence already holds)

- [ ] **Step 3: Implement the fix**

In `src/codemie/rest_api/security/user_providers/persistent.py` replace lines 101-107:

```python
        # 1. Check for dev header (ENV='local' only).
        # Only the dedicated user-id header triggers dev auth; the Authorization
        # header carries real credentials (local JWT or IDP token) and must fall
        # through to the auth branches below (EPMCDME-13491).
        if config.ENV == "local":
            dev_user_id = request.headers.get(USER_ID_HEADER)
            if dev_user_id:
                return await authentication_service.authenticate_dev_header(dev_user_id)
```

And change the import on line 25 from:

```python
from codemie.rest_api.security.user import User, USER_ID_HEADER, AUTHORIZATION_HEADER
```

to:

```python
from codemie.rest_api.security.user import User, USER_ID_HEADER
```

- [ ] **Step 4: Run the full provider test file to verify everything passes**

Run: `poetry run pytest tests/codemie/rest_api/security/test_persistent_user_provider.py -v`

Expected: all tests PASS (5 helper tests + 5 pre-existing provider tests + 3 new tests).

- [ ] **Step 5: Lint**

Run: `make ruff`

Expected: format + check pass; no unused-import warnings for `persistent.py`.

- [ ] **Step 6: Commit**

```bash
git add src/codemie/rest_api/security/user_providers/persistent.py tests/codemie/rest_api/security/test_persistent_user_provider.py
git commit -m "EPMCDME-13491: Stop treating Authorization header as dev user-id in local env"
```
