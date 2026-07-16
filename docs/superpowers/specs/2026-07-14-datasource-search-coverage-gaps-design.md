# Spec: Close ES Metrics Coverage Gaps for Datasource Search

**Ticket**: EPMCDME-13429 (follow-up)
**Date**: 2026-07-14
**Complexity**: S

---

## Problem

A LiteLLM vs ES comparison revealed that LLM calls triggered by the datasource search REST
API (`POST /api/v1/index/{id}/search`) are recorded in LiteLLM's spend logs but never
reported to Elasticsearch metrics. Two call types are missing:

1. **LLM routing calls** — `SearchAndRerankKB._llm_routing()` uses `get_llm_by_credentials()`
   to select relevant KB sources via a short gpt-4.1 prompt (~108 in / ~8 out tokens).
   Because `request_id` never reaches this call site from the API path, no
   `TokensCalculationCallback` is attached and the call goes untracked.

2. **Embedding calls** — `_knn_vector_search()` in `SearchAndRerankKB` and
   `SearchAndRerankCode` calls `embed_query()`. Embeddings bypass LangChain's callback
   system entirely, so even if a callback were attached it would not fire.

The root cause is the same for both: `invoke_datasource_search()` sets
`search_tool.metadata = {'llm_model': ...}` without a `REQUEST_ID`, and
`DatasourceSearchInvokeRequest` has no `request_id` field.

Agent-driven search paths (where tools are invoked through the agent executor) are not
affected — agents always inject `REQUEST_ID` into tool metadata.

---

## Chosen Approach

Propagate an optional `request_id` from the REST API request down to the search services.
No new monitoring infrastructure is needed: the LLM routing gap closes automatically once
`request_id` reaches `get_llm_by_credentials()`, and the embedding gap is closed by
injecting a manual `LLMRun` at the `embed_query()` call site — the same pattern already
used by `DatasourceMonitoringCallback.on_split_documents()` for indexing-time embeddings.

`SearchAndRerankTool` (used by `ToolkitLookupService` for dynamic tool selection) is
deliberately out of scope: its per-call embedding cost (~$0.0000047) is negligible and
threading `request_id` through `SmartToolSelector` would be disproportionate.

---

## Data Flow (after fix)

```
POST /api/v1/index/{id}/search  { request_id: "abc" }
  └─ invoke_datasource_search(datasource, request)
       ├─ search_tool.metadata[REQUEST_ID] = "abc"
       │
       ├─ SearchKBTool.execute(query)
       │    └─ SearchAndRerankKB(request_id="abc").execute()
       │         ├─ _knn_vector_search()
       │         │    └─ embed_query(query)
       │         │         └─ LLMRun(embedding, input_tokens, cost)
       │         │              └─ request_summary_manager.update_llm_run("abc", ...)
       │         │
       │         └─ _llm_routing()
       │              └─ get_llm_by_credentials(request_id="abc")
       │                   └─ TokensCalculationCallback attached
       │                        └─ on_llm_end → request_summary_manager.update_llm_run("abc", ...)
       │
       └─ [finally] emit_llm_token_metric(TOOLS_USAGE_TOKENS_METRIC, request_id="abc",
                        tool_name=search_tool.name, project=datasource.project_name)
              └─ request_summary_manager.clear_summary("abc")
```

When `request_id` is absent (caller omits it), `search_tool.metadata[REQUEST_ID]` is `""`
and the `finally` block's `if request.request_id` guard skips emission — identical to
today's behaviour.

---

## File Changes

### 1. `src/codemie/rest_api/models/tool.py`

Add `request_id` to `DatasourceSearchInvokeRequest`:

```python
class DatasourceSearchInvokeRequest(BaseModel):
    query: str
    llm_model: str = Field(default=llm_service.default_llm_model)
    code_search_params: Optional[CodeDatasourceSearchParams] = None
    params: Optional[InvokeParams] = None
    request_id: Optional[str] = None          # new — propagated into search tool metadata
```

### 2. `src/codemie/service/tools/tool_execution_service.py`

**`invoke_datasource_search()`** — two changes:

