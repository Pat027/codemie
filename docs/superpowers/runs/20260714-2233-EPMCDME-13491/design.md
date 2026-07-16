# EPMCDME-13491 — Local Auth Bearer JWT Fix Design

**Date**: 2026-07-14
**Ticket**: [EPMCDME-13491](https://jiraeu.epam.com/browse/EPMCDME-13491) (Bug, Major)
**Branch**: EPMCDME-13491_local-auth-bearer-jwt-fix
**Status**: Approved (autonomous run 20260714-2233-EPMCDME-13491)

---

## Problem

With `ENV=local`, `ENABLE_USER_MANAGEMENT=True`, `IDP_PROVIDER=local`, every authenticated request carrying `Authorization: Bearer <local JWT>` returns 401.

`PersistentUserProvider.authenticate_and_load_user` (`src/codemie/rest_api/security/user_providers/persistent.py:101-107`) runs a dev-header shortcut before any real authentication:

```python
# 1. Check for dev header (ENV='local' only)
if config.ENV == "local":
    dev_user_id = request.headers.get(USER_ID_HEADER)
    if not dev_user_id:
        dev_user_id = request.headers.get(AUTHORIZATION_HEADER)
    if dev_user_id:
        return await authentication_service.authenticate_dev_header(dev_user_id)
```

When the dedicated `user-id` header is absent, the shortcut grabs the raw `Authorization` header and passes the entire `"Bearer <JWT>"` string to `authenticate_dev_header` as a user-id. That produces invalid `UserDB` data and a generic 401. The `IDP_PROVIDER == "local"` branch below — `_extract_local_auth_token` + `validate_local_jwt` — is never reached.

**Impact**: local-auth backend is unusable for Bearer-authenticated clients; `codemie-test-harness --sanity-ui` is fully blocked at auth fixture setup.

## Decision

**Variant A — remove the Authorization-header fallback from the dev shortcut.** Only the dedicated `user-id` header triggers dev auth. (Product-owner-stand-in verdict, gate `spec.clarification`, confidence high; matches the ticket's stated preference.)

Rejected alternative — Variant B (keep the fallback but skip values starting with `"Bearer "`): minimal diff, but preserves the unsafe behavior where any arbitrary `Authorization` value auto-creates an `is_admin=True` user in the local DB, and keeps two overlapping ways to express a dev identity.

## Change

In `PersistentUserProvider.authenticate_and_load_user`, the dev shortcut becomes:

```python
# 1. Check for dev header (ENV='local' only).
# Only the dedicated user-id header triggers dev auth; the Authorization
# header is reserved for real credentials (local JWT or IDP token) so it
# must fall through to the auth branches below (EPMCDME-13491).
if config.ENV == "local":
    dev_user_id = request.headers.get(USER_ID_HEADER)
    if dev_user_id:
        return await authentication_service.authenticate_dev_header(dev_user_id)
```

The `AUTHORIZATION_HEADER` import becomes unused in this module and is removed.

Behavior matrix after the fix (ENV=local, ENABLE_USER_MANAGEMENT=True):

| Request carries | Before | After |
|---|---|---|
| `user-id: alice` | dev auth as `alice` | dev auth as `alice` (unchanged) |
| `Authorization: Bearer <valid local JWT>` | 401 (treated as dev user-id) | authenticated via `validate_local_jwt` |
| `Authorization: Bearer <valid local JWT>` + `user-id: alice` | dev auth as `alice` | dev auth as `alice` (unchanged — dedicated header wins) |
| `Authorization: bob` (bare user-id, legacy convention) | dev auth as `bob`, auto-creates admin | falls through to real auth → 401 in local-JWT mode (**intentional removal**) |
| cookie token only (no Authorization header), IDP_PROVIDER=local | works (shortcut skipped when Authorization absent) | works (unchanged) |

## Out of scope

- `LocalIdp.authenticate` (`src/codemie/rest_api/security/idp/local.py:71-73`) has the same Authorization fallback in transient (non-user-management) mode. Different provider, different semantics (mock tokens, no DB writes in ENV=local). Follow-up ticket recommended; not changed here.
- `authenticate_dev_header` itself (admin auto-create semantics) is unchanged.

## Testing

Extend `tests/codemie/rest_api/security/test_persistent_user_provider.py` (existing mock patterns for config/auth service):

1. **Regression (the bug)**: ENV=local, IDP_PROVIDER=local, request has only `Authorization: Bearer <valid JWT>` → `authenticate_dev_header` is NOT called; `validate_local_jwt` path is used; user authenticates.
2. **Dev shortcut preserved**: ENV=local, `user-id` header present → `authenticate_dev_header` called with the header value (existing test keeps passing).
3. **Precedence**: ENV=local, both `user-id` and Bearer Authorization present → dev shortcut wins (matches current behavior when both are present).
4. **Legacy convention removed**: ENV=local, IDP_PROVIDER=local, only `Authorization: bob` (non-Bearer) → dev auth NOT invoked; `_extract_local_auth_token` raises 401 (no Bearer header, no cookie).

Existing suite must stay green (`test_authenticate_dev_header_local_env` uses the dedicated header — unaffected).

## Risks

- **Breaking change (dev-only)**: tools relying on bare user-id in the Authorization header in persistent local mode lose that path; they must send the `user-id` header instead. Called out for the PR description. Production paths (`ENV != local`) are untouched — the modified block is guarded by `config.ENV == "local"`.
