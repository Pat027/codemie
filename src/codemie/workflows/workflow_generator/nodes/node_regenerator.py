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

from typing import Optional

from codemie.configs.logger import logger
from codemie.workflows.workflow_generator.nodes.node_generator import NodeGeneratorNode
from codemie.workflows.workflow_generator.nodes.tools_selector import ToolsSelectorNode
from codemie.workflows.workflow_generator.schemas import NodeMappingPlan, StepPlan
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk


class NodeRegeneratorNode:
    """Regenerates only the validation-failed nodes, in intent order, each with its correct predecessor."""

    def __init__(self, llm_model: str, request_id: Optional[str] = None):
        self.llm_model = llm_model
        self.request_id = request_id
        self._generator = NodeGeneratorNode(llm_model, request_id)
        self._tools_selector = ToolsSelectorNode(llm_model, request_id)

    def _resolve_predecessor(self, i: int, intent, nodes_by_id: dict, failed_regen: set):
        pred = intent.steps[i - 1] if i > 0 else None
        return nodes_by_id.get(pred.id) if pred and pred.id not in failed_regen else None

    def _try_generate_node(
        self,
        step,
        step_plan,
        all_step_ids,
        previous_node,
        available_tools,
        failed_regen: set,
        validation_errors: str = "",
    ):
        try:
            return self._generator._generate_node(
                step_plan, all_step_ids, previous_node, available_tools, validation_errors or None
            )
        except Exception as exc:
            logger.error(f"Regeneration failed for step '{step.id}': {exc}", exc_info=True)
            failed_regen.add(step.id)
            return None

    @staticmethod
    def _build_step_errors_section(step_id: str, all_errors: list[str]) -> str:
        lines = [e for e in all_errors if e.startswith(f"State '{step_id}':")]
        if not lines:
            return ""
        body = "\n".join(f"  - {e}" for e in lines)
        header = "\n── REGENERATION — FIX THESE ERRORS ──────────────────────────────\n"
        preamble = "\nFix each validation error below before producing the new node:\n\n"
        return f"{header}{preamble}{body}\n"

    def _try_select_tools(self, new_node, step, available_tools):
        try:
            return self._tools_selector.select_tools_for_node(
                node=new_node,
                step_action=step.description,
                has_side_effect=step.has_side_effect,
                available_tools=available_tools,
            )
        except Exception as exc:
            logger.warning(f"Tools selection failed for step '{step.id}' during regeneration: {exc}")
            return new_node

    def __call__(self, state: WorkflowGeneratorState) -> dict:
        failed_step_ids: list[str] = state.get(sk.FAILED_STEP_IDS) or []
        if not failed_step_ids:
            return {sk.FAILED_STEP_IDS: []}

        intent = state[sk.INTENT]
        step_plans: list[StepPlan] = state[sk.STEP_PLANS]
        node_plan: NodeMappingPlan = state[sk.NODE_PLAN]
        available_tools: list = state.get(sk.AVAILABLE_TOOLS) or []
        all_step_ids = [s.id for s in intent.steps]

        step_plan_by_id = {sp.step_id: sp for sp in step_plans}
        nodes_by_id = {n.step_id: n for n in node_plan.nodes}

        all_errors: list[str] = state.get(sk.VALIDATION_ERRORS) or []
        failed_set = set(failed_step_ids)
        failed_regen: set[str] = set()
        for i, step in enumerate(intent.steps):
            if step.id not in failed_set:
                continue
            step_plan = step_plan_by_id.get(step.id)
            if not step_plan:
                logger.warning(f"No StepPlan found for failed step '{step.id}' — skipping")
                failed_regen.add(step.id)
                continue
            previous_node = self._resolve_predecessor(i, intent, nodes_by_id, failed_regen)
            errors_section = self._build_step_errors_section(step.id, all_errors)
            new_node = self._try_generate_node(
                step, step_plan, all_step_ids, previous_node, available_tools, failed_regen, errors_section
            )
            if new_node:
                nodes_by_id[step.id] = self._try_select_tools(new_node, step, available_tools)

        ordered_nodes = [nodes_by_id[s.id] for s in intent.steps if s.id in nodes_by_id]
        return {
            sk.NODE_PLAN: NodeMappingPlan(nodes=ordered_nodes),
            sk.FAILED_STEP_IDS: [],
        }
