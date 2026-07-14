# Complexity Assessment: workflow generator langgraph chain nl-to-workflow

**Task**: Implement WorkflowGeneratorService as a multi-step LangGraph chain that accepts a natural language query and generates a validated CreateWorkflowRequest with guardrail assignments.
**Generated**: 2026-06-30T00:00:00Z

---

## Dimension Scores

| Dimension            | Score | Label |
|----------------------|-------|-------|
| Component Scope      | 6     | XXL   |
| Requirements Clarity | 5     | XL    |
| Technical Risk       | 5     | XL    |
| File Change Estimate | 5     | XL    |
| Dependencies         | 1     | XS    |
| Affected Layers      | 4     | L     |

**Total: 26/36 — XL**

> Borderline note: score of 26 lands at the L/XL boundary. Component Scope scores XXL (6), which triggers the lean-higher rule per guide. Routing is XL.

---

## Key Reasoning

- **Component Scope (XXL)**: The task creates a new `src/codemie/workflows/workflow_generator/` subpackage (chain class, 3–5 node classes, state TypedDict, 3–5 output Pydantic models) mirroring `assistant_generator/`, plus modifies `workflow_generator_service.py` (stub to full), `rest_api/routers/workflow.py` (new endpoint), and calls into `WorkflowExecutor`, `GuardrailService`, and `WorkflowService`. Multiple workflows and orchestration subsystems are affected. Red flag applied: "affects multiple workflows or agents" bumped XL(5) to XXL(6).
- **Requirements Clarity (XL)**: The 5-step chain is enumerated but critical details are absent — no router endpoint path/schema, no definition of structured output models per chain step, guardrail application strategy during generation is ambiguous, and the task_context conflates `WorkflowConfigIndexService` with the validation entrypoint (it is a listing service; actual validation lives in `WorkflowExecutor.validate_workflow`). Red flag applied: vague acceptance criteria bumped L(4) to XL(5).
- **Technical Risk (XL)**: Applying guardrails to LLM-generated workflow nodes during generation is novel — `BaseNode._apply_node_input_guardrails` is a runtime execution construct. The multi-step LLM chain (5+ sequential calls) creates compounding hallucination risk; `WorkflowState @model_validator` strictness means structurally valid LLM output can still fail resource cross-reference validation. Red flag applied: novel guardrail integration use case bumped L(4) to XL(5).
- **File Change Estimate (XL)**: 12–18 files across 5+ directories — new `workflows/workflow_generator/` subpackage (chain, nodes, models), prompt templates, service implementation, router endpoint, and test files.
- **Red flags applied**: "Affects multiple workflows or agents" bumped Component Scope XL(5) to XXL(6); vague acceptance criteria and conflated service reference bumped Requirements Clarity L(4) to XL(5); novel guardrail-in-generation use case bumped Technical Risk L(4) to XL(5).

---

## Routing

SPLIT REQUIRED — XL. Splitting is strongly recommended.

---

## Splitting Recommendation — By Layer (selected)

- **Story 1 — Workflow generation chain (Workflow/Orchestration layer)**: Create `src/codemie/workflows/workflow_generator/` subpackage — chain class, 3–5 node classes (intent analysis, planning, node generation, state generation, validation node), state TypedDict, structured output Pydantic models, and prompt templates in `src/codemie/templates/`. Unit tests under `tests/codemie/workflows/workflow_generator/`. No service wiring, no router. Delivers a self-contained, independently testable LangGraph chain.
- **Story 2 — Service layer and validation gate**: Implement `WorkflowGenerator.generate()` in `src/codemie/service/workflow_generator_service.py` — wire the generation chain, call `WorkflowExecutor.validate_workflow`, integrate `GuardrailService.apply_guardrails_for_entities` and `GuardrailService.sync_guardrail_assignments_for_entity`, delegate persistence to `WorkflowService.create_workflow`. Service-level unit tests under `tests/codemie/service/`. No router changes.
- **Story 3 — API layer**: Add `POST /v1/workflows/generate` endpoint to `src/codemie/rest_api/routers/workflow.py`, define request/response schemas, wire `WorkflowGenerator`, apply `ExtendedHTTPException` error handling. Register router in `src/codemie/rest_api/main.py` if needed. Router-level tests under `tests/codemie/rest_api/routers/`.

> XL: Splitting is strongly recommended. Stories 1 → 2 → 3 have a clear dependency order and each fits M size independently.
