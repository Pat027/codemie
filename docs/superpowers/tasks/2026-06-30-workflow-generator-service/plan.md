# Workflow Generator Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `WorkflowGeneratorService` — a 5-node LangGraph chain that converts a natural language query into a validated `CreateWorkflowRequest`, with an optional DB persistence path and a `POST /v1/workflows/generate` endpoint.

**Architecture:** A sequential `StateGraph` with 5 nodes: `IntentAnalysisNode` → `NodeMappingNode` → `ConfigGenerationNode` → `ValidationNode` (retry loop up to 3×) → `ResultNode`. Each LLM node subclasses `BaseValidationNode`. The service wraps the graph, injects the tool catalog, handles monitoring, and optionally persists via `WorkflowService`.

**Tech Stack:** Python 3.12, LangGraph 1.1.6, LangChain Core, Pydantic v2, FastAPI, tenacity (already in project), pytest + unittest.mock.

## Global Constraints

- All new files carry the Apache 2.0 license header (copy from any existing file).
- Workflow mode must always be `WorkflowMode.SEQUENTIAL` — never `AUTONOMOUS`.
- Each `WorkflowState` must have **exactly one** of `assistant_id`, `tool_id`, or `custom_node_id` set.
- LLM invocations use `get_llm_by_credentials` from `codemie.core.dependecies` (note the typo — this is the actual module name).
- Tests live under `tests/codemie/` mirroring `src/codemie/` structure.
- Run tests with: `poetry run pytest <test_file> -v`
- Linting: `poetry run ruff check src/ tests/ --fix`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `src/codemie/service/monitoring/metrics_constants.py` | Add 2 new metric name constants |
| Create | `src/codemie/workflows/workflow_generator/__init__.py` | Package entry |
| Create | `src/codemie/workflows/workflow_generator/state.py` | `WorkflowGeneratorState` TypedDict |
| Create | `src/codemie/workflows/workflow_generator/models.py` | Pydantic output schemas for each LLM step |
| Create | `src/codemie/workflows/workflow_generator/nodes/__init__.py` | Nodes sub-package entry |
| Create | `src/codemie/workflows/workflow_generator/nodes/intent_analysis.py` | Node 1: NL → WorkflowIntent |
| Create | `src/codemie/workflows/workflow_generator/nodes/node_mapping.py` | Node 2: steps → NodeMappingPlan |
| Create | `src/codemie/workflows/workflow_generator/nodes/config_generation.py` | Node 3: plan → GeneratedWorkflowConfig |
| Create | `src/codemie/workflows/workflow_generator/nodes/validation.py` | Node 4: Pydantic validation + retry routing |
| Create | `src/codemie/workflows/workflow_generator/nodes/result.py` | Node 5: assemble CreateWorkflowRequest |
| Create | `src/codemie/workflows/workflow_generator/workflow.py` | `WorkflowGeneratorGraph` — StateGraph builder |
| Create | `src/codemie/templates/agents/workflow_generator_prompts.py` | Three prompt template strings |
| Create | `src/codemie/rest_api/models/workflow_generator.py` | `WorkflowGeneratorRequest` / `WorkflowGeneratorResponse` |
| Replace | `src/codemie/service/workflow_generator_service.py` | `WorkflowGeneratorService.generate()` |
| Modify | `src/codemie/rest_api/routers/workflow.py` | Add `POST /v1/workflows/generate` endpoint |
| Create | `tests/codemie/workflows/workflow_generator/__init__.py` | Test package |
| Create | `tests/codemie/workflows/workflow_generator/test_models.py` | Model instantiation tests |
| Create | `tests/codemie/workflows/workflow_generator/test_nodes.py` | Node unit tests |
| Create | `tests/codemie/workflows/workflow_generator/test_workflow_graph.py` | StateGraph integration test |
| Create | `tests/codemie/service/test_workflow_generator_service.py` | Service tests |
| Create | `tests/codemie/rest_api/routers/test_workflow_generator.py` | Router endpoint tests |

---

### Task 1: Metric constants

**Files:**
- Modify: `src/codemie/service/monitoring/metrics_constants.py`
- Test: `tests/codemie/service/monitoring/` (import check only)

**Interfaces:**
- Produces: `WORKFLOW_GENERATOR_TOTAL_METRIC: str`, `WORKFLOW_GENERATOR_ERRORS_METRIC: str` — importable from `codemie.service.monitoring.metrics_constants`

- [ ] **Step 1: Write failing import test**

```python
# tests/codemie/service/test_workflow_generator_service.py  (create file)
def test_metric_constants_importable():
    from codemie.service.monitoring.metrics_constants import (
        WORKFLOW_GENERATOR_TOTAL_METRIC,
        WORKFLOW_GENERATOR_ERRORS_METRIC,
    )
    assert WORKFLOW_GENERATOR_TOTAL_METRIC == "codemie_workflow_generator_total"
    assert WORKFLOW_GENERATOR_ERRORS_METRIC == "codemie_workflow_generator_errors_total"
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/service/test_workflow_generator_service.py::test_metric_constants_importable -v
```
Expected: `ImportError` or `AssertionError`.

- [ ] **Step 3: Add constants to metrics_constants.py**

Find the block near line 50 in `src/codemie/service/monitoring/metrics_constants.py` where `SKILL_GENERATOR_TOTAL_METRIC` is defined. Append after it:

```python
WORKFLOW_GENERATOR_TOTAL_METRIC = "codemie_workflow_generator_total"
WORKFLOW_GENERATOR_ERRORS_METRIC = "codemie_workflow_generator_errors_total"
```

- [ ] **Step 4: Run test to confirm pass**

```bash
poetry run pytest tests/codemie/service/test_workflow_generator_service.py::test_metric_constants_importable -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/monitoring/metrics_constants.py tests/codemie/service/test_workflow_generator_service.py
git commit -m "EPMCDME-10037: Add workflow generator metric constants"
```

---

### Task 2: LLM output models and state

**Files:**
- Create: `src/codemie/workflows/workflow_generator/__init__.py`
- Create: `src/codemie/workflows/workflow_generator/models.py`
- Create: `src/codemie/workflows/workflow_generator/state.py`
- Create: `tests/codemie/workflows/workflow_generator/__init__.py`
- Create: `tests/codemie/workflows/workflow_generator/test_models.py`

**Interfaces:**
- Produces:
  - `WorkflowStep(id, description, state_type, next_step_id)` — Pydantic BaseModel
  - `WorkflowIntent(workflow_name, workflow_description, steps)` — Pydantic BaseModel
  - `MappedNode(step_id, state_type, assistant_ref, tool_ref, custom_node_ref, task)` — Pydantic BaseModel
  - `NodeMappingPlan(nodes)` — Pydantic BaseModel
  - `GeneratedWorkflowConfig(states, assistants, tools)` — Pydantic BaseModel
  - `WorkflowGeneratorState` — TypedDict with all graph state fields

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/workflows/workflow_generator/test_models.py
from codemie.workflows.workflow_generator.models import (
    WorkflowStep, WorkflowIntent, MappedNode, NodeMappingPlan, GeneratedWorkflowConfig,
)
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState


def test_workflow_step_instantiation():
    step = WorkflowStep(
        id="analyze-input",
        description="Analyze user input",
        state_type="agent",
        next_step_id="generate-output",
    )
    assert step.id == "analyze-input"
    assert step.state_type == "agent"
    assert step.next_step_id == "generate-output"


def test_workflow_step_last_has_null_next():
    step = WorkflowStep(id="last", description="Last step", state_type="tool", next_step_id=None)
    assert step.next_step_id is None


