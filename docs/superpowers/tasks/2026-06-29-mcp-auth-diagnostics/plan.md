# MCP OAuth2 Auth-Flow Diagnostics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add diagnostics-only observability to the MCP OAuth2 auth flow (backend beacon endpoint + bridge-script `sendBeacon` + CSP fix + backend/ frontend logs) so the next reproduction reveals where the success notification is lost.

**Architecture:** Backend changes live in `src/codemie/enterprise/mcp_auth/` (constants, a new diagnostics module, the bridge-script generator, the callback handler logs, and the router). Frontend changes add console logging to two hooks in `codemie-ui/src/hooks/`. The auth tab's bridge page fires a same-origin `navigator.sendBeacon` to a new log-only backend endpoint, surfacing the otherwise-unobservable client-side outcome in exportable backend logs.

**Tech Stack:** FastAPI + Pydantic v2 (backend), Vitest + React Testing Library (frontend).

## Global Constraints

- **No auth-behavior change.** The bridge still `postMessage`s and still `window.close()`s; diagnostics are additive.
- **Never log/transmit secrets:** OAuth `code`, raw `state`, access/refresh tokens, `auth_token`, client secrets, `session_binding_hash`. Only non-secret identifiers (`auth_config_id`, `discovered_flow_id`), origins, booleans, error codes.
- **Beacon endpoint:** log-only, no side effects, strict Pydantic validation, field length caps, unknown fields ignored, input never reflected, returns `204`.
- Commit format: `EPMCDME-13237: <Description>`.
- Backend repo: `/home/taras_spashchenko/EPAM/cm/codemie`. Frontend repo: `/home/taras_spashchenko/EPAM/cm/codemie-ui`.

---

### Task 1: CSP allows the same-origin beacon

**Files:**
- Modify: `src/codemie/enterprise/mcp_auth/_constants.py:56`
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Test-first: yes** — assert the callback page's `Content-Security-Policy` header contains `connect-src 'self'` (currently it does not, so `sendBeacon` is blocked).

**Interfaces:** Produces the updated `_CALLBACK_CONTENT_SECURITY_POLICY` string consumed by `_CALLBACK_SECURITY_HEADERS`.

- [ ] **Step 1: Write the failing test** in `test_oauth2_callback_bridge.py`:
```python
from codemie.enterprise.mcp_auth._constants import _CALLBACK_CONTENT_SECURITY_POLICY

def test_callback_csp_allows_same_origin_connect_for_beacon():
    assert "connect-src 'self'" in _CALLBACK_CONTENT_SECURITY_POLICY
```
- [ ] **Step 2: Run → FAIL.** `poetry run pytest tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_callback_csp_allows_same_origin_connect_for_beacon -v` → FAIL.
- [ ] **Step 3: Implement** — `_constants.py:56`:
```python
_CALLBACK_CONTENT_SECURITY_POLICY = "default-src 'none'; script-src 'self'; connect-src 'self'"
```
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `EPMCDME-13237: Allow same-origin connect in MCP OAuth2 callback CSP for diagnostics beacon`.

---

### Task 2: Beacon endpoint (model + handler + routes)

**Files:**
- Create: `src/codemie/enterprise/mcp_auth/_diagnostics.py`
- Modify: `src/codemie/enterprise/mcp_auth/router.py` (add disabled + enabled POST routes)
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Test-first: yes** — POST a valid diagnostics payload to `/v1/mcp-auth/oauth2/callback-diagnostics` → `204` and a log line containing `result`/`opener_present`/`target_origin`; POST an invalid `result` → `422`; the log line contains no secret-looking fields.

**Interfaces:**
- Produces `OAuth2CallbackDiagnostics` (Pydantic model) and `build_oauth2_callback_diagnostics_response(payload) -> Response` (logs one line, returns 204), imported by `router.py`.

