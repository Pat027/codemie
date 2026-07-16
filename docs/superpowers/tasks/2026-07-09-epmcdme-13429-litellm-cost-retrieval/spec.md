# Spec: Read Pre-Calculated Cost from LiteLLM Proxy Response

**Ticket**: EPMCDME-13429
**Date**: 2026-07-09
**Complexity**: S (revised from L after approach change)

---

## Problem

CodeMie calculates LLM call costs independently using YAML price tables
(`config/llms/llm-*-config.yaml`). These tables can drift from LiteLLM's own pricing,
causing the cost values shown in CodeMie's metrics to diverge from the costs shown in
LiteLLM's portal UI. Both portals should agree because they use the same underlying
pricing source.

---

## Chosen Approach: Read proxy's pre-calculated cost from the response

Rather than replicating the proxy's cost calculation (dict lookups, normalization, merging),
read the cost the LiteLLM proxy already computed and injected into its own response.

The proxy exposes pre-calculated cost in two places:

1. **Streaming responses** — when `include_cost_in_streaming_usage: true` is set in
   `litellm_config.yaml`, the final SSE usage chunk carries a `cost` field inside the
   `usage` object (e.g. `{"usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.000012}}`).
   This field is non-standard (not in the OpenAI spec) and would be stripped by LangChain's
   default chunk conversion, so an override is needed to preserve it.

2. **Non-streaming responses** — the proxy returns a `x-litellm-response-cost` HTTP
   response header with the total cost as a float string. LangChain's `ChatOpenAI` can
   capture response headers in `generation_info` via the `include_response_headers=True`
   init parameter.

### What changes

1. **`LiteLLMChatOpenAI._convert_chunk_to_generation_chunk`** (new override in
   `llm_factory.py`) — reads `cost` from the raw chunk's `usage` dict and injects it as
   `generation_info["litellm_cost"]` on the final `ChatGenerationChunk`. This value
   survives LangChain's `merge_dicts` aggregation and is readable in `on_llm_end`.

2. **`_build_chat_model_base_args`** (`llm_factory.py`) — sets
   `include_response_headers: config.LLM_PROXY_TRACK_USAGE` so HTTP response headers
   (including `x-litellm-response-cost`) land in `generation_info["headers"]`. Gated by
   `LLM_PROXY_TRACK_USAGE` to avoid collecting headers when cost tracking is disabled.

3. **`TokensCalculationCallback.on_llm_end`** (`tokens_callback.py`) — reads the proxy
   cost with this priority chain:
   - `generation_info["litellm_cost"]` (streaming, most accurate)
   - `generation_info["headers"]["x-litellm-response-cost"]` (non-streaming)
   - `calculate_token_cost()` using YAML prices (fallback — existing behaviour)

   The proxy cost path is only entered when `config.LLM_PROXY_ENABLED` and
   `config.LLM_PROXY_TRACK_USAGE` are both `True`, ensuring non-proxy deployments are
   unaffected.

### What does not change

- `CostConfig` interface, fields, and `calculate_token_cost()` arithmetic — unchanged.
- `LLMModel` data model — unchanged.
- YAML price config files — remain as the fallback source.
- `get_model_cost()` in `LLMService` — unchanged.
- `proxy_router.py` (enterprise) — unchanged.
- Non-proxy path (`LLM_PROXY_ENABLED=False`) — behaviour identical to today.

---

## Proxy Config Prerequisite

`litellm_config.yaml` must have `include_cost_in_streaming_usage: true` at the top level
for the streaming cost field to be populated. This was already set before implementation.

---

## Data Flow

```
Streaming path:
  LiteLLM proxy SSE → final usage chunk with cost field
    └─ LiteLLMChatOpenAI._convert_chunk_to_generation_chunk()
         └─ chunk["usage"]["cost"]  →  generation_info["litellm_cost"]
              └─ TokensCalculationCallback.on_llm_end()
                   └─ proxy_cost = float(generation_info["litellm_cost"])

Non-streaming path:
  LiteLLM proxy HTTP response → x-litellm-response-cost header
    └─ ChatOpenAI(include_response_headers=True)
         └─ generation_info["headers"]["x-litellm-response-cost"]
              └─ TokensCalculationCallback.on_llm_end()
                   └─ proxy_cost = float(cost_str)

Fallback path (no proxy, or proxy cost unavailable):
  TokensCalculationCallback.on_llm_end()
    └─ calculate_token_cost(llm_model, model_costs, input_tokens, output_tokens, ...)
```

---

## Configuration Gates

Both proxy cost paths are conditional on:

```python
config.LLM_PROXY_ENABLED and config.LLM_PROXY_TRACK_USAGE
```

- `LLM_PROXY_ENABLED=False` → proxy cost paths are skipped entirely; YAML fallback used.
- `LLM_PROXY_TRACK_USAGE=False` → proxy cost paths are skipped; `include_response_headers`
  is set to `False` (no header overhead); YAML fallback used.
- Enterprise package not installed → `LiteLLMChatOpenAI` is never instantiated; the
  `_convert_chunk_to_generation_chunk` override never runs; `litellm_cost` is never in
  `generation_info`; the fallback fires naturally.

