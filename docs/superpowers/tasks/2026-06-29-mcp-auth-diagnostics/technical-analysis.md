# Technical Analysis — EPMCDME-13237: MCP OAuth2 auth-flow diagnostics

**Feature area:** mcp auth oauth2 callback diagnostics
**Source:** Derived from a full end-to-end trace of the MCP OAuth2 auth flow performed during the
preceding investigation (backend callback, bridge page, frontend listener) cross-referenced with
production logs. All file/line anchors below were verified against the current `main`.

## Context / Problem

Users authenticating an MCP server that requires OAuth2 see the auth tab close after they
authenticate, but the MCP-config tab hangs "waiting for authentication completion" and times out
at 60s. Production logs proved the **backend callback succeeds and stores the credential**
(`operation=store source=oauth2_callback success=True`) while the browser console shows only
`Awaiting auth callback → Timed out`, with **no** `Received` and **no** `Ignoring` line. That means
the success `window.opener.postMessage()` from the callback bridge page never reaches the config-tab
listener. The decisive client-side step happens on the **auth tab**, which calls `window.close()`
immediately, so its console cannot be captured. This ticket adds observability (it does **not** fix
the bug) so the next reproduction reveals where the notification is lost.

## Codebase Findings

### Backend — `src/codemie/enterprise/mcp_auth/`

- **`_callback_pages.py`**
  - `build_oauth2_callback_page_script_response()` (`:158`) generates the bridge JS as a Python
    f-string (note `{{ }}` escaping). On success with `window.opener` it calls
    `window.opener.postMessage({type, status:'success', auth_config_id}, targetOrigin)` then
    `window.close()` (`:182-188`); on success without opener it shows an "open CodeMie" message and
    does **not** post or close (`:180-181`); on error it posts only when
    `window.opener && authConfigId && targetOrigin && errorCode` (`:197-204`).
  - `_build_callback_page()` (`:39`) renders the HTML with `data-callback-result`,
    `data-auth-config-id`, `data-target-origin`, `data-idp-error-code`, `data-bridge-error-code`
    attributes and returns `HTMLResponse(status_code=200, headers=_CALLBACK_SECURITY_HEADERS)` —
    **the page is always HTTP 200, even on failure.**
  - `_derive_callback_target_origin()` (`:129`) computes the `postMessage` targetOrigin as
    `scheme://netloc` of `config.FRONTEND_URL` (the suspected mismatch source).
  - `_build_success_callback_response()` (`:104`) / `_build_error_callback_response()` (`:115`).
- **`_constants.py`**
  - `_OAUTH2_CALLBACK_PAGE_SCRIPT_PATH = get_api_root_path() + "/v1/mcp-auth/oauth2/callback-page.js"` (`:42`).
  - `_CALLBACK_CONTENT_SECURITY_POLICY = "default-src 'none'; script-src 'self'"` (`:56`) — **no
    `connect-src`, so it inherits `'none'` and BLOCKS `navigator.sendBeacon`.** Must add `connect-src 'self'`.
  - `_CALLBACK_SECURITY_HEADERS` (`:57`), `_CALLBACK_EVENT_TYPE = "mcp_auth_callback"` (`:83`),
    `_CALLBACK_FALLBACK_DELAY_MS = 300` (`:89`).
- **`_oauth2_callback.py`**
  - `build_oauth2_callback_response()` (`:470`) is the entry wrapper; logs failures at `:487`
    (`CallbackPageError`), `:495` (`ExtendedHTTPException`), `:501` (unexpected). `_build_*` variants
    do the work. Existing INFO "verified; resolving token exchange" at `:540`; token-exchange failure
    WARNING at `:433`; persist failure WARNING at `:460`. Token exchange uses
    `httpx.Client(timeout=2.0)` (`:419`).
- **`router.py`** — `@router.get("/oauth2/callback")` (`:338`, **public, no `Depends(authenticate)`**),
  `@enabled_router.get("/oauth2/callback-page.js")` (`:351`). New diagnostics route follows this pattern.
- **`config.py`** — `FRONTEND_URL: str = "http://localhost:3000"  # For email links` (`:249`);
  `CALLBACK_API_BASE_URL` (`:54`). `FRONTEND_URL` is repurposed as the bridge targetOrigin.

