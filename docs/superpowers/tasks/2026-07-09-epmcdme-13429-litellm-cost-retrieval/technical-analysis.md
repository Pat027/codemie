# Technical Research

**Task**: litellm cost tokens callback proxy_router llm_service
**Generated**: 2026-07-08T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

Retrieve LLM call cost from LiteLLM instead of calculating it internally (EPMCDME-13429). Currently CodeMie retrieves token counts from LiteLLM but calculates monetary cost internally. The goal is to use LiteLLM's own pricing data (litellm.model_cost dict) as the single source of truth instead of maintaining internal YAML price tables.

---

## 2. Codebase Findings

### Existing Implementations

Primary change sites:

- `src/codemie/agents/callbacks/tokens_callback.py` — `TokensCalculationCallback`; `on_llm_end()` at lines 62/66 calls `llm_service.get_model_cost()` then `calculate_token_cost()`; `on_llm_error()` at lines 121/122 repeats the same two calls. This is one of the two primary call sites the task must modify.
- `src/codemie/enterprise/litellm/proxy_router.py` — `_parse_usage_with_cost()` at line 840; calls `llm_service.get_model_cost(llm_model)` at line 866 and passes `calculate_token_cost` as a callback into the enterprise layer at line 876. This is the second primary call site.

Supporting implementation files:

- `src/codemie/service/llm_service/llm_service.py` — `LLMService.get_model_cost()` at line 162 returns `CostConfig`; `get_embeddings_model_cost()` at line 179; `initialize_default_litellm_models()` at line 300; `llm_service` singleton at line 448. The method dispatches to LiteLLM-sourced models or YAML models depending on `LLM_PROXY_ENABLED`. Silent fallback to default model cost at lines 174–177 when model not found.
- `src/codemie/configs/llm_config.py` — `CostConfig` Pydantic model at line 26 (fields: `input`, `output`, `input_cost_per_token_batches`, `output_cost_per_token_batches`, `cache_read_input_token_cost`, `cache_creation_input_token_cost`); `LLMModel` at line 84 with `cost: Optional[CostConfig] = None` at line 95; `LLMConfig`/`llm_config` singleton at line 145.
- `src/codemie/enterprise/litellm/models.py` — `map_litellm_to_llm_model()` at line 40; constructs `CostConfig` from LiteLLM proxy API `model_info` dict at lines 103–114 using `input_cost_per_token`/`output_cost_per_token` keys; the only `LLMModel(...)` construction site outside of Pydantic itself (line 138). Sets `LLMModel.base_name` and `LLMModel.deployment_name` to the routing alias (e.g. `"gpt-4.1"`), NOT to the provider-prefixed name.
- `src/codemie/core/utils.py` — `calculate_token_cost()` at line 349; pure arithmetic over a `CostConfig`; also `calculate_cli_metric_cost()` at line 442 which calls `llm_service.get_model_cost()` at line 478 and `calculate_token_cost()` at line 481 — a third call site not mentioned in the task description.
- `src/codemie/datasource/callback/datasource_monitoring_callback.py` — `on_split_documents()` at line 73 calls `get_embeddings_model_cost()` and multiplies the rate directly (no `calculate_token_cost`); separate embeddings cost path, not in scope for this task but exists as a parallel pattern.
- `/Users/Sviatoslav_Likhtarchyk/mdtu_gpt/codemie-enterprise/src/codemie_enterprise/litellm/proxy_utils.py` — `calculate_token_costs()` at line 278; `parse_usage_from_response()` at line 314; zero codemie imports — receives `cost_config` and `cost_calculator` as injected arguments; the enterprise layer does not need to change.

### Architecture and Layers Affected

