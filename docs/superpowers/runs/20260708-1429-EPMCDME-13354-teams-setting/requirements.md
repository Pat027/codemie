# Requirements — 20260708-1429-EPMCDME-13354-teams-setting

**Source**: ticket-unresolved:EPMCDME-13354
**Work Item**: docs/superpowers/work-items/EPMCDME-13354.md
**Original input**: |
  EPMCDME-13354

  Requirments:

  - a new endpoints as a part of administration for listing enabled assistants for teams per project
  - enpoints for enabling / disabling an assistant for teams per project
  - given a project, a new endpouint to fetch teams-enabled assistants

## Goal

Add admin endpoints to manage per-project assistant access (enable/disable) and a project-scoped endpoint for team members to fetch which assistants are enabled for their project.

## Acceptance Criteria

- `GET /v1/admin/projects/{projectName}/assistants` — returns the list of assistants that have been enabled for the given team/project; admin only.
- `POST /v1/admin/projects/{projectName}/assistants/{assistantId}/enable` — marks an assistant as enabled for the given project; admin only.
- `POST /v1/admin/projects/{projectName}/assistants/{assistantId}/disable` — marks an assistant as disabled/removed for the given project; admin only.
- `GET /v1/projects/{projectName}/assistants/team-enabled` — returns the list of team-enabled assistants visible to authenticated project members.
- A new DB table (or settings record) persists the project↔assistant enablement; no in-memory-only state.
- Admin endpoints return `404` for non-existent project or assistant.
- Enable/disable is idempotent (enabling an already-enabled assistant is a no-op returning 200/201).
- Project-scoped endpoint enforces that the caller is a member of the project or a global admin.
- No regression on existing `GET /v1/assistants`, `GET /v1/applications`, or admin endpoints.

## Context

- "Team" and "project" are used interchangeably; the backing entity is `Application` (`applications` table, PK `name`).
- Assistants are stored in the `assistants` table; each has a `project` field and an `is_global` flag.
- The existing admin router (`src/codemie/rest_api/routers/admin.py`) uses `dependencies=[Depends(authenticate), Depends(admin_access_only)]` at router level — new admin endpoints must follow this pattern.
- For project-scoped access control, follow the `Ability`/`Action` pattern used in `projects.py`.
- Storage pattern: prefer a dedicated join table `project_assistant_access (project_name, assistant_id, enabled, updated_by, updated_at)` for relational clarity; a DB migration is required.
- All admin endpoints live under prefix `/v1/admin/`.
- The project-scoped endpoint lives under the existing projects router or a new project-assistants sub-router.
- Follow the existing `SettingsService` or repository pattern for data access depending on what the storage model uses.

## Open questions

- (none — requirements are sufficiently specific from raw_input and codebase inspection)
