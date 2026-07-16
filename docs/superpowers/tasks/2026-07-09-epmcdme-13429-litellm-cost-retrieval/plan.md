# Read Pre-Calculated Cost from LiteLLM Proxy Response — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the LiteLLM proxy's own pre-calculated cost from the streaming response body or HTTP response header instead of recomputing it from YAML price tables.

**Architecture:** Override `_convert_chunk_to_generation_chunk` in `LiteLLMChatOpenAI` to extract `cost` from the final streaming usage chunk and expose it as `generation_info["litellm_cost"]`. Enable HTTP response header capture to pick up `x-litellm-response-cost` for non-streaming. Extend `TokensCalculationCallback.on_llm_end` to read either value before falling back to `calculate_token_cost()`. Gate both paths on `LLM_PROXY_ENABLED and LLM_PROXY_TRACK_USAGE`.

**Tech Stack:** Python 3.12, LangChain (langchain-openai), pytest 8.3

## Global Constraints

- Commit prefix: `EPMCDME-13429:` on every commit
- Lint: `make ruff` must pass before committing
- `calculate_token_cost()` signature and behaviour must not change
- `CostConfig`, `LLMModel`, `get_model_cost()` must not be modified
- Non-proxy path (`LLM_PROXY_ENABLED=False`) must behave identically to today
- Proxy cost path must be gated by `config.LLM_PROXY_ENABLED and config.LLM_PROXY_TRACK_USAGE`

---

## File Map

| File | Change |
|---|---|
| `src/codemie/enterprise/litellm/llm_factory.py` | Add `_convert_chunk_to_generation_chunk` override; gate `include_response_headers` by `LLM_PROXY_TRACK_USAGE` |
| `src/codemie/agents/callbacks/tokens_callback.py` | Add `config` import; extend `on_llm_end` with proxy cost reading; gate on `LLM_PROXY_ENABLED and LLM_PROXY_TRACK_USAGE` |
| `tests/enterprise/litellm/test_llm_factory.py` | Add `TestLiteLLMChatOpenAI` and `TestBuildChatModelBaseArgs` test classes |
| `tests/codemie/agents/callbacks/test_tokens_callback.py` | Add proxy cost tests; add gate-disabled test |

---

### Task 1: Add `on_llm_error` test coverage

**Files:**
- Modify: `tests/codemie/agents/callbacks/test_tokens_callback.py`

**Interfaces:**
- Consumes: `TokensCalculationCallback.on_llm_error()` (already exists — untested)
- Produces: test coverage for partial-token error path

**Test-first: yes**

- [x] **Step 1: Write the failing tests**

  ```python
  @patch('codemie.agents.callbacks.tokens_callback.llm_service.get_model_cost')
  @patch('codemie.agents.callbacks.tokens_callback.request_summary_manager.update_llm_run')
  @patch('codemie.agents.callbacks.tokens_callback.calculate_token_cost')
  def test_on_llm_error_records_partial_tokens(mock_calculate, mock_update, mock_get_cost, callback, sample_llm_result, mock_model_costs):
      mock_get_cost.return_value = mock_model_costs
      mock_calculate.return_value = (0.0003, 0.0, 0.0)
      callback.on_llm_error(error=RuntimeError("upstream"), run_id=uuid4(), response=sample_llm_result)
      mock_update.assert_called_once()
      assert mock_update.call_args.kwargs["llm_run"].money_spent == 0.0003

  def test_on_llm_error_skips_update_when_no_response(mock_update, callback):
      callback.on_llm_error(error=RuntimeError("error"), run_id=uuid4())
      mock_update.assert_not_called()

  def test_on_llm_error_skips_update_when_zero_tokens(mock_update, callback):
      # zero usage_metadata → update_llm_run not called
      ...
  ```

- [x] **Step 2: Run to confirm RED** — `pytest tests/codemie/agents/callbacks/test_tokens_callback.py -k on_llm_error`
- [x] **Step 3: No production code change needed** — `on_llm_error` already exists
- [x] **Step 4: Run to confirm GREEN**
- [x] **Step 5: Lint + commit**

  ```bash
  git add tests/codemie/agents/callbacks/test_tokens_callback.py
  git commit -m "EPMCDME-13429: Add on_llm_error coverage and verify existing patch stacks"
  ```

---

### Task 2: Read `x-litellm-response-cost` header in `on_llm_end` + enable header capture

**Files:**
- Modify: `src/codemie/enterprise/litellm/llm_factory.py:241`
- Modify: `src/codemie/agents/callbacks/tokens_callback.py`
- Test: `tests/codemie/agents/callbacks/test_tokens_callback.py`, `tests/enterprise/litellm/test_llm_factory.py`

