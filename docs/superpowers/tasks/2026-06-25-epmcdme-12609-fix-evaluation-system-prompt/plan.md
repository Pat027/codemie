# EPMCDME-12609: Fix evaluation API None system_prompt validation error

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `AssistantEvaluationService._run_evaluation_task` so that omitting `system_prompt` in the evaluation request no longer causes a Pydantic `ValidationError`.

**Architecture:** Surgical one-line fix in the service layer — pass `system_prompt` to `AssistantChatRequest` only when it is not `None`, letting Pydantic use its `default=""` otherwise. No model changes. New regression test file.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, `unittest.mock`

---

### Task 1: Write failing regression tests

**Files:**
- Create: `tests/codemie/service/test_assistant_evaluation_service.py`

- [ ] **Step 1: Create the test file with the failing test for `system_prompt=None`**

```python
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

from unittest.mock import MagicMock, patch

from codemie.service.assistant_evaluation_service import AssistantEvaluationService


def _make_context(system_prompt):
    """Assemble mocks and invoke _run_evaluation_task. Returns the mock handler."""
    mock_response = MagicMock()
    mock_response.generated = "response text"

    mock_handler = MagicMock()
    mock_handler.process_request.return_value = mock_response

    root_span = MagicMock()
    item = MagicMock()
    item.input = "test query"
    # MagicMock supports __enter__/__exit__ by default; configure the return value
    item.run.return_value.__enter__ = MagicMock(return_value=root_span)
    item.run.return_value.__exit__ = MagicMock(return_value=False)

    dataset = MagicMock()
    dataset.items = [item]

    mock_langfuse = MagicMock()
    mock_langfuse.get_dataset.return_value = dataset

    with (
        patch(
            "codemie.service.assistant_evaluation_service.get_request_handler",
            return_value=mock_handler,
        ),
        patch(
            "codemie.service.assistant_evaluation_service.require_langfuse_client",
            return_value=mock_langfuse,
        ),
    ):
        AssistantEvaluationService._run_evaluation_task(
            assistant=MagicMock(),
            dataset_id="ds-1",
            experiment_name="exp-1",
            system_prompt=system_prompt,
        )

    return mock_handler


class TestRunEvaluationTask:
    def test_without_system_prompt_does_not_raise(self):
        """Omitting system_prompt must not raise a ValidationError."""
        # Before the fix, this raises ValidationError because None is passed
        # to AssistantChatRequest.system_prompt which requires a str.
        mock_handler = _make_context(system_prompt=None)
        chat_request = mock_handler.process_request.call_args[0][0]
        assert chat_request.system_prompt == ""

    def test_with_system_prompt_forwards_value(self):
        """Providing system_prompt must forward it to AssistantChatRequest."""
        mock_handler = _make_context(system_prompt="custom override")
        chat_request = mock_handler.process_request.call_args[0][0]
        assert chat_request.system_prompt == "custom override"
```

- [ ] **Step 2: Run the tests to confirm they fail (RED)**

```bash
cd /home/taras_spashchenko/EPAM/cm/codemie
poetry run pytest tests/codemie/service/test_assistant_evaluation_service.py -v 2>&1 | tail -30
```

Expected: `test_without_system_prompt_does_not_raise` FAILS with `ValidationError` (or similar); `test_with_system_prompt_forwards_value` may pass or fail depending on mock setup.

---

### Task 2: Fix `_run_evaluation_task` — conditional kwarg omission

**Files:**
- Modify: `src/codemie/service/assistant_evaluation_service.py:149-151`

- [ ] **Step 1: Replace the unconditional `system_prompt=system_prompt` with conditional kwargs**

In `_run_evaluation_task`, lines 149–151, change:

```python
# Before
chat_request = AssistantChatRequest(
    text=query, llm_model=llm_model, stream=False, system_prompt=system_prompt
)
```

To:

```python
# After
extra = {"system_prompt": system_prompt} if system_prompt is not None else {}
chat_request = AssistantChatRequest(text=query, llm_model=llm_model, stream=False, **extra)
```

- [ ] **Step 2: Run the tests to confirm they pass (GREEN)**

```bash
cd /home/taras_spashchenko/EPAM/cm/codemie
poetry run pytest tests/codemie/service/test_assistant_evaluation_service.py -v 2>&1 | tail -20
```

Expected: Both tests PASS.

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd /home/taras_spashchenko/EPAM/cm/codemie
poetry run pytest tests/ -x -q 2>&1 | tail -30
```

Expected: No new failures.

- [ ] **Step 4: Commit**

```bash
git add src/codemie/service/assistant_evaluation_service.py \
        tests/codemie/service/test_assistant_evaluation_service.py
git commit -m "EPMCDME-12609: Fix evaluation API passing None system_prompt to AssistantChatRequest"
```

Test-first: yes — `test_without_system_prompt_does_not_raise` fails before the fix and passes after.
