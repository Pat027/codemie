# Spec: Codemie Traffic Tagging Headers (non-LiteLLM path)

**Ticket:** EPMCDME-12602
**Branch:** EPMCDME-12602_codemie-traffic-tagging

---

## Goal

Inject `X-CodeMie-Version` and `X-CodeMie-Project` HTTP headers into every outbound LLM request on the non-LiteLLM (internal) routing path. This enables cost control and troubleshooting for clients using custom AI gateways (DIAL, Kong, or any OpenAI-compatible endpoint) without LiteLLM.

---

## Scope

### In scope

- Inject `X-CodeMie-Version` and `X-CodeMie-Project` on the three HTTP-header-capable providers in `get_llm_by_credentials_raw()` and its sub-factories:
  - Azure/DIAL (OpenAI-compatible) — `AzureChatOpenAI(default_headers=...)`
  - Google Vertex AI — `ChatVertexAI(client_options={"additional_headers": ...})`
  - Anthropic direct — `ChatAnthropic(model_kwargs={"extra_headers": ...})`
- Two new header-name constants in `src/codemie/core/constants.py`.
- One private helper `_build_codemie_tagging_headers()` in `src/codemie/core/dependecies.py`.
- Tests for the Azure, Vertex AI, and Anthropic injection paths.
- LiteLLM regression assertion (existing test file).

### Out of scope

- AWS Bedrock — `additional_model_request_fields` maps to the request body, not HTTP headers. Bedrock injection requires a custom boto3 event hook and is deferred.
- LiteLLM / proxy-router path — already has `x-litellm-tags`; this story does not touch it.
- STT client (`get_stt_openai_client`) and image generator — not mentioned in the ticket.
- User-identifying headers — explicitly excluded by PO.

---

## Design

### Constants

Two new constants added to the `# HTTP Header names` block in `src/codemie/core/constants.py`:

```python
HEADER_CODEMIE_VERSION = "X-CodeMie-Version"
HEADER_CODEMIE_TAGGING_PROJECT = "X-CodeMie-Project"
```

`HEADER_CODEMIE_TAGGING_PROJECT` is a distinct constant from the existing `HEADER_CODEMIE_CLI_PROJECT` (`"X-CodeMie-Project"`) — same string value, different names to make inbound vs. outbound usage explicit.

### Helper function

New private function in `src/codemie/core/dependecies.py`:

```python
def _build_codemie_tagging_headers() -> dict[str, str]:
    headers = {HEADER_CODEMIE_VERSION: config.APP_VERSION}
    project = get_current_project()
    if project:
        headers[HEADER_CODEMIE_TAGGING_PROJECT] = project
    return headers
```

- `X-CodeMie-Version` is always emitted (value: `config.APP_VERSION`).
- `X-CodeMie-Project` is emitted only when `get_current_project()` returns a non-empty string. When no project context is set (background tasks, startup), the header is skipped.

### Merge order and precedence

In each applicable provider factory, the header merge becomes:

```python
merged_headers = _build_codemie_tagging_headers()          # Codemie tags first
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)  # model config overwrites
```

**Precedence rule:** Model YAML `client_headers` take precedence over Codemie tagging headers. If a model explicitly configures `X-CodeMie-Version`, that value is used; Codemie's default is silently overridden. This satisfies the ticket requirement to "preserve existing configured headers."

### Injection sites

| Provider | Factory function | Header argument |
|---|---|---|
| Azure/DIAL | `get_llm_by_credentials_raw()` | `AzureChatOpenAI(default_headers=merged_headers)` |
| Vertex AI | `get_vertex_llm()` | `ChatVertexAI(client_options={"additional_headers": merged_headers})` |
| Anthropic direct | `get_anthropic_llm()` | `ChatAnthropic(model_kwargs={"extra_headers": merged_headers})` |
| AWS Bedrock | `get_bedrock_llm()` | **Not changed** — body field, not HTTP headers |

`format_headers_for_openai_api()` is called after the merge (unchanged). It only transforms `anthropic_beta` and is unaffected by the new plain-string headers.

For `get_anthropic_llm()`, the current code passes `extra_headers=merged_headers if merged_headers else None`. After the change, `merged_headers` always contains at least `X-CodeMie-Version`, so the conditional guard is always true and should be simplified to `extra_headers=merged_headers`.

---

## Testing

### New test file: `tests/codemie/core/test_dependencies_tagging_headers.py`

All tests use `unittest.mock.patch` and the `mock_database_engine` autouse fixture from `tests/conftest.py`.

| # | Test name | What it verifies |
|---|---|---|
| 1 | `test_azure_path_injects_both_tags` | `AzureChatOpenAI` receives `default_headers` with both `X-CodeMie-Version` and `X-CodeMie-Project` when project is set |
| 2 | `test_azure_path_skips_project_when_empty` | `default_headers` contains only `X-CodeMie-Version` when `get_current_project()` returns `""` |
| 3 | `test_azure_path_client_headers_win_collision` | Model config `client_headers` with `X-CodeMie-Version: override` results in `default_headers["X-CodeMie-Version"] == "override"` |
| 4 | `test_vertex_path_injects_tags` | `ChatVertexAI` receives `client_options["additional_headers"]` containing both tags |
| 5 | `test_anthropic_path_injects_tags` | `ChatAnthropic` receives `model_kwargs["extra_headers"]` containing both tags |

### Regression assertion (existing file)

`tests/enterprise/litellm/test_llm_factory.py` — `TestCreateLiteLLMChatModel`: add one assertion that the LiteLLM path's `default_headers` still contains `x-litellm-tags` and does **not** contain `X-CodeMie-Version` or `X-CodeMie-Project`.

---

## Files changed

| File | Change |
|---|---|
| `src/codemie/core/constants.py` | Add `HEADER_CODEMIE_VERSION`, `HEADER_CODEMIE_TAGGING_PROJECT` |
| `src/codemie/core/dependecies.py` | Add `_build_codemie_tagging_headers()`; update merge logic in `get_llm_by_credentials_raw`, `get_vertex_llm`, `get_anthropic_llm` |
| `tests/codemie/core/test_dependencies_tagging_headers.py` | New — 5 test cases |
| `tests/enterprise/litellm/test_llm_factory.py` | Add LiteLLM regression assertion |

---

## Decisions and rationale

| Decision | Choice | Rationale |
|---|---|---|
| Header casing | `X-CodeMie-*` (capital M) | Matches all existing inbound header constants; consistent across the codebase |
| Precedence | Model config wins | Ticket requirement: "existing configured headers must be preserved" |
| Empty project | Skip header | No project context → no header emitted; avoids confusing sentinel values at gateways |
| Bedrock | Excluded | `additional_model_request_fields` is a request body field; HTTP header injection requires a boto3 event hook (deferred) |
| Helper location | Private fn in `dependecies.py` | No new module needed; all injection logic stays in the file that owns the factories |