- [ ] **Step 1: Write the failing test** (uses the existing enabled test client/fixture in this file):
```python
def test_callback_diagnostics_logs_and_returns_204(enabled_client, caplog):
    with caplog.at_level("INFO"):
        resp = enabled_client.post(
            "/v1/mcp-auth/oauth2/callback-diagnostics",
            json={"result": "success", "auth_config_id": "discovered:abc",
                  "opener_present": True, "target_origin": "https://app.example.com",
                  "post_message_attempted": True, "window_should_close": True},
        )
    assert resp.status_code == 204
    line = "\n".join(r.message for r in caplog.records)
    assert "MCP OAuth2 callback client diagnostics" in line
    assert "opener_present=True" in line and "target_origin=https://app.example.com" in line

def test_callback_diagnostics_rejects_invalid_result(enabled_client):
    resp = enabled_client.post("/v1/mcp-auth/oauth2/callback-diagnostics",
                               json={"result": "bogus", "opener_present": True})
    assert resp.status_code == 422
```
*(If the file lacks an `enabled_client` fixture, reuse the same app/test-client construction the other `*_enabled` tests in this file already use.)*
- [ ] **Step 2: Run → FAIL** (route 404).
- [ ] **Step 3: Implement** `_diagnostics.py`:
```python
from __future__ import annotations
from typing import Literal
from fastapi import status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from codemie.configs.logger import logger

class OAuth2CallbackDiagnostics(BaseModel):
    model_config = ConfigDict(extra="ignore")  # unknown fields dropped, never logged
    result: Literal["success", "error"]
    auth_config_id: str | None = Field(default=None, max_length=256)
    opener_present: bool
    target_origin: str | None = Field(default=None, max_length=256)
    post_message_attempted: bool = False
    post_message_error: str | None = Field(default=None, max_length=512)
    window_should_close: bool = False
    bridge_error_code: str | None = Field(default=None, max_length=128)
    idp_error_code: str | None = Field(default=None, max_length=128)

def build_oauth2_callback_diagnostics_response(payload: OAuth2CallbackDiagnostics) -> Response:
    message = (
        "MCP OAuth2 callback client diagnostics: "
        f"result={payload.result} auth_config_id={payload.auth_config_id} "
        f"opener_present={payload.opener_present} target_origin={payload.target_origin} "
        f"post_message_attempted={payload.post_message_attempted} "
        f"post_message_error={payload.post_message_error} "
        f"window_should_close={payload.window_should_close} "
        f"bridge_error_code={payload.bridge_error_code} idp_error_code={payload.idp_error_code}"
    )
    # WARNING for the interesting failure shapes so they are greppable; INFO otherwise.
    if payload.result == "error" or not payload.opener_present or payload.post_message_error:
        logger.warning(message)
    else:
        logger.info(message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```
- [ ] **Step 4: Wire routes** in `router.py` (mirror the callback disabled/enabled pattern; **no `Depends(authenticate)`**):
```python
from ._diagnostics import OAuth2CallbackDiagnostics, build_oauth2_callback_diagnostics_response

@router.post("/oauth2/callback-diagnostics", status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             response_model=MCPAuthDisabledResponse)
def oauth2_callback_diagnostics() -> MCPAuthDisabledResponse:
    return _DISABLED_RESPONSE

@enabled_router.post("/oauth2/callback-diagnostics", status_code=status.HTTP_204_NO_CONTENT,
                     response_class=Response)
def oauth2_callback_diagnostics_enabled(payload: OAuth2CallbackDiagnostics) -> Response:
    return build_oauth2_callback_diagnostics_response(payload)
```
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit** `EPMCDME-13237: Add log-only MCP OAuth2 callback diagnostics beacon endpoint`.

---

### Task 3: Bridge script fires the beacon in every branch

**Files:**
- Modify: `src/codemie/enterprise/mcp_auth/_constants.py` (add diagnostics path constant)
- Modify: `src/codemie/enterprise/mcp_auth/_callback_pages.py` (`build_oauth2_callback_page_script_response`)
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Test-first: yes** — assert the served `callback-page.js` contains `navigator.sendBeacon`, the diagnostics path, a `post_message_error` capture, and that `postMessage` is wrapped so an exception is recorded (not thrown).

**Interfaces:** Consumes `_OAUTH2_CALLBACK_DIAGNOSTICS_PATH`. Produces the augmented script string.

