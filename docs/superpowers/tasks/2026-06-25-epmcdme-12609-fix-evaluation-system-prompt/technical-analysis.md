# Technical Research

**Task**: evaluation assistant system_prompt AssistantChatRequest
**Generated**: 2026-06-25T00:00:00Z
**Research path**: codegraph

---

## 1. Original Context

Bug EPMCDME-12609: Codemie Assistant Evaluation API forces end-users to override the assistant's system prompt.

The AssistantEvaluationRequest model has system_prompt as Optional[str] = Field(default=None, ...). When calling the /evaluate API without system_prompt, the request returns 200 OK but internally fails with:
ValidationError: 1 validation error for AssistantChatRequest system_prompt Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]

Root cause: somewhere in the evaluation code, the optional system_prompt (which can be None) is being passed directly to AssistantChatRequest without checking if it's None first.

The fix should: when system_prompt is None in the evaluation request, do NOT pass it to AssistantChatRequest (or pass the assistant's own system prompt, or omit the field so AssistantChatRequest uses its own default).

Repository paths to check:
- /home/taras_spashchenko/EPAM/cm/codemie (main backend repo)
- /home/taras_spashchenko/EPAM/cm/codemie-enterprise (enterprise extensions repo)

Look for: AssistantEvaluationRequest, AssistantChatRequest, evaluate endpoint, evaluation service, any code that constructs AssistantChatRequest from evaluation parameters.

---

## 2. Codebase Findings

### Existing Implementations

- `src/codemie/core/models.py` (lines 505–621): `AssistantChatRequest` — the core chat request model. Field `system_prompt: str = Field(default="")` at line 552 declares it as a **non-optional `str`** with a default of `""`. Pydantic therefore rejects `None` with a type error.
- `src/codemie/core/models.py` (lines 623–631): `AssistantEvaluationRequest` — the evaluation request model. Field `system_prompt: Optional[str] = Field(default=None, ...)` at line 628 declares it correctly as nullable.
- `src/codemie/service/assistant_evaluation_service.py` (lines 37–163): `AssistantEvaluationService` — orchestrates evaluation logic. `_run_evaluation_task` at line 149 constructs `AssistantChatRequest(text=query, llm_model=llm_model, stream=False, system_prompt=system_prompt)` unconditionally, passing `None` when the caller omits `system_prompt`. **This is the exact bug site.**
- `src/codemie/rest_api/routers/assistant.py` (lines 999–1036): `evaluate_assistant` router function — passes `request.system_prompt` (potentially `None`) to `AssistantEvaluationService.evaluate_assistant`, which forwards it unchanged to `_run_evaluation_task`.

### Architecture and Layers Affected

| Layer | Component | File |
|---|---|---|
| API (Router) | `evaluate_assistant` endpoint | `src/codemie/rest_api/routers/assistant.py:999` |
| Service | `AssistantEvaluationService._run_evaluation_task` | `src/codemie/service/assistant_evaluation_service.py:112` |
| Model | `AssistantChatRequest.system_prompt` field | `src/codemie/core/models.py:552` |
| Model | `AssistantEvaluationRequest.system_prompt` field | `src/codemie/core/models.py:628` |

Only the Service layer requires a code change. The models are correctly defined; the type mismatch arises at construction time in the service.

### Integration Points

- `AssistantEvaluationService` calls `get_request_handler` (from `codemie.rest_api.handlers.assistant_handlers`) to get a handler, then calls `handler.process_request(chat_request, None, raw_request)`.
- `require_langfuse_client` is called from `codemie.enterprise.langfuse` — enterprise feature gate, no changes needed here.
- The enterprise repo (`codemie-enterprise`) contains no source files matching these symbols; all relevant files are in the main `codemie` repo.

### Patterns and Conventions

- `AssistantChatRequest` uses `Field(default="")` for `system_prompt`, meaning if the field is omitted entirely from construction kwargs, it defaults to `""`. The fix should conditionally exclude the kwarg rather than passing `None`.
- The standard Python pattern for conditional kwargs is: build a `dict`, conditionally add the key, then unpack with `**kwargs`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/api/rest-api-patterns.md` — covers FastAPI router patterns; relevant for verifying the router layer requires no change.
- `.ai-run/guides/architecture/service-layer-patterns.md` — covers service orchestration; relevant for the fix location in `AssistantEvaluationService`.
- `.ai-run/guides/testing/testing-service-patterns.md` — relevant for writing a regression test.

### Architectural Decisions

- No ADRs found specifically for the evaluation feature.
- `AssistantChatRequest.system_prompt` being `str` (not `Optional[str]`) appears intentional: an empty string `""` is a valid no-override sentinel, while `None` is not accepted by the field validator.

### Derived Conventions

- Conditional kwarg omission is the idiomatic fix: `kwargs = {}; if system_prompt is not None: kwargs["system_prompt"] = system_prompt; AssistantChatRequest(..., **kwargs)`.
- Alternatively, pass `system_prompt or ""` which converts `None` to the field's natural default.

---

## 4. Testing Landscape

### Existing Coverage

- No test files found covering `AssistantEvaluationService` or the `evaluate_assistant` router endpoint. Codegraph confirmed "no covering tests found" for both `AssistantEvaluationService` and `evaluate_assistant`.
- Tests exist for adjacent components: `tests/codemie/rest_api/handlers/test_assistant_handlers_streaming.py`, `tests/codemie/agents/test_assistant_agent.py`.

### Testing Framework and Patterns

- pytest with standard fixtures. Mock patterns follow `unittest.mock.patch` or `pytest-mock` (`mocker`), inferred from related test files.
- Service tests instantiate the service under test and mock external calls (LangFuse client, handler).

### Coverage Gaps

- `AssistantEvaluationService._run_evaluation_task` has zero test coverage.
- The regression scenario — calling `/evaluate` without `system_prompt` — has no test.
- A new unit test for `_run_evaluation_task` with `system_prompt=None` would directly verify the fix.

---

## 5. Configuration and Environment

### Environment Variables

- LangFuse connectivity is controlled by environment variables consumed by `require_langfuse_client` (enterprise module). Not affected by this fix.

### Configuration Files

- No evaluation-specific config files. The feature is gated by LangFuse availability.

### Feature Flags and Deployment Concerns

- The evaluation endpoint is an enterprise feature gated by `require_langfuse_client`. The fix itself has no deployment or flag implications.

---

## 6. Risk Indicators

- **Exact bug site confirmed**: `src/codemie/service/assistant_evaluation_service.py` line 150 — `system_prompt=system_prompt` passed unconditionally when `system_prompt` may be `None`, but `AssistantChatRequest.system_prompt` is declared `str`, not `Optional[str]`.
- **Zero test coverage** for `AssistantEvaluationService` and `evaluate_assistant` router — any regression introduced by the fix will not be caught by existing tests.
- **Silent background failure**: the `ValidationError` is caught by the broad `except Exception` at line 155, logged, and silently skipped per item. The API returns HTTP 200 even when all items fail — this behavior is pre-existing and out of scope but worth noting.
- **Enterprise repo is clean**: no evaluation-related source files exist outside `.venv` in `codemie-enterprise` — the fix is entirely in the main repo.
- **No guides** specifically documenting the evaluation feature — conventions must be inferred from code.

---

## 7. Summary for Complexity Assessment

This is a minimal, surgical bug fix touching a single line in one service file. The affected layers are: Service (`AssistantEvaluationService._run_evaluation_task` in `src/codemie/service/assistant_evaluation_service.py`) and potentially the Model layer if the fix is implemented by changing `AssistantChatRequest.system_prompt` to `Optional[str]` (not recommended — that would widen the model's contract). The correct and narrowest fix is at the construction site on line 150: either omit `system_prompt` from the kwargs when it is `None`, or coerce `None` to `""` with `system_prompt or ""`. Total file change surface: 1 file, 1 line.

The task follows an established pattern (conditional kwarg construction is common throughout the codebase) and introduces no new patterns. There is no architectural novelty. The type mismatch between `AssistantEvaluationRequest.system_prompt: Optional[str]` and `AssistantChatRequest.system_prompt: str` is a straightforward interface boundary oversight.

Test coverage posture is the primary risk: the evaluation service has no tests at all. A regression test should be added to `tests/codemie/service/` to cover `_run_evaluation_task` with `system_prompt=None`, confirming the `AssistantChatRequest` is constructed without raising a `ValidationError`. The fix itself is low complexity (1); the test gap elevates the overall delivery risk slightly to low-medium.