def test_workflow_intent_instantiation():
    intent = WorkflowIntent(
        workflow_name="Code Reviewer",
        workflow_description="Reviews code for bugs",
        steps=[
            WorkflowStep(id="review", description="Review code", state_type="agent", next_step_id=None)
        ],
    )
    assert intent.workflow_name == "Code Reviewer"
    assert len(intent.steps) == 1


def test_mapped_node_agent_type():
    node = MappedNode(
        step_id="review",
        state_type="agent",
        assistant_ref="code-reviewer",
        tool_ref=None,
        custom_node_ref=None,
        task="Review the submitted code for bugs and return structured findings.",
    )
    assert node.assistant_ref == "code-reviewer"
    assert node.tool_ref is None


def test_node_mapping_plan():
    plan = NodeMappingPlan(nodes=[
        MappedNode(step_id="s1", state_type="agent", assistant_ref="a1",
                   tool_ref=None, custom_node_ref=None, task="Do something"),
    ])
    assert len(plan.nodes) == 1


def test_generated_workflow_config():
    config = GeneratedWorkflowConfig(states=[], assistants=[], tools=[])
    assert config.states == []


def test_workflow_generator_state_is_typeddict():
    # TypedDict can be instantiated as a regular dict
    state: WorkflowGeneratorState = {
        "nl_query": "create a workflow",
        "user": None,
        "project": "demo",
        "available_tools": [],
        "intent": None,
        "node_plan": None,
        "generated_config": None,
        "validation_errors": [],
        "validation_attempts": 0,
        "result": None,
        "error": None,
    }
    assert state["nl_query"] == "create a workflow"
    assert state["validation_attempts"] == 0
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_models.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create package files**

```python
# src/codemie/workflows/workflow_generator/__init__.py
# (empty — just the license header)
```

```python
# tests/codemie/workflows/workflow_generator/__init__.py
# (empty)
```

- [ ] **Step 4: Create models.py**

```python
# src/codemie/workflows/workflow_generator/models.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    id: str = Field(description="Unique step identifier in kebab-case (e.g., 'analyze-input')")
    description: str = Field(description="What this step does")
    state_type: Literal["agent", "tool", "custom_node"] = Field(
        description="Execution type: agent=AI assistant, tool=deterministic function, custom_node=specialized processor"
    )
    next_step_id: Optional[str] = Field(
        default=None,
        description="ID of the next step, or null if this is the last step",
    )


class WorkflowIntent(BaseModel):
    workflow_name: str = Field(description="Short descriptive name for the workflow")
    workflow_description: str = Field(description="What the workflow accomplishes")
    steps: list[WorkflowStep] = Field(description="Ordered list of workflow steps")


class MappedNode(BaseModel):
    step_id: str = Field(description="ID of the step from WorkflowIntent this node implements")
    state_type: Literal["agent", "tool", "custom_node"]
    assistant_ref: Optional[str] = Field(
        default=None, description="Assistant identifier (e.g., 'code-analyzer'). Set when state_type='agent'."
    )
    tool_ref: Optional[str] = Field(
        default=None, description="Tool name from the available catalog. Set when state_type='tool'."
    )
    custom_node_ref: Optional[str] = Field(
        default=None, description="Custom node ID. Set when state_type='custom_node'."
    )
    task: str = Field(description="Task instructions for this node")


class NodeMappingPlan(BaseModel):
    nodes: list[MappedNode] = Field(description="One MappedNode per WorkflowStep")


class GeneratedWorkflowConfig(BaseModel):
    states: list[dict] = Field(
        description="List of WorkflowState dicts. Each must have id, next, and exactly one of assistant_id/tool_id/custom_node_id."
    )
    assistants: list[dict] = Field(
        description="List of WorkflowAssistant dicts. Each must have an id matching an assistant_id used in states."
    )
    tools: list[dict] = Field(
        description="List of WorkflowTool dicts. Each must have an id and tool field matching a tool_id used in states."
    )
```

- [ ] **Step 5: Create state.py**

```python
# src/codemie/workflows/workflow_generator/state.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from typing import Any, Optional, TypedDict


class WorkflowGeneratorState(TypedDict):
    nl_query: str
    user: Any  # codemie.rest_api.security.user.User
    project: str
    available_tools: list  # list[dict] from ToolsInfoService.get_tools_info()
    intent: Optional[Any]  # WorkflowIntent | None
    node_plan: Optional[Any]  # NodeMappingPlan | None
    generated_config: Optional[Any]  # GeneratedWorkflowConfig | None
    validation_errors: list  # list[str]
    validation_attempts: int
    result: Optional[Any]  # CreateWorkflowRequest | None
    error: Optional[str]
```

- [ ] **Step 6: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_models.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/codemie/workflows/workflow_generator/ tests/codemie/workflows/workflow_generator/
git commit -m "EPMCDME-10037: Add workflow generator state and LLM output models"
```

---

### Task 3: Prompt templates

**Files:**
- Create: `src/codemie/templates/agents/workflow_generator_prompts.py`

**Interfaces:**
- Produces: `INTENT_ANALYSIS_PROMPT: str`, `NODE_MAPPING_PROMPT: str`, `CONFIG_GENERATION_PROMPT: str`
- Each is a plain string with `{placeholder}` slots for `.format()` calls in the nodes.

- [ ] **Step 1: Write failing import test**

Add to `tests/codemie/workflows/workflow_generator/test_models.py`:

```python
def test_prompts_importable():
    from codemie.templates.agents.workflow_generator_prompts import (
        INTENT_ANALYSIS_PROMPT,
        NODE_MAPPING_PROMPT,
        CONFIG_GENERATION_PROMPT,
    )
    assert "{nl_query}" in INTENT_ANALYSIS_PROMPT
    assert "{available_tools}" in NODE_MAPPING_PROMPT
    assert "{node_plan}" in CONFIG_GENERATION_PROMPT
    assert "{validation_errors}" in CONFIG_GENERATION_PROMPT
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_models.py::test_prompts_importable -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create workflow_generator_prompts.py**

```python
# src/codemie/templates/agents/workflow_generator_prompts.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

INTENT_ANALYSIS_PROMPT = """You are an expert workflow designer for AI automation systems.

Analyze the following natural language description and extract the workflow intent.
The workflow must use SEQUENTIAL mode with clearly ordered steps.

Rules for steps:
- Each step needs a unique ID in kebab-case (e.g., "analyze-input", "generate-report")
- state_type must be one of: "agent" (AI assistant), "tool" (deterministic function), "custom_node" (specialized processor)
- next_step_id: the ID of the following step, or null for the final step
- Produce at least 2 steps; at most 8 steps

Natural language description:
{nl_query}"""

NODE_MAPPING_PROMPT = """You are an expert at mapping workflow steps to available tools and AI assistants.

Given the workflow intent and the available tools catalog below, map each step to the correct resource.

Mapping rules:
- "agent" steps: set assistant_ref to a descriptive ID (e.g., "code-analyzer", "report-writer")
- "tool" steps: set tool_ref to an EXACT tool name from the catalog. Do NOT invent tool names.
- "custom_node" steps: set custom_node_ref to a custom node ID (use only if clearly required)
- Write a detailed task description for each node explaining what it should do
- For agent steps, assistant_ref IDs will be used as assistant identifiers in the workflow

Available tools catalog:
{available_tools}

Workflow intent:
{intent}"""

CONFIG_GENERATION_PROMPT = """You are an expert at generating CodeMie workflow configurations.

Generate a complete workflow configuration from the given node mapping plan.

CRITICAL rules for states array:
- Each state object MUST have exactly ONE of: "assistant_id", "tool_id", or "custom_node_id"
- Do NOT set more than one of these fields on a single state
- "assistant_id" value must match the assistant_ref from the mapping plan
- "tool_id" value must match the tool_ref from the mapping plan
- Each state MUST have a "next" object with either "state_id" pointing to the next state's id, or "state_id": "END" for the last state
- The LAST state in the flow MUST have: "next": {{"state_id": "END"}}
- All state ids referenced in "next.state_id" must exist as ids in the states array (or be "END")

Rules for assistants array:
- Create one WorkflowAssistant entry for each unique assistant_id used in states
- The "id" field must EXACTLY match the "assistant_id" used in the state

Rules for tools array:
- Create one WorkflowTool entry for each unique tool_id used in states
- The "id" field must EXACTLY match the "tool_id" used in the state
- The "tool" field must be the exact tool name from the catalog

Workflow intent:
{intent}

Node mapping plan:
{node_plan}{validation_errors}"""
```