**Interfaces:**
- Produces: `on_llm_end` reads `generation_info["headers"]["x-litellm-response-cost"]` as
  `proxy_cost` before calling `calculate_token_cost()`; gated on `LLM_PROXY_ENABLED and LLM_PROXY_TRACK_USAGE`

**Test-first: yes**

- [x] **Step 1: Write the failing tests**

  ```python
  # test_llm_factory.py
  def test_include_response_headers_follows_track_usage(track_usage, expected):
      # include_response_headers == config.LLM_PROXY_TRACK_USAGE

  # test_tokens_callback.py
  def test_on_llm_end_uses_proxy_cost_header(...):
      # header "0.0042" → money_spent == 0.0042, calculate_token_cost not called

  def test_on_llm_end_falls_back_to_calculate_when_header_absent(...):
      # no generation_info → falls back to calculate_token_cost

  def test_on_llm_end_falls_back_when_cost_header_invalid(...):
      # "None", "", "error" → all fall back to calculate_token_cost
  ```

- [x] **Step 2: Run to confirm RED**
- [x] **Step 3: Add `include_response_headers` to `_build_chat_model_base_args`**

  ```python
  'include_response_headers': config.LLM_PROXY_TRACK_USAGE,
  ```

- [x] **Step 4: Extend `on_llm_end` with header reading and config gate**

  ```python
  from codemie.configs import config, logger
  import contextlib

  # In on_llm_end, inside the generation loop:
  if (
      proxy_cost is None
      and gen_result.generation_info
      and config.LLM_PROXY_ENABLED
      and config.LLM_PROXY_TRACK_USAGE
  ):
      cost_str = gen_result.generation_info.get("headers", {}).get("x-litellm-response-cost")
      if cost_str:
          with contextlib.suppress(ValueError, TypeError):
              proxy_cost = float(cost_str)

  # After loop:
  if proxy_cost is not None:
      money_spent = proxy_cost
      cached_tokens_money_spent = 0.0
      cached_tokens_creation_cost = 0.0
  else:
      # existing calculate_token_cost() call
  ```

- [x] **Step 5: Run to confirm GREEN**
- [x] **Step 6: Fix ruff SIM105** — replace `try/except/pass` with `contextlib.suppress`
- [x] **Step 7: Lint + commit**

  ```bash
  git add src/codemie/enterprise/litellm/llm_factory.py \
          src/codemie/agents/callbacks/tokens_callback.py \
          tests/codemie/agents/callbacks/test_tokens_callback.py \
          tests/enterprise/litellm/test_llm_factory.py
  git commit -m "EPMCDME-13429: Read cost from LiteLLM proxy response header instead of calculating"
  # then:
  git commit -m "EPMCDME-13429: Fix ruff SIM105 — use contextlib.suppress instead of try/except/pass"
  ```

---

### Task 3: Extract `cost` from streaming usage body

**Files:**
- Modify: `src/codemie/enterprise/litellm/llm_factory.py` — add `_convert_chunk_to_generation_chunk` override
- Modify: `src/codemie/agents/callbacks/tokens_callback.py` — add `litellm_cost` check (before header check)
- Test: `tests/enterprise/litellm/test_llm_factory.py`, `tests/codemie/agents/callbacks/test_tokens_callback.py`

**Background:** When `include_cost_in_streaming_usage: true` is set in `litellm_config.yaml`,
the LiteLLM proxy appends `cost` to the final SSE usage chunk. LangChain's default
`_convert_chunk_to_generation_chunk` builds the chunk via `ChatCompletionChunk.model_dump()`,
which preserves the extra field in Pydantic v2, but it's lost unless the override copies it
into `generation_info`.

**Interfaces:**
- Produces: `LiteLLMChatOpenAI._convert_chunk_to_generation_chunk` injects
  `generation_info["litellm_cost"]` when `chunk["usage"]["cost"]` is present;
  `on_llm_end` reads `litellm_cost` before checking the header

**Test-first: yes**

- [x] **Step 1: Write the failing tests**

  ```python
  # test_llm_factory.py
  def test_convert_chunk_injects_litellm_cost():
      chunk = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.000012}}
      # After override: gen_chunk.generation_info["litellm_cost"] == 0.000012

  def test_convert_chunk_skips_inject_when_no_cost():
      chunk = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
      # gen_chunk returned unchanged (no litellm_cost key)

  # test_tokens_callback.py
  def test_on_llm_end_uses_litellm_cost_from_generation_info(...):
      # generation_info={"litellm_cost": 0.0099} → money_spent == 0.0099, calculate not called
  ```

