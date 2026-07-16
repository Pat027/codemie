# Technical Research

**Task**: llm http headers traffic tagging custom gateway openai
**Generated**: 2026-07-14T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

Implement Codemie traffic tagging headers (X-Codemie-Version and X-Codemie-Project) for non-LiteLLM/custom AI gateway integrations. CodeMie should inject these headers on outbound LLM requests where the selected provider path supports custom headers. Existing model/client configured headers must be preserved. If a client explicitly configures the same header, define deterministic precedence and document it. Do not add user-identifying headers. Add tests for the direct gateway/OpenAI-compatible path and verify no regression for existing LiteLLM/header configuration.

Full ticket description: Clients who use custom AI GW (it can be DIAL, Kong, etc.) will benefit from custom headers injected into all requests from Codemie to LLM endpoints. X-Codemie-Version and X-Codemie-Project could be good starting headers to support troubleshooting and cost control. PO clarification: This story targets automatic CodeMie traffic-tagging headers for non-LiteLLM/custom AI gateway integrations, for example DIAL, Kong, or client-hosted gateways. CodeMie should inject X-Codemie-Version and X-Codemie-Project on outbound LLM requests where the selected provider path supports custom headers. Existing model/client configured headers must be preserved; if a client explicitly configures the same header, define deterministic precedence and document it. Do not add user-identifying headers as part of this story. Add tests for the direct gateway/OpenAI-compatible path and verify no regression for existing LiteLLM/header configuration.

---

## 2. Codebase Findings

### Existing Implementations

**Central LLM client factory (non-LiteLLM / internal path) — PRIMARY INJECTION TARGET**
- `src/codemie/core/dependecies.py` — `get_llm_by_credentials()` (line ~244): public entry point; tries LiteLLM first, falls back to `get_llm_by_credentials_raw()`
- `src/codemie/core/dependecies.py` — `get_llm_by_credentials_raw()` (line 339): creates `AzureChatOpenAI` (Azure/DIAL OpenAI-compatible), `ChatVertexAI`/`ChatAnthropicVertex`, `ChatBedrockConverse`, or `ChatAnthropic` depending on provider enum. This is the primary target for `X-Codemie-Version` and `X-Codemie-Project` header injection.
- `src/codemie/core/dependecies.py` — `format_headers_for_openai_api()` (line 332): in-place JSON-encodes the `anthropic_beta` key in `merged_headers` before it is passed to the OpenAI SDK. New X-Codemie-* headers (plain strings) are unaffected by this.
- `src/codemie/core/dependecies.py` — `litellm_context` ContextVar (line 115): carries `LiteLLMContext(credentials, current_project)` for the current request. Accessible inside `get_llm_by_credentials_raw()` (same module).
- `src/codemie/core/dependecies.py` — `get_current_project(fallback)` (line 131): reads `litellm_context` and returns `ctx.current_project`. This is the source for `X-Codemie-Project` value.

**Provider-specific factories within `get_llm_by_credentials_raw`**
- `get_vertex_llm()`: uses `ChatVertexAI(client_options={"additional_headers": merged_headers}, ...)` — HTTP headers supported.
- `get_bedrock_llm()`: uses `ChatBedrockConverse(additional_model_request_fields=merged_headers, ...)` — THIS IS A REQUEST BODY FIELD, NOT AN HTTP HEADER. Traffic tagging headers are NOT applicable on this path without a custom boto3 event hook.
- `get_anthropic_llm()`: uses `ChatAnthropic(model_kwargs={"extra_headers": merged_headers}, ...)` — HTTP headers supported via Anthropic SDK.

**LiteLLM enterprise model factory (existing tagging pattern — reference implementation)**
- `src/codemie/enterprise/litellm/llm_factory.py` — `create_litellm_chat_model()`: sets `base_args['default_headers'] = merged_headers` from `_generate_litellm_headers()`.
- `src/codemie/enterprise/litellm/llm_factory.py` — `_generate_litellm_headers()` (line 761): applies static `client_headers` from model YAML config first, then adds `x-litellm-tags` from context. This is the established pattern for dynamic header injection.
- `src/codemie/enterprise/litellm/llm_factory.py` — `generate_litellm_headers_from_context()` (line 723): public function generating the `x-litellm-tags` header value from the current project context.

