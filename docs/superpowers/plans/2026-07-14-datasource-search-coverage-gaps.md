# Datasource Search ES Metrics Coverage Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate `request_id` from the datasource search REST API through to search services so that LLM routing calls and embedding calls are tracked in Elasticsearch metrics.

**Architecture:** Add an optional `request_id` field to `DatasourceSearchInvokeRequest`, inject it into tool metadata inside `invoke_datasource_search()`, and emit a token metric in a `finally` block mirroring the existing tool invocation pattern. Separately, add a manual `LLMRun` injection at each `embed_query()` call site using the same pattern as `DatasourceMonitoringCallback.on_split_documents()`.

**Tech Stack:** Python, pytest-mock, pydantic, `request_summary_manager.LLMRun`

## Global Constraints

- `request_id` is optional everywhere — callers that omit it get today's (no-op) behaviour.
- No new metric names or monitoring services — reuse `TOOLS_USAGE_TOKENS_METRIC`.
- `SearchAndRerankTool` / `ToolkitLookupService` are **out of scope** (negligible cost, disproportionate threading).
- All tests: `poetry run pytest <path> -v`

---

### Task 1: Add `request_id` to model + propagate through `invoke_datasource_search`

**Files:**
- Modify: `src/codemie/rest_api/models/tool.py:61-65`
- Modify: `src/codemie/service/tools/tool_execution_service.py:119-125`
- Modify: `tests/codemie/service/tools/test_tool_execution_search.py`

**Interfaces:**
- Produces: `DatasourceSearchInvokeRequest.request_id: Optional[str] = None`
- Produces: `invoke_datasource_search` sets `search_tool.metadata[REQUEST_ID]` and calls `emit_llm_token_metric` / `request_summary_manager.clear_summary` when `request_id` is truthy

- [ ] **Step 1: Write the failing tests**

Add to `tests/codemie/service/tools/test_tool_execution_search.py`:

```python
from codemie.core.constants import REQUEST_ID

_SVC = "codemie.service.tools.tool_execution_service"


def test_invoke_datasource_search_injects_request_id_in_metadata():
    """REQUEST_ID must land in tool metadata when request_id is provided."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "my-project"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = "req-abc-123"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_kb_my-index"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric"):
            with patch(f"{_SVC}.request_summary_manager"):
                ToolExecutionService.invoke_datasource_search(datasource, request)

    assert mock_search_tool.metadata[REQUEST_ID] == "req-abc-123"


def test_invoke_datasource_search_emits_token_metric_with_real_attrs():
    """emit_llm_token_metric is called with tool.name and datasource.project_name."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "my-project"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = "req-abc-123"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_kb_my-index"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric") as mock_emit:
            with patch(f"{_SVC}.request_summary_manager"):
                ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_emit.assert_called_once()
    call_kwargs = mock_emit.call_args[1]
    assert call_kwargs["request_id"] == "req-abc-123"
    assert call_kwargs["base_attributes"][MetricsAttributes.TOOL_NAME] == "search_kb_my-index"
    assert call_kwargs["base_attributes"][MetricsAttributes.PROJECT] == "my-project"


def test_invoke_datasource_search_clears_summary_in_finally_on_error():
    """Summary is cleared even when execute() raises."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "proj"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "q"
    request.llm_model = "gpt-4"
    request.request_id = "req-err"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(side_effect=RuntimeError("ES down"))

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric"):
            with patch(f"{_SVC}.request_summary_manager") as mock_rsm:
                with pytest.raises(RuntimeError):
                    ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_rsm.clear_summary.assert_called_once_with("req-err")


def test_invoke_datasource_search_skips_tracking_when_no_request_id():
    """No metric emission or summary clear when request_id is absent."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "proj"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "q"
    request.llm_model = "gpt-4"
    request.request_id = None

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric") as mock_emit:
            with patch(f"{_SVC}.request_summary_manager") as mock_rsm:
                ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_emit.assert_not_called()
    mock_rsm.clear_summary.assert_not_called()
```