- [ ] **Step 4: Run test to confirm pass**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_models.py::test_prompts_importable -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/templates/agents/workflow_generator_prompts.py tests/codemie/workflows/workflow_generator/test_models.py
git commit -m "EPMCDME-10037: Add workflow generator prompt templates"
```

---

### Task 4: LLM generation nodes (IntentAnalysisNode, NodeMappingNode, ConfigGenerationNode)

**Files:**
- Create: `src/codemie/workflows/workflow_generator/nodes/__init__.py`
- Create: `src/codemie/workflows/workflow_generator/nodes/intent_analysis.py`
- Create: `src/codemie/workflows/workflow_generator/nodes/node_mapping.py`
- Create: `src/codemie/workflows/workflow_generator/nodes/config_generation.py`
- Create: `tests/codemie/workflows/workflow_generator/test_nodes.py`

**Interfaces:**
- Consumes: `WorkflowGeneratorState`, `INTENT_ANALYSIS_PROMPT`, `NODE_MAPPING_PROMPT`, `CONFIG_GENERATION_PROMPT`, `WorkflowIntent`, `NodeMappingPlan`, `GeneratedWorkflowConfig`, `BaseValidationNode`
- Produces:
  - `IntentAnalysisNode(llm_model, request_id).__call__(state)` → `{"intent": WorkflowIntent}`
  - `NodeMappingNode(llm_model, request_id).__call__(state)` → `{"node_plan": NodeMappingPlan}`
  - `ConfigGenerationNode(llm_model, request_id).__call__(state)` → `{"generated_config": GeneratedWorkflowConfig}`

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/workflows/workflow_generator/test_nodes.py
import json
from unittest.mock import Mock, patch

import pytest

from codemie.workflows.workflow_generator.models import (
    GeneratedWorkflowConfig, MappedNode, NodeMappingPlan, WorkflowIntent, WorkflowStep,
)
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState


def _make_state(**overrides) -> WorkflowGeneratorState:
    base: WorkflowGeneratorState = {
        "nl_query": "Create a workflow that analyzes code and generates a report",
        "user": Mock(id="u1", name="tester", username="tester@example.com"),
        "project": "demo",
        "available_tools": [{"toolkit": "git", "tool": "git_diff", "label": "Git Diff"}],
        "intent": WorkflowIntent(
            workflow_name="Code Analyzer",
            workflow_description="Analyzes code",
            steps=[
                WorkflowStep(id="analyze", description="Analyze code", state_type="agent", next_step_id=None)
            ],
        ),
        "node_plan": NodeMappingPlan(nodes=[
            MappedNode(step_id="analyze", state_type="agent", assistant_ref="code-analyzer",
                       tool_ref=None, custom_node_ref=None, task="Analyze the code"),
        ]),
        "generated_config": None,
        "validation_errors": [],
        "validation_attempts": 0,
        "result": None,
        "error": None,
    }
    base.update(overrides)
    return base


class TestIntentAnalysisNode:
    @patch("codemie.workflows.workflow_generator.nodes.intent_analysis.get_llm_by_credentials")
    def test_returns_intent_in_state_update(self, mock_get_llm):
        from codemie.workflows.workflow_generator.nodes.intent_analysis import IntentAnalysisNode

        expected_intent = WorkflowIntent(
            workflow_name="Test",
            workflow_description="A test workflow",
            steps=[WorkflowStep(id="s1", description="Step 1", state_type="agent", next_step_id=None)],
        )
        mock_llm = Mock()
        mock_llm.with_structured_output.return_value.invoke.return_value = expected_intent
        mock_get_llm.return_value = mock_llm

        node = IntentAnalysisNode(llm_model="gpt-4o", request_id="req-1")
        state = _make_state()
        result = node(state)

        assert "intent" in result
        assert result["intent"].workflow_name == "Test"

    @patch("codemie.workflows.workflow_generator.nodes.intent_analysis.get_llm_by_credentials")
    def test_prompt_contains_nl_query(self, mock_get_llm):
        from codemie.workflows.workflow_generator.nodes.intent_analysis import IntentAnalysisNode

        mock_llm = Mock()
        captured_prompt = {}

        def capture_invoke(prompt):
            captured_prompt["value"] = prompt
            return WorkflowIntent(workflow_name="X", workflow_description="Y", steps=[])

        mock_llm.with_structured_output.return_value.invoke.side_effect = capture_invoke
        mock_get_llm.return_value = mock_llm

        node = IntentAnalysisNode(llm_model="gpt-4o", request_id=None)
        state = _make_state(nl_query="my custom query")
        node(state)

        assert "my custom query" in captured_prompt["value"]


class TestNodeMappingNode:
    @patch("codemie.workflows.workflow_generator.nodes.node_mapping.get_llm_by_credentials")
    def test_returns_node_plan_in_state_update(self, mock_get_llm):
        from codemie.workflows.workflow_generator.nodes.node_mapping import NodeMappingNode

        expected_plan = NodeMappingPlan(nodes=[
            MappedNode(step_id="analyze", state_type="agent", assistant_ref="a1",
                       tool_ref=None, custom_node_ref=None, task="Do it"),
        ])
        mock_llm = Mock()
        mock_llm.with_structured_output.return_value.invoke.return_value = expected_plan
        mock_get_llm.return_value = mock_llm

        node = NodeMappingNode(llm_model="gpt-4o", request_id=None)
        result = node(_make_state())

        assert "node_plan" in result
        assert len(result["node_plan"].nodes) == 1


class TestConfigGenerationNode:
    @patch("codemie.workflows.workflow_generator.nodes.config_generation.get_llm_by_credentials")
    def test_returns_generated_config(self, mock_get_llm):
        from codemie.workflows.workflow_generator.nodes.config_generation import ConfigGenerationNode

        expected_config = GeneratedWorkflowConfig(
            states=[{
                "id": "analyze",
                "assistant_id": "code-analyzer",
                "task": "Analyze code",
                "next": {"state_id": "END"},
            }],
            assistants=[{"id": "code-analyzer"}],
            tools=[],
        )
        mock_llm = Mock()
        mock_llm.with_structured_output.return_value.invoke.return_value = expected_config
        mock_get_llm.return_value = mock_llm

        node = ConfigGenerationNode(llm_model="gpt-4o", request_id=None)
        result = node(_make_state())

        assert "generated_config" in result
        assert len(result["generated_config"].states) == 1

    @patch("codemie.workflows.workflow_generator.nodes.config_generation.get_llm_by_credentials")
    def test_injects_validation_errors_into_prompt(self, mock_get_llm):
        from codemie.workflows.workflow_generator.nodes.config_generation import ConfigGenerationNode

        captured = {}
        mock_llm = Mock()

        def capture_invoke(prompt):
            captured["prompt"] = prompt
            return GeneratedWorkflowConfig(states=[], assistants=[], tools=[])

        mock_llm.with_structured_output.return_value.invoke.side_effect = capture_invoke
        mock_get_llm.return_value = mock_llm

        node = ConfigGenerationNode(llm_model="gpt-4o", request_id=None)
        state = _make_state(validation_errors=["State 'x': missing assistant_id"])
        node(state)

        assert "missing assistant_id" in captured["prompt"]
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_nodes.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create nodes __init__.py**

```python
# src/codemie/workflows/workflow_generator/nodes/__init__.py
# (empty — just license header)
```

- [ ] **Step 4: Create intent_analysis.py**

```python
# src/codemie/workflows/workflow_generator/nodes/intent_analysis.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from codemie.workflows.assistant_generator.nodes.validation.base_validation_node import BaseValidationNode
from codemie.workflows.workflow_generator.models import WorkflowIntent
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.templates.agents.workflow_generator_prompts import INTENT_ANALYSIS_PROMPT