1. **Config model layer** — `src/codemie/configs/llm_config.py`: `LLMModel` lacks a `litellm_model_name` (or `base_model`) field. Adding this field is a prerequisite for the `litellm.model_cost` lookup. This is a schema change to a core config object used throughout the codebase.
2. **LiteLLM model mapping layer** — `src/codemie/enterprise/litellm/models.py`: `map_litellm_to_llm_model()` must be extended to read `model_info["base_model"]` from the LiteLLM proxy API response and store it in the new `LLMModel.litellm_model_name` field.
3. **Service layer** — `src/codemie/service/llm_service/llm_service.py`: `get_model_cost()` is the natural home for the `litellm.model_cost` lookup with fallback to YAML prices. Guide conventions mandate that this method (not the call sites) should absorb the new logic.
4. **Calculation layer** — `src/codemie/core/utils.py`: `calculate_token_cost()` itself should remain unchanged; it receives a `CostConfig` regardless of pricing source. The change is limited to how `CostConfig` is populated.
5. **Callback layer** — `src/codemie/agents/callbacks/tokens_callback.py`: If the lookup logic moves into `get_model_cost()`, the call sites here may need no change. If the task opts to replace at call sites, both `on_llm_end` (lines 62/66) and `on_llm_error` (lines 121/122) are affected.
6. **Proxy integration (thin wrapper) layer** — `src/codemie/enterprise/litellm/proxy_router.py`: `_parse_usage_with_cost()` at line 866. Same conditional as above — either changed or left intact depending on where lookup logic lives.

### Integration Points

Internal module dependencies:

- `tokens_callback.py` → `llm_service.get_model_cost()` → `CostConfig` → `calculate_token_cost()`
- `proxy_router._parse_usage_with_cost()` → `llm_service.get_model_cost()` → `CostConfig` → passes to enterprise `parse_usage_from_response()` as callback
- `core/utils.calculate_cli_metric_cost()` → `llm_service.get_model_cost()` → `calculate_token_cost()` (third call site, not in task scope but touches same chain)
- `models.map_litellm_to_llm_model()` → reads LiteLLM proxy API response → constructs `LLMModel` with `CostConfig`

External service connections:

- **LiteLLM SDK in-process dict**: `litellm.model_cost` is populated at import time from LiteLLM's bundled pricing JSON. No network call required for the dict itself. However `litellm.model_cost` is keyed by canonical provider-prefixed public model names (e.g. `"azure/gpt-4.1-2025-04-14"`).
- **LiteLLM proxy HTTP API** (via `LITE_LLM_URL`): model metadata is fetched at startup by `initialize_default_litellm_models()` which drives `map_litellm_to_llm_model()`. The `model_info["base_model"]` field from this API response is the correct key for `litellm.model_cost`.

### Patterns and Conventions

