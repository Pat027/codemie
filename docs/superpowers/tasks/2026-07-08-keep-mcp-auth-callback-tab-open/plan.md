# EPMCDME-11515 — Keep MCP Auth Callback Tab Open (Diagnostic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task, inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a config-gated switch (`MCP_AUTH_CALLBACK_KEEP_TAB_OPEN`, default off) so the OAuth2 callback bridge tab stays open after a successful auth instead of calling `window.close()`, preserving its console/URL for incident analysis.

**Architecture:** The bridge JS served by `GET /v1/mcp-auth/oauth2/callback-page.js` is one Python f-string in `build_oauth2_callback_page_script_response` (`_callback_pages.py`). Injected consts are string-quoted or raw-numeric. We add a boolean-lowered const `CALLBACK_KEEP_TAB_OPEN` derived from the new config flag, gate the success-branch `window.close()` behind it, and make the diagnostics beacon's `window_should_close` reflect the gated state (`!CALLBACK_KEEP_TAB_OPEN`) so the beacon stays truthful.

**Tech Stack:** FastAPI, pydantic-settings `Config(BaseSettings)`, f-string-templated JS, pytest + `fastapi.testclient.TestClient`, `monkeypatch`.

## Global Constraints

- Default behavior unchanged: `MCP_AUTH_CALLBACK_KEEP_TAB_OPEN` defaults to `False` → tab still auto-closes on success. Opt-in only. (Matches the `False`-default convention of the `MCP_AUTH_*` diagnostic/feature toggles.)
- Python `bool` MUST be lowered to JS `true`/`false` when injected (naive interpolation yields invalid `True`/`False`).
- `postMessage` and `sendDiagnostics` behavior/timing/content unchanged; only `window.close()` (and the `window_should_close` field value) are gated.
- Beacon must stay truthful: `window_should_close` = `!CALLBACK_KEEP_TAB_OPEN` on the success+opener branch.
- Error branch (`_callback_pages.py:255-277`) untouched — it already never closes.
- No CSP / security-header change. No router change. No deployment-manifest change.
- Reuse existing copy `_CALLBACK_SUCCESS_CLOSE_MESSAGE` ("Authentication successful! You can close this tab.") when the tab stays open. No new strings.
- Commit format: `EPMCDME-11515: <Capital description>`.

---

### Task 1: Add the `MCP_AUTH_CALLBACK_KEEP_TAB_OPEN` config flag

**Files:**
- Modify: `src/codemie/configs/config.py` (in the `MCP_AUTH_*` cluster, after line 463)
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Interfaces:**
- Produces: `config.MCP_AUTH_CALLBACK_KEEP_TAB_OPEN: bool` (default `False`).

**Test-first: yes** — assert the field's default is `False` via `Config.model_fields[...].default`, which fails before the field exists.

- [ ] **Step 1: Write the failing default-value test**

Add to `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`:

```python
def test_keep_callback_tab_open_flag_defaults_to_false() -> None:
    from codemie.configs.config import Config

    assert Config.model_fields["MCP_AUTH_CALLBACK_KEEP_TAB_OPEN"].default is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `poetry run pytest "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_keep_callback_tab_open_flag_defaults_to_false" -v`
Expected: FAIL with `KeyError: 'MCP_AUTH_CALLBACK_KEEP_TAB_OPEN'`.

- [ ] **Step 3: Add the config field**

In `src/codemie/configs/config.py`, immediately after the last `MCP_AUTH_*` field (line 463, `MCP_AUTH_RESOURCE_METADATA_DISCOVERY_TIMEOUT_SECONDS`):

```python
    # Diagnostic: keep the OAuth2 callback tab open after successful auth instead of
    # calling window.close(), so its console/URL can be inspected. Default False
    # preserves the auto-close UX.
    MCP_AUTH_CALLBACK_KEEP_TAB_OPEN: bool = False
```

- [ ] **Step 4: Run it to verify it passes**

Run: `poetry run pytest "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_keep_callback_tab_open_flag_defaults_to_false" -v`
Expected: PASS.

---

### Task 2: Gate `window.close()` behind the flag in the bridge script

**Files:**
- Modify: `src/codemie/enterprise/mcp_auth/_callback_pages.py:177-280` (`build_oauth2_callback_page_script_response`)
- Test: `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`

**Interfaces:**
- Consumes: `config.MCP_AUTH_CALLBACK_KEEP_TAB_OPEN`, `_CALLBACK_SUCCESS_CLOSE_MESSAGE`, `_CALLBACK_FALLBACK_DELAY_MS`.
- Produces: injected JS const `CALLBACK_KEEP_TAB_OPEN` (`true`/`false`); success+opener branch closes the tab only when it is `false`; `window_should_close` = `!CALLBACK_KEEP_TAB_OPEN`.

**Test-first: yes** — assert default script still contains `window.close();` and `const CALLBACK_KEEP_TAB_OPEN = false;`, and that with the flag monkeypatched `True` the script contains `const CALLBACK_KEEP_TAB_OPEN = true;` and gates close behind `if (!CALLBACK_KEEP_TAB_OPEN)` while still calling `window.opener.postMessage`. These fail before the const/gate exist.

- [ ] **Step 1: Write the failing tests**

Add to `tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`:

```python
def test_callback_script_closes_tab_by_default() -> None:
    client = _build_enabled_client()

    script = client.get("/v1/mcp-auth/oauth2/callback-page.js").text

    assert "const CALLBACK_KEEP_TAB_OPEN = false;" in script
    assert "window.close();" in script
    assert "if (!CALLBACK_KEEP_TAB_OPEN)" in script