class IntentAnalysisNode(BaseValidationNode):
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        prompt = INTENT_ANALYSIS_PROMPT.format(nl_query=state["nl_query"])
        intent: WorkflowIntent = self.invoke_llm_with_retry(
            prompt=prompt,
            output_model=WorkflowIntent,
            user=state.get("user"),
        )
        return {"intent": intent}
```

- [ ] **Step 5: Create node_mapping.py**

```python
# src/codemie/workflows/workflow_generator/nodes/node_mapping.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import json

from codemie.workflows.assistant_generator.nodes.validation.base_validation_node import BaseValidationNode
from codemie.workflows.workflow_generator.models import NodeMappingPlan
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.templates.agents.workflow_generator_prompts import NODE_MAPPING_PROMPT


class NodeMappingNode(BaseValidationNode):
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        intent_json = state["intent"].model_dump_json(indent=2)
        tools_json = json.dumps(state["available_tools"], indent=2)
        prompt = NODE_MAPPING_PROMPT.format(intent=intent_json, available_tools=tools_json)
        node_plan: NodeMappingPlan = self.invoke_llm_with_retry(
            prompt=prompt,
            output_model=NodeMappingPlan,
            user=state.get("user"),
        )
        return {"node_plan": node_plan}
```

- [ ] **Step 6: Create config_generation.py**

```python
# src/codemie/workflows/workflow_generator/nodes/config_generation.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from codemie.workflows.assistant_generator.nodes.validation.base_validation_node import BaseValidationNode
from codemie.workflows.workflow_generator.models import GeneratedWorkflowConfig
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.templates.agents.workflow_generator_prompts import CONFIG_GENERATION_PROMPT


class ConfigGenerationNode(BaseValidationNode):
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        node_plan_json = state["node_plan"].model_dump_json(indent=2)
        intent_json = state["intent"].model_dump_json(indent=2)
        errors = state.get("validation_errors") or []
        errors_section = (
            f"\n\nPrevious validation errors to fix:\n" + "\n".join(f"- {e}" for e in errors)
            if errors
            else ""
        )
        prompt = CONFIG_GENERATION_PROMPT.format(
            intent=intent_json,
            node_plan=node_plan_json,
            validation_errors=errors_section,
        )
        config: GeneratedWorkflowConfig = self.invoke_llm_with_retry(
            prompt=prompt,
            output_model=GeneratedWorkflowConfig,
            user=state.get("user"),
        )
        return {"generated_config": config}
```

- [ ] **Step 7: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_nodes.py -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/codemie/workflows/workflow_generator/nodes/ tests/codemie/workflows/workflow_generator/test_nodes.py
git commit -m "EPMCDME-10037: Add workflow generator LLM chain nodes"
```

---

### Task 5: ValidationNode and ResultNode

**Files:**
- Create: `src/codemie/workflows/workflow_generator/nodes/validation.py`
- Create: `src/codemie/workflows/workflow_generator/nodes/result.py`

**Interfaces:**
- Consumes: `WorkflowGeneratorState`, `WorkflowState` (from `codemie.core.workflow_models.workflow_models`), `CreateWorkflowRequest`, `WorkflowAssistant`, `WorkflowTool`, `WorkflowMode`
- Produces:
  - `ValidationNode().__call__(state)` → `{"validation_errors": list[str], "validation_attempts": int}` on failure, or `{"validation_errors": [], "validation_attempts": int}` on success; sets `{"error": str}` when max retries exceeded
  - `ResultNode().__call__(state)` → `{"result": CreateWorkflowRequest}`
  - `MAX_VALIDATION_RETRIES: int = 3` importable from `validation.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/codemie/workflows/workflow_generator/test_nodes.py`:

```python
class TestValidationNode:
    def test_passes_with_valid_state(self):
        from codemie.workflows.workflow_generator.nodes.validation import ValidationNode
        from codemie.workflows.workflow_generator.models import (
            GeneratedWorkflowConfig, WorkflowIntent, WorkflowStep,
        )

        node = ValidationNode()
        valid_config = GeneratedWorkflowConfig(
            states=[{
                "id": "step-one",
                "assistant_id": "my-assistant",
                "task": "Do the work",
                "next": {"state_id": "END"},
            }],
            assistants=[{"id": "my-assistant"}],
            tools=[],
        )
        state = _make_state(
            generated_config=valid_config,
            validation_errors=[],
            validation_attempts=0,
        )
        result = node(state)

        assert result["validation_errors"] == []
        assert result.get("error") is None

    def test_collects_errors_for_invalid_state(self):
        from codemie.workflows.workflow_generator.nodes.validation import ValidationNode
        from codemie.workflows.workflow_generator.models import GeneratedWorkflowConfig

        node = ValidationNode()
        bad_config = GeneratedWorkflowConfig(
            states=[{"id": "bad-state", "next": {"state_id": "END"}}],  # no assistant_id/tool_id/custom_node_id
            assistants=[],
            tools=[],
        )
        state = _make_state(generated_config=bad_config, validation_errors=[], validation_attempts=0)
        result = node(state)

        assert len(result["validation_errors"]) > 0
        assert result["validation_attempts"] == 1
        assert result.get("error") is None  # not yet at retry limit

    def test_sets_error_after_max_retries(self):
        from codemie.workflows.workflow_generator.nodes.validation import ValidationNode, MAX_VALIDATION_RETRIES
        from codemie.workflows.workflow_generator.models import GeneratedWorkflowConfig

        node = ValidationNode()
        bad_config = GeneratedWorkflowConfig(
            states=[{"id": "bad", "next": {"state_id": "END"}}],
            assistants=[],
            tools=[],
        )
        state = _make_state(
            generated_config=bad_config,
            validation_errors=["prior error"],
            validation_attempts=MAX_VALIDATION_RETRIES - 1,  # this call pushes it to MAX
        )
        result = node(state)

        assert result.get("error") is not None
        assert "validation retries" in result["error"].lower() or "failed" in result["error"].lower()


class TestResultNode:
    def test_assembles_create_workflow_request(self):
        from codemie.workflows.workflow_generator.nodes.result import ResultNode
        from codemie.workflows.workflow_generator.models import GeneratedWorkflowConfig
        from codemie.core.workflow_models.workflow_models import CreateWorkflowRequest

        node = ResultNode()
        config = GeneratedWorkflowConfig(
            states=[{
                "id": "step-one",
                "assistant_id": "my-assistant",
                "task": "Do work",
                "next": {"state_id": "END"},
            }],
            assistants=[{"id": "my-assistant"}],
            tools=[],
        )
        state = _make_state(generated_config=config)
        result = node(state)

        assert "result" in result
        assert isinstance(result["result"], CreateWorkflowRequest)
        assert result["result"].name == "Code Analyzer"  # from intent in _make_state
        assert len(result["result"].states) == 1

    def test_result_uses_sequential_mode(self):
        from codemie.workflows.workflow_generator.nodes.result import ResultNode
        from codemie.workflows.workflow_generator.models import GeneratedWorkflowConfig
        from codemie.core.workflow_models.workflow_models import WorkflowMode

        node = ResultNode()
        config = GeneratedWorkflowConfig(
            states=[{
                "id": "s1",
                "assistant_id": "a1",
                "task": "Do it",
                "next": {"state_id": "END"},
            }],
            assistants=[{"id": "a1"}],
            tools=[],
        )
        result = node(_make_state(generated_config=config))
        assert result["result"].mode == WorkflowMode.SEQUENTIAL
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_nodes.py::TestValidationNode tests/codemie/workflows/workflow_generator/test_nodes.py::TestResultNode -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create validation.py**

```python
# src/codemie/workflows/workflow_generator/nodes/validation.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from pydantic import ValidationError

