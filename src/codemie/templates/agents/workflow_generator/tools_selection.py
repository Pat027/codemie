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

TOOLS_SELECTION_PROMPT = """You are a workflow tools analyst. Given a step's goal and its generated task, \
select EXACTLY the tools this step needs from the available tools catalog.

## Step Information
Action (high-level goal): {step_action}
Has side effect (writes to external system): {has_side_effect}

## Generated Task
{step_task}

## Available Tools
{tools_catalog}

## Selection Rules
1. Include a tool ONLY if the step's action or task explicitly requires calling that external system or API.
   Examples: "create Jira ticket" → include Jira tool; "fetch GitHub PRs" → include GitHub tool.
2. Include "code_executor" ONLY if the step creates or writes files, executes shell or Python scripts, \
or transforms large datasets via code — NOT for pure LLM text reasoning, summarization, or analysis.
3. If has_side_effect is false, the step is pure LLM work — return empty list unless \
code/file execution is clearly needed.
4. If has_side_effect is true, include the external tool(s) that enable the interaction. \
If no matching tool exists in the catalog, return empty list — do NOT invent tool names.
5. Return ONLY exact tool names from the catalog above — no invented names, no partial matches.
6. Omit tools the step does not use — a shorter, precise list beats a broad one."""