**LiteLLM proxy router (HTTP pass-through path)**
- `src/codemie/enterprise/litellm/proxy_router.py` — `_prepare_proxy_headers()` (line 777): builds outbound headers for the LiteLLM HTTP proxy path.
- `src/codemie/enterprise/litellm/proxy_router.py` — `_apply_context_headers()` (line 214): adds `x-litellm-tags` from context. The pattern to follow for any new `_apply_codemie_tagging_headers()` function.

**Model and header configuration**
- `src/codemie/configs/llm_config.py` — `ModelConfigurationSection.client_headers: Optional[dict[str, list[str] | str]]` (line 81): per-model static headers from YAML. Currently empty on all deployed models.
- `src/codemie/configs/config.py` — `Config.APP_VERSION: str = "0.16.0"` (line 50/51): canonical source for `X-Codemie-Version` value at runtime.
- `src/codemie/configs/config.py` — `Config.LLM_PROXY_MODE: Literal["internal", "lite_llm"] = "internal"` (line 583): routes to internal path (default) or LiteLLM proxy.
- `src/codemie/core/constants.py` — existing `HEADER_CODEMIE_CLI_PROJECT = "X-CodeMie-Project"` (line 51): inbound CLI request header, same string value as the target outbound tagging header but different concern. New constants for outbound tagging should be added alongside this block.

**Header merge pattern (current, both paths)**

Internal path (from `dependecies.py`, repeated in all four provider factories):
```python
merged_headers = {}
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
# [INJECTION POINT: add X-Codemie-Version / X-Codemie-Project here]
if merged_headers:
    format_headers_for_openai_api(merged_headers)
    base_args['default_headers'] = merged_headers
```

LiteLLM path (from `llm_factory.py`):
```python
merged_headers = {}
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
context_headers = generate_litellm_headers_from_context(litellm_context)
if context_headers:
    merged_headers.update(context_headers)  # context headers applied AFTER static config
return merged_headers
```

**Additional non-LangChain OpenAI clients (secondary scope)**
- `src/codemie/core/dependecies.py` — `get_stt_openai_client()` (line 514): bare `AzureOpenAI(...)` with no `default_headers`. STT traffic tagging not mentioned in ticket.
- `src/codemie_tools/data_management/file_system/image_generator.py` — `LiteLLMImageGenerator.__init__()` (line 77): bare `AzureOpenAI(...)` with no `default_headers`. Image generation traffic tagging not mentioned in ticket.

### Architecture and Layers Affected

| Layer | Files | Role |
|---|---|---|
| Config / Constants | `src/codemie/configs/config.py`, `src/codemie/core/constants.py` | `APP_VERSION` source; new header name constants |
| Core / LLM Factory | `src/codemie/core/dependecies.py` | Primary injection point for all non-LiteLLM providers |
| Enterprise / LiteLLM Factory | `src/codemie/enterprise/litellm/llm_factory.py` | Regression-check surface; `_generate_litellm_headers()` must not be disturbed |
| Enterprise / Proxy Router | `src/codemie/enterprise/litellm/proxy_router.py` | HTTP proxy path for CLI requests; `_apply_context_headers()` pattern reference |
| Model Config | `src/codemie/configs/llm_config.py` | `client_headers` static override mechanism; defines precedence interaction |

### Integration Points

**Primary gateway paths for header injection:**
- Azure OpenAI / DIAL (OpenAI-compatible): `AzureChatOpenAI(default_headers=...)` in `get_llm_by_credentials_raw()` — all custom gateway (DIAL, Kong, etc.) deployments use this path.
- Google Vertex AI: `ChatVertexAI(client_options={"additional_headers": ...})` in `get_vertex_llm()`.
- Anthropic direct: `ChatAnthropic(model_kwargs={"extra_headers": ...})` in `get_anthropic_llm()`.
- AWS Bedrock: `ChatBedrockConverse(additional_model_request_fields=...)` in `get_bedrock_llm()` — HTTP header injection NOT supported via this mechanism; out of scope unless a custom boto3 wrapper is added.

