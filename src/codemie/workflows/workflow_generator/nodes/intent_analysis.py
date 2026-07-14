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

from codemie.core.dependecies import get_llm_by_credentials
from codemie.templates.agents.workflow_generator import INTENT_ANALYSIS_PROMPT
from codemie.workflows.workflow_generator.schemas import WorkflowIntent
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk


class IntentAnalysisNode:
    def __init__(self, llm_model: str, request_id: Optional[str] = None):
        self.llm_model = llm_model
        self.request_id = request_id

    def __call__(self, state: WorkflowGeneratorState) -> dict:
        prompt = INTENT_ANALYSIS_PROMPT.replace("{nl_query}", state[sk.NL_QUERY])
        llm = get_llm_by_credentials(
            llm_model=self.llm_model,
            temperature=0.0,
            streaming=False,
            request_id=self.request_id,
        )
        intent: WorkflowIntent = llm.with_structured_output(WorkflowIntent).invoke(prompt)
        return {sk.INTENT: intent}