Also add `import pytest` to the imports in that file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/codemie/service/tools/test_tool_execution_search.py::test_invoke_datasource_search_injects_request_id_in_metadata tests/codemie/service/tools/test_tool_execution_search.py::test_invoke_datasource_search_emits_token_metric_with_real_attrs tests/codemie/service/tools/test_tool_execution_search.py::test_invoke_datasource_search_clears_summary_in_finally_on_error tests/codemie/service/tools/test_tool_execution_search.py::test_invoke_datasource_search_skips_tracking_when_no_request_id -v
```

Expected: FAIL — `DatasourceSearchInvokeRequest` has no `request_id`, metadata assertion fails.

- [ ] **Step 3: Add `request_id` to `DatasourceSearchInvokeRequest`**

In `src/codemie/rest_api/models/tool.py`, update the class (no new imports needed — `Optional` is already imported):

```python
class DatasourceSearchInvokeRequest(BaseModel):
    query: str
    llm_model: str = Field(default=llm_service.default_llm_model)
    code_search_params: Optional[CodeDatasourceSearchParams] = None
    params: Optional[InvokeParams] = None
    request_id: Optional[str] = None
```

- [ ] **Step 4: Update `invoke_datasource_search` in `tool_execution_service.py`**

Replace the current method body (lines 119-125):

```python
@classmethod
def invoke_datasource_search(cls, datasource: IndexInfo, request: DatasourceSearchInvokeRequest):
    """
    Invoke a search operation on a specific datasource.
    """
    search_tool = cls.get_search_tool(datasource, request)
    search_tool.metadata = {
        'llm_model': request.llm_model,
        REQUEST_ID: request.request_id or "",
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

No new imports needed — `REQUEST_ID`, `emit_llm_token_metric`, `TOOLS_USAGE_TOKENS_METRIC`, `MetricsAttributes`, and `request_summary_manager` are all already imported at the top of this file.

- [ ] **Step 5: Also update the existing `test_invoke_datasource_search` to include REQUEST_ID**

The existing assertion `assert mock_search_tool.metadata == {'llm_model': request.llm_model}` will now fail. Update it:

```python
def test_invoke_datasource_search():
    """Test invoking datasource search."""
    datasource = Mock(spec=IndexInfo)
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = None  # no tracking — keeps the test focused on basic execution

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(return_value="search results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool) as mock_get_tool:
        result = ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_get_tool.assert_called_once_with(datasource, request)
    mock_search_tool.execute.assert_called_once_with(query=request.query)
    assert mock_search_tool.metadata == {'llm_model': request.llm_model, REQUEST_ID: ""}
    assert result == "search results"
```

- [ ] **Step 6: Run all tests in the file to verify they pass**

```bash
poetry run pytest tests/codemie/service/tools/test_tool_execution_search.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codemie/rest_api/models/tool.py \
        src/codemie/service/tools/tool_execution_service.py \
        tests/codemie/service/tools/test_tool_execution_search.py
git commit -m "feat(EPMCDME-13429): propagate request_id through datasource search API path"
```

---

### Task 2: Track embedding tokens in `SearchAndRerankKB._knn_vector_search`

**Files:**
- Modify: `src/codemie/service/search_and_rerank/kb.py:325-368`
- Modify: `tests/codemie/service/search_and_rerank/test_kb.py`

**Interfaces:**
- Consumes: `self.request_id` (already a dataclass field on `SearchAndRerankKB`)
- Produces: when `self.request_id` is truthy, calls `request_summary_manager.update_llm_run` after `embed_query()` with an `LLMRun` whose `output_tokens=0` and `llm_model` is the deployment name

- [ ] **Step 1: Write the failing tests**

Add to `tests/codemie/service/search_and_rerank/test_kb.py`:

```python
from unittest.mock import MagicMock, call, patch

from codemie.service.request_summary_manager import LLMRun


class TestKBEmbeddingTracking:
    """LLMRun is pushed to request_summary_manager after embed_query when request_id is set."""

    @pytest.fixture
    def kb_index_mock(self):
        mock = MagicMock()
        mock.repo_name = "test_repo"
        mock.project_name = "test_project"
        mock.full_name = "test_repo"
        mock.embeddings_model = "text-embedding-ada-002"
        mock.get_index_identifier.return_value = "test-index"
        return mock

    @pytest.fixture
    def kb_with_request_id(self, kb_index_mock):
        from codemie.service.llm_service.llm_service import llm_service
        with patch('codemie.service.search_and_rerank.kb.SearchAndRerankKB.index_name',
                   new_callable=lambda: property(lambda self: "test-index")):
            return SearchAndRerankKB(
                query="find docs about auth",
                kb_index=kb_index_mock,
                llm_model=llm_service.default_llm_model,
                top_k=5,
                request_id="req-embed-001",
            )

    def test_pushes_llm_run_when_request_id_set(self, mocker, kb_index_mock):
        """A LLMRun with output_tokens=0 is added to request_summary_manager."""
        instance = SearchAndRerankKB(
            query="find docs",
            kb_index=kb_index_mock,
            llm_model="gpt-4",
            top_k=5,
            request_id="req-embed-001",
        )
        # patch index_name to avoid ES call
        instance.index_name = "test-index"

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3]

        mocker.patch('codemie.service.search_and_rerank.kb.get_embeddings_model', return_value=mock_embeddings)
        mocker.patch('codemie.service.search_and_rerank.kb.llm_service.get_embedding_deployment_name',
                     return_value="ada-002-deployment")

        mock_model_costs = MagicMock()
        mock_model_costs.input = 0.0001
        mocker.patch('codemie.service.search_and_rerank.kb.llm_service.get_embeddings_model_cost',
                     return_value=mock_model_costs)

        mocker.patch('codemie.service.search_and_rerank.kb.calculate_tokens', return_value=5)

        mock_rsm = mocker.patch('codemie.service.search_and_rerank.kb.request_summary_manager')

        es_mock = mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankBase.es', new_callable=mocker.PropertyMock
        )
        es_mock.return_value.search.return_value = {"hits": {"hits": []}}

        instance._knn_vector_search()

        mock_rsm.update_llm_run.assert_called_once()
        llm_run_arg = mock_rsm.update_llm_run.call_args[1]["llm_run"]
        assert isinstance(llm_run_arg, LLMRun)
        assert llm_run_arg.output_tokens == 0
        assert llm_run_arg.input_tokens == 5
        assert llm_run_arg.llm_model == "ada-002-deployment"
        assert llm_run_arg.money_spent == 5 * 0.0001

    def test_skips_llm_run_when_request_id_absent(self, mocker, kb_index_mock):
        """No update_llm_run call when request_id is empty string."""
        instance = SearchAndRerankKB(
            query="find docs",
            kb_index=kb_index_mock,
            llm_model="gpt-4",
            top_k=5,
            request_id="",
        )
        instance.index_name = "test-index"

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3]
        mocker.patch('codemie.service.search_and_rerank.kb.get_embeddings_model', return_value=mock_embeddings)
        mocker.patch('codemie.service.search_and_rerank.kb.llm_service.get_embedding_deployment_name',
                     return_value="ada-002-deployment")

        mock_rsm = mocker.patch('codemie.service.search_and_rerank.kb.request_summary_manager')

        es_mock = mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankBase.es', new_callable=mocker.PropertyMock
        )
        es_mock.return_value.search.return_value = {"hits": {"hits": []}}

        instance._knn_vector_search()

        mock_rsm.update_llm_run.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/codemie/service/search_and_rerank/test_kb.py::TestKBEmbeddingTracking -v
```

Expected: FAIL — `request_summary_manager` is not imported in `kb.py`, `update_llm_run` is never called.

- [ ] **Step 3: Add imports to `kb.py`**

Add to the import block in `src/codemie/service/search_and_rerank/kb.py`:

```python
import uuid

from codemie.core.utils import calculate_tokens
from codemie.service.request_summary_manager import LLMRun, request_summary_manager
```

- [ ] **Step 4: Inject `LLMRun` after `embed_query` in `_knn_vector_search`**

In `src/codemie/service/search_and_rerank/kb.py`, update `_knn_vector_search` — after the line
`query_vector = embeddings.embed_query(self.query)` (line ~344), add:

```python
query_vector = embeddings.embed_query(self.query)

if self.request_id:
    model_costs = llm_service.get_embeddings_model_cost(embeddings_model)
    input_tokens = calculate_tokens(self.query)
    request_summary_manager.update_llm_run(
        request_id=self.request_id,
        llm_run=LLMRun(
            run_id=str(uuid.uuid4()),
            input_tokens=input_tokens,
            output_tokens=0,
            money_spent=input_tokens * model_costs.input,
            llm_model=embeddings_model,
        ),
    )
```

Note: the local variable holding the deployment name is `embeddings_model` in `kb.py` (see line 340: `embeddings_model = llm_service.get_embedding_deployment_name(...)`).

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/codemie/service/search_and_rerank/test_kb.py -v
```

Expected: all tests PASS (including existing ones).

- [ ] **Step 6: Commit**

```bash
git add src/codemie/service/search_and_rerank/kb.py \
        tests/codemie/service/search_and_rerank/test_kb.py
git commit -m "feat(EPMCDME-13429): track KB embedding tokens in request_summary_manager"
```

---

### Task 3: Add `request_id` to `SearchAndRerankCode` + track its embeddings + update call sites

**Files:**
- Modify: `src/codemie/service/search_and_rerank/code.py:50-83` (constructor), `code.py:123-155` (`_knn_vector_search`)
- Modify: `src/codemie/agents/tools/code/tools.py:149,197`
- Modify: `tests/codemie/service/search_and_rerank/test_code.py`

**Interfaces:**
- Consumes: nothing new — `request_id` is threaded from `self.metadata.get(REQUEST_ID, "")` at the call sites in `tools.py`
- Produces: `SearchAndRerankCode.__init__` accepts `request_id: Optional[str] = None`; after `embed_query()` in `_knn_vector_search`, calls `request_summary_manager.update_llm_run` when truthy

- [ ] **Step 1: Write the failing tests**

Add to `tests/codemie/service/search_and_rerank/test_code.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

from codemie.service.request_summary_manager import LLMRun


class TestCodeEmbeddingTracking:
    @pytest.fixture
    def code_fields(self):
        from codemie.core.constants import CodeIndexType
        from codemie.core.models import CodeFields
        return CodeFields(app_name='test_app', repo_name='test_repo', index_type=CodeIndexType.CODE)

    def _make_instance(self, mocker, code_fields, request_id=""):
        mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankCode._get_index_name',
            return_value='test_index',
        )
        return SearchAndRerankCode(
            query="test query",
            keywords_list=[],
            file_path=[],
            code_fields=code_fields,
            top_k=10,
            request_id=request_id,
        )

    def test_stores_request_id(self, mocker, code_fields):
        instance = self._make_instance(mocker, code_fields, request_id="req-code-001")
        assert instance.request_id == "req-code-001"

    def test_request_id_defaults_to_empty_string(self, mocker, code_fields):
        mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankCode._get_index_name',
            return_value='test_index',
        )
        instance = SearchAndRerankCode(
            query="test query", keywords_list=[], file_path=[], code_fields=code_fields, top_k=10
        )
        assert instance.request_id is None

    def test_pushes_llm_run_when_request_id_set(self, mocker, code_fields):
        """LLMRun pushed to request_summary_manager after embed_query when request_id truthy."""
        instance = self._make_instance(mocker, code_fields, request_id="req-code-001")

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3]
        mocker.patch('codemie.service.search_and_rerank.code.get_embeddings_model', return_value=mock_embeddings)

        mock_git_repo = MagicMock()
        mock_git_repo.embeddings_model = "text-embedding-ada-002"
        mocker.patch('codemie.service.search_and_rerank.code.get_repo_from_fields', return_value=mock_git_repo)

        mocker.patch(
            'codemie.service.search_and_rerank.code.llm_service.get_embedding_deployment_name',
            return_value="ada-002-deployment",
        )

        mock_model_costs = MagicMock()
        mock_model_costs.input = 0.0001
        mocker.patch(
            'codemie.service.search_and_rerank.code.llm_service.get_embeddings_model_cost',
            return_value=mock_model_costs,
        )

        mocker.patch('codemie.service.search_and_rerank.code.calculate_tokens', return_value=4)

        mock_rsm = mocker.patch('codemie.service.search_and_rerank.code.request_summary_manager')

        es_mock = mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankBase.es', new_callable=mocker.PropertyMock
        )
        es_mock.return_value.search.return_value = {"hits": {"hits": []}}

        instance._knn_vector_search()

        mock_rsm.update_llm_run.assert_called_once()
        llm_run_arg = mock_rsm.update_llm_run.call_args[1]["llm_run"]
        assert isinstance(llm_run_arg, LLMRun)
        assert llm_run_arg.output_tokens == 0
        assert llm_run_arg.input_tokens == 4
        assert llm_run_arg.llm_model == "ada-002-deployment"

    def test_skips_llm_run_when_request_id_absent(self, mocker, code_fields):
        """No update_llm_run call when request_id is None."""
        instance = self._make_instance(mocker, code_fields, request_id=None)

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3]
        mocker.patch('codemie.service.search_and_rerank.code.get_embeddings_model', return_value=mock_embeddings)

        mock_git_repo = MagicMock()
        mock_git_repo.embeddings_model = "text-embedding-ada-002"
        mocker.patch('codemie.service.search_and_rerank.code.get_repo_from_fields', return_value=mock_git_repo)
        mocker.patch(
            'codemie.service.search_and_rerank.code.llm_service.get_embedding_deployment_name',
            return_value="ada-002-deployment",
        )

        mock_rsm = mocker.patch('codemie.service.search_and_rerank.code.request_summary_manager')

        es_mock = mocker.patch(
            'codemie.service.search_and_rerank.SearchAndRerankBase.es', new_callable=mocker.PropertyMock
        )
        es_mock.return_value.search.return_value = {"hits": {"hits": []}}

        instance._knn_vector_search()

        mock_rsm.update_llm_run.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/codemie/service/search_and_rerank/test_code.py::TestCodeEmbeddingTracking -v