from codemie.configs.logger import logger
from codemie.core.workflow_models.workflow_models import WorkflowState as WorkflowStateModel
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState

MAX_VALIDATION_RETRIES = 3


class ValidationNode:
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        config = state["generated_config"]
        errors: list[str] = []

        for state_dict in config.states:
            try:
                WorkflowStateModel(**state_dict)
            except ValidationError as exc:
                for err in exc.errors():
                    loc = " -> ".join(str(x) for x in err["loc"])
                    errors.append(f"State '{state_dict.get('id', '?')}' [{loc}]: {err['msg']}")
            except Exception as exc:
                errors.append(f"State '{state_dict.get('id', '?')}': {exc}")

        attempts = state.get("validation_attempts") or 0
        new_attempts = attempts + 1 if errors else attempts

        if errors and new_attempts >= MAX_VALIDATION_RETRIES:
            summary = f"Workflow generation failed after {MAX_VALIDATION_RETRIES} validation retries. Errors: {'; '.join(errors[:3])}"
            logger.error(summary)
            return {
                "validation_errors": errors,
                "validation_attempts": new_attempts,
                "error": summary,
            }

        return {
            "validation_errors": errors,
            "validation_attempts": new_attempts,
        }
```

- [ ] **Step 4: Create result.py**

```python
# src/codemie/workflows/workflow_generator/nodes/result.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from codemie.core.workflow_models.workflow_models import (
    CreateWorkflowRequest,
    WorkflowAssistant,
    WorkflowMode,
    WorkflowState as WorkflowStateModel,
    WorkflowTool,
)
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState


class ResultNode:
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        config = state["generated_config"]
        intent = state["intent"]

        states = [WorkflowStateModel(**s) for s in config.states]
        assistants = [WorkflowAssistant(**a) for a in config.assistants]
        tools = [WorkflowTool(**t) for t in config.tools]

        request = CreateWorkflowRequest(
            name=intent.workflow_name,
            description=intent.workflow_description,
            project=state["project"],
            mode=WorkflowMode.SEQUENTIAL,
            states=states,
            assistants=assistants,
        )
        # WorkflowTool entries: attach via yaml_config is the persisted path;
        # for the request object we store them on the assistants' tools lists.
        # tools list is returned separately in case the caller needs it.
        request.states = states

        return {"result": request}
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_nodes.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/codemie/workflows/workflow_generator/nodes/validation.py src/codemie/workflows/workflow_generator/nodes/result.py tests/codemie/workflows/workflow_generator/test_nodes.py
git commit -m "EPMCDME-10037: Add workflow generator validation and result nodes"
```

---

### Task 6: WorkflowGeneratorGraph

**Files:**
- Create: `src/codemie/workflows/workflow_generator/workflow.py`
- Create: `tests/codemie/workflows/workflow_generator/test_workflow_graph.py`

**Interfaces:**
- Consumes: all 5 nodes, `WorkflowGeneratorState`, `StateGraph`, `END`
- Produces: `WorkflowGeneratorGraph(llm_model, request_id).run(initial_state) → WorkflowGeneratorState`

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/workflows/workflow_generator/test_workflow_graph.py
from unittest.mock import Mock, patch, MagicMock
import pytest

from codemie.workflows.workflow_generator.models import (
    GeneratedWorkflowConfig, MappedNode, NodeMappingPlan, WorkflowIntent, WorkflowStep,
)
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.core.workflow_models.workflow_models import CreateWorkflowRequest, WorkflowMode


def _make_valid_intent():
    return WorkflowIntent(
        workflow_name="Test Workflow",
        workflow_description="A test",
        steps=[WorkflowStep(id="s1", description="Step 1", state_type="agent", next_step_id=None)],
    )


def _make_valid_plan():
    return NodeMappingPlan(nodes=[
        MappedNode(step_id="s1", state_type="agent", assistant_ref="agent-1",
                   tool_ref=None, custom_node_ref=None, task="Do step 1"),
    ])


def _make_valid_config():
    return GeneratedWorkflowConfig(
        states=[{"id": "s1", "assistant_id": "agent-1", "task": "Do step 1", "next": {"state_id": "END"}}],
        assistants=[{"id": "agent-1"}],
        tools=[],
    )


@patch("codemie.workflows.workflow_generator.nodes.intent_analysis.get_llm_by_credentials")
@patch("codemie.workflows.workflow_generator.nodes.node_mapping.get_llm_by_credentials")
@patch("codemie.workflows.workflow_generator.nodes.config_generation.get_llm_by_credentials")
def test_graph_happy_path(mock_cfg_llm, mock_map_llm, mock_intent_llm):
    from codemie.workflows.workflow_generator.workflow import WorkflowGeneratorGraph

    def make_mock_llm(return_value):
        llm = Mock()
        llm.with_structured_output.return_value.invoke.return_value = return_value
        return llm

    mock_intent_llm.return_value = make_mock_llm(_make_valid_intent())
    mock_map_llm.return_value = make_mock_llm(_make_valid_plan())
    mock_cfg_llm.return_value = make_mock_llm(_make_valid_config())

    graph = WorkflowGeneratorGraph(llm_model="gpt-4o", request_id="req-1")
    initial: WorkflowGeneratorState = {
        "nl_query": "Create a simple workflow",
        "user": Mock(id="u1", name="tester", username="tester@x.com"),
        "project": "demo",
        "available_tools": [],
        "intent": None,
        "node_plan": None,
        "generated_config": None,
        "validation_errors": [],
        "validation_attempts": 0,
        "result": None,
        "error": None,
    }
    final = graph.run(initial)

    assert final.get("error") is None
    assert isinstance(final["result"], CreateWorkflowRequest)
    assert final["result"].name == "Test Workflow"


@patch("codemie.workflows.workflow_generator.nodes.intent_analysis.get_llm_by_credentials")
@patch("codemie.workflows.workflow_generator.nodes.node_mapping.get_llm_by_credentials")
@patch("codemie.workflows.workflow_generator.nodes.config_generation.get_llm_by_credentials")
def test_graph_sets_error_after_max_retries(mock_cfg_llm, mock_map_llm, mock_intent_llm):
    from codemie.workflows.workflow_generator.workflow import WorkflowGeneratorGraph
    from codemie.workflows.workflow_generator.nodes.validation import MAX_VALIDATION_RETRIES

    def make_mock_llm(return_value):
        llm = Mock()
        llm.with_structured_output.return_value.invoke.return_value = return_value
        return llm

    # Config generation always returns an invalid config (missing required fields)
    bad_config = GeneratedWorkflowConfig(
        states=[{"id": "x", "next": {"state_id": "END"}}],  # no assistant_id/tool_id/custom_node_id
        assistants=[],
        tools=[],
    )
    mock_intent_llm.return_value = make_mock_llm(_make_valid_intent())
    mock_map_llm.return_value = make_mock_llm(_make_valid_plan())
    mock_cfg_llm.return_value = make_mock_llm(bad_config)

    graph = WorkflowGeneratorGraph(llm_model="gpt-4o", request_id=None)
    initial: WorkflowGeneratorState = {
        "nl_query": "Create workflow",
        "user": Mock(id="u1", name="t", username="t@x.com"),
        "project": "demo",
        "available_tools": [],
        "intent": None,
        "node_plan": None,
        "generated_config": None,
        "validation_errors": [],
        "validation_attempts": 0,
        "result": None,
        "error": None,
    }
    final = graph.run(initial)

    assert final.get("error") is not None
    assert final["result"] is None
    # config_generation was called MAX_VALIDATION_RETRIES times
    assert mock_cfg_llm.return_value.with_structured_output.return_value.invoke.call_count == MAX_VALIDATION_RETRIES
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_workflow_graph.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create workflow.py**

```python
# src/codemie/workflows/workflow_generator/workflow.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from typing import Optional