**Context variable that supplies project identity:**
- `litellm_context` ContextVar in `dependecies.py` — already set per-request by `set_llm_context()` in `src/codemie/service/llm_service/utils.py:59`. Carries `LiteLLMContext.current_project` (str or None).

**Version source:**
- `config.APP_VERSION` from `src/codemie/configs/config.py` — read via the imported `config` singleton already available in `dependecies.py`.

### Patterns and Conventions

- **Header constant naming**: `HEADER_CODEMIE_<SUFFIX>` strings in `src/codemie/core/constants.py`. New outbound traffic tagging constants must follow this naming pattern. Note: existing constants use `"X-CodeMie-*"` (capital `M`); the ticket specifies `"X-Codemie-*"` (lowercase `m`) — this casing discrepancy must be resolved explicitly.
- **Dynamic header injection precedence**: In the LiteLLM path, static `client_headers` are written first (`.update()`), then dynamic context headers overwrite any collision. The same order must be chosen deliberately for the internal path: write Codemie tagging headers first (before `.update(client_headers)`) so that explicit model config can override them, or write them after so Codemie headers win. The ticket requires "define deterministic precedence and document it."
- **Config reads**: Never read env vars directly in feature code; always use `config.<FIELD>` from the pydantic-settings `Config` class. (`MODELS_ENV`, `APP_VERSION`, etc. are already there.)
- **Guard against empty/None project**: `get_current_project()` returns `""` when no context is set. The injection must handle this (skip the header, or emit a `"unknown"` sentinel — must be decided and documented).
- **`format_headers_for_openai_api`** is called after building `merged_headers` and only transforms `anthropic_beta` key. New plain-string headers are unaffected.

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `C:\Projects\codemie-dev\codemie\.ai-run\guides\integration\llm-providers.md` — Covers provider configuration conventions. Key rule: avoid hardcoding model names; config files live under `config/llms/`. Gate LiteLLM path behind `is_litellm_enabled`.
- `C:\Projects\codemie-dev\codemie\.ai-run\guides\architecture\layered-architecture.md` — HTTP concerns in routers; business logic in services; cross-cutting utilities (constants, config) in `core/` and `configs/`. Reading env vars directly in feature code is explicitly prohibited.
- `C:\Projects\codemie-dev\codemie\.ai-run\guides\architecture\project-structure.md` — Two packages: `codemie` and `codemie_tools`. LLM agent logic at `src/codemie/agents/`; provider factory logic in `src/codemie/core/`.
- `C:\Projects\codemie-dev\codemie\.ai-run\guides\architecture\service-layer-patterns.md` — Use existing provider registries and factories; do not duplicate provider-selection rules.
- `C:\Projects\codemie-dev\codemie\.ai-run\guides\development\configuration-patterns.md` — Use `src/codemie/configs/` and pydantic-settings; never read env vars directly in feature code.
- `C:\Projects\codemie-dev\codemie\.ai-run\guides\integration\request-hedging.md` — Not directly relevant. Mentions `{{headers.<name>}}` Jinja2 pattern for inbound header forwarding to hedging tools.

### Architectural Decisions

- **Two-path LLM routing** is a first-class architectural decision: `LLM_PROXY_MODE=internal` (direct SDK calls, default) vs. `LLM_PROXY_MODE=lite_llm` (enterprise LiteLLM proxy). Traffic tagging for the `internal` path is the task's scope. The LiteLLM path already has `x-litellm-tags` injection; the `internal` path has none.
- **Per-model static headers via YAML `client_headers`** — the existing mechanism for custom header injection on the non-LiteLLM path. No deployed model config currently uses this field.
- **`litellm_context` ContextVar** carries the per-request project identity for both LiteLLM tagging and billing. The same mechanism will power `X-Codemie-Project` on the internal path.
- **`FORWARDED_HEADERS_BLOCKLIST`** controls which inbound `X-*` headers are propagated to MCP/DSP tools — separate from the outbound LLM header injection mechanism.

