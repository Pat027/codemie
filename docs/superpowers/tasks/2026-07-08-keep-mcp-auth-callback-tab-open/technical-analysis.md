# Technical Research

**Task**: mcp-auth oauth2 callback bridge-page window-close pydantic-settings-config
**Generated**: 2026-07-08
**Research path**: filesystem

---

## 1. Original Context

"We need to modify the behaviour of the authentication tab. Now it closes and we can't grab any logs from that tab, but we need to preserve that tab in order to have a chance for analysis."

Additional context established with the user: The auth tab is the OAuth2 callback bridge page served by the CodeMie backend at GET /v1/mcp-auth/oauth2/callback (bridge JS at /v1/mcp-auth/oauth2/callback-page.js). On successful auth it currently calls window.close(), which destroys the tab's console/URL before a tester can inspect it — that inspection is exactly the missing evidence in an MCP OAuth hang incident. The agreed approach is a config-gated switch (default off, preserving today's auto-close UX) that, when enabled, keeps the tab open instead of closing it. This is a diagnostic aid.

---

## 2. Codebase Findings

### Existing Implementations

- `src/codemie/enterprise/mcp_auth/_callback_pages.py` — builds the HTML bridge page (`_build_callback_page`, `_build_success_callback_response`, `_build_error_callback_response`) and the client-side JS bridge script (`build_oauth2_callback_page_script_response`, ~line 170-280) served as `callback-page.js`.
- `src/codemie/enterprise/mcp_auth/_constants.py` — all string/timing/security constants consumed by `_callback_pages.py` (`_CALLBACK_FALLBACK_DELAY_MS`, message strings, `_CALLBACK_CONTENT_SECURITY_POLICY`, `_CALLBACK_SECURITY_HEADERS`, path constants).
- `src/codemie/enterprise/mcp_auth/_diagnostics.py` — `OAuth2CallbackDiagnostics` pydantic model (lines 41-60, includes `window_should_close: bool = False`) and `build_oauth2_callback_diagnostics_response` (lines 63-85): logs the beacon payload posted from the bridge page; unauthenticated by design ("the bridge page that fires this beacon is itself unauthenticated"); no persistence, returns 204.
- `src/codemie/enterprise/mcp_auth/router.py` — route defs: `oauth2_callback_page_script_enabled` (GET `/oauth2/callback-page.js`, lines 354-359), `oauth2_callback_enabled` (GET `/oauth2/callback`, lines 362-379), `oauth2_callback_diagnostics_enabled` (POST `/oauth2/callback-diagnostics`, lines 391-399), plus disabled-state stub twins returning `MCPAuthDisabledResponse` (503) when MCP auth is off (dual enabled/disabled router pattern used throughout this package).
- `src/codemie/enterprise/mcp_auth/dependencies.py` — re-exports the builder functions; already imports `config` (`from codemie.configs import config`) — no new import needed for a config-gated flag.
- `src/codemie/configs/config.py` — `Config(BaseSettings)`, `MCP_AUTH_*` boolean-flag cluster at lines 414-463; module singleton `config = Config()` at line 917.

**Close logic** — the only `window.close()` call site, `_callback_pages.py:224-253`, inside the success branch of `build_oauth2_callback_page_script_response`:
```js
if (main.dataset.callbackResult === 'success') {
    if (!window.opener) {
      sendDiagnostics({});
      updateMessage(CALLBACK_SUCCESS_OPEN_CODEMIE_MESSAGE);
    } else if (authConfigId && targetOrigin) {
      window.opener.postMessage({ type: CALLBACK_EVENT_TYPE, status: 'success', auth_config_id: authConfigId }, targetOrigin);
      postMessageAttempted = true;
      sendDiagnostics({
        post_message_attempted: postMessageAttempted,
        post_message_error: postMessageError,
        window_should_close: true,
      });
      window.close();                                   // line 246
      window.setTimeout(() => {                          // fallback if close is blocked by the browser
        if (!window.closed) {
          updateMessage(CALLBACK_SUCCESS_CLOSE_MESSAGE);
        }
      }, CALLBACK_FALLBACK_DELAY_MS);
    }
}
```
- Fires only on success **with** `opener` + `authConfigId` + `targetOrigin` (real popup flow). No-opener success path never closes. The error branch (lines 255-277) never calls `window.close()`.
- `CALLBACK_FALLBACK_DELAY_MS` (300ms) only updates the message if `window.close()` was blocked — it is not itself a close trigger.

