# Work Item: EPMCDME-13491 — Local auth returns 401 for Bearer JWT in local user-management mode

**External Ticket**: https://jiraeu.epam.com/browse/EPMCDME-13491
**Type**: Bug
**Priority**: Major
**Status**: Ready for review
**Epic**: EPMCDME-3868 (Admin Functionality Enhancements)
**Branch**: EPMCDME-13491_local-auth-bearer-jwt-fix
**External sync**: resolved (adapter lookup succeeded 2026-07-14)

## Summary

Local auth (ENABLE_USER_MANAGEMENT=True, IDP_PROVIDER=local, ENV=local) returns 401 on every authenticated request because the local dev-header shortcut in `PersistentUserProvider.authenticate_and_load_user` (src/codemie/rest_api/security/user_providers/persistent.py) treats the Bearer JWT from the Authorization header as a dev user-id before local JWT validation can run. The `validate_local_jwt` path for IDP_PROVIDER=local is never reached.

## Acceptance Criteria

- Valid local JWT from POST /v1/local-auth/login is accepted on authenticated endpoints (no 401).
- Dev shortcut no longer treats `Bearer <JWT>` Authorization values as dev user-ids; requests fall through to local JWT validation.
- Dev shortcut still works with the dedicated user-id header in ENV=local.

## Linked Artifacts

- docs/superpowers/runs/20260714-2233-EPMCDME-13491/requirements.md
- docs/superpowers/runs/20260714-2233-EPMCDME-13491/work-item.md

## History

| When | Event | Detail |
|---|---|---|
| 2026-07-14T19:33:30Z | created | Canonical local work item created from Jira adapter lookup (codemie-jira-assistant) |
| 2026-07-14T19:36:00Z | linked_artifact | requirements.md written by requirements-intake |
| 2026-07-14T21:30:00Z | transitioned | Ready for review — branch EPMCDME-13491_local-auth-bearer-jwt-fix, commit ef0f0db84; QA report + review verdict linked; external sync pending (adapter has no lifecycle intents) |