- [ ] **Step 1: Write the failing test:**
```python
def test_callback_script_includes_diagnostics_beacon():
    script = build_oauth2_callback_page_script_response().body.decode()
    assert "navigator.sendBeacon" in script
    assert "/v1/mcp-auth/oauth2/callback-diagnostics" in script
    assert "post_message_error" in script
    # beacon fires on the silent error branch too (error path without postMessage)
    assert script.count("sendDiagnostics(") >= 4
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Add the path constant** in `_constants.py` (next to `_OAUTH2_CALLBACK_PAGE_SCRIPT_PATH`):
```python
_OAUTH2_CALLBACK_DIAGNOSTICS_PATH = get_api_root_path() + "/v1/mcp-auth/oauth2/callback-diagnostics"
```
- [ ] **Step 4: Implement** the script changes in `build_oauth2_callback_page_script_response` (import the constant, add a `sendDiagnostics` helper, call it in all four branches, wrap `postMessage` in try/catch). Keep f-string `{{ }}` escaping:
```python
from ._constants import _OAUTH2_CALLBACK_DIAGNOSTICS_PATH
# ...inside the f-string, after authConfigId/targetOrigin/errorCode are read:
#
#   const DIAGNOSTICS_URL = '{_OAUTH2_CALLBACK_DIAGNOSTICS_PATH}';
#   const sendDiagnostics = (extra) => {{
#     try {{
#       const body = JSON.stringify(Object.assign({{
#         result: main.dataset.callbackResult,
#         auth_config_id: authConfigId || null,
#         target_origin: targetOrigin || null,
#         opener_present: !!window.opener,
#         bridge_error_code: main.dataset.bridgeErrorCode || null,
#         idp_error_code: main.dataset.idpErrorCode || null,
#         post_message_attempted: false,
#         window_should_close: false,
#       }}, extra || {{}}));
#       navigator.sendBeacon(DIAGNOSTICS_URL, new Blob([body], {{ type: 'application/json' }}));
#     }} catch (e) {{ /* diagnostics must never break the flow */ }}
#   }};
#
# success + opener:
#   let pmError = null, pmAttempted = false;
#   try {{ window.opener.postMessage({{...}}, targetOrigin); pmAttempted = true; }}
#   catch (err) {{ pmError = String((err && err.message) || err); }}
#   sendDiagnostics({{ post_message_attempted: pmAttempted, post_message_error: pmError, window_should_close: true }});
#   window.close();
#
# success + !opener:  sendDiagnostics({{ }}); updateMessage(CALLBACK_SUCCESS_OPEN_CODEMIE_MESSAGE);
# error + postMessage: same try/catch around postMessage, then sendDiagnostics({{ post_message_attempted: pmAttempted, post_message_error: pmError }});
# error + no postMessage (silent case): sendDiagnostics({{ }});
```
- [ ] **Step 5: Run → PASS.** Also run the full bridge test file (existing script assertions may need updating for the new content).
- [ ] **Step 6: Commit** `EPMCDME-13237: Fire client diagnostics beacon from MCP OAuth2 callback bridge`.

---

### Task 4: Backend callback entry + page-served logs

**Files:**
- Modify: `src/codemie/enterprise/mcp_auth/_oauth2_callback.py` (`build_oauth2_callback_response` entry log)
- Modify: `src/codemie/enterprise/mcp_auth/_callback_pages.py` (`_build_success_callback_response`, `_build_error_callback_response`, add `_safe_target_origin`)
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Test-first: yes** — a GET callback with no `code`/`state` logs `MCP OAuth2 callback received: has_code=False has_state=False` and an `error page served` line with `target_origin=...`; the entry log never contains the raw `state`/`code` values.

**Interfaces:** Produces `_safe_target_origin() -> str | None` (wraps `_derive_callback_target_origin`, returns `None` on failure).

- [ ] **Step 1: Write the failing test:**
```python
def test_callback_logs_entry_and_error_page_served(enabled_client, caplog):
    with caplog.at_level("INFO"):
        enabled_client.get("/v1/mcp-auth/oauth2/callback")  # no code/state -> error page
    text = "\n".join(r.message for r in caplog.records)
    assert "MCP OAuth2 callback received: has_code=False has_state=False" in text
    assert "MCP OAuth2 callback error page served" in text
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the entry log at the top of `build_oauth2_callback_response`:
```python
logger.info(
    "MCP OAuth2 callback received: "
    f"has_code={code is not None} has_state={state is not None} has_error={error is not None}"
)
```
Add `_safe_target_origin` and the served logs in `_callback_pages.py`:
```python
def _safe_target_origin() -> str | None:
    try:
        return _derive_callback_target_origin()
    except Exception:
        return None
```
In `_build_success_callback_response`:
```python
logger.info(
    "MCP OAuth2 callback success page served: "
    f"auth_config_id={auth_config_id} target_origin={_safe_target_origin()} server_name={server_name}"
)
```
In `_build_error_callback_response`:
```python
logger.warning(
    "MCP OAuth2 callback error page served: "
    f"auth_config_id={error.auth_config_id} target_origin={_safe_target_origin()} "
    f"bridge_error_code={error.bridge_error_code} idp_error_code={error.error_code}"
)
```
(Import `logger` in `_callback_pages.py` if not already imported.)
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `EPMCDME-13237: Add entry and page-served logs to MCP OAuth2 callback`.

