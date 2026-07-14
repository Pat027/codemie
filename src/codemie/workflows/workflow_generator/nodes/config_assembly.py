# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deterministic translation of NodeMappingPlan → GeneratedWorkflowConfig.

No LLM call — all information is already in the node plan after schema_enrichment.
"""

from __future__ import annotations

from codemie.workflows.workflow_generator.schemas import (
    GeneratedAssistant,
    GeneratedCondition,
    GeneratedNextState,
    GeneratedState,
    GeneratedSwitch,
    GeneratedSwitchCase,
    MappedNode,
    NodeMappingPlan,
    GeneratedWorkflowConfig,
    StepPlan,
)
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk


def _extract_write_metadata(node: MappedNode, output_contracts: dict) -> tuple:
    contract = output_contracts.get(node.step_id)
    # output_key from node's own context_store write — authoritative source;
    # step_plan is advisory only, LLM may use a slightly different key name
    writes = node.context_store.writes if node.context_store else []
    if writes:
        output_key = writes[0].key
    elif contract:
        output_key = contract.output_key
    else:
        output_key = None
    is_json = contract.output_is_json if contract else False
    append = writes[0].append if writes else False
    return output_key, is_json, append


def _build_next_state_kwargs(node: MappedNode, output_key, is_json: bool, append: bool) -> dict:
    kwargs: dict = {}
    if output_key:
        kwargs["output_key"] = output_key
        if is_json:
            kwargs["include_in_llm_history"] = False
    else:
        kwargs["store_in_context"] = False
    if append:
        kwargs["append_to_context"] = True
    if node.include_in_iterator_context is not None:
        kwargs["include_in_iterator_context"] = node.include_in_iterator_context
    return kwargs


def _build_transition(node: MappedNode, tt: str, kwargs: dict) -> GeneratedNextState:
    if tt == "conditional":
        return GeneratedNextState(
            condition=GeneratedCondition(
                expression=node.condition_expression or "",
                then=node.then_state_id or "end",
                otherwise=node.otherwise_state_id or "end",
            ),
            **kwargs,
        )
    if tt == "switch":
        return GeneratedNextState(
            switch=GeneratedSwitch(
                cases=[GeneratedSwitchCase(condition=c.condition, state_id=c.state_id) for c in node.switch_cases],
                default=node.switch_default or "end",
            ),
            **kwargs,
        )
    if tt == "parallel":
        return GeneratedNextState(state_ids=node.next_state_ids or [], **kwargs)
    next_id = (node.next_state_ids[0] if node.next_state_ids else None) or "end"
    if tt == "iterative":
        return GeneratedNextState(state_id=next_id, iter_key=node.iter_key, **kwargs)
    return GeneratedNextState(state_id=next_id, **kwargs)


def _build_next_state(node: MappedNode, output_contracts: dict) -> GeneratedNextState:
    output_key, is_json, append = _extract_write_metadata(node, output_contracts)
    kwargs = _build_next_state_kwargs(node, output_key, is_json, append)
    return _build_transition(node, node.transition_type or "simple", kwargs)


def _build_states(node_plan: NodeMappingPlan, output_contracts: dict) -> list[GeneratedState]:
    states = []
    for node in node_plan.nodes:
        next_state = _build_next_state(node, output_contracts)
        state = GeneratedState(
            id=node.step_id,
            task=node.task,
            assistant_id=node.assistant_ref,
            output_schema=node.output_schema or None,
            finish_iteration=node.finish_iteration or None,
            interrupt_before=node.interrupt_before or None,
            resolve_dynamic_values_in_prompt=True if "{{" in (node.task or "") else None,
            next=next_state,
        )
        states.append(state)
    return states


def _build_assistants(node_plan: NodeMappingPlan) -> list[GeneratedAssistant]:
    seen: dict[str, GeneratedAssistant] = {}
    for node in node_plan.nodes:
        ref = node.assistant_ref
        if not ref:
            continue
        if ref not in seen:
            seen[ref] = GeneratedAssistant(
                id=ref,
                system_prompt=node.assistant_system_prompt,
                tools=list(node.tools),
            )
        else:
            # Union tools if same assistant used by multiple states
            existing_tools = set(seen[ref].tools)
            for t in node.tools:
                if t not in existing_tools:
                    seen[ref].tools.append(t)
                    existing_tools.add(t)
    return list(seen.values())


class ConfigAssemblyNode:
    def __call__(self, state: WorkflowGeneratorState) -> dict:
        node_plan: NodeMappingPlan = state[sk.NODE_PLAN]
        step_plans: list[StepPlan] = state.get(sk.STEP_PLANS) or []

        output_contracts = {sp.step_id: sp for sp in step_plans}

        states = _build_states(node_plan, output_contracts)
        assistants = _build_assistants(node_plan)

        config = GeneratedWorkflowConfig(states=states, assistants=assistants)
        return {sk.GENERATED_CONFIG: config}
