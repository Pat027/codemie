# Work Item: EPMCDME-13354

**Title**: Team-level assistant access control — admin and project-scoped endpoints
**Type**: Task
**Status**: In Progress
**Assignee**: Andriy Lukashchuk
**External Ticket**: ticket-unresolved:EPMCDME-13354
**Created**: 2026-07-08T11:29:22Z
**Updated**: 2026-07-08T11:30:00Z

## Summary

Add administration endpoints to manage which assistants are enabled for specific teams (projects), plus a project-scoped endpoint so team members can fetch the assistants enabled for their project.

## Acceptance Criteria

- Admin can list all team-enabled assistants across projects (with optional project filter)
- Admin can enable an assistant for a given project/team
- Admin can disable an assistant for a given project/team
- Project members can retrieve the list of assistants enabled for their project
- Data persisted durably (new DB table or settings-based storage per project conventions)
- All admin endpoints require `admin_access_only` dependency
- Project-scoped endpoint enforces project membership or admin access
- No regression on existing assistant and project endpoints

## Context

In CodeMie, `Application` (table: `applications`) serves as both the team and the project entity. Assistants (`assistants` table) belong to a project via `assistant.project`. The current model supports `is_global` (marketplace) and per-project ownership, but has no per-project enablement toggle for assistants from the global pool or other projects. This feature adds that control layer.

## Linked Artifacts

- `docs/superpowers/runs/20260708-1429-EPMCDME-13354-teams-setting/requirements.md`

## History

| Timestamp | Event | Actor | Notes |
|---|---|---|---|
| 2026-07-08T11:29:22Z | work_item.created | requirements-intake | Created from raw_input; Jira adapter returned 401 |
| 2026-07-08T11:30:00Z | work_item.linked_artifact | requirements-intake | Linked requirements.md |
