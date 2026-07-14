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
import re
from pydantic import ValidationError

from codemie.configs.logger import logger
from codemie.core.workflow_models.workflow_models import (
    CreateWorkflowRequest,
    WorkflowAssistant,
    WorkflowAssistantTool,
    WorkflowMode,
    WorkflowState as WorkflowStateModel,
)
from codemie.workflows.workflow_generator.schemas import TaskVariable
from codemie.workflows.workflow_generator.state import WorkflowGeneratorState
from codemie.workflows.workflow_generator import state_keys as sk

MAX_VALIDATION_RETRIES = 3

_STEP_ID_RE = re.compile(r"^State '([^']+)':")


class ValidationNode:
    def _check_iter_key_producers(self, config) -> list[str]:
        errors: list[str] = []
        output_keys = {s.next.output_key for s in config.states if s.next.output_key}
        for s in config.states:
            if s.next.iter_key:
                # RFC 6901 JSON Pointer: strip leading '/' and take first segment
                first_segment = s.next.iter_key.lstrip("/").split("/")[0]
                if first_segment not in output_keys:
                    errors.append(
                        f"State '{s.id}': iter_key '{s.next.iter_key}' (first segment '{first_segment}') "
                        "is not produced by any state's next.output_key — iteration will fail at runtime"
                    )
        return errors

    def _validate_iter_and_finish_flags(self, gen_state) -> list[str]:
        errors: list[str] = []
        if gen_state.next.iter_key and not gen_state.next.output_key:
            errors.append(f"State '{gen_state.id}': iter_key requires output_key to store the list results")
        if gen_state.finish_iteration and not gen_state.next.append_to_context:
            errors.append(
                f"State '{gen_state.id}': finish_iteration=True requires next.append_to_context=True "
                "— without it each iteration overwrites instead of accumulating results"
            )
        return errors

    def _validate_state_transitions(self, gen_state) -> list[str]:
        errors: list[str] = []
        if gen_state.next.condition and not gen_state.next.condition.expression.strip():
            errors.append(f"State '{gen_state.id}': condition.expression is empty")
        errors.extend(self._validate_iter_and_finish_flags(gen_state))
        return errors

    def _validate_output_schema(self, gen_state) -> list[str]:
        errors: list[str] = []
        if not gen_state.output_schema:
            return errors
        try:
            schema = json.loads(gen_state.output_schema)
        except ValueError as exc:
            errors.append(f"State '{gen_state.id}': output_schema is not valid JSON: {exc}")
            return errors
        if gen_state.next.output_key:
            props = schema.get("properties", {})
            if gen_state.next.output_key not in props:
                errors.append(
                    f"State '{gen_state.id}': output_schema must wrap output under "
                    f"output_key '{gen_state.next.output_key}' — expected top-level property "
                    f"'{gen_state.next.output_key}' in schema.properties but it was not found. "
                    "The platform extracts context[output_key] from the assistant's JSON response."
                )
        return errors

    def _validate_state(self, gen_state) -> list[str]:
        errors: list[str] = []

        try:
            WorkflowStateModel(**gen_state.model_dump(exclude_none=True))
        except ValidationError as exc:
            for err in exc.errors():
                loc = " -> ".join(str(x) for x in err["loc"])
                errors.append(f"State '{gen_state.id}' [{loc}]: {err['msg']}")
        except Exception as exc:
            errors.append(f"State '{gen_state.id}': {exc}")

        if not gen_state.assistant_id:
            errors.append(f"State '{gen_state.id}': assistant_id is required — all states must be agent type")

        # Only flag missing output_key when the state explicitly produces structured output
        # (output_schema is set) but store_in_context has not been disabled.
        # Plain text / side-effect states have no output_schema and do not require output_key.
        if (
            gen_state.assistant_id
            and gen_state.output_schema
            and gen_state.next.store_in_context is not False
            and not gen_state.next.output_key
        ):
            errors.append(
                f"State '{gen_state.id}': output_schema is set but next.output_key is not — "
                "downstream states cannot access this structured output via {{variable}}"
            )

        errors.extend(self._validate_state_transitions(gen_state))
        errors.extend(self._validate_output_schema(gen_state))

        if gen_state.task and "{{" in gen_state.task and not gen_state.resolve_dynamic_values_in_prompt:
            errors.append(
                f"State '{gen_state.id}': task contains '{{{{' Jinja references but "
                "resolve_dynamic_values_in_prompt is not set to True — "
                "context variable references will not be resolved at runtime"
            )

        return errors

    def _validate_task_variables(self, gen_state, node_variable_specs: dict) -> list[str]:
        errors = []
        step_vars = node_variable_specs.get(gen_state.id, [])
        task_text = gen_state.task or ""
        for var in step_vars:
            # Match {{key}}, {{key.path}}, {{key.a.b}} — any reference to the key
            if f"{{{{{var.key}" not in task_text:
                errors.append(
                    f"State '{gen_state.id}': required placeholder '{var.placeholder}' "
                    f"missing from task — variable '{var.key}' will not reach the assistant"
                )
        if step_vars and not gen_state.resolve_dynamic_values_in_prompt:
            errors.append(
                f"State '{gen_state.id}': has required context variables but "
                "resolve_dynamic_values_in_prompt is not True"
            )
        return errors

    def _validate_iter_key_schema(self, gen_state, config) -> list[str]:
        """Walk the full JSON pointer path through the producer's output_schema.
        Every segment must exist in properties{}; the final segment must be type 'array'."""
        errors: list[str] = []
        iter_key = gen_state.next.iter_key
        if not iter_key:
            return errors

        segments = [s for s in iter_key.lstrip("/").split("/") if s]
        if not segments:
            return errors

        producer = next(
            (s for s in config.states if s.next.output_key == segments[0]),
            None,
        )
        if producer is None or not producer.output_schema:
            # _validate_global already flags unknown output_key references
            return errors

        try:
            current = json.loads(producer.output_schema)
            for i, seg in enumerate(segments):
                props = current.get("properties", {})
                if seg not in props:
                    path = "/" + "/".join(segments[: i + 1])
                    errors.append(
                        f"State '{producer.id}': output_schema missing property at '{path}' — "
                        f"state '{gen_state.id}' iterates over iter_key='{iter_key}'"
                    )
                    return errors
                current = props[seg]

            prop_type = current.get("type")
            _non_iterable = {"string", "number", "integer", "boolean", "null"}
            if prop_type in _non_iterable:
                errors.append(
                    f"State '{producer.id}': output_schema property '{iter_key}' has type "
                    f"'{prop_type}' but state '{gen_state.id}' iterates over it — must be 'array'"
                )
        except ValueError:
            pass  # invalid JSON already caught by _validate_state
        return errors

    def _validate_switch_redundancy(self, gen_state) -> list[str]:
        """Flag switch blocks where all cases and default point to the same state_id."""
        errors: list[str] = []
        switch = gen_state.next.switch
        if not switch:
            return errors
        targets = {c.state_id for c in switch.cases}
        targets.add(switch.default)
        if len(targets) == 1:
            target = next(iter(targets))
            errors.append(
                f"State '{gen_state.id}': switch has all cases and default pointing to "
                f"'{target}' — replace with next.state_id: '{target}' (redundant switch)"
            )
        return errors

    def _validate_producer_schemas(self, config, node_variable_specs: dict) -> list[str]:
        """Check that every state producing a key consumed by a downstream state has output_schema set."""
        producer_by_key: dict[str, any] = {s.next.output_key: s for s in config.states if s.next.output_key}

        errors: list[str] = []
        seen: set[str] = set()
        for consumer_step_id, variables in node_variable_specs.items():
            for var in variables:
                if var.is_iter_item:
                    continue  # iterator items are runtime-resolved, schema not strictly required
                producer = producer_by_key.get(var.key)
                if producer and not producer.output_schema:
                    dedup_key = producer.id
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        errors.append(
                            f"State '{producer.id}': produces '{var.key}' consumed by "
                            f"'{consumer_step_id}' but output_schema is not set — "
                            f"the platform cannot validate the shape of '{var.key}' and "
                            f"downstream placeholder '{var.placeholder}' may fail at runtime"
                        )
        return errors

    def _build_flow_adjacency(self, config) -> dict[str, list[str]]:
        first_id = config.states[0].id if config.states else "end"
        adjacency: dict[str, list[str]] = {"start": [first_id]}
        for s in config.states:
            targets: list[str] = []
            if s.next.state_id:
                targets.append(s.next.state_id)
            if s.next.state_ids:
                targets.extend(s.next.state_ids)
            if s.next.condition:
                targets.extend([s.next.condition.then, s.next.condition.otherwise])
            if s.next.switch:
                targets.extend(c.state_id for c in s.next.switch.cases)
                targets.append(s.next.switch.default)
            adjacency[s.id] = list(dict.fromkeys(targets))
        return adjacency

    def _bfs_levels(self, adjacency: dict[str, list[str]]) -> dict[str, int]:
        from collections import deque

        levels: dict[str, int] = {"start": 0}
        queue: deque[str] = deque(["start"])
        while queue:
            node = queue.popleft()
            for neighbor in adjacency.get(node, []):
                if neighbor not in levels:
                    levels[neighbor] = levels[node] + 1
                    queue.append(neighbor)
        levels.setdefault("end", max(levels.values(), default=0) + 1)
        return levels

    def _build_result(self, state: WorkflowGeneratorState, config) -> CreateWorkflowRequest:
        import yaml

        intent = state[sk.INTENT]
        states = [WorkflowStateModel(**s.model_dump(exclude_none=True)) for s in config.states]
        assistants = [
            WorkflowAssistant(
                id=a.id,
                system_prompt=a.system_prompt,
                model=a.model,
                temperature=a.temperature,
                tools=[WorkflowAssistantTool(name=t) for t in (a.tools or [])],
            )
            for a in config.assistants
        ]
        execution_config = {
            "states": [s.model_dump(exclude_none=True) for s in states],
            "assistants": [a.model_dump(exclude_none=True) for a in assistants],
            "tools": [],
        }
        yaml_config = yaml.safe_dump(
            execution_config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        return CreateWorkflowRequest(
            name=intent.workflow_name,
            description=intent.workflow_description,
            project=state[sk.PROJECT],
            mode=WorkflowMode.SEQUENTIAL,
            states=states,
            assistants=assistants,
            tools=[],
            yaml_config=yaml_config,
        )

    def _collect_specs_for_read(self, read, node, iter_keys: set) -> list[TaskVariable]:
        if read.key not in iter_keys:
            return [
                TaskVariable(
                    placeholder=f"{{{{{read.key}}}}}",
                    key=read.key,
                    path=None,
                    is_iter_item=False,
                    description=f"context key '{read.key}'",
                )
            ]
        # Iterated by platform via iter_key — not a Jinja reference in task
        if node.finish_iteration and read.access_paths:
            # Per-item processor: platform promotes each field to top-level context
            return [
                TaskVariable(
                    placeholder=f"{{{{{field}}}}}",
                    key=field,
                    path=None,
                    is_iter_item=True,
                    description=f"iterator field '{field}' promoted from '{read.key}'",
                )
                for field in read.access_paths
            ]
        return []

    def _build_node_variable_specs(self, node_plan, config) -> dict[str, list]:
        # Keys used as iter_key are platform-iterated — they are never Jinja-injected into tasks
        iter_keys: set[str] = {s.next.iter_key.lstrip("/").split("/")[0] for s in config.states if s.next.iter_key}
        node_variable_specs: dict[str, list] = {}
        for node in node_plan.nodes:
            if not (node.context_store and node.context_store.reads):
                continue
            specs: list[TaskVariable] = []
            for read in node.context_store.reads:
                specs.extend(self._collect_specs_for_read(read, node, iter_keys))
            if specs:
                node_variable_specs[node.step_id] = specs
        return node_variable_specs

    def _extract_failed_step_ids(self, errors: list[str]) -> list[str]:
        return list({m.group(1) for e in errors if (m := _STEP_ID_RE.match(e))})

    def _validate_with_executor(self, state: WorkflowGeneratorState, config, result=None) -> list[str]:
        """Run WorkflowExecutor.validate_workflow to catch YAML schema, resource availability,
        and graph compilation errors that structural validation cannot detect."""
        from codemie.core.workflow_models import WorkflowConfig
        from codemie.workflows.workflow import WorkflowExecutor

        try:
            if result is None:
                result = self._build_result(state, config)
            workflow_config = WorkflowConfig(
                name=result.name,
                description=result.description or "",
                project=result.project,
                mode=result.mode,
                states=result.states,
                assistants=result.assistants,
                tools=result.tools,
                yaml_config=result.yaml_config,
                meta_config=result.meta_config,
            )
            WorkflowExecutor.validate_workflow(workflow_config, state.get(sk.USER), error_format="json")
            return []
        except ValueError as exc:
            return self._parse_executor_errors(exc)
        except Exception as exc:
            logger.warning(f"Executor validation raised unexpected error: {exc}")
            return []

    def _format_error_entry(self, err: dict) -> str:
        msg = err.get("message") or ""
        field = err.get("field") or err.get("resource_id") or ""
        state_ref = err.get("reference_state") or ""
        parts = []
        if state_ref:
            parts.append(f"State '{state_ref}':")
        if field:
            parts.append(f"[{field}]")
        if msg:
            parts.append(msg)
        return " ".join(parts) if parts else str(err)

    def _parse_executor_errors(self, exc: ValueError) -> list[str]:
        error_val = exc.args[0] if exc.args else str(exc)
        if not isinstance(error_val, dict):
            return [str(error_val)]
        detail_errors = error_val.get("errors") or []
        if detail_errors:
            return [self._format_error_entry(err) for err in detail_errors]
        top_msg = error_val.get("message")
        return [top_msg] if top_msg else [str(error_val)]

    def _build_validation_return(self, errors, new_attempts, failed_ids, result=None) -> dict:
        if errors and new_attempts >= MAX_VALIDATION_RETRIES:
            summary = (
                f"Workflow generation failed after {MAX_VALIDATION_RETRIES} validation retries. "
                f"Errors: {'; '.join(errors[:3])}"
            )
            logger.error(summary)
            return {
                sk.VALIDATION_ERRORS: errors,
                sk.VALIDATION_ATTEMPTS: new_attempts,
                sk.FAILED_STEP_IDS: failed_ids,
                sk.ERROR: summary,
            }
        if errors:
            return {
                sk.VALIDATION_ERRORS: errors,
                sk.VALIDATION_ATTEMPTS: new_attempts,
                sk.FAILED_STEP_IDS: failed_ids,
            }
        return {
            sk.VALIDATION_ERRORS: [],
            sk.VALIDATION_ATTEMPTS: new_attempts,
            sk.FAILED_STEP_IDS: [],
            sk.RESULT: result,
        }

    def __call__(self, state: WorkflowGeneratorState) -> dict:
        config = state[sk.GENERATED_CONFIG]
        node_plan = state.get(sk.NODE_PLAN)
        node_variable_specs = self._build_node_variable_specs(node_plan, config) if node_plan else {}

        errors = self._check_iter_key_producers(config)

        for gen_state in config.states:
            errors.extend(self._validate_state(gen_state))
            errors.extend(self._validate_task_variables(gen_state, node_variable_specs))
            errors.extend(self._validate_iter_key_schema(gen_state, config))
            errors.extend(self._validate_switch_redundancy(gen_state))

        errors.extend(self._validate_producer_schemas(config, node_variable_specs))
        errors.extend(self._validate_with_executor(state, config))

        result = None
        if not errors:
            result = self._build_result(state, config)

        attempts = state.get(sk.VALIDATION_ATTEMPTS) or 0
        new_attempts = attempts + 1 if errors else attempts
        failed_ids = self._extract_failed_step_ids(errors)

        return self._build_validation_return(errors, new_attempts, failed_ids, result=result)
