# Spec: Workflow Generator Service

## Purpose

`WorkflowGeneratorService` accepts a natural language query and returns a validated `CreateWorkflowRequest` using a 5-node LangGraph `StateGraph`. Optionally persists the generated workflow. Exposed via `POST /v1/workflows/generate`.

---

## Architecture

### New subpackage: `src/codemie/workflows/workflow_generator/`

```
src/codemie/workflows/workflow_generator/
├── __init__.py
├── state.py                      ← WorkflowGeneratorState TypedDict
├── models.py                     ← Pydantic output schemas per LLM step
├── nodes/
│   ├── __init__.py
│   ├── intent_analysis.py        ← node 1: parse NL → WorkflowIntent
│   ├── node_mapping.py           ← node 2: steps → NodeMappingPlan
│   ├── config_generation.py      ← node 3: plan → GeneratedWorkflowConfig
│   ├── validation.py             ← node 4: validate Pydantic; retry loop
│   └── result.py                 ← node 5: assemble CreateWorkflowRequest
└── workflow.py                   ← WorkflowGeneratorGraph (StateGraph builder)
```

Additional files:
- `src/codemie/templates/agents/workflow_generator_prompts.py` — prompt templates
- `src/codemie/service/workflow_generator_service.py` — replaces one-line stub
- `src/codemie/rest_api/models/workflow_generator.py` — request/response models
- `src/codemie/rest_api/routers/workflow.py` — new endpoint appended
- `src/codemie/service/monitoring/metrics_constants.py` — 2 new metric constants

---

## State

```python
class WorkflowGeneratorState(TypedDict):
    nl_query: str
    intent: Optional[WorkflowIntent]
    node_plan: Optional[NodeMappingPlan]
    generated_config: Optional[GeneratedWorkflowConfig]
    validation_errors: list[str]
    validation_attempts: int
    result: Optional[CreateWorkflowRequest]
    available_tools: list[dict]   # injected from ToolsInfoService
    project: str                  # from user.current_project
    error: Optional[str]
```

---

## LLM Output Models (`models.py`)

```python
class WorkflowStep(BaseModel):
    id: str
    description: str
    state_type: Literal["agent", "tool", "custom_node"]
    next_step_id: Optional[str]

class WorkflowIntent(BaseModel):
    workflow_name: str
    workflow_description: str
    steps: list[WorkflowStep]

class MappedNode(BaseModel):
    step_id: str
    state_type: Literal["agent", "tool", "custom_node"]
    assistant_ref: Optional[str]   # assistant name or id
    tool_ref: Optional[str]        # tool name from catalog
    custom_node_ref: Optional[str]
    task: str

class NodeMappingPlan(BaseModel):
    nodes: list[MappedNode]

class GeneratedWorkflowConfig(BaseModel):
    states: list[dict]        # raw dicts, validated by WorkflowState Pydantic in node 4
    assistants: list[dict]    # raw WorkflowAssistant dicts
    tools: list[dict]         # raw WorkflowTool dicts
    custom_nodes: list[dict]  # raw CustomWorkflowNode dicts
```

---

## Graph Data Flow

```
NL query
  ↓
IntentAnalysisNode    → WorkflowIntent (name, description, steps[])
  ↓
NodeMappingNode       → NodeMappingPlan (step→state_type, tool/assistant refs)
  ↓
ConfigGenerationNode  → GeneratedWorkflowConfig (states[], assistants[], tools[])
  ↓
ValidationNode        → Pydantic validation of each WorkflowState
  │  fail (≤3 attempts) → back to ConfigGenerationNode with error context
  │  fail (>3 attempts) → error state
  ↓ pass
ResultNode            → CreateWorkflowRequest + guardrail_assignments
```

**Retry loop**: `ValidationNode` attempts `WorkflowState(**state_dict)` for each state + `CreateWorkflowRequest` construction. On `pydantic.ValidationError`, collects error messages into `validation_errors`, increments `validation_attempts`, and routes back to `ConfigGenerationNode` (which re-runs with `validation_errors` injected into the prompt). After 3 failures, sets `state["error"]` and routes to END. `WorkflowGeneratorGraph` checks for `state["error"]` after graph completion and raises `ExtendedHTTPException(500)`.

---

## Prompt Templates (`workflow_generator_prompts.py`)

Three `ChatPromptTemplate` instances:

1. **`INTENT_ANALYSIS_PROMPT`** — system: workflow design expert; user: `{nl_query}` → structured `WorkflowIntent`
2. **`NODE_MAPPING_PROMPT`** — system: maps logical steps to available tools/assistants; user: `{intent}` + `{available_tools}` → `NodeMappingPlan`
3. **`CONFIG_GENERATION_PROMPT`** — system: produces valid CodeMie workflow YAML config; user: `{node_plan}` + optional `{validation_errors}` → `GeneratedWorkflowConfig`

---

## Service (`workflow_generator_service.py`)