```python
@classmethod
def invoke_datasource_search(cls, datasource: IndexInfo, request: DatasourceSearchInvokeRequest):
    search_tool = cls.get_search_tool(datasource, request)
    search_tool.metadata = {
        'llm_model': request.llm_model,
        REQUEST_ID: request.request_id or "",   # propagate request_id
    }
    try:
        return search_tool.execute(query=request.query)
    finally:
        if request.request_id:
            emit_llm_token_metric(
                name=TOOLS_USAGE_TOKENS_METRIC,
                request_id=request.request_id,
                base_attributes={
                    MetricsAttributes.LLM_MODEL: request.llm_model or "default",
                    MetricsAttributes.TOOL_NAME: search_tool.name,
                    MetricsAttributes.PROJECT: datasource.project_name,
                },
            )
            request_summary_manager.clear_summary(request.request_id)
```

Add imports: `emit_llm_token_metric`, `TOOLS_USAGE_TOKENS_METRIC`, `MetricsAttributes`,
`request_summary_manager`, `REQUEST_ID` (most are already imported in this file).

### 3. `src/codemie/service/search_and_rerank/kb.py`

**`_knn_vector_search()`** — inject an `LLMRun` after `embed_query()`:

```python
query_vector = embeddings.embed_query(self.query)

if self.request_id:
    model_costs = llm_service.get_embeddings_model_cost(embedding_deployment_name)
    input_tokens = calculate_tokens(self.query)
    request_summary_manager.update_llm_run(
        request_id=self.request_id,
        llm_run=LLMRun(
            run_id=str(uuid.uuid4()),
            input_tokens=input_tokens,
            output_tokens=0,
            money_spent=input_tokens * model_costs.input,
            llm_model=embedding_deployment_name,
        ),
    )
```

Add imports: `uuid`, `calculate_tokens`, `llm_service`, `request_summary_manager`, `LLMRun`.

`self.request_id` is already a field on the dataclass — no constructor changes needed.

### 4. `src/codemie/service/search_and_rerank/code.py`

**`SearchAndRerankCode.__init__()`** — add optional `request_id` parameter:

```python
def __init__(
    self,
    query: str,
    keywords_list: List[str],
    file_path: List[str],
    code_fields: CodeFields,
    top_k: int,
    use_knn_search: bool = True,
    request_id: Optional[str] = None,   # new
):
    ...
    self.request_id = request_id
```

**`_knn_vector_search()`** — same `LLMRun` injection as `kb.py` (only reached when
`use_knn_search=True`, which is the default):

```python
query_vector = embeddings.embed_query(self.query)

if self.request_id:
    model_costs = llm_service.get_embeddings_model_cost(embedding_deployment_name)
    input_tokens = calculate_tokens(self.query)
    request_summary_manager.update_llm_run(
        request_id=self.request_id,
        llm_run=LLMRun(
            run_id=str(uuid.uuid4()),
            input_tokens=input_tokens,
            output_tokens=0,
            money_spent=input_tokens * model_costs.input,
            llm_model=embedding_deployment_name,
        ),
    )
```

**`src/codemie/agents/tools/code/tools.py`** — update both `SearchAndRerankCode`
instantiation sites (lines 149, 197) to pass `request_id`:

```python
search_results = SearchAndRerankCode(
    query=query,
    keywords_list=keywords_list,
    file_path=file_path,
    code_fields=self.code_fields,
    top_k=self.top_k,
    request_id=self.metadata.get(REQUEST_ID, ""),   # new
).execute()
```

---

## What Does Not Change

- `SearchAndRerankKB._llm_routing()` — no change; works automatically once `request_id`
  flows through via `self.request_id`.
- `SearchAndRerankTool` and `ToolkitLookupService` — out of scope.
- `SearchAndRerankMarketplace` — extends `SearchAndRerankKB`, inherits `request_id` from
  the dataclass; no separate change needed.
- All existing monitoring services, metric names, and agent-driven search paths — unchanged.
- `DatasourceSearchInvokeRequest.request_id` is optional; callers that omit it retain
  today's behaviour exactly.

---

## Testing

- `tests/codemie/service/tools/test_tool_execution_service.py` — verify that
  `invoke_datasource_search` sets `REQUEST_ID` in metadata and calls
  `emit_llm_token_metric` + `clear_summary` when `request_id` is provided; verify it
  skips emission when `request_id` is absent.
- `tests/codemie/service/search_and_rerank/test_kb.py` — verify that
  `_knn_vector_search` pushes an `LLMRun` to `request_summary_manager` when
  `request_id` is set and skips it when absent.
- `tests/codemie/service/search_and_rerank/test_code.py` — same for `SearchAndRerankCode`.
- `tests/codemie/agents/tools/code/test_tools.py` — verify `request_id` is passed through
  to `SearchAndRerankCode`.
