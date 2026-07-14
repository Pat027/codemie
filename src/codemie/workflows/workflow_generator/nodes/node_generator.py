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

from __future__ import annotations

import json
from typing import Optional

from codemie.configs.logger import logger
from codemie.core.dependecies import get_llm_by_credentials
from codemie.templates.agents.workflow_generator import NODE_GENERATION_PROMPT
from codemie.workflows.workflow_generator.schemas import MappedNode, NodeMappingPlan, StepPlan
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk


class NodeGeneratorNode:
    def __init__(self, llm_model: str, request_id: Optional[str] = None):
        self.llm_model = llm_model
        self.request_id = request_id

    def _format_tools(self, available_tools: list) -> str:
        lines: list[str] = []
        for toolkit in available_tools:
            for tool in toolkit.get("tools", []):
                name = tool.get("name", "")
                desc = tool.get("description", "")
                if name:
                    lines.append(f"  {name}: {desc}")
        lines.append("  code_executor: Execute Python/shell scripts, read/write files, process large datasets")
        return "\n".join(lines)

    def _format_previous_node(self, previous_node: Optional[MappedNode]) -> str:
        if previous_node is None:
            return "none (this is the first node)"
        return json.dumps(
            {
                "step_id": previous_node.step_id,
                "output_key": previous_node.context_store.writes[0].key
                if previous_node.context_store and previous_node.context_store.writes
                else None,
                "output_schema": previous_node.output_schema,
                "transition_type": previous_node.transition_type,
            },
            indent=2,
        )

    def _generate_node(
        self,
        step_plan: StepPlan,
        all_step_ids: list[str],
        previous_node: Optional[MappedNode],
        available_tools: list,
        validation_errors: Optional[str] = None,
    ) -> MappedNode:
        prompt = NODE_GENERATION_PROMPT.format(
            step_plan=step_plan.model_dump_json(indent=2),
            all_step_ids="\n".join(f"  - {sid}" for sid in all_step_ids) + "\n  - end",
            previous_node=self._format_previous_node(previous_node),
            available_tools=self._format_tools(available_tools),
            validation_errors=validation_errors or "",
        )
        llm = get_llm_by_credentials(
            llm_model=self.llm_model,
            temperature=0.0,
            streaming=False,
            request_id=self.request_id,
        )
        return llm.with_structured_output(MappedNode).invoke(prompt)

    def __call__(self, state: WorkflowGeneratorState) -> dict:
        idx: int = state.get(sk.CURRENT_NODE_INDEX, 0)
        step_plans: list[StepPlan] = state[sk.STEP_PLANS]
        if idx >= len(step_plans):
            return {
                sk.ERROR: (
                    f"step_plans index {idx} out of range — "
                    f"StepPlannerNode returned {len(step_plans)} plans for "
                    f"{len(state[sk.INTENT].steps)} intent steps"
                )
            }
        step_plan = step_plans[idx]

        intent = state[sk.INTENT]
        all_step_ids = [s.id for s in intent.steps]
        previous_node: Optional[MappedNode] = state.get(sk.PREVIOUS_NODE)
        available_tools: list = state.get(sk.AVAILABLE_TOOLS) or []

        try:
            new_node = self._generate_node(step_plan, all_step_ids, previous_node, available_tools)
        except Exception as exc:
            logger.error(f"Node generation failed for step '{step_plan.step_id}': {exc}", exc_info=True)
            return {sk.ERROR: f"Node generation failed for step '{step_plan.step_id}': {exc}"}

        existing_plan: Optional[NodeMappingPlan] = state.get(sk.NODE_PLAN)
        existing_nodes = list(existing_plan.nodes) if existing_plan else []
        updated_plan = NodeMappingPlan(nodes=existing_nodes + [new_node])

        return {
            sk.NODE_PLAN: updated_plan,
            sk.CURRENT_NODE_INDEX: idx + 1,
            sk.PREVIOUS_NODE: new_node,
        }