- **Lookup-then-calculate**: every cost computation follows `get_model_cost(name)` → `CostConfig` → `calculate_token_cost(model, cost_config, ...)`. This two-step pattern is used at all three call sites. The new implementation must preserve this interface so the enterprise layer stays unchanged.
- **Enterprise layer is pure (injection pattern)**: `proxy_utils.py` receives `cost_config` and `cost_calculator` as injected arguments and has no codemie imports. The thin wrapper in `proxy_router._parse_usage_with_cost()` is the correct seam to swap pricing sources.
- **CostConfig as the pricing interface**: `CostConfig` is the stable interface between the pricing source and the arithmetic. Switching to `litellm.model_cost` means constructing a `CostConfig` from `litellm.model_cost[key]` — the field mapping is direct (`input_cost_per_token` → `input`, `output_cost_per_token` → `output`, `cache_read_input_token_cost` → `cache_read_input_token_cost`, `cache_creation_input_token_cost` → `cache_creation_input_token_cost`).
- **Dual pricing source coexistence**: LiteLLM-proxy-backed models and YAML-backed models both produce a `CostConfig` on `LLMModel.cost`. The new logic must follow this same shape: populate `LLMModel.cost` from `litellm.model_cost` where a match exists, fall back to YAML pricing otherwise.
- **Silent fallback in `get_model_cost()`**: lines 174–177 silently return the default model's cost if the model is not found. This masks missing pricing. The new implementation should make fallback explicit and log a warning when `litellm.model_cost` lookup fails.

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/integration/llm-providers.md` — mandates keeping all provider paths pluggable and gating LiteLLM-specific behavior with `is_litellm_enabled`; provider configs live under `config/llms/`. Directly relevant.
- `.ai-run/guides/architecture/layered-architecture.md` — cost logic belongs in the service layer, not in routers or callbacks; cross-cutting utilities go in `codemie.core`, not feature packages.
- `.ai-run/guides/architecture/service-layer-patterns.md` — avoid duplicating provider-selection rules; use existing provider registries and factories; the correct pattern is to extend `llm_service.get_model_cost()` rather than adding parallel lookup paths at call sites.
- `.ai-run/guides/architecture/project-structure.md` — integration/provider logic belongs in services or adapters, not routers; do not create new top-level packages without precedent.
- `.ai-run/guides/development/configuration-patterns.md` — avoid hardcoding model-provider choices; gate optional behavior (like LiteLLM cost lookup) near service assembly; do not call `litellm.model_cost` directly in feature code — route through `src/codemie/configs/` and the service/provider registry.

### Architectural Decisions

No formal ADR files exist for cost calculation or LiteLLM integration. The implicit decision recorded in source is:
- YAML files (`config/llms/*.yaml`) supply pricing for the non-proxy path; LiteLLM proxy API `model_info` fields supply pricing for the proxy path. Both converge on `CostConfig` stored on `LLMModel.cost`.
- `map_litellm_to_llm_model()` in `models.py` already reads `input_cost_per_token`/`output_cost_per_token` from the LiteLLM model_info dict (lines 103–114) — so LiteLLM-backed models already carry cost data through the same `CostConfig` pipeline at startup. The task extends this to read from `litellm.model_cost` at call time rather than relying solely on startup-populated data.

### Derived Conventions

- `get_model_cost()` is the single gateway for cost retrieval — callers should not reach into LiteLLM internals directly.
- `calculate_token_cost()` must remain provider-agnostic; it takes a `CostConfig`, not a raw dict.
- Any behavioral change to cost retrieval must be gated by `LLM_PROXY_ENABLED` (or a more specific flag); the YAML path must continue to work unchanged.
- No inline TODOs or DECISION markers relevant to cost/pricing were found in any of the four target files. One security NOTE exists at `proxy_router.py:1390` (unrelated to cost).

---

## 4. Testing Landscape

### Existing Coverage

- `tests/codemie/agents/callbacks/test_tokens_callback.py` — 7 tests for `TokensCalculationCallback.on_llm_end`: basic success, error handling, empty generations, cached tokens, cache-creation tokens, mixed cache/read, no-cache-cost model. Each test uses `@patch` to mock `llm_service.get_model_cost` and `calculate_token_cost`. **Zero tests for `on_llm_error`.**
- `tests/enterprise/litellm/test_proxy_router.py` — 2 tests in `TestParseUsageWithCost` for `_parse_usage_with_cost`: success path and cost-config-failure path. Both mock `llm_service.get_model_cost` and `parse_usage_from_response` (pre-baking `money_spent`). Large file (2106 lines) also covers `_streaming_response_with_usage_tracking` and other proxy functionality.
- `tests/codemie/core/test_core_utils.py` — 4 parametrized unit tests for `calculate_token_cost` directly with `CostConfig`; covers caching cases, batch costs, zero tokens, return type. Does not touch `get_model_cost`.
- `tests/codemie/service/test_llm_service.py` — exercises `LLMService` and `LLMModel` but never calls `get_model_cost` directly; no coverage of that method's logic.
- `tests/codemie/service/llm_service/test_llm_service_litellm_integration.py` — tests `initialize_default_litellm_models`, LiteLLM vs YAML fallback, deployment-name resolution; does not touch `get_model_cost` or cost config.
- `tests/codemie/service/llm_service/test_litellm_service.py` — **entirely skipped** (`pytestmark = pytest.mark.skip`; reason: deprecated service / enterprise package not installed). Contains tests asserting `result.cost.input == 0.00003` from `input_cost_per_token` — the only active tests for `map_litellm_to_llm_model` cost mapping, but none execute.

### Testing Framework and Patterns

- pytest 8.3.x, pytest-asyncio 0.23.x, pytest-mock 3.14.x, pytest-env 1.1.x, pytest-httpx 0.35.x.
- `@patch(...)` decorator stacking (up to 3 deep) for `llm_service.get_model_cost`, `calculate_token_cost`, and `request_summary_manager.update_llm_run`.
- `@pytest.fixture` functions for reusable `TokensCalculationCallback`, `CostConfig`, `LLMResult`, `LiteLLMModels` instances.
- `MagicMock` / `AsyncMock` throughout; `mock.assert_called_once_with(...)` call-site verification.
- `pytest.mark.asyncio` on all async proxy_router tests.
- `@pytest.mark.parametrize` for data-driven cost arithmetic cases in `test_core_utils.py`.
- Class-based grouping (`class TestParseUsageWithCost`) in proxy_router tests; flat function-based tests in callbacks.

### Coverage Gaps

1. `on_llm_error` in `tokens_callback.py` — zero tests; both `get_model_cost` (line 121) and `calculate_token_cost` (line 122) are called there.
2. `llm_service.get_model_cost()` — only ever mocked; the method's own logic (LiteLLM model lookup, YAML fallback, silent default fallback at lines 174–177) has no direct unit tests.
3. LiteLLM-native cost path in `_parse_usage_with_cost` — existing tests mock `parse_usage_from_response` to return a pre-built result; no test covers the new path where cost comes from `litellm.model_cost`.
4. `map_litellm_to_llm_model()` cost-field mapping — the only tests asserting `result.cost.input` are in the entirely-skipped `test_litellm_service.py`.
5. `calculate_token_cost` mock patches in `test_tokens_callback.py` — these will break as written when the call to `calculate_token_cost` is removed or bypassed at the callback level.
6. Streaming response with LiteLLM-provided cost — `TestStreamingResponseWithUsageTracking` does not verify that a LiteLLM-supplied cost field is used verbatim.

---

## 5. Configuration and Environment

### Environment Variables

- `MODELS_ENV` — selects which YAML file to load (`llm-{MODELS_ENV}-config.yaml`); values: `dial`, `azure`, `aws`, `gcp`.
- `LLM_PROXY_ENABLED` — master flag; when `True`, `get_all_llm_model_info()` returns LiteLLM-sourced models. This is the primary gate for the new cost path.
- `LLM_PROXY_MODE` — `"internal"` | `"lite_llm"`; controls LiteLLM proxy routing.
- `LLM_PROXY_TRACK_USAGE` — gates all usage/cost tracking in the proxy response stream.
- `LITE_LLM_URL` — base URL of the LiteLLM proxy (used by `initialize_default_litellm_models()`).
- `LITE_LLM_APP_KEY` / `LITE_LLM_PROXY_APP_KEY` / `LITE_LLM_MASTER_KEY` — auth keys.
- `LITELLM_MODELS_CACHE_TTL` — TTL for model metadata cache; affects freshness of `base_model` and pricing fields fetched at startup.
- `LITELLM_SPEND_COLLECTOR_ENABLED` / `LITELLM_BUDGET_RESET_TRACKER_ENABLED` / `LITELLM_BUDGET_RESET_RECONCILIATION_ENABLED` — APScheduler budget job flags; adjacent to cost tracking but not directly in the change surface.
- `LITELLM_PREMIUM_MODELS_ALIASES` — list of partial model-name strings for premium classification; separate from cost arithmetic.

### Configuration Files

- `litellm_config.yaml` — LiteLLM proxy model list. Each entry has `litellm_params.model` (provider-prefixed internal deployment name, e.g. `azure/codemie-gpt-4.1-2025-04-14`) and `model_info.base_model` (canonical public model name for `litellm.model_cost` resolution, e.g. `azure/gpt-4.1-2025-04-14`). Only the `deepseek-r1` entry has no `base_model` — it carries inline `input_cost_per_token`/`output_cost_per_token` in `model_info`. Most entries rely on `base_model` for pricing.
- `config/llms/llm-azure-config.yaml` — Azure OpenAI models with full `cost` price tables (input, output, cache rates, batch rates). CostConfig fields: `input`, `output`, `cache_read_input_token_cost`, `cache_creation_input_token_cost`, `input_cost_per_token_batches`, `output_cost_per_token_batches`.
- `config/llms/llm-aws-config.yaml` — AWS Bedrock models with `cost` tables including `cache_creation_input_token_cost`.
- `config/llms/llm-dial-config.yaml`, `config/llms/llm-gcp-config.yaml` — additional provider configs with same `cost` block structure.
- `src/codemie/configs/llm_config.py` — Pydantic definitions; `CostConfig` at line 26 maps 1:1 to the YAML `cost` block.
- `src/codemie/configs/config.py` — all `LLM_PROXY_*` and `LITELLM_*` env-var settings as typed Pydantic fields.

### Feature Flags and Deployment Concerns

- `LLM_PROXY_ENABLED=True` is the gate for the LiteLLM cost path; when `False`, only YAML pricing is used. The new implementation must respect this gate.
- **`litellm_params.model` is NOT a valid `litellm.model_cost` key.** The internal deployment name (e.g. `azure/codemie-gpt-4.1-2025-04-14`) will not match the bundled pricing dict. The correct key is `model_info.base_model` (e.g. `azure/gpt-4.1-2025-04-14`). This field is fetched from the LiteLLM proxy API at startup but is not currently stored on `LLMModel`.
- **Bedrock region-prefixed `base_model` values**: Bedrock entries use `us.anthropic.*`, `eu.anthropic.*`, `global.anthropic.*`, `jp.anthropic.*`. LiteLLM's `model_cost` dict typically carries only the canonical `bedrock/anthropic.*` key. Region-prefix normalization is required.
- **`deepseek-r1` has no `base_model`**: must fall back to inline `input_cost_per_token`/`output_cost_per_token` from `model_info`.
- **Newer model names likely absent from `litellm.model_cost`**: entries for `gpt-5`, `gpt-5-mini`, `gpt-5.2`, `gpt-5.4`, `claude-sonnet-4-6`, `claude-sonnet-5`, `claude-opus-4-6`, `qwen3-coder`, `kimi-k2.5` may not exist in LiteLLM v1.84's bundled dict. Fallback to YAML prices is required for these.
- **Batch cost fields (`input_cost_per_token_batches`, `output_cost_per_token_batches`) have no `litellm.model_cost` equivalent.** These Azure-specific fields in `CostConfig` will be silently zero if the new path does not explicitly preserve them from YAML.

---

## 6. Risk Indicators

- **Zero test coverage for `on_llm_error`** in `tokens_callback.py` — lines 121/122 are a named change site with no existing tests. Any regression there would go undetected.
- **`get_model_cost()` itself has no direct unit tests** — only ever mocked. The method's fallback logic (lines 174–177 silently return default model cost) has never been exercised. Changes to this method carry unknown blast radius.
- **All existing mock patches will break**: `test_tokens_callback.py` patches `calculate_token_cost` directly; `test_proxy_router.py` patches `get_model_cost` and `parse_usage_from_response`. When the implementation changes, these tests must be rewritten, not just updated.
- **`litellm_params.model` is the wrong key for `litellm.model_cost`** — the task description's chosen approach ("use the provider-prefixed model name stored in `litellm_params['model']`") will produce key-not-found failures for all custom internal deployment names. The correct key is `model_info.base_model`. A new field on `LLMModel` is required.
- **`LLMModel` schema change** — adding `litellm_model_name` (or `base_model`) to `LLMModel` is a change to a core config model. Any serialization, storage, or comparison of `LLMModel` objects elsewhere could be affected. The model is used widely across the service and callback layers.
- **`map_litellm_to_llm_model()` cost mapping has no active tests** — `test_litellm_service.py` is entirely skipped. The function that must be extended to store `base_model` has zero test coverage.
- **Bedrock region-prefix normalization is non-trivial** — `us.anthropic.*`, `eu.anthropic.*`, etc. are used across multiple entries in `litellm_config.yaml`; normalization logic must cover all observed prefix patterns without breaking non-Bedrock lookups.
- **`deepseek-r1` edge case** — no `base_model`; must fall back to inline cost fields; requires an explicit code path.
- **Newer models missing from `litellm.model_cost`** — if the fallback to YAML prices is not implemented correctly, cost tracking silently returns zero or falls back to default model prices for cutting-edge models.
- **Batch cost fields will be silently dropped** — `input_cost_per_token_batches` / `output_cost_per_token_batches` are `CostConfig` fields used in `calculate_token_cost()`. Unless explicitly preserved from YAML when building `CostConfig` from `litellm.model_cost`, batch cost tracking breaks for Azure models.
- **Third call site not in task scope** — `core/utils.calculate_cli_metric_cost()` at line 478 also calls `get_model_cost()` and `calculate_token_cost()`. If `get_model_cost()` is modified in-place, this path is affected. If the task only changes call sites in `tokens_callback.py` and `proxy_router.py`, this path is inconsistent.
- **Guide convention conflicts with task description's approach**: the `.ai-run/guides/architecture/service-layer-patterns.md` convention says "extend `get_model_cost()` rather than adding parallel lookup paths at call sites." The task description proposes replacing at call sites. Both approaches deliver the feature, but only extending the service method avoids fragmenting the lookup logic and covers the CLI metric cost path automatically.
- **`LITELLM_MODELS_CACHE_TTL` and pricing freshness**: `litellm.model_cost` is populated from LiteLLM's bundled pricing JSON at import time (static in-process dict). It does not reflect runtime updates to LiteLLM's pricing. Custom prices added in `litellm_config.yaml` `model_info` are only visible via the LiteLLM proxy API, not through the in-process dict.

---

## 7. Summary for Complexity Assessment

This task touches five architectural layers: the config model layer (`LLMModel`/`CostConfig` in `llm_config.py`), the LiteLLM model mapping layer (`map_litellm_to_llm_model()` in `models.py`), the service layer (`get_model_cost()` in `llm_service.py`), the callback layer (`tokens_callback.py`), and the proxy integration layer (`proxy_router.py`). The minimum file change surface is six files: `llm_config.py`, `enterprise/litellm/models.py`, `llm_service.py`, plus whichever call-site files are modified, plus at least three test files. The guide-recommended approach (extend `get_model_cost()` internally) would also cover the third call site in `core/utils.py` without additional changes, while the call-site replacement approach creates inconsistency.

The task introduces moderate technical novelty. The core lookup pattern (`litellm.model_cost[key]` → `CostConfig`) is straightforward and the field mapping is direct. However, a prerequisite data model change is required: `LLMModel` must gain a new field (e.g. `litellm_model_name`) to carry `model_info.base_model` from the LiteLLM proxy API response. This is non-trivial because `LLMModel` is a core config object used across multiple layers, and `map_litellm_to_llm_model()` — the function that must store this new field — has no active test coverage. Additional complexity arises from four edge cases that require explicit fallback logic: Bedrock region-prefixed model names, `deepseek-r1`'s missing `base_model`, newer models absent from `litellm.model_cost`, and Azure batch cost fields with no `litellm.model_cost` equivalent.

Test coverage posture is weak for the core change surface. `on_llm_error` has zero tests. `get_model_cost()` is only ever mocked and has no direct unit tests. All existing mock patches in `test_tokens_callback.py` and `test_proxy_router.py` will need to be rewritten when the implementation changes. The skipped `test_litellm_service.py` (which contained the only `map_litellm_to_llm_model` cost assertions) should be un-skipped and updated as part of this task. The complexity score should reflect: a core data model change, four fallback edge cases requiring careful handling, and a test suite that will need partial reconstruction rather than simple extension.
