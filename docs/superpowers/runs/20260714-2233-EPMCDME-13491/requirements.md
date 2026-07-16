# Requirements — 20260714-2233-EPMCDME-13491

**Source**: ticket:EPMCDME-13491
**Work Item**: docs/superpowers/work-items/EPMCDME-13491.md
**Original input**: |
  EPMCDME-13491 — Local auth returns 401 for Bearer JWT in local user-management mode (https://jiraeu.epam.com/browse/EPMCDME-13491)

## Goal

Fix local auth (ENV=local, ENABLE_USER_MANAGEMENT=True, IDP_PROVIDER=local) so a freshly issued local RS256 JWT sent as `Authorization: Bearer <token>` authenticates successfully instead of returning 401 on every request.

## Acceptance Criteria

Derived from the ticket's Expected result and Suggested fix sections:

- A valid local JWT (`iss: codemie-local`) obtained from `POST /v1/local-auth/login` is accepted on authenticated endpoints (e.g. `GET /v1/admin/applications?search=codemie`) — the request authenticates normally, no 401.
- The ENV=local dev shortcut no longer treats a Bearer token as a dev user-id: either only the dedicated user-id header (`USER_ID_HEADER`) is honored for the dev shortcut, or Authorization values starting with `"Bearer "` are ignored by the shortcut so the request falls through to `validate_local_jwt`.
- The dev-header shortcut keeps working for its intended case (dedicated user-id header present in ENV=local).

## Context

- **Type**: Bug, Major. Epic: EPMCDME-3868 (Admin Functionality Enhancements). Status: In Progress.
- **Root cause (verified in ticket against current source)**: `PersistentUserProvider.authenticate_and_load_user` in `src/codemie/rest_api/security/user_providers/persistent.py` checks the `ENV == "local"` dev shortcut before local JWT validation. When `USER_ID_HEADER` is absent it falls back to the raw `Authorization` header and passes `"Bearer <JWT>"` to `authenticate_dev_header`, producing invalid UserDB data and a generic 401. The `IDP_PROVIDER == "local"` branch calling `validate_local_jwt` (`src/codemie/rest_api/security/jwt_local.py`) is never reached.
- **Preconditions**: ENV=local, ENABLE_USER_MANAGEMENT=True, IDP_PROVIDER=local.
- **Impact**: blocks `codemie-test-harness --sanity-ui` — all UI tests fail at shared auth fixture setup because authenticated API calls receive 401.
- **Related**: EPMCDME-10160 (core user-management logic).

## Open questions

(none)
