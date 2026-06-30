# Spec — EPMCDME-13237: MCP OAuth2 auth-flow diagnostics

## Goal

Add **diagnostics-only** observability across the MCP OAuth2 auth flow so the next reproduction of
the "backend authenticates but the MCP-config tab hangs" issue reveals exactly where the success
notification is lost. **This ticket changes no auth behavior and does not fix the root cause** — the
fix is a separate follow-up once these diagnostics confirm the cause.

The decisive blind spot is the **auth tab** (the OAuth2 callback bridge page): it sends the success
`window.opener.postMessage()` and then `window.close()`, so its console is unreadable in practice.
We close that blind spot with a client→backend **beacon** that lands in the exportable backend logs.

## Components

### 1. Backend beacon endpoint (new)
`POST {api_root}/v1/mcp-auth/oauth2/callback-diagnostics`, registered on the MCP-auth-enabled router
(same gating as the other callback routes). **Log-only, no side effects, returns `204`.** Accepts a
small, strictly-validated JSON body (Pydantic), whitelisted fields only, size-capped, input never
reflected in the response. Unauthenticated (the bridge page is unauthenticated). Logs one structured
line. Fields:

| field | type | notes |
|---|---|---|
| `result` | `"success" \| "error"` | which bridge branch ran |
| `auth_config_id` | str \| null | non-secret identifier; length-capped |
| `opener_present` | bool | was `window.opener` non-null |
| `target_origin` | str \| null | the origin the bridge used for `postMessage` |
| `post_message_attempted` | bool | did the bridge call `postMessage` |
| `post_message_error` | str \| null | exception message if it threw; length-capped |
| `window_should_close` | bool | did the success-close branch run |
| `bridge_error_code` | str \| null | from `data-bridge-error-code` |
| `idp_error_code` | str \| null | from `data-idp-error-code` |

### 2. Bridge script instrumentation
In `build_oauth2_callback_page_script_response()` (`_callback_pages.py`), fire
`navigator.sendBeacon(diagnosticsUrl, payload)` in **all four branches** (success-with-opener,
success-without-opener, error-with-postMessage, error-without-postMessage), **before**
`postMessage`/`window.close()`. Wrap `postMessage` in `try/catch` to capture `post_message_error`.
The diagnostics URL is derived the same way as the script path
(`get_api_root_path() + "/v1/mcp-auth/oauth2/callback-diagnostics"`), same-origin (no CORS).

### 3. CSP fix (required for the beacon to work)
`_CALLBACK_CONTENT_SECURITY_POLICY` is currently `default-src 'none'; script-src 'self'`, so
`connect-src` inherits `'none'` and **blocks `sendBeacon`**. Change to
`default-src 'none'; script-src 'self'; connect-src 'self'` — minimal broadening, same-origin only.

### 4. Backend structured logs (always-on, secret-safe)
In `_oauth2_callback.py`:
- **Callback entry:** `has_code` / `has_state` / `has_error` (presence booleans only — never values).
- **Success page served:** `auth_config_id`, `target_origin`, `server_name`.
- **Error page served:** `auth_config_id` (may be null), `target_origin`, `bridge_error_code`, `idp_error_code`.

Existing logs (verified / token-exchange-failed / persist-failed) are unchanged.

### 5. Frontend console logs (config tab stays open → console is capturable)
- `useAuthCallbackListener.ts`: on listener setup log `apiOrigin` + `window.location.origin` +
  tracked ids; in the message handler, log any incoming message whose `type === 'mcp_auth_callback'`
  even when it fails the shape/origin/tracked checks (origin, status, authConfigId, shapeValid,
  tracked) — to catch "message arrived but dropped."
- `useMCPAuthPrompt.ts` (`initiate`/`continueAuth`): log the `auth_url` origin,
  `window.location.origin`, and whether the popup handle was null (popup blocked).

## Data flow (the captured trace, per reproduction)
1. Config tab logs its `apiOrigin` + `window.location.origin` when the listener mounts.
2. User authenticates; backend logs callback entry → verified → success/error page served (with
   `target_origin`).
3. Bridge page (auth tab) fires the beacon with `opener_present` + `target_origin` +
   `post_message_attempted`/`error`, then posts/closes.
4. Backend logs the beacon line. Comparing the bridge's `target_origin` against the config tab's
   `window.location.origin` pinpoints an origin mismatch; `opener_present=false` pinpoints a severed
   opener; a `post_message_error` pinpoints an exception.

## Security constraints (must hold)
Never log or transmit secrets: OAuth `code`, raw `state`, access/refresh tokens, `auth_token`,
client secrets, `session_binding_hash`. Only non-secret identifiers, origins, booleans, error codes.
Beacon endpoint validates/whitelists/size-caps input, never reflects it, returns 204.

## Acceptance criteria
- **AC1** A hanging repro produces one beacon log line in exportable backend logs with at least
  `result`, `auth_config_id`, `opener_present`, `target_origin`, `post_message_attempted`/`error`.
- **AC2** A successful backend callback logs "success page served" including the exact `target_origin`.
- **AC3** The config-tab console logs `window.location.origin` + `apiOrigin` at setup and logs any
  `mcp_auth_callback`-typed message that arrives (matched or dropped).
- **AC4** The beacon is delivered (not blocked by CSP) for both success and error outcomes.
- **AC5** No secret values appear in any new log line or beacon payload.
- **AC6** No behavioral change to the auth flow (still posts message, still closes the tab).

## Out of scope
The actual fix (correcting `FRONTEND_URL`/`targetOrigin` handling or supporting multiple frontend
origins). Separate follow-up ticket once diagnostics confirm the cause.

## Testing
- Backend: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py` — beacon endpoint (valid
  payload logged at INFO/WARNING; oversized/invalid rejected; no secrets), CSP includes `connect-src
  'self'`, bridge script contains the `sendBeacon` call in each branch, new entry/page-served logs.
- Frontend: `useAuthCallbackListener.test.tsx`, `useMCPAuthPrompt.test.tsx` — the new logging.