```python
class WorkflowGeneratorService:

    @classmethod
    def generate(
        cls,
        nl_query: str,
        user: User,
        llm_model: Optional[str] = None,
        persist: bool = False,
        guardrail_ids: Optional[list[str]] = None,
        request_id: Optional[str] = None,
    ) -> WorkflowGeneratorResponse:
        ...
```

**Steps:**
1. Resolve `llm_model` from `llm_service.default_llm_model` if not provided
2. Load tool catalog via `ToolsInfoService.get_tools_info(user=user)`
3. Build and run `WorkflowGeneratorGraph`
4. Extract `CreateWorkflowRequest` from final state; apply guardrails
5. If `persist=True`: call `WorkflowService.create_workflow(request, user)`
6. Emit `emit_llm_token_metric(WORKFLOW_GENERATOR_TOTAL_METRIC)`
7. Return `WorkflowGeneratorResponse`

**Error path**: any exception → `send_log_metric(WORKFLOW_GENERATOR_ERRORS_METRIC)` → `ExtendedHTTPException(500)`. `finally` block calls `request_summary_manager.clear_summary(request_id)`.

---

## Guardrails

- If `guardrail_ids` is `None` (default): `CreateWorkflowRequest.guardrail_assignments = None` — runtime applies project-level defaults.
- If `guardrail_ids` is provided: build `list[GuardrailAssignmentItem]` from those IDs (mode=`INPUT_OUTPUT`, source=`USER`) and assign to `guardrail_assignments`.

---

## API Endpoint

**File**: `src/codemie/rest_api/routers/workflow.py` (append to existing router)

```
POST /v1/workflows/generate
Auth: authenticate (same as other workflow endpoints)
```

**Request model** (`src/codemie/rest_api/models/workflow_generator.py`):
```python
class WorkflowGeneratorRequest(BaseModel):
    nl_query: str
    llm_model: Optional[str] = None
    persist: bool = False
    guardrail_ids: Optional[list[str]] = None
```

**Response model**:
```python
class WorkflowGeneratorResponse(BaseModel):
    workflow_config: CreateWorkflowRequest
    workflow_id: Optional[str] = None  # set when persist=True
```

**Handler pattern** (mirrors `generate_skill`):
```python
@router.post("/workflows/generate", status_code=200, response_model=WorkflowGeneratorResponse)
def generate_workflow(raw_request: Request, request: WorkflowGeneratorRequest, user: User = Depends(authenticate)):
    request_id = raw_request.state.uuid
    set_logging_info(uuid=request_id, user_id=user.id, user_email=user.username)
    set_llm_context(None, user.current_project, user)
    return WorkflowGeneratorService.generate(
        nl_query=request.nl_query,
        user=user,
        llm_model=request.llm_model,
        persist=request.persist,
        guardrail_ids=request.guardrail_ids,
        request_id=request_id,
    )
```

---

## Monitoring

Add to `metrics_constants.py`:
```python
WORKFLOW_GENERATOR_TOTAL_METRIC = "codemie_workflow_generator_total"
WORKFLOW_GENERATOR_ERRORS_METRIC = "codemie_workflow_generator_errors_total"
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| LLM returns invalid Pydantic config | ValidationNode retries up to 3× with error context |
| 3 retries exhausted | `ExtendedHTTPException(500, "Workflow generation failed after validation retries")` |
| LLM call fails | `ExtendedHTTPException(500, "Failed to generate workflow")` |
| `persist=True`, DB save fails | `ExtendedHTTPException(500, "Failed to persist generated workflow")` |
| All paths | `finally: request_summary_manager.clear_summary(request_id)` |

---

## Testing

**Unit tests** (`tests/service/test_workflow_generator_service.py`):
- Each node independently: mock LLM output → assert correct state transition
- Validation retry: node 3 produces invalid config → node 4 retries → after 3 failures raises exception
- Full graph: mock all LLM calls → assert `CreateWorkflowRequest` produced with correct fields
- Guardrail assignment: assert default guardrails applied; assert override works with `guardrail_ids`

**API tests** (`tests/rest_api/routers/test_workflow_generator.py`):
- `POST /v1/workflows/generate` 200 with mocked `WorkflowGeneratorService.generate`
- `persist=True` path: assert `workflow_id` in response
- Error path: service raises → assert 500 response

---

## Acceptance Criteria

- [ ] `WorkflowGeneratorService.generate(nl_query, user)` returns valid `WorkflowGeneratorResponse`
- [ ] Generated `CreateWorkflowRequest.states` passes Pydantic `WorkflowState` validators
- [ ] Each generated `WorkflowState` has exactly one of `assistant_id`, `tool_id`, `custom_node_id`
- [ ] Guardrail assignments present in response
- [ ] `persist=True` creates `WorkflowConfig` in DB and returns `workflow_id`
- [ ] `POST /v1/workflows/generate` returns 200 with `WorkflowGeneratorResponse`
- [ ] Metrics emitted on success and error paths
- [ ] Unit tests cover each node + retry loop