```

Expected: FAIL — `SearchAndRerankCode` has no `request_id` parameter.

- [ ] **Step 3: Add `request_id` to `SearchAndRerankCode.__init__` in `code.py`**

In `src/codemie/service/search_and_rerank/code.py`:

1. Update the `from typing import` line to add `Optional`:
```python
from typing import Any, List, Optional, Tuple
```

2. Add three new imports after the existing ones:
```python
import uuid

from codemie.core.utils import calculate_tokens
from codemie.service.request_summary_manager import LLMRun, request_summary_manager
```

3. Update `__init__` — add `request_id` parameter and assignment:
```python
def __init__(
    self,
    query: str,
    keywords_list: List[str],
    file_path: List[str],
    code_fields: CodeFields,
    top_k: int,
    use_knn_search: bool = True,
    request_id: Optional[str] = None,
):
    if not query.strip():
        raise ValueError("Query string cannot be empty")
    if top_k < 1:
        raise ValueError("top_k must be greater than 0")

    self.query = query
    self.keywords_list = keywords_list or []
    self.file_path = file_path or []
    self.code_fields = code_fields
    self.top_k = top_k
    self.use_knn_search = use_knn_search
    self.request_id = request_id
    self.index_name = self._get_index_name()
```

- [ ] **Step 4: Inject `LLMRun` after `embed_query` in `_knn_vector_search` in `code.py`**

In `_knn_vector_search`, after `query_vector = embeddings.embed_query(self.query)` (line ~138):

```python
query_vector = embeddings.embed_query(self.query)

