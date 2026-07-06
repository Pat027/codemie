# Requirements — 20260701-1735-main

**Source**: ticket:EPMCDME-13222  
**Work Item**: docs/superpowers/work-items/EPMCDME-13222.md  
**Original input**: |
  Implement backend for Google OAuth 2.0 authorization to replace the current auth method for the Google Docs datasource.

  Jira Ticket: https://jiraeu.epam.com/browse/EPMCDME-13222 (read with Brianna)
  OAuth Flow: https://developers.google.com/identity/protocols/oauth2/web-server (read it too, it includes stuff you need + libs)

  Context

  Tokens: Fully managed backend-side — access token, refresh token, expiry, and refresh logic. Frontend never sees tokens.
  Frontend: Being implemented in parallel. Plan is here C:\Users\kostiantyn_pshenych1\Documents\cdme\codemie-ui-next\docs\superpowers\plans\2026-07-01-google-docs-oauth.md
  Reference: A similar OAuth flow exists for the SharePoint datasource. Plus there is a gcp tool already uses google api library. Analyze it and reuse what's genuinely useful.

  Requirements

  Endpoints to initiate auth, handle Google's callback, check auth status, and disconnect.
  Secure token storage, automatic refresh, and proper handling of revoked/expired tokens.
  CSRF protection on the OAuth flow (state parameter), correct scopes for Google Docs, safe redirect URI handling.
  Follow existing project conventions (structure, config, secrets management, logging, testing).
  Proper error handling and clear error responses to the frontend.

  Ask before coding if unclear

## Goal

Implement backend OAuth 2.0 authorization flow for Google Docs datasource to enable per-user integration, replacing the current shared service account approach.

## Acceptance Criteria

- Endpoint to initiate OAuth authorization flow (returns Google auth URL with state parameter)
- Endpoint to handle Google OAuth callback (exchanges code for tokens, stores them securely)
- Endpoint to check current authorization status for a user
- Endpoint to disconnect/revoke authorization
- Secure storage of access tokens, refresh tokens, and expiry timestamps per user
- Automatic token refresh before expiry when tokens are accessed
- CSRF protection via cryptographically random state parameter validation
- Correct Google Docs API scopes configured (read access to user's Google Docs)
- Redirect URI validation and safe handling (no open redirects)
- Error handling for expired, revoked, or invalid credentials with clear error responses
- Follow project conventions: layered architecture, service/repository patterns, FastAPI routers, SQLModel, error handling, logging, configuration management
- Error responses structured for frontend consumption

## Context

### OAuth 2.0 Implementation Details

**Authorization Endpoint**: `https://accounts.google.com/o/oauth2/v2/auth`
**Token Endpoint**: `https://oauth2.googleapis.com/token`

**Required Parameters**:
- `client_id`: From Google Cloud Console configuration
- `redirect_uri`: Must exactly match registered URI in Google Cloud Console
- `response_type`: Set to `code` (authorization code flow)
- `scope`: Space-delimited Google Docs API permissions
- `state`: Cryptographically random CSRF token
- `access_type`: Set to `offline` to receive refresh tokens

**Token Response**:
- `access_token`: Bearer token for API requests
- `refresh_token`: Long-lived token for obtaining new access tokens
- `expires_in`: Token lifetime in seconds
- `scope`: Granted permissions

**Security Requirements**:
- Store tokens securely in database, never in logs or client-side
- Use HTTPS for all OAuth endpoints (localhost exceptions for development)
- Validate state parameter matches on callback
- Store `client_secret` in environment/secrets, never in code
- Verify granted scopes match requested scopes

### Project Context

- **Backend-only scope**: Frontend integration is being implemented in parallel
- **Token management**: All token lifecycle (storage, refresh, expiry) handled backend-side
- **Reference implementations**: 
  - SharePoint datasource OAuth flow (similar pattern to follow)
  - Existing GCP tool using Google API library (reuse authentication patterns)
- **Related Jira sub-tasks**:
  - EPMCDME-13226: Infrastructure and migrations (may need coordination)
  - EPMCDME-13228: Indexing path and credential usage (downstream consumer)
  - EPMCDME-13230: Infrastructure and credential model (may need coordination)

## Open questions

(none)
