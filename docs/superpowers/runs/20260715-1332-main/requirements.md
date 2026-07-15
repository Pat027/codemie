# Requirements: EPMCDME-13546

**Source**: https://jiraeu.epam.com/browse/EPMCDME-13546  
**Type**: Sub-Bug  
**Status**: In Progress  
**Assignee**: Yana Asadchaya

---

## Goal

Fix MCP tool invocation failing with HTTP 500 when `user_context` is rejected as an extra forbidden input during MCP toolkit creation.

## Problem Statement

When a user invokes MCP tools through the CodeMie assistant model endpoint, the backend attempts to create an MCP toolkit and passes a `user_context` field that is rejected by the toolkit creation validator with:

```
Failed to create MCP toolkit: {"detail":[{"type":"extra_forbidden","loc":["body","user_context"],"msg":"Extra inputs are not permitted", ... }]}
```

This causes the endpoint `POST /v1/assistants/{assistant_id}/model` to return HTTP 500 rather than a useful response.

The `user_context` propagation was introduced by EPMCDME-13260 to pass authenticated user context to DSP and MCP tool invocations. The sub-bug: the MCP toolkit creation contract does not accept `user_context` as an input field, so passing it must be handled correctly (strip, transform, or conditionally exclude).

## Scope

- MCP toolkit creation logic — remove or conditionally exclude `user_context` from the MCP toolkit creation payload
- `POST /v1/assistants/{assistant_id}/model` — must not return HTTP 500 for this scenario
- Integration test `tests/assistant/tools/mcp/test_cli_mcp_server.py::test_cli_mcp_server[ls]` — must pass

## Acceptance Criteria

1. MCP tool invocation no longer fails due to `user_context` being rejected during MCP toolkit creation.
2. `POST /v1/assistants/{assistant_id}/model` does not return HTTP 500 for this scenario.
3. User context is either accepted, transformed, or excluded according to the MCP toolkit creation contract.
4. CLI MCP server integration test `test_cli_mcp_server[ls]` passes.
5. MCP toolkit creation logs contain adequate diagnostic context without exposing sensitive user data.
6. If invalid request data is detected, the API returns a clear 4xx validation error instead of generic HTTP 500.
7. Regression coverage is added or updated for MCP tool invocation with request-level user context.

## Out of Scope

- Redesigning the user_context propagation mechanism introduced by EPMCDME-13260
- Changes to the MCP toolkit creation API schema (unless required by the fix)
- Unrelated MCP server or assistant endpoint changes

## Open Questions

_None — requirements are fully specified by the ticket._
