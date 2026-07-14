# Frontend Handoff — Assistant Project Mapping (EPMCDME-13354)

**Date**: 2026-07-08  
**Branch**: `EPMCDME-13354-teams-setting`  
**Ticket**: EPMCDME-13354  
**Feature**: Enable/disable assistants for project features (Teams integration)

---

## ⚠️ Breaking Changes

**None.** All existing endpoints are untouched. No response shapes were modified. No field renames. Safe to deploy without any frontend changes blocking it.

---

## New Endpoints

### GET `/v1/assistants/projects/mapping`

List assistants enabled for a project feature. Returns the same paginated assistant list shape as `GET /v1/assistants`.

**Auth**: Project member or project admin for the given `project`.

**Query params**:
```
feature: string  — required, enum: "teams"
project: string  — required, project name
page:    number  — optional, default 0 (0-indexed)
per_page: number — optional, default 12, max 100
```

**Response** (same shape as the existing assistants list):
```typescript
{
  data: Assistant[],   // existing Assistant object shape
  pagination: {
    page: number,      // current page (0-indexed)
    per_page: number,
    total: number,     // total matching assistants
    pages: number,     // total page count
  }
}
```

**Status codes**:
- `200` — success (including empty list when no assistants enabled)
- `400` — invalid `feature` value (not in enum)
- `403` — caller is not a project member
- `500` — server error

**Notes**:
- Results are scoped to the calling user's access — an assistant the user cannot normally see will not appear even if it is mapped.
- Uses 0-indexed page numbers (same convention as the existing assistant list).

---

### POST `/v1/assistants/{assistant_id}/projects/mapping`

Enable an assistant for a project feature. Idempotent — calling it twice returns 200 both times.

**Auth**: Project admin for the `project_name` in the request body.

**Path params**:
```
assistant_id: string — UUID of the assistant
```

**Request body**:
```typescript
{
  project_name: string,           // required — project identifier
  feature: "teams"                // required — must be a valid AssistantProjectFeature value
}
```

**Response**:
```typescript
{
  message: string  // "Assistant enabled for project feature successfully"
}
```

**Status codes**:
- `200` — enabled (or was already enabled)
- `400` — invalid `feature` value
- `403` — caller is not project admin
- `404` — assistant not found, or project not found / deleted
- `500` — server error

---

### DELETE `/v1/assistants/{assistant_id}/projects/mapping`

Disable an assistant for a project feature. Returns 404 if the mapping did not exist.

**Auth**: Project admin for the `project` query param.

**Path params**:
```
assistant_id: string — UUID of the assistant
```

**Query params**:
```
project: string  — required, project name
feature: string  — required, enum: "teams"
```

**Response**:
```typescript
{
  message: string  // "Assistant disabled for project feature successfully"
}
```

**Status codes**:
- `200` — mapping removed
- `400` — invalid `feature` value
- `403` — caller is not project admin
- `404` — mapping not found (assistant was not enabled for this project/feature)
- `500` — server error

---

## Modified Endpoints

**None.** No existing endpoints were changed.

---

## New / Changed Data Shapes

### `AssistantProjectFeature` enum

```typescript
type AssistantProjectFeature = "teams";
```

- `"teams"` — assistant is enabled for the Teams feature within the project.
- This enum will grow over time. Code defensively: if a value arrives that is not in your local enum, treat it as unknown rather than crashing.

**Recommended UI states per value**:

| Value | UI treatment |
|-------|-------------|
| `"teams"` | Show "Teams" badge or toggle ON state |
| unknown future value | Show raw string or neutral badge; do not error |

---

## Streaming / Real-time Changes

**None.** No new SSE frame types or WebSocket messages.

---

## What Requires No Frontend Changes

- **Database migration**: a new `assistant_project_mapping` table was added. Fully transparent to the UI.
- **Alembic migration**: revision `a1b2c3d4e5f6` runs on deploy. No UI impact.
- **Service layer internals**: stale-project filtering via JOIN, IntegrityError race handling, circular-import workaround — all invisible to the frontend.
- **`main.py` router registration order**: a new router is registered before the existing `assistant` router to prevent FastAPI path collision. No API surface change from the frontend perspective.
- **Test files**: new unit and repository tests added. No UI impact.

---

## Frontend Action Checklist

```
- [ ] Add API client methods for all three new endpoints:
      GET  /v1/assistants/projects/mapping
      POST /v1/assistants/{assistant_id}/projects/mapping
      DELETE /v1/assistants/{assistant_id}/projects/mapping

- [ ] Add TypeScript type AssistantProjectFeature = "teams" (and handle unknown values gracefully)

- [ ] Build the project admin UI: enable/disable assistant toggle per project
      (POST on enable, DELETE on disable; confirm 404 → already disabled)

- [ ] Build the project member UI: list assistants enabled for the project Teams feature
      using GET /v1/assistants/projects/mapping?feature=teams&project=<name>

- [ ] Handle pagination on GET response (0-indexed page, per_page 1–100)

- [ ] Handle 403 on GET — show "no access" state rather than empty list

- [ ] Handle 404 on DELETE — the mapping was already gone; treat as no-op in UI

- [ ] Handle 400 on invalid feature — should not happen if enum is hard-coded
      in the client, but guard the error state anyway
```