### Derived Conventions

- Header name constants belong in `src/codemie/core/constants.py`.
- The `generate_litellm_headers_from_context()` function in `llm_factory.py` is the canonical pattern for "build a dict of dynamic context-derived headers." A parallel `generate_codemie_tagging_headers()` utility could be created in `dependecies.py` or a new `src/codemie/core/llm_headers.py` module.
- The `_generate_litellm_headers()` function demonstrates the merge pattern: static config headers first, then dynamic headers via `.update()`.
- `format_headers_for_openai_api()` is the post-merge transform step — do not move new headers after this call unless they need the same encoding.

---

## 4. Testing Landscape

### Existing Coverage

**LiteLLM path — well covered:**
- `tests/codemie/service/test_custom_headers_producer.py`: 5 test cases for `generate_litellm_headers_from_context()` covering valid context + project, no project, None context, special characters, context without credentials.
- `tests/enterprise/litellm/test_llm_factory.py` — `TestGenerateLiteLLMHeadersFromContext`: 3 cases (no context, project in allowlist, project not in allowlist). `TestCreateLiteLLMChatModel` covers budget check but does NOT assert on `default_headers` contents.
- `tests/enterprise/litellm/test_client.py`: covers `get_llm_proxy_client()` singleton lifecycle; mocks `httpx.AsyncClient`.
- `tests/enterprise/litellm/test_proxy_router.py`: covers proxy router including `_prepare_proxy_headers`.

**Internal (non-LiteLLM) path — NOT covered:**
- `get_llm_by_credentials_raw()` has **zero test coverage**. No test file exercises this function or asserts on what `default_headers` are passed to `AzureChatOpenAI`.
- `get_vertex_llm()`, `get_bedrock_llm()`, `get_anthropic_llm()` — no dedicated header injection tests.

**Related core tests:**
- `tests/codemie/core/test_core_dependencies.py`, `tests/codemie/core/test_dependecies.py`, `tests/codemie/core/test_dependencies_litellm_context.py` — exist but do not cover `get_llm_by_credentials_raw()`.
- `tests/codemie/configs/test_llm_config.py`, `tests/codemie/configs/test_config.py` — cover config parsing.

### Testing Framework and Patterns

- **Framework**: pytest with `pytest-asyncio` (`^0.23.7`). Config in `pytest.ini`: `testpaths = tests`, `pythonpath = src`, `--import-mode=importlib`.
- **Mocking**: `unittest.mock` exclusively — `patch`, `MagicMock`, `AsyncMock`.
- **LLM constructor capture pattern** (for asserting `default_headers`):
  ```python
  with patch("langchain_openai.AzureChatOpenAI") as mock_azure:
      get_llm_by_credentials_raw("gpt-4")
      call_kwargs = mock_azure.call_args[1]
      assert "X-Codemie-Version" in call_kwargs["default_headers"]
  ```
- **Config override pattern**: `patch.object(config, "APP_VERSION", "1.2.3")` — no env file editing needed.
- **`LLMModel` mock pattern**: `mock_model_details = MagicMock(); mock_model_details.configuration = None`.
- **Global autouse fixture**: `mock_database_engine` (session-scoped, `tests/conftest.py`) patches `PostgresClient.get_engine`. Required when the code under test touches DB sessions.
- `tests/enterprise/litellm/test_litellm_service.py` is entirely `skip`-marked — do not use as a pattern reference.

### Coverage Gaps