---

## File Changes

### 1. `src/codemie/enterprise/litellm/llm_factory.py`

**Add `_convert_chunk_to_generation_chunk` override to `LiteLLMChatOpenAI`:**

```python
def _convert_chunk_to_generation_chunk(
    self,
    chunk: dict,
    default_chunk_class: type,
    base_generation_info: dict | None,
):
    gen_chunk = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
    if gen_chunk is None:
        return None
    token_usage = chunk.get("usage") if isinstance(chunk, dict) else None
    if token_usage and (cost := token_usage.get("cost")) is not None:
        from langchain_core.outputs import ChatGenerationChunk
        info = dict(gen_chunk.generation_info or {})
        info["litellm_cost"] = cost
        return ChatGenerationChunk(message=gen_chunk.message, generation_info=info)
    return gen_chunk
```

**Update `include_response_headers` in `_build_chat_model_base_args`:**

```python
'include_response_headers': config.LLM_PROXY_TRACK_USAGE,
```

### 2. `src/codemie/agents/callbacks/tokens_callback.py`

**Add config import:**

```python
from codemie.configs import config, logger
```

**Extend `on_llm_end` to read proxy cost before falling back to YAML calculation:**

```python
proxy_cost: Optional[float] = None
for gen in response.generations:
    for gen_result in gen:
        # ... existing usage_metadata extraction ...
        if (
            proxy_cost is None
            and gen_result.generation_info
            and config.LLM_PROXY_ENABLED
            and config.LLM_PROXY_TRACK_USAGE
        ):
            # Prefer cost from streaming usage body (include_cost_in_streaming_usage)
            streaming_cost = gen_result.generation_info.get("litellm_cost")
            if streaming_cost is not None:
                with contextlib.suppress(ValueError, TypeError):
                    proxy_cost = float(streaming_cost)
            # Fall back to x-litellm-response-cost header (non-streaming)
            if proxy_cost is None:
                cost_str = gen_result.generation_info.get("headers", {}).get("x-litellm-response-cost")
                if cost_str:
                    with contextlib.suppress(ValueError, TypeError):
                        proxy_cost = float(cost_str)

if proxy_cost is not None:
    money_spent = proxy_cost
    cached_tokens_money_spent = 0.0
    cached_tokens_creation_cost = 0.0
else:
    model_costs = llm_service.get_model_cost(self.llm_model)
    money_spent, cached_tokens_money_spent, cached_tokens_creation_cost = calculate_token_cost(...)
```

---

## Edge Case Handling

| Case | Handling |
|---|---|
| `include_cost_in_streaming_usage` not set | `cost` field absent from chunk; `litellm_cost` never set in `generation_info`; YAML fallback fires |
| Non-numeric cost string (e.g. `"None"`, `""`) | `contextlib.suppress(ValueError, TypeError)` swallows parse error; YAML fallback fires |
| `LLM_PROXY_ENABLED=False` | Gate condition fails; YAML fallback fires |
| `LLM_PROXY_TRACK_USAGE=False` | Gate condition fails; `include_response_headers=False`; YAML fallback fires |
| Enterprise package not installed | `LiteLLMChatOpenAI` not used; `litellm_cost` never in `generation_info`; header not requested; YAML fallback fires |
| Multiple generations in response | First non-`None` proxy cost wins (`proxy_cost is None` guard) |

---

## Testing Plan

| Test file | Tests |
|---|---|
| `tests/enterprise/litellm/test_llm_factory.py` | `test_include_response_headers_follows_track_usage` (parametrized True/False), `test_convert_chunk_injects_litellm_cost`, `test_convert_chunk_skips_inject_when_no_cost` |
| `tests/codemie/agents/callbacks/test_tokens_callback.py` | `test_on_llm_end_uses_proxy_cost_header`, `test_on_llm_end_uses_litellm_cost_from_generation_info`, `test_on_llm_end_falls_back_to_calculate_when_header_absent`, `test_on_llm_end_falls_back_when_cost_header_invalid`, `test_on_llm_end_ignores_proxy_cost_when_gate_disabled` (parametrized) |

---

## Acceptance Criteria

1. When `LLM_PROXY_ENABLED=True`, `LLM_PROXY_TRACK_USAGE=True`, and the streaming
   response contains a `cost` field in the final usage chunk, `on_llm_end` uses that value
   as `money_spent` without calling `calculate_token_cost()`.
2. When `LLM_PROXY_ENABLED=True`, `LLM_PROXY_TRACK_USAGE=True`, and the non-streaming
   response contains a valid `x-litellm-response-cost` header, `on_llm_end` uses that
   value as `money_spent` without calling `calculate_token_cost()`.
3. When proxy cost is unavailable (absent field, non-numeric string, gate disabled),
   `on_llm_end` falls back to `calculate_token_cost()` — identical to current behaviour.
4. When `LLM_PROXY_ENABLED=False` or `LLM_PROXY_TRACK_USAGE=False`, behaviour is
   identical to today regardless of what `generation_info` contains.
5. All existing tests pass. New tests are green.