def test_callback_script_keeps_tab_open_when_flag_enabled(monkeypatch) -> None:
    from codemie.enterprise.mcp_auth import _callback_pages

    monkeypatch.setattr(_callback_pages.config, "MCP_AUTH_CALLBACK_KEEP_TAB_OPEN", True)
    client = _build_enabled_client()

    script = client.get("/v1/mcp-auth/oauth2/callback-page.js").text

    assert "const CALLBACK_KEEP_TAB_OPEN = true;" in script
    # close is gated, not unconditional
    assert "if (!CALLBACK_KEEP_TAB_OPEN)" in script
    # success path still notifies the opener before deciding whether to close
    assert "window.opener.postMessage" in script
    # beacon stays truthful about the gated close
    assert "window_should_close: !CALLBACK_KEEP_TAB_OPEN," in script
```

- [ ] **Step 2: Run them to verify they fail**

Run: `poetry run pytest "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_callback_script_closes_tab_by_default" "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_callback_script_keeps_tab_open_when_flag_enabled" -v`
Expected: FAIL (`const CALLBACK_KEEP_TAB_OPEN` and `if (!CALLBACK_KEEP_TAB_OPEN)` not found).

- [ ] **Step 3: Inject the boolean-lowered const**

In `src/codemie/enterprise/mcp_auth/_callback_pages.py`, add to the JS header const block, right after the `CALLBACK_DIAGNOSTICS_URL` line (currently line 183):

```python
const CALLBACK_KEEP_TAB_OPEN = {str(config.MCP_AUTH_CALLBACK_KEEP_TAB_OPEN).lower()};
```

- [ ] **Step 4: Gate the close block**

In the same function, replace the success-branch close block (current lines 241-251):

```python
      sendDiagnostics({{
        post_message_attempted: postMessageAttempted,
        post_message_error: postMessageError,
        window_should_close: true,
      }});
      window.close();
      window.setTimeout(() => {{
        if (!window.closed) {{
          updateMessage(CALLBACK_SUCCESS_CLOSE_MESSAGE);
        }}
      }}, CALLBACK_FALLBACK_DELAY_MS);
```

with:

```python
      sendDiagnostics({{
        post_message_attempted: postMessageAttempted,
        post_message_error: postMessageError,
        window_should_close: !CALLBACK_KEEP_TAB_OPEN,
      }});
      if (!CALLBACK_KEEP_TAB_OPEN) {{
        window.close();
        window.setTimeout(() => {{
          if (!window.closed) {{
            updateMessage(CALLBACK_SUCCESS_CLOSE_MESSAGE);
          }}
        }}, CALLBACK_FALLBACK_DELAY_MS);
      }} else {{
        updateMessage(CALLBACK_SUCCESS_CLOSE_MESSAGE);
      }}
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `poetry run pytest "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_callback_script_closes_tab_by_default" "tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py::test_callback_script_keeps_tab_open_when_flag_enabled" -v`
Expected: PASS.

- [ ] **Step 6: Run the full bridge module + feature-gating for regressions**

Run: `poetry run pytest tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py tests/enterprise/mcp_auth/test_feature_gating.py -v`
Expected: all PASS. In particular `test_callback_script_includes_diagnostics_beacon` (`sendDiagnostics(` count ≥ 4) and `test_enabled_callback_script_route_returns_first_party_javascript` still hold (default renders `window.close();` and both message strings).

- [ ] **Step 7: Lint the changed files**

Run: `poetry run ruff check src/codemie/configs/config.py src/codemie/enterprise/mcp_auth/_callback_pages.py tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py`
Expected: no errors.

- [ ] **Step 8: Commit Task 1 + Task 2**

```bash
git add src/codemie/configs/config.py src/codemie/enterprise/mcp_auth/_callback_pages.py tests/enterprise/mcp_auth/test_oauth2_callback_bridge.py
git commit -m "EPMCDME-11515: Add config flag to keep MCP auth callback tab open for diagnostics"
```

---

## Self-Review

- **Spec coverage:** config-gated (Task 1), default preserves close (default `False`), tab kept open reuses close-hint message (Task 2 Step 4), beacon truthful (`window_should_close: !CALLBACK_KEEP_TAB_OPEN`), error branch untouched, boolean-lowering handled (`str(...).lower()`). ✔
- **Placeholder scan:** none — ticket is the real `EPMCDME-11515`. ✔
- **Type consistency:** `MCP_AUTH_CALLBACK_KEEP_TAB_OPEN` (bool) referenced identically in config field, script injection, and both tests; JS const name `CALLBACK_KEEP_TAB_OPEN` consistent across script and assertions. ✔
