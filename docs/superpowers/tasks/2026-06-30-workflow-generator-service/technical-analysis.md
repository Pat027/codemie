# Technical Research

**Task**: workflow generator langgraph chain nl-to-workflow
**Generated**: 2026-06-30T00:00:00Z

---

## 1. Original Context

Workflow Generator Service. This is service for workflow generation from natural language using langgraph chain. Service should accept nl query and create workflow based on requirements. Should operate using pydantic base workflow models @src/codemie/core/workflow_models/workflow_models.py. Each created node should be validated and go through guardrails. Workflows should have guardrails assigned. For workflow configuration and validation use @src/codemie/service/workflow_config/__init__.py. Chain steps: 1. analyse user input, define intentions, define needed steps for execution, workflow states. 2. For each step define needed actions and tools, custom nodes. 3. Generate workflow nodes based on requirements. 4. Create workflow states based on requirements. 5. Validate workflow. Return created configuration.

---

## 2. Codebase Findings

### Existing Implementations

- `src/codemie/service/workflow_generator_service.py` — exists as a stub containing only `class WorkflowGenerator: ...`. This is the greenfield service class where all generation logic must be built.
- `src/codemie/core/workflow_models/workflow_models.py` — canonical Pydantic models for workflow objects: `WorkflowState`, `WorkflowNextState`, `WorkflowAssistant`, `WorkflowTool`, `CustomWorkflowNode`, `WorkflowRetryPolicy`, `WorkflowStateSwitchCondition`, `WorkflowStateSwitch`, `WorkflowStateCondition`, `CreateWorkflowRequest`, `UpdateWorkflowRequest`, `WorkflowMode`, `WorkflowErrorFormat`. All have Pydantic v2 `@model_validator` guards. These are the domain primitives the generator must produce.
- `src/codemie/core/workflow_models/__init__.py` — re-exports all workflow model types plus `WorkflowConfig`, `WorkflowExecution`, `WorkflowExecutionStatusEnum`, `WorkflowListResponse`, `WorkflowConfigListResponse`, etc.
- `src/codemie/core/workflow_models/workflow_config.py` — `WorkflowConfig` SQLModel class (DB-backed), includes `assistants`, `states`, `custom_nodes`, `tools`, `yaml_config`, `guardrail_assignments` fields, plus `parse_execution_config()` method.
- `src/codemie/service/workflow_config/workflow_config_index_service.py` — `WorkflowConfigIndexService` class (task_context reference). Handles workflow listing/querying against PostgreSQL. Not the validation entrypoint — its `__init__.py` only exports this class.
- `src/codemie/workflows/workflow.py` — `WorkflowExecutor` class with the canonical `validate_workflow(workflow_config, user, error_format)` static method. This is the validation entrypoint that calls: (1) `validate_workflow_execution_config_yaml`, (2) `workflow_config.parse_execution_config()`, (3) `validate_workflow_config_resources_availability`. Must be called by the generator before returning configuration.
- `src/codemie/workflows/validation/__init__.py` — exports `validate_workflow_execution_config_yaml`, `validate_workflow_config_resources_availability`, `PydanticErrorTransformer`, `WorkflowExecutionParsingError`, `WorkflowExecutionConfigSchemaValidationError`, `WorkflowExecutionConfigCrossReferenceValidationError`, `WorkflowConfigResourcesValidationError`.
- `src/codemie/workflows/assistant_generator/assistant_validation_workflow.py` — `AssistantValidationWorkflow`: the closest analog — a LangGraph-based generation/validation workflow using a parallel-fan-out StateGraph pattern with clarification, validation, and decision nodes. Direct template for the new workflow generator.
- `src/codemie/workflows/assistant_generator/nodes/validation/base_validation_node.py` — `BaseValidationNode`: lightweight base for LangGraph nodes that need LLM access only (no callbacks, no execution service). Pattern to follow for generation chain nodes.
- `src/codemie/workflows/assistant_generator/nodes/validation/generic_validation_node.py` — `GenericValidationNode(BaseValidationNode)`: configurable LLM-invocation node with structured output, prompt formatter, and typed result field. Template for workflow generator chain steps.
- `src/codemie/workflows/nodes/base_node.py` — `BaseNode(ABC, Generic[StateSchemaType])`: full lifecycle node used in the main `WorkflowExecutor`. Implements `__call__` with callbacks, guardrail application (`_apply_node_input_guardrails`), execution tracking, and state finalization. Guardrail logic lives here.
- `src/codemie/service/guardrail/guardrail_service.py` — `GuardrailService.apply_guardrails_for_entities()` and `GuardrailService.sync_guardrail_assignments_for_entity()` — the two guardrail APIs the generator must call: one to validate generated content, one to attach guardrail assignments to the created workflow.
- `src/codemie/service/assistant_generator_service.py` — `AssistantGeneratorService`: the closest analogous generation service (NL-to-assistant). Uses `get_llm_by_credentials`, `PromptTemplate`, structured LLM output, and `AssistantValidationWorkflow`. High-value reference for overall structure.
- `src/codemie/service/workflow_service.py` — `WorkflowService` with `create_workflow(workflow_config, user)` — the persistence entrypoint after validation.
- `src/codemie/rest_api/routers/workflow.py` — existing workflow router (`/v1/workflows`). A new endpoint for workflow generation (e.g. `POST /v1/workflows/generate`) will need to be added here following the existing pattern.
- `src/codemie/chains/base.py` — `BaseChain` and `StreamingChain` abstract base classes with `generate()` / `stream()` methods. If the generator is exposed as a chain (per the task description "langgraph chain"), it should extend `BaseChain`.
- `src/codemie/core/dependecies.py` — `get_llm_by_credentials(llm_model, temperature, streaming, request_id)` — the canonical LLM factory used throughout.
- `src/codemie/templates/agents/assistant_generator_prompt.py` — Jinja2/PromptTemplate patterns for generator prompts. The workflow generator will need analogous prompt templates.

