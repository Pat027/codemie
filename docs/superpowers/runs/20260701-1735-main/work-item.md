# Work Item: EPMCDME-13222

**Title**: Improve Google Docs datasource indexing by replacing shared service account with per-user integration  
**Type**: Task  
**Status**: In Progress  
**Assignee**: Kostiantyn Pshenychnyi1  
**External Ticket**: [EPMCDME-13222](https://jiraeu.epam.com/browse/EPMCDME-13222)  
**Run**: 20260701-1735-main

## Summary

Replace the shared service account approach for Google Docs datasource indexing with a per-user OAuth 2.0 integration. Backend implementation focuses on OAuth authorization flow.

## Acceptance Criteria

- OAuth 2.0 endpoints: initiate auth, handle callback, check status, disconnect
- Secure token storage with automatic refresh
- CSRF protection (state parameter)
- Correct scopes for Google Docs API
- Safe redirect URI handling
- Error handling for revoked/expired tokens
- Follow project conventions (structure, config, secrets, logging, testing)
- Clear error responses to frontend

## Context

- Backend-only scope: full token management (access, refresh, expiry, refresh logic)
- Frontend integration happening in parallel
- Reference implementations: SharePoint datasource OAuth, existing GCP tool

## Linked Artifacts

- `docs/superpowers/runs/20260701-1735-main/requirements.md`

## History

- 2026-07-01T17:36:00Z: Work item mirrored from canonical EPMCDME-13222 for run 20260701-1735-main
