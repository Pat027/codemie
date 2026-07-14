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

INTENT_ANALYSIS_PROMPT = """
## Instructions
Analyze the provided natural-language workflow request and extract a concise, structured workflow intent and execution plan. Produce a single, strictly formatted JSON object that downstream systems can parse reliably.

## Inputs
- {nl_query} (string): The user's request in natural language.
- Optional context (string, optional): Any constraints, available tools, policies, or environment details.

## Output Format (strict JSON only; no additional prose)
{
  "workflow_name": "kebab-case, <=5-words",
  "steps": [
    {
      "id": "kebab-case-identifier",
      "action": "Imperative verb phrase: the concrete action this step performs (e.g. 'Fetch all open PRs from GitHub', 'Deploy build artifact to staging').",
      "state_type": "agent",
      "next_step_id": "next-step-id or null if terminal or branching",
      "needs_iteration": true | false,
      "needs_branching": true | false,
      "has_side_effect": true | false,
      "needs_human_approval": true | false,
      "needs_code_executor": true | false
    }
    // ... additional steps in execution order
  ]
}

Notes:
- next_step_id:
  - For sequential flows: set to the id of the next step.
  - For terminal steps: set to null.
  - For branching steps (needs_branching=true): set to null. The orchestrator will derive conditional transitions.
- All steps MUST have state_type = "agent".
- Tools (including any code executor) are ALWAYS attached to assistant nodes, never standalone.
- Set needs_code_executor=true when a step requires creating or writing files, running scripts, executing shell/Python code, or large-data transformation. Pure LLM reasoning with no file I/O or script execution → false.

## Steps to Follow
1. Parse Intent
   - Identify the overarching goal, key entities (resources, systems), triggers, outputs, and side effects.
2. Define Steps
   - Enumerate minimal, logically ordered steps with unique kebab-case ids.
   - Write action as a short imperative verb phrase naming the concrete operation (verb + object + optional qualifier).
   - Mark the fan-out source (e.g., "fetch list") as needs_iteration=false.
   - Mark the loop body as needs_iteration=true, when the same operation repeats over a list that node produces.
   - Mark needs_branching=true where the next path depends on the step's output/value.
   - CRITICAL: When a step has needs_branching=true, you MUST define each branch target as its own separate step.
     Never fold two different processing paths into one step or skip defining them. Even if branches converge at
     a later join step, each branch path must be a distinct step_id in the list.
     Example: "if score <= 2 → analyze comments; else → mark passed" requires TWO steps:
       { "id": "analyze-comments", ... } and { "id": "mark-as-passed", ... }
     Not one step that handles both cases.
   - Set has_side_effect=true for steps that modify external state (deploy, write, notify, create ticket, etc.).
   - Set needs_code_executor=true only when the step creates/writes files, executes shell or Python scripts, or performs large-data processing; otherwise false.
   - Set needs_human_approval=true when risky or policy-gated side effects need confirmation.
3. Wire Transitions
   - Assign next_step_id for sequential transitions.
   - Use null for terminal steps and for branching steps (conditional routing is implied).
4. Validate and Refine (fix before output)
   - workflow_name <= 5 words, kebab-case.
   - action is an imperative verb phrase, not a sentence with subject.
   - Step ids are unique, kebab-case, and referenced correctly by next_step_id.
   - Flags are coherent:
     - needs_iteration only for loop bodies over lists.
     - needs_branching only when downstream path depends on output value.
     - has_side_effect only for externally visible actions.
     - needs_code_executor only when step creates/writes files, runs scripts, or executes code.
   - No dangling next_step_id references; no unreachable steps.
   - Ensure the final JSON is syntactically valid and self-consistent.

## Routing Flags Guide
- needs_iteration=true
  - Signals: "for each ...", "process every ...", "review all ...", "send to each ...", "analyze every ...".
  - Test: Does the same operation repeat over items in a list?
  - NOT iterative: Operating on a single complex item with multiple fields.
- needs_branching=true
  - Signals: "if ... then ... otherwise", "depending on the result", "based on severity", "when X ... else".
  - Test: Does the next step depend on a step's output value?
  - NOT branching: Always proceeds to the same next step.

## Constraints
- Output strictly as a single JSON object (no commentary).
- Be concise and precise; avoid speculative steps not implied by nl_query.
- If the request is ambiguous, choose the safest reasonable interpretation; avoid dangerous side effects unless explicitly requested.

## Examples

### Example 1 — Iterative + conditional branching per item
Input nl_query:
"Read rows from file. For each row: if score <= 2 analyse comments and suggest improvements, else mark as passed. Aggregate into report."

Expected JSON output (5 steps — evaluator + TWO branch steps + aggregator):
{
  "workflow_name": "score-topic-feedback-report",
  "steps": [
    {
      "id": "read-input-file",
      "action": "Read input file and extract all rows as structured data",
      "state_type": "agent",
      "next_step_id": "evaluate-score",
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": true
    },
    {
      "id": "evaluate-score",
      "action": "Evaluate each row's score and route to improvement or pass branch",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": true,
      "needs_branching": true,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "analyze-improvements",
      "action": "Analyse comments for low-score topic and suggest what to improve",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "mark-as-passed",
      "action": "Mark topic as passed with no improvement needed",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "aggregate-report",
      "action": "Aggregate all per-item results into a final summary report",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    }
  ]
}

NOTE: `analyze-improvements` and `mark-as-passed` are SEPARATE steps even though they both
eventually feed into `aggregate-report`. Never collapse them into the evaluator step or skip them.

### Example 2 — Iterative (no per-item branching) + post-loop aggregation
Input nl_query:
"For each open GitHub PR, run tests and deploy to staging if passed, otherwise notify on Slack"

Expected JSON output:
{
  "workflow_name": "pr-test-deploy",
  "steps": [
    {
      "id": "fetch-prs",
      "action": "Fetch all open GitHub PRs",
      "state_type": "agent",
      "next_step_id": "run-tests",
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "run-tests",
      "action": "Execute test suite for each PR and produce pass/fail result",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": true,
      "needs_branching": true,
      "has_side_effect": false,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "deploy-staging",
      "action": "Deploy PR build artifact to staging environment",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": true,
      "needs_human_approval": false,
      "needs_code_executor": false
    },
    {
      "id": "notify-slack",
      "action": "Send test failure notification to Slack",
      "state_type": "agent",
      "next_step_id": null,
      "needs_iteration": false,
      "needs_branching": false,
      "has_side_effect": true,
      "needs_human_approval": false,
      "needs_code_executor": false
    }
  ]
}
"""