### Architecture and Layers Affected

| Layer | Components |
|---|---|
| API / Router | `src/codemie/rest_api/routers/workflow.py` — new endpoint for NL-to-workflow generation |
| Service / Business Logic | `src/codemie/service/workflow_generator_service.py` — main orchestration (stub to implement), plus `WorkflowService.create_workflow` for persistence, `GuardrailService.sync_guardrail_assignments_for_entity` for guardrail binding |
| Agent-Tool / Workflow / Orchestration | New LangGraph `StateGraph`-based generation chain under `src/codemie/workflows/` — likely a new subpackage (e.g. `src/codemie/workflows/workflow_generator/`) mirroring `assistant_generator/` structure |
| Validation | `WorkflowExecutor.validate_workflow` (YAML schema + Pydantic + resource cross-reference), `GuardrailService.apply_guardrails_for_entities` (per-node guardrail check) |
| Core Models | `src/codemie/core/workflow_models/workflow_models.py` — `WorkflowState`, `WorkflowNextState`, `WorkflowAssistant`, `CreateWorkflowRequest` used as output types |
| LLM / External | `get_llm_by_credentials` from `src/codemie/core/dependecies.py`, `llm_service` from `src/codemie/service/llm_service/llm_service.py` |

### Integration Points

- **LangGraph** (`langgraph==1.1.6`): `StateGraph`, `END`, `Send`, `defer=True` for convergence nodes — the generation chain must be built as a LangGraph `StateGraph`.
- **LLM abstraction**: `get_llm_by_credentials` returns a `BaseLanguageModel`; `.with_structured_output(PydanticModel)` used for structured generation (see `BaseValidationNode.invoke_llm_with_retry`).
- **GuardrailService**: `apply_guardrails_for_entities(entity_configs, input, source)` blocks or rewrites input; `sync_guardrail_assignments_for_entity(user, entity_type, entity_id, ...)` assigns guardrails to the created workflow.
- **WorkflowExecutor.validate_workflow**: integrates YAML schema validation, Pydantic model validation, and resource cross-reference validation in a single call. Must be called before saving.
- **WorkflowService.create_workflow**: persists `WorkflowConfig` to PostgreSQL via SQLModel session.
- **WorkflowConfigIndexService**: the task_context points here but it is a query/listing service — not directly invoked in the generation flow, but available for lookups (e.g., checking for duplicate workflow names).
- **Internal dependencies into the generator**: `codemie.rest_api.security.user.User` for auth context, `codemie.core.workflow_models` for domain types, `codemie.service.tools.tools_info_service.ToolsInfoService` for available tool enumeration (used by `AssistantGeneratorService` to inform LLM of valid tool names).

