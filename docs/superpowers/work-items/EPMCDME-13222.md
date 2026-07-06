# Work Item: EPMCDME-13222

**Title**: Improve Google Docs datasource indexing by replacing shared service account with per-user integration  
**Type**: Task  
**Status**: In Progress  
**Assignee**: Kostiantyn Pshenychnyi1  
**External Ticket**: [EPMCDME-13222](https://jiraeu.epam.com/browse/EPMCDME-13222)  
**Created**: 2026-07-01T17:35:00Z  
**Updated**: 2026-07-01T17:36:00Z

## Summary

Replace the shared service account approach for Google Docs datasource indexing with a per-user OAuth 2.0 integration. This ensures content is indexed according to authenticated user's access and permissions, improving security, traceability, and alignment with user-specific datasource access.

## Acceptance Criteria

- Google Docs datasource indexing no longer depends on a shared service account
- Google Docs integration is implemented per user
- User-specific Google Docs permissions are respected during indexing
- System indexes only Google Docs content accessible to the authenticated user
- Existing Google Docs datasource indexing behavior continues to work after migration to per-user integration
- Error handling is implemented for missing, expired, or invalid user-specific Google Docs credentials
- No regression is introduced for existing datasource indexing flows
- The implementation is documented where Google Docs datasource configuration or integration behavior is described

## Context

Currently using a shared service account for Google Docs indexing. This task is part of the larger effort to implement per-user integration across datasources.

**Related Sub-tasks**:
- EPMCDME-13226: Infrastructure and migrations
- EPMCDME-13228: Indexing path and credential usage
- EPMCDME-13229: OAuth authorization flow (current focus)
- EPMCDME-13230: Infrastructure and credential model

**Backend Implementation Scope** (this run):
- OAuth 2.0 authorization endpoints (initiate, callback, status, disconnect)
- Secure token storage with automatic refresh
- CSRF protection via state parameter
- Proper scopes for Google Docs API
- Error handling for revoked/expired tokens
- Following project conventions for structure, config, secrets, logging, testing

## Linked Artifacts

- `docs/superpowers/runs/20260701-1735-main/requirements.md`

## History

- 2026-07-01T17:35:00Z: Work item created from Jira ticket EPMCDME-13222
- 2026-07-01T17:36:00Z: Linked requirements.md artifact from run 20260701-1735-main