1. **Primary gap**: No tests for `get_llm_by_credentials_raw()` — the entire non-LiteLLM path is untested. New tests must be added to verify that `X-Codemie-Version` and `X-Codemie-Project` appear in `AzureChatOpenAI(default_headers=...)`.
2. **Precedence tests**: No test covers the merged-headers behavior when both `client_headers` from model config and traffic-tagging headers are present simultaneously. The deterministic precedence rule needs a dedicated test.
3. **Project empty/None case**: No test verifies behavior when `get_current_project()` returns `""` or `None`.
4. **LiteLLM regression**: `TestCreateLiteLLMChatModel` does not assert on `default_headers` at all — a regression test should verify `x-litellm-tags` is still present and `X-Codemie-*` tags are absent on the LiteLLM path.
5. **Vertex AI and Anthropic header injection**: `get_vertex_llm()` and `get_anthropic_llm()` have no header injection tests.

---

## 5. Configuration and Environment

### Environment Variables

| Variable | Default | Relevance to task |
|---|---|---|
| `APP_VERSION` | `"0.16.0"` | Value for `X-Codemie-Version` header. Overridable at runtime via env var. |
| `LLM_PROXY_MODE` | `"internal"` | Routes to internal path (target) or LiteLLM proxy (existing tagging). |
| `LLM_PROXY_ENABLED` | `False` | When False, LiteLLM returns None; internal path always runs. |
| `MODELS_ENV` | `"dial"` | Selects YAML config; `"dial"` maps to DIAL custom gateway path. |
| `LITE_LLM_PROJECTS_TO_TAGS_LIST` | `""` | Only used in LiteLLM path; not relevant to new headers. |
| `LITE_LLM_TAGS_HEADER_VALUE` | `"default"` | Only used in LiteLLM path; not relevant to new headers. |
| `AZURE_OPENAI_URL` | `""` | Azure/DIAL endpoint URL for the internal path. |

### Configuration Files

- `src/codemie/configs/config.py` — pydantic-settings `Config` class. Source of `APP_VERSION`. Governs `LLM_PROXY_MODE`, `MODELS_ENV`, and all provider credentials.
- `config/llms/llm-dial-config.yaml` — DIAL/custom gateway model registry. Models set `provider: "azure_openai"`. `configuration.client_headers` is empty on all models currently.
- `config/llms/llm-azure-config.yaml` — Azure OpenAI native model registry. Same structure.
- `config/llms/llm-aws-config.yaml`, `config/llms/llm-gcp-config.yaml` — AWS Bedrock and GCP Vertex AI registries.
- `pyproject.toml` — `[tool.poetry] version = "0.8.0"` — this is the Python package version and differs from `config.APP_VERSION`. Do NOT use `importlib.metadata` to read this as the tagging version; use `config.APP_VERSION` exclusively.

### Feature Flags and Deployment Concerns

- **`LLM_PROXY_MODE`** is the gating flag. The task targets `"internal"` (default). No additional feature flag is needed unless the tagging headers are to be opt-in.
- **`APP_VERSION` is not set in the Dockerfile or docker-compose.yml.** The value `"0.16.0"` is hardcoded in `config.py`. For the `X-Codemie-Version` header to reflect the actual deployed version in production, the CI/CD pipeline must inject `APP_VERSION` as a runtime env var (Helm chart, Kubernetes deployment manifest, or compose override). Without this, all deployments report the same hardcoded version regardless of release.
- **`current_project` can be empty.** `get_current_project()` returns `""` when `litellm_context` is not set. The header injection must handle the empty/None case.
- **Bedrock is out of scope for HTTP header injection.** `additional_model_request_fields` maps to AWS `additionalModelRequestFields` in the request body, not HTTP transport headers. Injecting HTTP headers on Bedrock would require a custom `botocore` event hook — a non-trivial change outside this story's scope.

---

## 6. Risk Indicators