### Patterns and Conventions

- **LangGraph generation workflow pattern** (`AssistantValidationWorkflow`): `StateGraph(TypedDict-state)` → set entry point → add nodes → add edges → `workflow.compile()`. Parallel fan-out with `defer=True` on convergence nodes is standard.
- **State schema**: use `TypedDict` with `Annotated[field_type, reducer_fn]` for parallel-safe state fields (see `AssistantValidationState`). Sequential chains can use a plain `TypedDict`.
- **Generation nodes**: subclass `BaseValidationNode` (not `BaseNode`) when the node only needs LLM access. `BaseNode` is for full-lifecycle workflow execution nodes with callbacks and guardrails. For the generation chain steps, `BaseValidationNode` or inline callables are appropriate.
- **Structured LLM output**: `llm.with_structured_output(PydanticModel)` — the LLM returns a validated Pydantic instance. Each chain step should define its own output model (e.g., `IntentAnalysisResult`, `WorkflowPlanResult`, `GeneratedNodesResult`).
- **Prompt templates**: `langchain_core.prompts.PromptTemplate` or plain `str.format()` (see `GenericValidationNode`). Store templates in `src/codemie/templates/` following the pattern in `assistant_generator_prompt.py`.
- **Service class pattern**: stateless class methods (see `WorkflowConfigIndexService`, `AssistantGeneratorService`). The `WorkflowGenerator` service should expose a `generate(nl_query, user, llm_model, project)` class/static method.
- **Error handling**: raise `ExtendedHTTPException` with structured `code`, `message`, `details`, `help` fields at the router layer. Catch `ValueError` from validators and re-wrap. See `create_workflow` router handler.
- **Guardrail assignment**: after persisting, call `GuardrailService.sync_guardrail_assignments_for_entity(user, GuardrailEntity.WORKFLOW, str(workflow_config.id), ...)`. The generated workflow's `guardrail_assignments` field on `CreateWorkflowRequest` carries the assignment intent.
- **Retry**: use `tenacity` (`retry`, `stop_after_attempt`, `wait_exponential`) on LLM calls — established in `BaseValidationNode.invoke_llm_with_retry`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/workflows/langgraph-workflows.md` — directly relevant: mandates extending `WorkflowExecutor` for new workflow behavior; use existing config parsing and validation; do not bypass workflow config parsing. Evidence points to `src/codemie/workflows/workflow.py:29` and `src/codemie/workflows/nodes`.
- `.ai-run/guides/architecture/layered-architecture.md` — API→Service→Repository separation; route registration through `src/codemie/rest_api/main.py`.
- `.ai-run/guides/architecture/service-layer-patterns.md` — feature-scoped services under `src/codemie/service/`; avoid catch-all services.
- `.ai-run/guides/api/rest-api-patterns.md` and `.ai-run/guides/api/endpoint-conventions.md` — FastAPI router patterns (not read in detail, but applicable).
- `.ai-run/guides/development/error-handling.md` — typed exceptions, `ExtendedHTTPException`.
- `.ai-run/guides/testing/testing-patterns.md` — tests under `tests/codemie/`, mock provider boundaries.

### Architectural Decisions

- The langgraph-workflows guide explicitly states: "Extend `WorkflowExecutor`, nodes, or validation utilities" rather than creating a separate graph execution path. However, the generator is a _generation_ workflow (not an _execution_ workflow), so it parallels `AssistantValidationWorkflow` — a standalone `StateGraph` used for pre-creation processing, not extending `WorkflowExecutor` directly.
- `WorkflowExecutor.validate_workflow` is the established validation gate. All workflow creation (including AI-generated ones) must pass through it before persisting.
- Guardrail assignment at creation time is established in `POST /v1/workflows` handler via `GuardrailService.sync_guardrail_assignments_for_entity`. AI-generated workflows must follow the same pattern.
- Sequential workflow mode (`WorkflowMode.SEQUENTIAL`) is the only permitted mode — autonomous is disabled (`HTTP 410 Gone` on create).

### Derived Conventions

- New generation-chain workflow subpackage should mirror `src/codemie/workflows/assistant_generator/` structure: a top-level workflow class, `models/` subpackage for state and output types, `nodes/` subpackage for individual chain step nodes.
- Prompt templates belong in `src/codemie/templates/` (possibly `src/codemie/templates/agents/workflow_generator_prompt.py`).
- The service class `WorkflowGenerator` in `src/codemie/service/workflow_generator_service.py` should be the public API consumed by the router — it orchestrates the generation chain and delegates to `WorkflowService.create_workflow` and `GuardrailService`.
- Router endpoint is expected at `POST /v1/workflows/generate` (or similar) registered in `workflow.router` in `src/codemie/rest_api/routers/workflow.py` and included via `app.include_router(workflow.router)` in `main.py`.

---

## 4. Testing Landscape

### Existing Coverage

- `tests/codemie/workflows/test_base_node_lifecycle.py` — comprehensive tests for `BaseNode.__call__`, lifecycle hooks, guardrail application, state finalization, context store management.
- `tests/codemie/workflows/assistant_generator/nodes/validation/` — unit tests for `BaseValidationNode`, `ValidateToolsNode`, and validation utilities. Pattern to follow for generator node tests.
- `tests/codemie/core/workflow_models/test_workflow_models.py` — Pydantic model validation tests for `WorkflowState`, `WorkflowNextState`, etc.
- `tests/codemie/workflows/test_config_yaml_validation.py`, `test_config_resources_validation.py` — validation pipeline tests.
- `tests/codemie/rest_api/routers/test_workflow.py` — router-level tests using FastAPI `TestClient` with mocked services.
- `tests/codemie/service/test_workflow_service.py` — `WorkflowService` unit tests.
- No existing tests for `src/codemie/service/workflow_generator_service.py` (stub only).

### Testing Framework and Patterns

- **Framework**: `pytest` with `unittest.mock` (Mock, patch, MagicMock).
- **Session fixture**: `tests/conftest.py` patches `PostgresClient.get_engine` globally — no DB connections in unit tests.
- **LLM mocking**: `patch("codemie.core.dependecies.get_llm_by_credentials")` or mock the LLM at the `BaseValidationNode._llm` level. Pattern established in `tests/codemie/workflows/assistant_generator/nodes/validation/conftest.py`.
- **Router tests**: FastAPI `TestClient` with service-level mocks; see `tests/codemie/rest_api/routers/test_workflow.py`.
- **Workflow tests**: standalone `StateGraph.invoke(initial_state)` calls with mocked node callables (see `test_workflow_state_transitions.py` pattern).

### Coverage Gaps

The following areas will be entirely new and have no existing tests:

- `WorkflowGenerator.generate()` service method — the primary generation orchestration path.
- The NL-to-workflow LangGraph chain itself — all chain step nodes (`IntentAnalysisNode`, `PlanningNode`, `NodeGenerationNode`, `StateGenerationNode`, `ValidationNode` or equivalent).
- State schema (`TypedDict`) for the generation workflow.
- Prompt templates for workflow generation.
- The new router endpoint (`POST /v1/workflows/generate`).
- Integration of guardrail assignment into the generation flow (existing guardrail tests cover the service but not from a generation context).
- Structured output Pydantic models for each generation chain step.

---

## 5. Configuration and Environment

### Environment Variables

- No dedicated environment variables for workflow generation were found. The feature will consume existing LLM configuration:
  - `LLM_PROXY_ENABLED` — determines whether LiteLLM proxy is used for model resolution.
  - `VERBOSE` (maps to `config.verbose`) — enables debug logging in LangGraph compile.
  - Standard LLM model config via `llm_config` (YAML-based model catalogue or LiteLLM-proxied models).
- Guardrail feature is always enabled (no feature flag found).

### Configuration Files

- `src/codemie/configs/` — config module with `config` singleton (pydantic-settings based). New generation config (e.g., `WORKFLOW_GENERATOR_LLM_MODEL`, `WORKFLOW_GENERATOR_MAX_RETRIES`) may need to be added here if the model is configurable separately.
- `src/codemie/configs/llm_config.py` — `LLMConfig` and `llm_service` singleton; `llm_service.default_llm_model` is the fallback model for LLM calls.
- YAML workflow validation schema: `src/codemie/workflows/validation/` (referenced by `WORKFLOW_EXECUTION_CONFIG_SCHEMA_YAML_FILE_PATH`) — no changes needed unless the generator produces non-standard YAML structures.

### Feature Flags and Deployment Concerns

- No feature flag for the workflow generator was found. It will need to be added to a config toggle if staged rollout is required.
- Autonomous workflow mode is hard-disabled at the router level (HTTP 410) — generated workflows must be `SEQUENTIAL` only.
- The generation chain invokes LLM API calls (latency: likely 5–20 seconds for a multi-step chain). The endpoint will need to run in a background thread or be async if the API client is synchronous. The existing `create_workflow` endpoint uses `BackgroundTasks` for post-creation schema drawing — the generation call itself is synchronous but long-running.
- No DB migration needed: the generator produces `CreateWorkflowRequest` / `WorkflowConfig` instances that are persisted via the existing `WorkflowService.create_workflow` path.

---

## 6. Risk Indicators

- **Stub service with no implementation**: `src/codemie/service/workflow_generator_service.py` contains only `class WorkflowGenerator: ...`. The entire generation logic is greenfield. No existing test coverage.
- **No existing tests** for `WorkflowGenerator` — any implementation must be accompanied by new test files under `tests/codemie/service/` and `tests/codemie/workflows/workflow_generator/` (to be created).
- **Complex multi-step chain**: the 5-step chain (intent analysis → planning → node generation → state generation → validation) involves multiple sequential LLM calls. Each step can fail, hallucinate invalid model fields, or produce structurally inconsistent states. Pydantic validation catches structural errors but LLM-generated values may still fail `WorkflowExecutor.validate_workflow` (e.g., referencing non-existent assistant IDs).
- **WorkflowState `@model_validator` strictness**: `WorkflowState.check_state_type` requires exactly one of `assistant_id`, `custom_node_id`, or `tool_id` to be set. LLM-generated states must comply; hallucinated IDs that pass schema validation will still fail resource availability check.
- **Guardrail integration in generation flow**: the task says "each created node should be validated and go through guardrails." Applying input guardrails per-node during _generation_ (not during _execution_) is a novel use case — `BaseNode._apply_node_input_guardrails` is built for runtime execution context. The generation chain must determine when and how to apply guardrails to generated node content (likely on the final generated workflow config, not on each intermediate LLM call).
- **WorkflowConfigIndexService is a listing service, not a creation/validation service**: the task_context points to `@src/codemie/service/workflow_config/__init__.py` for "workflow configuration and validation" but this service only indexes and queries workflows. The actual validation entry point is `WorkflowExecutor.validate_workflow`. This conflation in the requirements is a clarity risk.
- **LLM retry and timeout handling**: `BaseValidationNode` uses tenacity for retries but has no explicit timeout. For a 5-step generation chain, unhandled LLM latency can cause request timeouts at the FastAPI layer.
- **Tool/assistant availability in generation context**: the generator needs a catalog of available tools and custom nodes to generate valid `WorkflowAssistantTool`, `WorkflowTool`, and `CustomWorkflowNode` references. Without querying `ToolsInfoService` and `CustomNodeInfoService`, the LLM cannot know valid `tool` field values for `WorkflowTool`, causing resource validation failures.
- **No router endpoint yet**: `src/codemie/rest_api/routers/workflow.py` has no `generate` endpoint and no `WorkflowGenerator` import. Both need to be added and registered.
- **Chain output is a `CreateWorkflowRequest` (not a `WorkflowConfig`)**: `CreateWorkflowRequest` has `assistants: Optional[list[WorkflowAssistant]]` and `states: Optional[list[WorkflowState]]` — the LLM must populate both. `WorkflowAssistant` includes `id`, `assistant_id`, `tools`, `datasource_ids`, `mcp_servers`, `skill_ids` — many optional, but some cross-references must be consistent.
- **`WorkflowNextState` terminal validation**: if the last state's `next.state_id` or `state_ids` does not point to `END` (or an implicit terminal), the workflow graph will have dangling edges. The generator must produce a valid termination state.

---

## 7. Summary for Complexity Assessment

The task introduces a **new multi-layer feature** that spans the API, Service, Workflow/Orchestration, and Validation layers. The service stub (`src/codemie/service/workflow_generator_service.py`) exists but contains no logic — the entire implementation is greenfield. The feature requires building: (1) a 5-step LangGraph `StateGraph` generation chain (analogous to `AssistantValidationWorkflow`) with distinct nodes for intent analysis, planning, node generation, state generation, and validation; (2) a new `src/codemie/workflows/workflow_generator/` package mirroring `assistant_generator/`; (3) prompt templates in `src/codemie/templates/`; (4) a `WorkflowGenerator.generate()` service method; and (5) a new FastAPI endpoint in the existing `workflow.py` router. Estimated file change surface: 8–15 new files (chain class, 3–5 node classes, state TypedDict, output Pydantic models, prompt templates, service method, router endpoint, tests) plus modifications to `workflow.py` router and `main.py` registration if the endpoint is in a new router.

The task follows **established patterns** closely — `AssistantValidationWorkflow`, `BaseValidationNode`, `GenericValidationNode`, `AssistantGeneratorService`, and `WorkflowExecutor.validate_workflow` are all direct templates to follow. The LangGraph parallel-fan-out pattern with `defer=True` and TypedDict state is already proven. The LLM invocation pattern (`get_llm_by_credentials` + `with_structured_output`) is standard throughout the codebase. The key **technical novelty** is the guardrail integration requirement: applying guardrails to generated workflow nodes is novel in this codebase — existing guardrail application in `BaseNode` is designed for runtime execution input validation, not for validating LLM-generated workflow configuration. This will require a deliberate design decision about where and how guardrails apply during generation (most likely as a post-generation content check on the assembled `CreateWorkflowRequest` rather than per intermediate LLM call).

**Test coverage posture**: the affected domain (workflows, validation, guardrails) is well-tested in general — there are over 40 workflow-related test files. However, the new generation service and chain nodes will have zero existing coverage. Risk factors are moderate-to-high: LLM-generated workflow structure must satisfy multiple strict validators (`WorkflowState` model validators + YAML schema + resource cross-reference check + resource availability check), requiring careful prompt engineering and robust error handling in the generation chain. The conflict between the task_context's reference to `WorkflowConfigIndexService` as a validation source (it is actually a listing service) is a requirements clarity risk that should be confirmed before implementation.