if self.request_id:
    model_costs = llm_service.get_embeddings_model_cost(embeddings_model)
    input_tokens = calculate_tokens(self.query)
    request_summary_manager.update_llm_run(
        request_id=self.request_id,
        llm_run=LLMRun(
            run_id=str(uuid.uuid4()),
            input_tokens=input_tokens,
            output_tokens=0,
            money_spent=input_tokens * model_costs.input,
            llm_model=embeddings_model,
        ),
    )
```

Note: the local variable is `embeddings_model` in `code.py` (line 136: `embeddings_model = llm_service.get_embedding_deployment_name(git_repo.embeddings_model)`).

- [ ] **Step 5: Run code search tests to verify they pass**

```bash
poetry run pytest tests/codemie/service/search_and_rerank/test_code.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Thread `request_id` through the two call sites in `tools.py`**

In `src/codemie/agents/tools/code/tools.py`, update both `SearchAndRerankCode` instantiations to pass `request_id`.

**Site 1** — `SearchCodeRepoTool.execute` (around line 149):
```python
search_results = SearchAndRerankCode(
    query=query,
    keywords_list=keywords_list,
    file_path=file_path,
    code_fields=self.code_fields,
    top_k=self.top_k,
    request_id=self.metadata.get(REQUEST_ID, ""),
).execute()
```

**Site 2** — `SearchCodeRepoByPathsTool.execute` (around line 197):
```python
search_results = SearchAndRerankCode(
    query=query,
    keywords_list=keywords_list,
    file_path=file_path,
    code_fields=self.code_fields,
    top_k=self.top_k,
    use_knn_search=False,
    request_id=self.metadata.get(REQUEST_ID, ""),
).execute()
```

Verify `REQUEST_ID` is already imported at the top of `tools.py`:
```bash
grep "REQUEST_ID" src/codemie/agents/tools/code/tools.py
```
If not present, add: `from codemie.core.constants import REQUEST_ID`

- [ ] **Step 7: Run full test suite for affected packages**

```bash
poetry run pytest tests/codemie/service/search_and_rerank/ tests/codemie/service/tools/ tests/codemie/agents/tools/code/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/codemie/service/search_and_rerank/code.py \
        src/codemie/agents/tools/code/tools.py \
        tests/codemie/service/search_and_rerank/test_code.py
git commit -m "feat(EPMCDME-13429): track code embedding tokens and thread request_id through SearchAndRerankCode"
```