- **`get_llm_by_credentials_raw()` has zero test coverage.** The primary injection target is entirely untested. Any regression in this function is undetectable without new tests.
- **Header casing inconsistency.** Existing constants use `"X-CodeMie-*"` (capital `M`). The ticket specifies `"X-Codemie-*"` (lowercase `m`). These are different HTTP header strings. The implementation must decide canonical casing and add matching constants; mismatched casing in tests vs. source code is a silent correctness bug.
- **Deterministic precedence is unspecified.** The ticket requires it but does not define it. In the existing LiteLLM factory, static `client_headers` are applied first, then context headers overwrite collisions. If the internal path follows the same pattern, client model config would take precedence over Codemie tagging headers. If reversed, Codemie headers are authoritative. This decision must be made before implementation.
- **`APP_VERSION` is hardcoded to `"0.16.0"` and not injected by Docker/CI.** The `X-Codemie-Version` header will carry a stale value in any deployment that does not explicitly set the `APP_VERSION` env var at container startup.
- **`current_project` may be empty or None.** If no `litellm_context` is set (e.g., background tasks, startup-time LLM calls), `get_current_project()` returns `""`. The header injection must not emit an empty or malformed header value.
- **Bedrock does not support HTTP header injection via the current pattern.** `additional_model_request_fields` is a request body parameter. Any attempt to inject `X-Codemie-*` headers on Bedrock via the existing mechanism would silently pass invalid fields to the AWS API. Bedrock should be explicitly excluded from scope.
- **`format_headers_for_openai_api()` is duplicated** between `dependecies.py` (line 332) and `llm_factory.py` (line 794). The internal path copy must be updated if header encoding logic changes.
- **`LiteLLMImageGenerator` and `get_stt_openai_client`** use bare `AzureOpenAI()` with no `default_headers` support. These are not covered by the ticket but are gap surfaces for future header injection.
- **`TestCreateLiteLLMChatModel` does not assert on `default_headers`.** There is no existing regression protection for the LiteLLM header injection path. If a change accidentally removes header injection from the LiteLLM factory, no test will catch it.
- **No codegraph indexing available.** All research was done via filesystem tools. Cross-module call chains not visible in direct Grep/Read searches may have been missed.

---

## 7. Summary for Complexity Assessment

The task requires injecting two new outbound HTTP headers (`X-Codemie-Version` and `X-Codemie-Project`) into requests from Codemie to LLM provider endpoints on the non-LiteLLM (internal) routing path. The implementation touches three architectural layers: Config/Constants (adding two new header-name string constants to `src/codemie/core/constants.py`), the Core LLM Factory (`src/codemie/core/dependecies.py`, specifically `get_llm_by_credentials_raw()` and up to three provider-specific sub-factories for Vertex AI, Anthropic, and Azure/DIAL), and the Enterprise LiteLLM Factory (`src/codemie/enterprise/litellm/llm_factory.py`) as a regression-check surface. The estimated file change surface is 3–5 source files plus 2–3 test files. The LiteLLM proxy router (`proxy_router.py`) may optionally receive a parallel `_apply_codemie_tagging_headers()` function, adding one more file.

The task follows an established pattern: the LiteLLM path already injects `x-litellm-tags` via `_generate_litellm_headers()` and the `litellm_context` ContextVar. The same context variable (`current_project`) and the existing `config.APP_VERSION` field provide the two header values. The implementation will replicate the same merge-and-update pattern inside `get_llm_by_credentials_raw()` and its provider-specific callees. The only novel decision is formalizing header precedence (Codemie tagging headers vs. model-config `client_headers`) and handling the empty-project case. AWS Bedrock is a technical exception — its current header injection mechanism is a request-body field, not HTTP transport headers — and must be explicitly excluded from scope.

The primary risk factors are (1) the complete absence of test coverage for `get_llm_by_credentials_raw()`, meaning the task must build the entire test foundation from scratch for the injection point; (2) the header casing discrepancy (`X-CodeMie-*` existing vs. `X-Codemie-*` specified) requiring an explicit naming decision; and (3) the `APP_VERSION` env var not being set in the Dockerfile or docker-compose, meaning the injected version value will be stale in any deployment that does not explicitly configure it. The LiteLLM regression surface is limited and well-understood: `_generate_litellm_headers()` must not be modified; only a new assertion in `TestCreateLiteLLMChatModel` is needed to confirm no regressions.
