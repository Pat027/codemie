# LLM Providers

## Provider Configuration

Use model provider YAML files and central LLM services.

| Avoid | Prefer |
|---|---|
| Hardcoding model names in feature code | Read configured model/service values |
| Assuming one provider | Keep AWS, Azure, GCP, Anthropic, LiteLLM paths pluggable |

Evidence: provider config files live under `config/llms/`; README documents `MODELS_ENV` at `README.md:61`.

## Enterprise LiteLLM

Treat LiteLLM proxy behavior as provider-backed enterprise functionality.

| Avoid | Prefer |
|---|---|
| Importing enterprise implementation everywhere | Use service/provider registry boundaries |
| Assuming LiteLLM is always enabled | Gate behavior with `is_litellm_enabled` and config |

Evidence: app startup registers LiteLLM providers conditionally at `src/codemie/rest_api/main.py:265`.

## Traffic Tagging Headers

Inject `X-CodeMie-Version` and `X-CodeMie-Project` on outbound LLM requests via the internal (non-LiteLLM) path only.

**Helper**: `_build_codemie_tagging_headers()` in `src/codemie/core/dependecies.py` — always emits `X-CodeMie-Version: config.APP_VERSION`; emits `X-CodeMie-Project` only when `get_current_project()` returns a non-empty string.

**Precedence rule**: Codemie tags are seeded first; model YAML `client_headers` are merged on top and win on collision.

**Per-provider injection sites** (all in `src/codemie/core/dependecies.py`):

| Provider | Factory | Header argument |
|---|---|---|
| Azure / DIAL | `get_llm_by_credentials_raw()` | `AzureChatOpenAI(default_headers=merged_headers)` |
| Vertex AI | `get_vertex_llm()` | `ChatVertexAI(client_options={"additional_headers": merged_headers})` |
| Anthropic direct | `get_anthropic_llm()` | `ChatAnthropic(model_kwargs={"extra_headers": merged_headers})` |
| AWS Bedrock | `get_bedrock_llm()` | **Not injected** — uses request-body fields, not HTTP headers |

| Avoid | Prefer |
|---|---|
| Adding `X-CodeMie-*` headers on the LiteLLM path | LiteLLM path uses `x-litellm-tags`; keep the two paths separate |
| Injecting user-identifying information | Tagging headers carry version and project only |
| Overriding `client_headers` from model config | Seed Codemie tags first; let `client_headers` win |

Evidence: helper and injection sites at `src/codemie/core/dependecies.py`; constants at `src/codemie/core/constants.py` (`HEADER_CODEMIE_VERSION`, `HEADER_CODEMIE_TAGGING_PROJECT`); introduced in EPMCDME-12602.