---

### Task 5: Frontend listener logs origin context + observed messages

**Files:**
- Modify: `codemie-ui/src/hooks/useAuthCallbackListener.ts`
- Test: `codemie-ui/src/hooks/__tests__/useAuthCallbackListener.test.tsx`

**Test-first: yes** — mounting the hook logs `apiOrigin` + `window.location.origin`; dispatching a `window` message with `{type:'mcp_auth_callback'}` from a non-matching origin / untracked id logs an `[mcp-auth] message observed` entry with `shapeValid`/`tracked` (so dropped messages are visible).

**Interfaces:** Consumes `getApiOrigin()`, `AUTH_CALLBACK_EVENT_TYPE`, `trackedIdsRef`.

- [ ] **Step 1: Write the failing test** (spy on `console.info`, render with `trackedAuthConfigIds`, fire a `MessageEvent`). Assert `'[mcp-auth] listener ready'` and `'[mcp-auth] message observed'` were logged.
- [ ] **Step 2: Run → FAIL.** `cd codemie-ui && npx vitest run src/hooks/__tests__/useAuthCallbackListener.test.tsx`.
- [ ] **Step 3: Implement** — in the listener `useEffect` after `const apiOrigin = getApiOrigin()`:
```ts
console.info('[mcp-auth] listener ready', { apiOrigin, windowOrigin: window.location.origin })
```
At the top of `handleMessage`, before the `isAuthCallbackMessage` early return:
```ts
const observed = event.data as Partial<AuthCallbackMessage> | undefined
if (observed?.type === AUTH_CALLBACK_EVENT_TYPE) {
  console.info('[mcp-auth] message observed', {
    origin: event.origin,
    expectedApiOrigin: apiOrigin,
    status: observed.status,
    authConfigId: observed.auth_config_id,
    shapeValid: isAuthCallbackMessage(event.data),
    tracked: observed.auth_config_id ? trackedIdsRef.current.has(observed.auth_config_id) : false,
  })
}
```
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `EPMCDME-13237: Log origin context and observed callback messages in MCP auth listener`.

---

### Task 6: Frontend logs the auth-tab open origin + popup-blocked

**Files:**
- Modify: `codemie-ui/src/hooks/useMCPAuthPrompt.ts` (`initiate` ~:122, `continueAuth` ~:145)
- Test: `codemie-ui/src/hooks/__tests__/useMCPAuthPrompt.test.tsx`

**Test-first: yes** — calling `initiate`/`continueAuth` logs `[mcp-auth] opened auth tab` with `authUrlOrigin`, `windowOrigin`, and `popupBlocked` (true when `window.open` returns null).

**Interfaces:** Adds a local `safeOrigin(url)` helper.

- [ ] **Step 1: Write the failing test** (mock `window.open` to return a truthy object and `null`; assert the log fires with `popupBlocked` reflecting the handle).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — add helper and logs at both open sites:
```ts
const safeOrigin = (url: string): string | null => {
  try { return new URL(url).origin } catch { return null }
}
// initiate (~line 122): capture the handle and log
const popup = window.open(payload.auth_url, '_blank')
console.info('[mcp-auth] opened auth tab', {
  authUrlOrigin: safeOrigin(payload.auth_url),
  windowOrigin: window.location.origin,
  popupBlocked: popup === null,
})
// continueAuth (~line 145): popup is already captured — add the same log after it
console.info('[mcp-auth] opened auth tab', {
  authUrlOrigin: safeOrigin(pendingInitiate.auth_url),
  windowOrigin: window.location.origin,
  popupBlocked: popup === null,
})
```
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `EPMCDME-13237: Log auth-tab open origin and popup-blocked state in MCP auth prompt`.

---

## Self-Review

- **Spec coverage:** Beacon endpoint (T2) ✓, bridge `sendBeacon` all branches (T3) ✓, CSP `connect-src 'self'` (T1) ✓, backend entry/success/error logs (T4) ✓, frontend listener logs (T5) ✓, frontend prompt open logs (T6) ✓. AC1–AC6 each map to a task. No gaps.
- **Secrets:** No task logs `code`/`state`/tokens/`auth_token`/`session_binding_hash`; entry log uses presence booleans only. ✓
- **Type consistency:** `OAuth2CallbackDiagnostics` fields match the beacon JSON keys in T3 and the endpoint in T2; `sendDiagnostics`/`safeOrigin` names used consistently. ✓