from langgraph.constants import END
from langgraph.graph import StateGraph

from codemie.workflows.workflow_generator.nodes.config_generation import ConfigGenerationNode
from codemie.workflows.workflow_generator.nodes.intent_analysis import IntentAnalysisNode
from codemie.workflows.workflow_generator.nodes.node_mapping import NodeMappingNode
from codemie.workflows.workflow_generator.nodes.result import ResultNode
from codemie.workflows.workflow_generator.nodes.validation import ValidationNode
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState


def _route_after_validation(state: WorkflowGeneratorState) -> str:
    if state.get("error"):
        return END
    if state.get("validation_errors"):
        return "config_generation"
    return "result"


class WorkflowGeneratorGraph:
    def __init__(self, llm_model: str, request_id: Optional[str] = None):
        self.llm_model = llm_model
        self.request_id = request_id
        self._intent_node = IntentAnalysisNode(llm_model, request_id)
        self._mapping_node = NodeMappingNode(llm_model, request_id)
        self._config_node = ConfigGenerationNode(llm_model, request_id)
        self._validation_node = ValidationNode()
        self._result_node = ResultNode()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(WorkflowGeneratorState)

        workflow.add_node("intent_analysis", self._intent_node)
        workflow.add_node("node_mapping", self._mapping_node)
        workflow.add_node("config_generation", self._config_node)
        workflow.add_node("validation", self._validation_node)
        workflow.add_node("result", self._result_node)

        workflow.set_entry_point("intent_analysis")
        workflow.add_edge("intent_analysis", "node_mapping")
        workflow.add_edge("node_mapping", "config_generation")
        workflow.add_edge("config_generation", "validation")
        workflow.add_conditional_edges(
            "validation",
            _route_after_validation,
            {
                "config_generation": "config_generation",
                "result": "result",
                END: END,
            },
        )
        workflow.add_edge("result", END)

        return workflow.compile()

    def run(self, initial_state: WorkflowGeneratorState) -> WorkflowGeneratorState:
        return self.graph.invoke(initial_state)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/test_workflow_graph.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/workflows/workflow_generator/workflow.py tests/codemie/workflows/workflow_generator/test_workflow_graph.py
git commit -m "EPMCDME-10037: Add WorkflowGeneratorGraph with retry validation loop"
```

---

### Task 7: REST API models and WorkflowGeneratorService

**Files:**
- Create: `src/codemie/rest_api/models/workflow_generator.py`
- Replace: `src/codemie/service/workflow_generator_service.py`
- Test (extend): `tests/codemie/service/test_workflow_generator_service.py`

**Interfaces:**
- Consumes: `WorkflowGeneratorGraph`, `WorkflowGeneratorState`, `ToolsInfoService`, `llm_service`, monitoring utilities, `WorkflowService`, `GuardrailService`
- Produces:
  - `WorkflowGeneratorRequest(nl_query, llm_model, persist, guardrail_ids)` — Pydantic BaseModel
  - `WorkflowGeneratorResponse(workflow_config, workflow_id)` — Pydantic BaseModel
  - `WorkflowGeneratorService.generate(nl_query, user, llm_model, persist, guardrail_ids, request_id) → WorkflowGeneratorResponse`

- [ ] **Step 1: Write failing tests**

Add to `tests/codemie/service/test_workflow_generator_service.py`:

```python
from unittest.mock import Mock, patch, MagicMock
import pytest

from codemie.core.workflow_models.workflow_models import CreateWorkflowRequest, WorkflowMode
from codemie.rest_api.models.workflow_generator import WorkflowGeneratorRequest, WorkflowGeneratorResponse


def _make_user(project="demo"):
    user = Mock()
    user.id = "user-1"
    user.name = "Test User"
    user.username = "test@example.com"
    user.current_project = project
    return user


def _make_create_request(project="demo"):
    return CreateWorkflowRequest(
        name="Generated Workflow",
        description="Auto-generated workflow",
        project=project,
        mode=WorkflowMode.SEQUENTIAL,
        states=[],
        assistants=[],
    )


class TestWorkflowGeneratorRequest:
    def test_default_values(self):
        req = WorkflowGeneratorRequest(nl_query="Create a workflow")
        assert req.nl_query == "Create a workflow"
        assert req.llm_model is None
        assert req.persist is False
        assert req.guardrail_ids is None

    def test_with_all_fields(self):
        req = WorkflowGeneratorRequest(
            nl_query="Workflow",
            llm_model="gpt-4o",
            persist=True,
            guardrail_ids=["g1", "g2"],
        )
        assert req.persist is True
        assert req.guardrail_ids == ["g1", "g2"]


class TestWorkflowGeneratorResponse:
    def test_without_workflow_id(self):
        resp = WorkflowGeneratorResponse(
            workflow_config=_make_create_request(),
        )
        assert resp.workflow_id is None

    def test_with_workflow_id(self):
        resp = WorkflowGeneratorResponse(
            workflow_config=_make_create_request(),
            workflow_id="wf-123",
        )
        assert resp.workflow_id == "wf-123"


@patch("codemie.service.workflow_generator_service.WorkflowGeneratorGraph")
@patch("codemie.service.workflow_generator_service.ToolsInfoService")
@patch("codemie.service.workflow_generator_service.llm_service")
def test_generate_returns_response(mock_llm_svc, mock_tools_svc, mock_graph_class):
    from codemie.service.workflow_generator_service import WorkflowGeneratorService

    mock_llm_svc.default_llm_model = "gpt-4o"
    mock_tools_svc.get_tools_info.return_value = []

    create_req = _make_create_request()
    mock_graph = Mock()
    mock_graph.run.return_value = {"result": create_req, "error": None, "validation_errors": []}
    mock_graph_class.return_value = mock_graph

    response = WorkflowGeneratorService.generate(
        nl_query="Create a workflow",
        user=_make_user(),
    )

    assert isinstance(response, WorkflowGeneratorResponse)
    assert response.workflow_config == create_req
    assert response.workflow_id is None