### Frontend — `codemie-ui/src/`

- **`hooks/useAuthCallbackListener.ts`** — the config-tab listener. `getApiOrigin()` (`:54`) derives
  the expected sender origin from `VITE_MCP_AUTH_ORIGIN` → `api.BASE_URL` → `window.location.origin`.
  `handleMessage` (`:189`) returns silently when `isAuthCallbackMessage` fails (`:192`), logs ignore
  on origin mismatch (`:194`) / untracked id (`:201`), logs `Received` (`:209`); `Awaiting` (`:169`),
  `Timed out` (`:134`).
- **`hooks/useMCPAuthPrompt.ts`** — opens the auth tab via `window.open(payload.auth_url, '_blank')`
  in `initiate` (`:122`) and `window.open(pendingInitiate.auth_url, '_blank')` in `continueAuth`
  (`:145`) — **no `noopener`, so `window.opener` is preserved** (consistent with the tab closing).
  `continueAuth` already null-checks the popup handle (popup-blocked) (`:151`).
- **`MCPToolsSelectionStep.tsx:296`** uses `window.open(brokerLoginUrl, '_blank', 'noopener,noreferrer')` —
  a **separate** broker-login path, not the OAuth2 discovered flow; out of scope here.

### Existing test patterns (TDD targets)

- Backend: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py` (callback + bridge script),
  `test_oauth2_initiate_bridge.py`, and siblings `tests/enterprise/mcp_auth/test_*_bridge.py`. These
  exercise the FastAPI routes via a test client and assert on response bodies / served script text.
- Frontend: `codemie-ui/src/hooks/__tests__/useAuthCallbackListener.test.tsx`,
  `useMCPAuthPrompt.test.tsx` (Vitest + Testing Library).

### Integration points

- The bridge script is served same-origin from `/v1/mcp-auth/oauth2/callback-page.js`; the new
  diagnostics endpoint is same-origin, so `sendBeacon` needs only `connect-src 'self'`.
- A `navigator.sendBeacon` payload is best-effort delivered during page unload — fired *before*
  `postMessage`/`window.close()`.

## Risk Indicators

- **Security-sensitive surface (OAuth2 callback).** Must never log/transmit secrets: OAuth `code`,
  raw `state`, access/refresh tokens, `auth_token`, client secrets, or `session_binding_hash`. Only
  non-secret identifiers (`auth_config_id`, `discovered_flow_id`), origins, booleans, error codes.
- **New endpoint is unauthenticated** (called from the unauthenticated bridge page). Must be
  log-only, no side effects, strict payload validation, size-capped, input never reflected, gated by
  MCP-auth-enabled, return 204.
- **CSP broadening** on a hardened page — keep the change minimal (`connect-src 'self'` only).
- **Bridge script is an f-string** with `{{ }}` escaping — adding JS must preserve escaping; existing
  `test_oauth2_callback_bridge.py` assertions on the script text will need updating.
- **Additive only** — no change to auth behavior (still posts message, still closes the tab).
- Auth/security keywords present → heavier review warranted (noted; user chose sdlc-task).

## Implementation notes

- Inject the diagnostics URL into the bridge script the same way the script path is derived
  (`get_api_root_path() + "/v1/mcp-auth/oauth2/callback-diagnostics"`); use a relative/absolute
  same-origin path so no CORS/preflight is involved (text/plain or application/json beacon body).
- Beacon fields: `result`, `auth_config_id`, `opener_present`, `target_origin`,
  `post_message_attempted`, `post_message_error`, `window_should_close`, `bridge_error_code`,
  `idp_error_code`. Wrap `postMessage` in try/catch to capture `post_message_error`.
- Backend logs to add: callback entry (`has_code`/`has_state`/`has_error` — presence only),
  success-page-served (`auth_config_id`, `target_origin`, `server_name`), error-page-served
  (`auth_config_id` may be null, `target_origin`, `bridge_error_code`, `idp_error_code`).
- Frontend logs to add: listener setup (`apiOrigin`, `window.location.origin`, tracked ids);
  incoming `type === 'mcp_auth_callback'` messages even when dropped; auth-tab open origin + popup-blocked.