- [x] **Step 2: Run to confirm RED**
- [x] **Step 3: Add `_convert_chunk_to_generation_chunk` override to `LiteLLMChatOpenAI`**

  ```python
  def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
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

- [x] **Step 4: Add `litellm_cost` check before header check in `on_llm_end`**

  ```python
  streaming_cost = gen_result.generation_info.get("litellm_cost")
  if streaming_cost is not None:
      with contextlib.suppress(ValueError, TypeError):
          proxy_cost = float(streaming_cost)
  if proxy_cost is None:
      cost_str = gen_result.generation_info.get("headers", {}).get("x-litellm-response-cost")
      ...
  ```

- [x] **Step 5: Run to confirm GREEN**
- [x] **Step 6: Lint + commit**

  ```bash
  git add src/codemie/enterprise/litellm/llm_factory.py \
          src/codemie/agents/callbacks/tokens_callback.py \
          tests/codemie/agents/callbacks/test_tokens_callback.py \
          tests/enterprise/litellm/test_llm_factory.py
  git commit -m "EPMCDME-13429: Read pre-calculated cost from LiteLLM proxy streaming response"
  ```

---

### Task 4: Gate proxy cost reading behind config flags

**Files:**
- Modify: `src/codemie/agents/callbacks/tokens_callback.py` — tighten the gate condition
- Modify: `src/codemie/enterprise/litellm/llm_factory.py` — `include_response_headers` mirrors `LLM_PROXY_TRACK_USAGE`
- Modify: `tests/codemie/agents/callbacks/test_tokens_callback.py` — add parametrized gate test; add config patches to proxy cost tests
- Modify: `tests/enterprise/litellm/test_llm_factory.py` — parametrize header test for True/False

**Interfaces:**
- Produces: proxy cost paths are completely inert when `LLM_PROXY_ENABLED=False` or
  `LLM_PROXY_TRACK_USAGE=False`; existing tests for proxy cost pass `mock_config.LLM_PROXY_ENABLED=True`
  and `mock_config.LLM_PROXY_TRACK_USAGE=True`

**Test-first: yes** — `test_on_llm_end_ignores_proxy_cost_when_gate_disabled`

- [x] **Step 1: Write the failing test**

  ```python
  @pytest.mark.parametrize("proxy_enabled,track_usage", [(False,True),(True,False),(False,False)])
  def test_on_llm_end_ignores_proxy_cost_when_gate_disabled(...):
      # generation_info has litellm_cost=0.9999 and header "0.9999"
      # but gate is off → calculate_token_cost() called, money_spent==0.01 (mocked)
  ```

- [x] **Step 2: Run to confirm RED**
- [x] **Step 3: Verify gate in `on_llm_end`** — `config.LLM_PROXY_ENABLED and config.LLM_PROXY_TRACK_USAGE`
- [x] **Step 4: Add `mock_config` patches to all proxy cost tests** — `mock_config.LLM_PROXY_ENABLED=True`, `mock_config.LLM_PROXY_TRACK_USAGE=True`
- [x] **Step 5: Parametrize `test_include_response_headers_follows_track_usage`** in `test_llm_factory.py`
- [x] **Step 6: Run to confirm GREEN**
- [x] **Step 7: Lint + commit**

  ```bash
  git add src/codemie/agents/callbacks/tokens_callback.py \
          src/codemie/enterprise/litellm/llm_factory.py \
          tests/codemie/agents/callbacks/test_tokens_callback.py \
          tests/enterprise/litellm/test_llm_factory.py
  git commit -m "EPMCDME-13429: Gate proxy cost reading behind LLM_PROXY_ENABLED + LLM_PROXY_TRACK_USAGE"
  ```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Override `_convert_chunk_to_generation_chunk` | Task 3 |
| `include_response_headers` mirrors `LLM_PROXY_TRACK_USAGE` | Tasks 2 + 4 |
| `on_llm_end` reads `litellm_cost` (streaming) | Task 3 |
| `on_llm_end` reads `x-litellm-response-cost` header (non-streaming) | Task 2 |
| Fallback to `calculate_token_cost()` when proxy cost absent | Task 2 |
| Gate on `LLM_PROXY_ENABLED and LLM_PROXY_TRACK_USAGE` | Task 4 |
| Non-proxy path unchanged | Task 4 `test_on_llm_end_ignores_proxy_cost_when_gate_disabled` |
| Non-numeric cost string handled | Task 2 `test_on_llm_end_falls_back_when_cost_header_invalid` |
| `on_llm_error` test coverage | Task 1 |

**Placeholder scan:** None.

**Type consistency:**
- `generation_info["litellm_cost"]` is set as raw `cost` from chunk (any numeric type) and read as `float()` ✓
- `generation_info["headers"]["x-litellm-response-cost"]` is a string, read as `float()` ✓
- `contextlib.suppress(ValueError, TypeError)` handles both conversion failure cases ✓