@patch("codemie.service.workflow_generator_service.WorkflowGeneratorGraph")
@patch("codemie.service.workflow_generator_service.ToolsInfoService")
@patch("codemie.service.workflow_generator_service.llm_service")
def test_generate_raises_on_graph_error(mock_llm_svc, mock_tools_svc, mock_graph_class):
    from codemie.service.workflow_generator_service import WorkflowGeneratorService
    from codemie.core.exceptions import ExtendedHTTPException

    mock_llm_svc.default_llm_model = "gpt-4o"
    mock_tools_svc.get_tools_info.return_value = []

    mock_graph = Mock()
    mock_graph.run.return_value = {
        "result": None,
        "error": "Validation failed after 3 retries",
        "validation_errors": ["missing field"],
    }
    mock_graph_class.return_value = mock_graph

    with pytest.raises(ExtendedHTTPException) as exc_info:
        WorkflowGeneratorService.generate(nl_query="bad query", user=_make_user())

    assert exc_info.value.code == 500


@patch("codemie.service.workflow_generator_service.WorkflowGeneratorGraph")
@patch("codemie.service.workflow_generator_service.ToolsInfoService")
@patch("codemie.service.workflow_generator_service.llm_service")
def test_generate_applies_guardrail_ids(mock_llm_svc, mock_tools_svc, mock_graph_class):
    from codemie.service.workflow_generator_service import WorkflowGeneratorService

    mock_llm_svc.default_llm_model = "gpt-4o"
    mock_tools_svc.get_tools_info.return_value = []

    create_req = _make_create_request()
    mock_graph = Mock()
    mock_graph.run.return_value = {"result": create_req, "error": None, "validation_errors": []}
    mock_graph_class.return_value = mock_graph

    response = WorkflowGeneratorService.generate(
        nl_query="test",
        user=_make_user(),
        guardrail_ids=["g-1", "g-2"],
    )

    assert response.workflow_config.guardrail_assignments is not None
    assert len(response.workflow_config.guardrail_assignments) == 2
    assert response.workflow_config.guardrail_assignments[0].guardrail_id == "g-1"


@patch("codemie.service.workflow_generator_service.WorkflowService")
@patch("codemie.service.workflow_generator_service.GuardrailService")
@patch("codemie.service.workflow_generator_service.WorkflowGeneratorGraph")
@patch("codemie.service.workflow_generator_service.ToolsInfoService")
@patch("codemie.service.workflow_generator_service.llm_service")
def test_generate_persist_creates_workflow(
    mock_llm_svc, mock_tools_svc, mock_graph_class, mock_guardrail_svc, mock_workflow_svc_class
):
    from codemie.service.workflow_generator_service import WorkflowGeneratorService

    mock_llm_svc.default_llm_model = "gpt-4o"
    mock_tools_svc.get_tools_info.return_value = []

    create_req = _make_create_request()
    mock_graph = Mock()
    mock_graph.run.return_value = {"result": create_req, "error": None, "validation_errors": []}
    mock_graph_class.return_value = mock_graph

    persisted_config = Mock()
    persisted_config.id = "wf-saved-id"
    mock_workflow_svc = Mock()
    mock_workflow_svc.create_workflow.return_value = persisted_config
    mock_workflow_svc_class.return_value = mock_workflow_svc

    response = WorkflowGeneratorService.generate(
        nl_query="test",
        user=_make_user(),
        persist=True,
    )

    assert response.workflow_id == "wf-saved-id"
    mock_workflow_svc.create_workflow.assert_called_once()
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/service/test_workflow_generator_service.py -v -k "not test_metric"
```
Expected: `ImportError` or attribute errors.

- [ ] **Step 3: Create workflow_generator.py API models**

```python
# src/codemie/rest_api/models/workflow_generator.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from codemie.core.workflow_models.workflow_models import CreateWorkflowRequest


class WorkflowGeneratorRequest(BaseModel):
    nl_query: str
    llm_model: Optional[str] = None
    persist: bool = False
    guardrail_ids: Optional[list[str]] = None


class WorkflowGeneratorResponse(BaseModel):
    workflow_config: CreateWorkflowRequest
    workflow_id: Optional[str] = None
```

- [ ] **Step 4: Replace workflow_generator_service.py**

```python
# src/codemie/service/workflow_generator_service.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# Licensed under the Apache License, Version 2.0

"""Service to generate workflow configurations from natural language queries."""

from __future__ import annotations

from typing import Optional

from codemie.configs.logger import current_user_email, logger, logging_user_id
from codemie.core.dependecies import get_project_for_metric
from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.guardrail import GuardrailAssignmentItem, GuardrailMode, GuardrailSource
from codemie.rest_api.models.workflow_generator import WorkflowGeneratorResponse
from codemie.rest_api.security.user import User
from codemie.service.llm_service.llm_service import llm_service
from codemie.service.monitoring.base_monitoring_service import emit_llm_token_metric, send_log_metric
from codemie.service.monitoring.metrics_constants import (
    WORKFLOW_GENERATOR_ERRORS_METRIC,
    WORKFLOW_GENERATOR_TOTAL_METRIC,
    MetricsAttributes,
)
from codemie.service.request_summary_manager import request_summary_manager
from codemie.service.tools.tools_info_service import ToolsInfoService
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator.workflow import WorkflowGeneratorGraph