**Diagnostics beacon / `window_should_close`** — built at `_callback_pages.py:199-222`, fired via `navigator.sendBeacon` **before** `window.close()`, deliberately, "so it survives the tab closing":
```js
// Diagnostics-only beacon: report whether this page could notify the opener
// window. Fired before postMessage/window.close so it survives the tab closing.
// Never throws - diagnostics must not break the auth flow. Carries no secrets.
const sendDiagnostics = (extra) => {
  try {
    const payload = Object.assign({
      result: main.dataset.callbackResult,
      auth_config_id: authConfigId || null,
      target_origin: targetOrigin || null,
      opener_present: !!window.opener,
      window_should_close: false,
      ...
    }, extra || {});
    navigator.sendBeacon(CALLBACK_DIAGNOSTICS_URL, new Blob([JSON.stringify(payload)], { type: 'application/json' }));
  } catch (e) { /* diagnostics must never break the auth flow */ }
};
```
- `window_should_close` defaults `false`, overridden `true` only in the success+opener branch, right before `window.close()`.
- Target is not `postMessage` — it is an HTTP POST beacon to the backend (`CALLBACK_DIAGNOSTICS_URL` = `/v1/mcp-auth/oauth2/callback-diagnostics`), handled unauthenticated by `oauth2_callback_diagnostics_enabled`, which only logs (WARNING on error/no-opener/postMessage-error, else INFO) and returns 204.
- Explicit rationale in `_diagnostics.py:44-47`: "The bridge page (which closes itself) reports whether it could notify the opener window, so the otherwise-unobservable client step lands in the backend logs." — this beacon is the *existing* mitigation for the exact pain point this task addresses client-side.
- Ordering relative to `window.close()`: `sendDiagnostics(...)` fires strictly before `window.close()`, and independently (fire-and-forget `sendBeacon`). Gating/removing `window.close()` does not change beacon or `postMessage` timing or content, except that `window_should_close` should be set to reflect the new gated behavior (e.g. `!CALLBACK_KEEP_TAB_OPEN`) to keep the beacon truthful.

**Constants relevant to this change** (`_constants.py`, consumed in `_callback_pages.py`):
- `_CALLBACK_FALLBACK_DELAY_MS = 300` — injected as unquoted numeric JS const.
- `_CALLBACK_EVENT_TYPE = "mcp_auth_callback"`, `_CALLBACK_SUCCESS_CLOSE_MESSAGE`, `_CALLBACK_SUCCESS_OPEN_CODEMIE_MESSAGE` — injected as quoted JS string consts.
- `_CALLBACK_SECURITY_HEADERS` / `_CALLBACK_CONTENT_SECURITY_POLICY` (see Risk Indicators — CSP).
- `_OAUTH2_CALLBACK_DIAGNOSTICS_PATH` — injected as `CALLBACK_DIAGNOSTICS_URL`.

### Architecture and Layers Affected

- **Config layer** (`src/codemie/configs/config.py`) — add a new `MCP_AUTH_*` boolean flag to the existing cluster (lines 414-463).
- **Constants layer** (`_constants.py`) — optionally add a new JS-const-name constant if following the existing string-constant convention (not strictly required; the flag can be interpolated directly).
- **JS-generation/templating layer** (`_callback_pages.py::build_oauth2_callback_page_script_response`) — the entire client script is one Python triple-quoted f-string with `{{`/`}}` used for literal JS braces; config/constants are interpolated as top-of-script `const` declarations. This is where the new gate must be read (`config.<NEW_FLAG>`) and injected, and where the `window.close()` call and `window_should_close` value must be conditioned.
- **API/router layer** (`router.py`) — no route changes expected; it only delegates to the builder function.
- **Diagnostics/telemetry layer** (`_diagnostics.py`) — schema (`window_should_close: bool = False`) unaffected in shape; only the value produced by the client changes.

### Integration Points

