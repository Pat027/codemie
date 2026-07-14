# Work Item: EPMCDME-13354

**Title**: Team-level assistant access control — admin and project-scoped endpoints
**Type**: Task
**Status**: In Progress
**Assignee**: Andriy Lukashchuk
**External Ticket**: ticket-unresolved:EPMCDME-13354
**External Sync**: failed (Jira 401 at intake)
**Branch**: TBD (set after branch guard in Phase 2)

## Summary

Add administration endpoints to manage which assistants are enabled for specific teams (projects), plus a project-scoped endpoint so team members can fetch the assistants enabled for their project.

## Acceptance Criteria

- `GET /v1/admin/projects/{projectName}/assistants` — list team-enabled assistants for project (admin)
- `POST /v1/admin/projects/{projectName}/assistants/{assistantId}/enable` — enable assistant for project (admin)
- `POST /v1/admin/projects/{projectName}/assistants/{assistantId}/disable` — disable assistant for project (admin)
- `GET /v1/projects/{projectName}/assistants/team-enabled` — project member view of enabled assistants
- Durable DB storage (new join table + migration)
- Idempotent enable/disable
- Correct auth on all endpoints
- No regression

## Linked Artifacts

- `docs/superpowers/runs/20260708-1429-EPMCDME-13354-teams-setting/requirements.md`

## History

| Timestamp | Event | Actor | Notes |
|---|---|---|---|
| 2026-07-08T11:29:22Z | work_item.created | requirements-intake | Placeholder from raw_input |
| 2026-07-08T11:30:10Z | work_item.adapter_receipt | requirements-intake | Jira adapter status: failed (401 Unauthorized) — external sync: failed |
| 2026-07-08T11:30:20Z | work_item.linked_artifact | requirements-intake | requirements.md written |
