# EPMCDME-12609: Fix evaluation API None system_prompt validation error

## Problem

`AssistantEvaluationService._run_evaluation_task` constructs `AssistantChatRequest` with `system_prompt=system_prompt` unconditionally. When `system_prompt` is `None` (the default for `AssistantEvaluationRequest`), Pydantic rejects it because `AssistantChatRequest.system_prompt` is declared `str = Field(default="")` — it does not accept `None`. The evaluation silently fails per item; the API returns HTTP 200.

## Fix

**File:** `src/codemie/service/assistant_evaluation_service.py`

**Location:** `_run_evaluation_task`, line ~149

**Change:** Replace the unconditional kwarg with conditional omission:

```python
# Before
chat_request = AssistantChatRequest(
    text=query, llm_model=llm_model, stream=False, system_prompt=system_prompt
)

# After
extra = {"system_prompt": system_prompt} if system_prompt is not None else {}
chat_request = AssistantChatRequest(text=query, llm_model=llm_model, stream=False, **extra)
```

When `system_prompt` is `None`, the kwarg is omitted and Pydantic uses the field default `""`, which lets the assistant's own system prompt take effect downstream. When provided, the value is forwarded as an explicit override.

**No model changes.** Both `AssistantChatRequest.system_prompt: str` and `AssistantEvaluationRequest.system_prompt: Optional[str]` stay as-is.

## Regression Test

**File:** `tests/codemie/service/test_assistant_evaluation_service.py` (new)

Two test cases for `AssistantEvaluationService._run_evaluation_task`:

1. **`test_run_evaluation_task_without_system_prompt`** — call with `system_prompt=None`, verify `AssistantChatRequest` is constructed without a `ValidationError` and that `system_prompt` defaults to `""`.
2. **`test_run_evaluation_task_with_system_prompt`** — call with `system_prompt="custom"`, verify it's forwarded to `AssistantChatRequest.system_prompt`.

Mocks: `get_request_handler`, `handler.process_request`, `require_langfuse_client`, LangFuse dataset and item objects.

## Acceptance Criteria

- `/evaluate` called without `system_prompt` completes without `ValidationError`.
- `/evaluate` called with `system_prompt="..."` still forwards the override correctly.
- Both scenarios are covered by unit tests.