- `config` is already imported into `_callback_pages.py` and `dependencies.py` as `from codemie.configs import config` — no new import required.
- No other module currently reads settings inside `_callback_pages.py`/`_oauth2_callback.py` — this will be the first settings-driven branch in that file.
- `MCP_AUTH_*` flags elsewhere are consumed in `_guards.py`, `dependencies.py`, `_discovery.py`, and `src/codemie/clients/postgres.py` (enterprise TMS/alembic gating) — none of these touch the bridge-page close behavior; the new flag is independent of the enable/disable-router gating (`MCP_AUTH_ENABLED`).
- CSP (`connect-src 'self'`) already permits the existing `sendBeacon` call; no CSP change is needed since no new inline script/external endpoint is introduced.

### Patterns and Conventions

- JS is built as a single Python f-string, no template engine; string constants wrapped in `'...'`, numbers interpolated raw. **A Python `bool` interpolated directly would render as `True`/`False`, invalid JS** — must be lowered to `'true'`/`'false'` (lowercase string) when injecting a boolean config value into the script.
- Double-brace escaping (`{{`/`}}`) must be preserved for any new JS block.
- Config fields: plain `NAME: bool = False` with a one-line `#` comment above (no `Field(description=...)`) is the convention for the entire `MCP_AUTH_*` cluster; no `env=`/alias mapping — env var name matches the field name exactly (pydantic-settings default, case-insensitive).
- Feature-toggle booleans (`MCP_AUTH_ENABLED`, `MCP_AUTH_TMS_ENABLED`) default `False`; safety-positive booleans (`MCP_AUTH_ENFORCE_HTTPS`) default `True`. The requested flag (diagnostic aid, default off to preserve current UX) fits the `False`-default convention exactly, e.g.:
  ```python
  # Keeps the OAuth2 callback tab open instead of closing it via window.close(), to allow log capture/analysis.
  MCP_AUTH_KEEP_CALLBACK_TAB_OPEN: bool = False
  ```
  placed adjacent to the existing `MCP_AUTH_*` fields (after line 463).
