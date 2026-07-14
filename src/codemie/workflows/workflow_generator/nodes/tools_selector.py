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

"""Runs after each node is generated. Determines which tools the step actually needs
(based on the step's intent goal and generated task) and replaces the node's tool list."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from codemie.configs.logger import logger
from codemie.core.dependecies import get_llm_by_credentials
from codemie.templates.agents.workflow_generator import TOOLS_SELECTION_PROMPT
from codemie.workflows.workflow_generator.schemas import MappedNode, NodeMappingPlan
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk


class _ToolSelection(BaseModel):
    tools: list[str] = Field(
        description="Exact tool names from the catalog needed for this step. Empty list if none required."
    )


class ToolsSelectorNode:
    """Corrects the tool list of the last generated node in node_plan.

    Runs between node_generator and node_generator_router.
    NodeRegeneratorNode calls select_tools_for_node() directly on each regenerated node.
    """

    def __init__(self, llm_model: str, request_id: Optional[str] = None):
        self.llm_model = llm_model
        self.request_id = request_id

    def _format_tools_catalog(self, available_tools: list) -> str:
        lines: list[str] = []
        for toolkit in available_tools:
            for tool in toolkit.get("tools", []):
                name = tool.get("name", "")
                desc = tool.get("description", "")
                if name:
                    lines.append(f"  {name}: {desc}")
        lines.append("  code_executor: Execute Python/shell scripts, read/write files, process large datasets")
        return "\n".join(lines)

    def select_tools_for_node(
        self,
        node: MappedNode,
        step_action: str,
        has_side_effect: bool,
        available_tools: list,
    ) -> MappedNode:
        """Determine correct tools for a node and return a corrected copy."""
        tools_catalog = self._format_tools_catalog(available_tools)
        prompt = TOOLS_SELECTION_PROMPT.format(
            step_action=step_action,
            has_side_effect=has_side_effect,
            step_task=node.task or "(no task defined)",
            tools_catalog=tools_catalog,
        )
        llm = get_llm_by_credentials(
            llm_model=self.llm_model,
            temperature=0.0,
            streaming=False,
            request_id=self.request_id,
        )
        result: _ToolSelection = llm.with_structured_output(_ToolSelection).invoke(prompt)
        return node.model_copy(update={"tools": result.tools})

    def __call__(self, state: WorkflowGeneratorState) -> dict:
        node_plan: Optional[NodeMappingPlan] = state.get(sk.NODE_PLAN)
        if not node_plan or not node_plan.nodes:
            return {}

        intent = state[sk.INTENT]
        available_tools: list = state.get(sk.AVAILABLE_TOOLS) or []
        intent_steps_by_id = {s.id: s for s in intent.steps}

        last_node = node_plan.nodes[-1]
        intent_step = intent_steps_by_id.get(last_node.step_id)
        if not intent_step:
            return {}

        try:
            corrected = self.select_tools_for_node(
                node=last_node,
                step_action=intent_step.description,
                has_side_effect=intent_step.has_side_effect,
                available_tools=available_tools,
            )
        except Exception as exc:
            logger.warning(f"Tools selection failed for node '{last_node.step_id}': {exc} — keeping generated tools")
            return {}

        updated_nodes = list(node_plan.nodes[:-1]) + [corrected]
        return {sk.NODE_PLAN: NodeMappingPlan(nodes=updated_nodes)}