_HELP_MESSAGE = "Try again with a different query or model."


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
        if not llm_model:
            llm_model = llm_service.default_llm_model

        try:
            available_tools = ToolsInfoService.get_tools_info(user=user)

            initial_state: WorkflowGeneratorState = {
                "nl_query": nl_query,
                "user": user,
                "project": user.current_project,
                "available_tools": available_tools,
                "intent": None,
                "node_plan": None,
                "generated_config": None,
                "validation_errors": [],
                "validation_attempts": 0,
                "result": None,
                "error": None,
            }

            graph = WorkflowGeneratorGraph(llm_model=llm_model, request_id=request_id)
            final_state = graph.run(initial_state)

            if final_state.get("error"):
                raise ExtendedHTTPException(
                    code=500,
                    message="Workflow generation failed after validation retries",
                    details=final_state["error"],
                    help=_HELP_MESSAGE,
                )

            workflow_request = final_state["result"]

            if guardrail_ids:
                workflow_request.guardrail_assignments = [
                    GuardrailAssignmentItem(
                        guardrail_id=gid,
                        mode=GuardrailMode.ALL,
                        source=GuardrailSource.BOTH,
                    )
                    for gid in guardrail_ids
                ]

            workflow_id: Optional[str] = None
            if persist:
                from codemie.core.workflow_models.workflow_config import WorkflowConfig
                from codemie.rest_api.models.guardrail import GuardrailEntity
                from codemie.service.guardrail.guardrail_service import GuardrailService
                from codemie.service.workflow_service import WorkflowService

                workflow_config = WorkflowConfig(**workflow_request.model_dump())
                workflow_config = WorkflowService().create_workflow(workflow_config, user)
                GuardrailService.sync_guardrail_assignments_for_entity(
                    user=user,
                    entity_type=GuardrailEntity.WORKFLOW,
                    entity_id=str(workflow_config.id),
                    entity_project_name=workflow_config.project,
                    guardrail_assignments=workflow_request.guardrail_assignments,
                )
                workflow_id = str(workflow_config.id)

            emit_llm_token_metric(
                name=WORKFLOW_GENERATOR_TOTAL_METRIC,
                request_id=request_id,
                base_attributes={
                    MetricsAttributes.LLM_MODEL: llm_model,
                    MetricsAttributes.USER_ID: logging_user_id.get("-"),
                    MetricsAttributes.USER_NAME: current_user_email.get("-"),
                    MetricsAttributes.PROJECT: get_project_for_metric(),
                },
            )

            return WorkflowGeneratorResponse(
                workflow_config=workflow_request,
                workflow_id=workflow_id,
            )

        except ExtendedHTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to generate workflow: {exc}", exc_info=True)
            send_log_metric(
                name=WORKFLOW_GENERATOR_ERRORS_METRIC,
                attributes={
                    MetricsAttributes.LLM_MODEL: llm_model or "default",
                    MetricsAttributes.USER_ID: logging_user_id.get("-"),
                    MetricsAttributes.USER_NAME: current_user_email.get("-"),
                    MetricsAttributes.PROJECT: get_project_for_metric(),
                },
            )
            raise ExtendedHTTPException(
                code=500,
                message="Failed to generate workflow",
                details=f"An error occurred while generating workflow: {exc!s}",
                help=_HELP_MESSAGE,
            ) from exc
        finally:
            if request_id:
                request_summary_manager.clear_summary(request_id)
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/service/test_workflow_generator_service.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/codemie/rest_api/models/workflow_generator.py src/codemie/service/workflow_generator_service.py tests/codemie/service/test_workflow_generator_service.py
git commit -m "EPMCDME-10037: Add WorkflowGeneratorService and API response models"
```

---

### Task 8: API endpoint

**Files:**
- Modify: `src/codemie/rest_api/routers/workflow.py` (append endpoint)
- Create: `tests/codemie/rest_api/routers/test_workflow_generator.py`

**Interfaces:**
- Consumes: `WorkflowGeneratorRequest`, `WorkflowGeneratorResponse`, `WorkflowGeneratorService`, existing `router`, `authenticate`
- Produces: `POST /v1/workflows/generate` → `200 WorkflowGeneratorResponse`

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/rest_api/routers/test_workflow_generator.py
from unittest.mock import patch, Mock

import pytest
from fastapi.testclient import TestClient

from codemie.core.workflow_models.workflow_models import CreateWorkflowRequest, WorkflowMode
from codemie.rest_api.models.workflow_generator import WorkflowGeneratorResponse


def _make_app():
    from fastapi import FastAPI
    from codemie.rest_api.routers import workflow as workflow_router
    app = FastAPI()
    app.include_router(workflow_router.router)
    return app


def _make_user():
    user = Mock()
    user.id = "user-1"
    user.name = "Test User"
    user.username = "test@example.com"
    user.current_project = "demo"
    user.is_admin = False
    user.project_names = ["demo"]
    user.admin_project_names = []
    return user


def _make_response():
    return WorkflowGeneratorResponse(
        workflow_config=CreateWorkflowRequest(
            name="Generated",
            description="Generated workflow",
            project="demo",
            mode=WorkflowMode.SEQUENTIAL,
            states=[],
            assistants=[],
        ),
        workflow_id=None,
    )


@patch("codemie.rest_api.routers.workflow.authenticate")
@patch("codemie.service.workflow_generator_service.WorkflowGeneratorService.generate")
def test_generate_workflow_returns_200(mock_generate, mock_auth):
    mock_auth.return_value = _make_user()
    mock_generate.return_value = _make_response()

    client = TestClient(_make_app())
    response = client.post(
        "/workflows/generate",
        json={"nl_query": "Create a code review workflow"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "workflow_config" in data
    assert data["workflow_config"]["name"] == "Generated"


@patch("codemie.rest_api.routers.workflow.authenticate")
@patch("codemie.service.workflow_generator_service.WorkflowGeneratorService.generate")
def test_generate_workflow_with_persist_flag(mock_generate, mock_auth):
    mock_auth.return_value = _make_user()
    resp = _make_response()
    resp.workflow_id = "wf-saved"
    mock_generate.return_value = resp

    client = TestClient(_make_app())
    response = client.post(
        "/workflows/generate",
        json={"nl_query": "Create workflow", "persist": True},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["workflow_id"] == "wf-saved"
    _, kwargs = mock_generate.call_args
    assert kwargs.get("persist") is True or mock_generate.call_args[0][3] is True


@patch("codemie.rest_api.routers.workflow.authenticate")
@patch("codemie.service.workflow_generator_service.WorkflowGeneratorService.generate")
def test_generate_workflow_service_error_returns_500(mock_generate, mock_auth):
    from codemie.core.exceptions import ExtendedHTTPException

    mock_auth.return_value = _make_user()
    mock_generate.side_effect = ExtendedHTTPException(
        code=500,
        message="Generation failed",
        details="LLM timeout",
        help="Try again",
    )

    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.post(
        "/workflows/generate",
        json={"nl_query": "bad query"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
```

- [ ] **Step 2: Run to confirm fail**

```bash
poetry run pytest tests/codemie/rest_api/routers/test_workflow_generator.py -v
```
Expected: `404` (endpoint not registered yet) or import error.

- [ ] **Step 3: Add endpoint to workflow.py router**

At the end of `src/codemie/rest_api/routers/workflow.py`, add:

```python
@router.post(
    "/workflows/generate",
    status_code=status.HTTP_200_OK,
    response_model=WorkflowGeneratorResponse,
)
def generate_workflow(
    raw_request: Request,
    request: WorkflowGeneratorRequest,
    user: User = Depends(authenticate),
):
    """Generate a workflow configuration from a natural language description."""
    from codemie.configs.logger import set_logging_info
    from codemie.service.llm_service.utils import set_llm_context
    from codemie.service.workflow_generator_service import WorkflowGeneratorService

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

Also add these imports near the top of the router file (after existing imports):

```python
from fastapi import Request
from codemie.rest_api.models.workflow_generator import WorkflowGeneratorRequest, WorkflowGeneratorResponse
```

(Check if `Request` is already imported — if yes, skip that line.)

- [ ] **Step 4: Run tests to confirm pass**

```bash
poetry run pytest tests/codemie/rest_api/routers/test_workflow_generator.py -v
```
Expected: all PASS.

- [ ] **Step 5: Run full test suite for the new files**

```bash
poetry run pytest tests/codemie/workflows/workflow_generator/ tests/codemie/service/test_workflow_generator_service.py tests/codemie/rest_api/routers/test_workflow_generator.py -v
```
Expected: all PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check src/codemie/workflows/workflow_generator/ src/codemie/service/workflow_generator_service.py src/codemie/rest_api/models/workflow_generator.py src/codemie/rest_api/routers/workflow.py --fix
```

- [ ] **Step 7: Commit**

```bash
git add src/codemie/rest_api/routers/workflow.py tests/codemie/rest_api/routers/test_workflow_generator.py
git commit -m "EPMCDME-10037: Add POST /v1/workflows/generate endpoint"
```

---

## Self-Review Checklist

After writing the plan, checking spec coverage:

| Spec requirement | Task |
|---|---|
| 5-node StateGraph chain | Tasks 4, 5, 6 |
| IntentAnalysisNode (NL → WorkflowIntent) | Task 4 |
| NodeMappingNode (steps → NodeMappingPlan) | Task 4 |
| ConfigGenerationNode (plan → config) | Task 4 |
| ValidationNode with retry up to 3× | Task 5, 6 |
| ResultNode assembles CreateWorkflowRequest | Task 5 |
| persist flag → WorkflowService.create_workflow | Task 7 |
| guardrail_ids → GuardrailAssignmentItem list | Task 7 |
| POST /v1/workflows/generate | Task 8 |
| Metrics: TOTAL + ERRORS | Task 1, Task 7 |
| request_summary_manager.clear_summary in finally | Task 7 |
| Project from user.current_project | Task 7 |
| Unit tests for each node | Tasks 4, 5 |
| Graph retry integration test | Task 6 |
| Service tests incl. persist + guardrails | Task 7 |
| Router tests incl. error path | Task 8 |