- Enabled/disabled dual-router pattern is a sibling convention (not directly relevant to this flag, since it gates the whole package, not one behavior).

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/integration/mcp-integration.md` — exists; only states MCP auth logic must stay behind existing MCP config/auth routers/services. No mention of the callback bridge page, `window.close()`, or diagnostics.
- `.ai-run/guides/integration/mcp-auth-log-diagnostics.md` — **exists but untracked** (new, uncommitted). This is the incident runbook motivating the task: frames the OAuth2 flow as two "wires" — Wire 1 (storage, TMS credential persistence) and Wire 2 (notify, `postMessage` to opener) — and states "the hang = Wire 2 failed." Documents the beacon fields including `window_should_close` and the golden-path invariant (`result=success, opener_present=True, post_message_attempted=True, post_message_error=None`). Notes that in production (`LOG_LEVEL=WARNING`) a success-shaped beacon log is invisible (INFO level), which compounds the diagnosis gap this feature addresses. Quotes the CSP verbatim.

### Architectural Decisions

- No formal ADRs found. The diagnostics beacon itself (added in a prior task, commit `481cbc17f`, "EPMCDME-13237: Add MCP OAuth2 auth-callback diagnostics instrumentation") is the direct predecessor of this task — it was the first attempt to make the "tab closes before you can inspect it" problem observable, via server-side logging instead of client-side tab persistence. Prior task artifacts exist at `docs/superpowers/tasks/2026-06-29-mcp-auth-diagnostics/`.
- A draft implementation plan for this exact ticket already exists at `docs/superpowers/plans/2026-07-08-mcp-auth-keep-tab-open.md` (dated today), proposing a flag named `MCP_AUTH_CALLBACK_KEEP_TAB_OPEN` and the same gating approach described above. This is background information only — it was not authored or verified by this research pass and should not be treated as authoritative; downstream planning should independently validate its assumptions against the findings in this document.

### Derived Conventions

See "Patterns and Conventions" above (config field style, f-string JS templating, boolean-lowering requirement).

---

## 4. Testing Landscape

### Existing Coverage

- `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py` — 1046 lines, ~40 test functions. Directly relevant ones:
  - `test_enabled_callback_script_route_returns_first_party_javascript` — asserts script contains `window.opener.postMessage`, event type, success/error status strings, and both close/redirect message strings.
  - `test_enabled_callback_adds_security_headers_on_success_and_failure` — asserts exact CSP header string and `X-Frame-Options: DENY`.
  - `test_callback_csp_allows_same_origin_connect_for_beacon` — imports `_CALLBACK_CONTENT_SECURITY_POLICY` directly and asserts `connect-src 'self'` is present.
  - `test_callback_script_includes_diagnostics_beacon` — asserts `navigator.sendBeacon`, diagnostics path, `post_message_error`, `sendDiagnostics(` call count ≥ 4, `catch` present.
  - `test_callback_diagnostics_logs_and_returns_204` / `test_callback_diagnostics_warns_on_lost_opener_and_returns_204` — post diagnostics payload (including `window_should_close`) and assert on logged fields, but never assert on `window_should_close`'s own logged value.
- `tests/enterprise/mcp_auth/test_feature_gating.py` — canonical pattern for `MCP_AUTH_ENABLED` default/env/gating assertions.
- `tests/enterprise/mcp_auth/test_discovery_probe_bridge.py` — `Config.model_fields["MCP_AUTH_DISCOVERY_CONCURRENCY_LIMIT"].default` assertion pattern for a new numeric/boolean flag's default.
- `tests/enterprise/mcp_auth/test_tms_bridge.py`, `test_trust_policy_bridge.py`, `test_private_network_allowlist_bridge.py` — sibling MCP_AUTH_* flag test patterns.

### Testing Framework and Patterns

- pytest, bare test functions + `@pytest.mark.parametrize`, `monkeypatch`, `caplog`.
- `fastapi.testclient.TestClient` with router built fresh per test via `_build_enabled_client()` / `_build_disabled_client()` helpers (importing `enabled_router` / `router` from `codemie.enterprise.mcp_auth.router`).
- **Config override pattern used in this file** — direct attribute patching on the imported config object, not env vars:
  ```python
  monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "https://codemie.example.com")
  monkeypatch.setattr(mcp_auth_dependencies.config, "FRONTEND_URL", "https://frontend.example.com/app")
  ```
  (`test_oauth2_callback_bridge.py:117-118`, reused at 396, 678-679, 805-806)
- **Alternate pattern used in `test_feature_gating.py`** — `monkeypatch.setenv("MCP_AUTH_ENABLED", "true")` for env-driven `Config()` re-instantiation, and `Config.model_fields["MCP_AUTH_ENABLED"].default is False` for default-value assertions.
- `_assert_has_callback_script(text)` helper used across many tests to check the script tag is present.

### Coverage Gaps

- **No test asserts `window.close()` is called vs. skipped** — none of the ~40 existing tests inspect for the literal `window.close()` call or any conditional presence in the generated script.
- **No test exists for a config-gated JS behavior switch** — every existing JS-content assertion checks fixed/unconditional strings, never a flag-dependent variant.
- **No test exercises `window_should_close` as a controllable/branching value** — only checked as an input field in the diagnostics POST body, never asserted as an output of the gated close logic.
- **No default-value test exists yet** for a hypothetical new `MCP_AUTH_*` flag (would follow the `test_feature_gating.py:43` / `test_discovery_probe_bridge.py:31` pattern: `Config.model_fields["<NEW_FLAG>"].default is False`).

---

## 5. Configuration and Environment

### Environment Variables

- `MCP_AUTH_ENABLED`, `MCP_AUTH_TMS_ENABLED`, `MCP_AUTH_ENFORCE_HTTPS`, and ~15 other `MCP_AUTH_*` vars are declared plainly at `src/codemie/configs/config.py:414-463`, no explicit alias — env var name equals field name (case-insensitive, pydantic-settings default). A new flag (e.g. `MCP_AUTH_KEEP_CALLBACK_TAB_OPEN` / `MCP_AUTH_CALLBACK_KEEP_TAB_OPEN`) would follow the same convention.

### Configuration Files

- `src/codemie/configs/config.py` — `Config(BaseSettings)`, `model_config = SettingsConfigDict(env_file=find_dotenv(".env", raise_error_if_not_found=False), extra="ignore")` (line 747). No `env_prefix`. Module singleton `config = Config()` at line 917.
- No `.env.example` file exists anywhere in the repo. No `MCP_AUTH_*` references found in `config/` or `deploy-templates/` (checked `values.yaml`, `templates/deployment.yaml`, `README.md`). Documentation for these flags exists only as inline `#` comments above each field in `config.py`.

### Feature Flags and Deployment Concerns

- No deployment-manifest changes are implied — `MCP_AUTH_*` flags are not currently surfaced in Helm values or deploy templates, consistent with the existing undocumented-at-deploy-level pattern for this cluster.
- Default-off requirement (stated in task_context) aligns exactly with the codebase's existing convention of defaulting risky/diagnostic toggles to `False`.

