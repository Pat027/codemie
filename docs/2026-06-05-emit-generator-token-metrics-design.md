# Design: Emit Token Usage Metrics for Assistant / Skill Generator Calls

**Ticket:** EPMCDME-12659  
**Date:** 2026-06-05

## Problem

`POST /v1/assistants/generate`, `/prompt/generate`, `/refine`, and `POST /v1/skills/refine` all invoke LLM chains. `TokensCalculationCallback` correctly accumulates token usage in `RequestSummaryManager` keyed by `request_id`. However, after each chain call no code reads that summary — the data is never emitted to Elasticsearch, and the in-memory entries are never cleared.

Consequences:
- Generator LLM costs are invisible in the Insights analytics platform (not in `platform_cost`, not in `total_money_spent`)
- `RequestSummaryManager` grows unbounded — one entry per generator call, never freed (memory leak)

## Root Cause

The generator services only emit a count metric (`send_log_metric(ASSISTANT_GENERATOR_TOTAL_METRIC, ...)`) with no token payload. The three lines to read + emit + clear the summary are simply absent.

## Design

### Approach

Minimal wiring fix. No new abstractions, no new metric names, no new models. Three additions per generator method:

1. **Read** — `summary = request_summary_manager.get_summary(request_id)` (already calls `.calculate()` internally; returns an empty `TokensUsage` if no runs accumulated)
2. **Enrich** — pass `summary.tokens_usage` fields into the existing `send_log_metric()` attributes dict
3. **Clear** — `request_summary_manager.clear_summary(request_id)` in a `finally` block to prevent leaks on all exit paths (including when `send_log_metric` itself raises)

Guard with `if request_id:` where `request_id` is `Optional[str]` (only `generate_skill_details`).

### Files Changed

#### `src/codemie/service/assistant_generator_service.py`

Three methods receive the read + enrich + finally-clear pattern:

- `generate_assistant_details()` — success `send_log_metric` at ~line 161 (ASSISTANT_GENERATOR_TOTAL_METRIC)
- `generate_assistant_prompt()` — success `send_log_metric` at ~line 253 (PROMPT_GENERATOR_TOTAL_METRIC)
- `generate_refine_prompt()` — success `send_log_metric` at ~line 320 (ASSISTANT_GENERATOR_TOTAL_METRIC)

Token attributes added to each success metric call:
```python
MetricsAttributes.INPUT_TOKENS: tokens_usage.input_tokens,
MetricsAttributes.OUTPUT_TOKENS: tokens_usage.output_tokens,
MetricsAttributes.CACHE_READ_INPUT_TOKENS: tokens_usage.cached_tokens,
MetricsAttributes.MONEY_SPENT: tokens_usage.money_spent,
MetricsAttributes.CACHED_TOKENS_MONEY_SPENT: tokens_usage.cached_tokens_money_spent,
MetricsAttributes.CACHE_CREATION_TOKENS_MONEY_SPENT: tokens_usage.cached_tokens_creation_money_spent,
```

All attribute keys already exist in `MetricsAttributes` (`metrics_constants.py`).

#### `src/codemie/service/skill_generator_service.py`

Two methods:

- `generate_skill_details()` — has success metric; uses `get_llm_by_credentials(llm_model, request_id)` directly (not `PromptGeneratorChain`), but callback still attaches. Add summary read + enrich + finally-clear guarded by `if request_id:`.
- `refine_skill()` — **currently has no success `send_log_metric` at all** (only the error path). Add a success call with `SKILL_GENERATOR_TOTAL_METRIC` + token attributes + finally-clear.

#### `src/codemie/service/analytics/metric_names.py`

Add three entries to the `MetricName` enum:
```python
ASSISTANT_GENERATOR_TOTAL = "codemie_assistant_generator_total"
PROMPT_GENERATOR_TOTAL = "codemie_prompt_generator_total"
SKILL_GENERATOR_TOTAL = "codemie_skill_generator_total"
```

Add all three to `MetricName.SPENDING_METRICS` group so analytics queries that use this group automatically include generator costs.

#### `src/codemie/service/analytics/handlers/summary_handler.py`

Add the three new `MetricName` values to the `platform_llm_cost` aggregation's `terms` filter:
```python
"platform_llm_cost": {
    "filter": {
        "terms": {
            METRIC_NAME_KEYWORD_FIELD: [
                MetricName.CONVERSATION_ASSISTANT_USAGE.value,
                MetricName.WORKFLOW_EXECUTION_TOTAL.value,
                MetricName.DATASOURCE_TOKENS_USAGE.value,
                MetricName.ASSISTANT_GENERATOR_TOTAL.value,   # new
                MetricName.PROMPT_GENERATOR_TOTAL.value,      # new
                MetricName.SKILL_GENERATOR_TOTAL.value,       # new
            ]
        }
    },
    ...
}
```

This makes generator spending visible as "Platform LLM Cost" in the Insights summary view, not just "Total Money Spent".

### Data Flow (after fix)

```
LLM call
  → TokensCalculationCallback.on_llm_end()
  → RequestSummaryManager.update_llm_run(request_id, LLMRun)
  → [chain returns]
  → request_summary_manager.get_summary(request_id)  ← NEW
  → summary.tokens_usage                              ← NEW
  → send_log_metric(METRIC, {... token attrs})        ← NEW attrs
  → Elasticsearch codemie_metrics_logs*
  → summary_handler.platform_llm_cost aggregation    ← includes new metric names
  → Insights "Platform LLM Cost"
  [finally]
  → request_summary_manager.clear_summary(request_id) ← NEW (leak fix)
```

## Error Handling

- `get_summary()` returns an empty `TokensUsage(input_tokens=0, output_tokens=0, money_spent=0)` if no runs were accumulated — safe to emit with zero values.
- `clear_summary()` is idempotent and safe to call with unknown `request_id` — no-op if absent.
- Placing `clear_summary()` in `finally` ensures cleanup even when `send_log_metric` raises (e.g., ES unavailable).

## Testing

**Unit tests** (existing test files for each service):
- Mock `request_summary_manager.get_summary()` to return a `RequestSummary` with known `tokens_usage`
- Assert `send_log_metric` is called with `money_spent` > 0
- Assert `clear_summary(request_id)` is called exactly once per invocation
- Assert `clear_summary` is called even when the success path raises

**Integration smoke test:**
- Call `POST /v1/assistants/refine` locally
- Query Elasticsearch `codemie_metrics_logs*` for `metric_name = codemie_assistant_generator_total` with `money_spent > 0`

**Leak check:**
- Before fix: `RequestSummaryManager().request_summaries` grows after each generator call
- After fix: dict is empty after each call completes
