# Work Item: EPMCDME-13491 — Local auth returns 401 for Bearer JWT in local user-management mode

**External ticket**: [EPMCDME-13491](https://jiraeu.epam.com/browse/EPMCDME-13491)
**Type**: Bug
**Priority**: Major
**Status**: Ready for review
**Epic**: EPMCDME-3868 (Admin Functionality Enhancements)
**Branch**: EPMCDME-13491_local-auth-bearer-jwt-fix

## Summary

Local auth (ENABLE_USER_MANAGEMENT=True, IDP_PROVIDER=local, ENV=local) returns 401 on every authenticated request because the local dev-header shortcut in `PersistentUserProvider.authenticate_and_load_user` treats the Bearer JWT from the Authorization header as a dev user-id before local JWT validation can run.

## Linked Artifacts

- docs/superpowers/runs/20260714-2233-EPMCDME-13491/work-item.md

## History

| When | Event | Detail |
|---|---|---|
| 2026-07-14T19:33:30Z | created | Run mirror created from raw_input (placeholder; Phase 1 synchronizes) |