---

## 6. Risk Indicators

- No existing test coverage for `window.close()` presence/absence or for any config-gated JS branch in `_callback_pages.py` — new tests must be authored from scratch following the `test_oauth2_callback_bridge.py` `monkeypatch.setattr(mcp_auth_dependencies.config, ...)` pattern, plus a default-value test following `test_feature_gating.py`'s `Config.model_fields[...].default` pattern.
- `window_should_close` is a documented diagnostics-beacon contract field consumed by the incident runbook (`.ai-run/guides/integration/mcp-auth-log-diagnostics.md`) — if the new flag is implemented, `window_should_close` must be updated to reflect actual close behavior (e.g. `!<flag>`), or the beacon becomes misleading for future incident diagnosis (the very tool this change is meant to support).
- Python-to-JS boolean interpolation pitfall: the f-string templating layer interpolates Python values into JS with no serialization step (string constants are manually quoted, numbers are raw) — injecting a Python `bool` naively would emit invalid JS (`True`/`False` instead of `true`/`false`); this must be handled explicitly in the builder function.
- No `.env.example` or deployment-manifest documentation exists for any `MCP_AUTH_*` flag — the new flag will be discoverable only via the `config.py` inline comment, consistent with existing (weak) documentation posture for this cluster, not a regression.
- A draft plan for this exact task already exists at `docs/superpowers/plans/2026-07-08-mcp-auth-keep-tab-open.md`, proposing a specific flag name and gating shape — this research did not validate that plan's content against source; downstream planning should treat it as an unverified prior artifact, not ground truth.
- CSP (`default-src 'none'; script-src 'self'; connect-src 'self'`, `X-Frame-Options: DENY`) requires no change for this feature — confirmed no new inline script or new endpoint is introduced by keeping the tab open; flagged here only to close out the security-header risk explicitly requested.
- Filesystem-fallback research path used (codegraph MCP tool not available to this agent) — findings are based on direct file reads of the four named files plus targeted greps; confidence is high given the narrow, well-defined scope, but a fresh reindex/codegraph pass was not available to cross-check call graphs.

---

## 7. Summary for Complexity Assessment

This task touches three architectural layers with a small, well-bounded file-change surface: the **config layer** (`src/codemie/configs/config.py`, one new boolean field following an established ~20-field sibling pattern), the **JS-generation/templating layer** (`src/codemie/enterprise/mcp_auth/_callback_pages.py`, a single conditional wrapped around one existing `window.close()` call plus one field update in the diagnostics payload object, both inside the already-identified `build_oauth2_callback_page_script_response` function), and the **test layer** (`tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`, net-new test cases with no existing pattern to extend for the close-branching behavior specifically, though a directly analogous config-monkeypatch pattern and a default-value-assertion pattern both already exist in this test module and in `test_feature_gating.py`). Estimated surface: 2 production files touched, 1 test file extended, 0 router/API changes, 0 CSP/security-header changes, 0 deployment-manifest changes.

Technical novelty is low: the change follows three well-established codebase conventions almost exactly (boolean config-flag declaration style, f-string-based JS constant injection, dual-router-adjacent feature-flag gating) rather than introducing new patterns. The one genuinely novel wrinkle is that this will be the *first* settings-driven conditional inside `_callback_pages.py` (today the module has zero config-driven branching), and the Python-bool-to-JS-boolean serialization has no existing precedent in this file to copy verbatim — both are small, well-understood risks rather than complexity drivers.

Test coverage posture is mixed: the affected file (`_callback_pages.py`) is thoroughly tested for its existing behaviors (~40 tests covering success/error rendering, security headers, diagnostics beacon, CSP), but there is zero existing coverage for the specific behavior this task modifies (conditional `window.close()`) and zero precedent for asserting on a config-gated JS-content variant, meaning new test scaffolding — not just new assertions — is required. Key risk factors for complexity scoring: (1) the beacon-contract consistency requirement (`window_should_close` must stay truthful under the new flag) is a correctness risk more than an effort risk; (2) the missing boolean-lowering precedent is a one-line fix but must not be overlooked; (3) the pre-existing draft plan document should be independently re-derived rather than trusted, to avoid propagating unverified assumptions.
