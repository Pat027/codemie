# SDK Handoff — Assistant Project Mapping (EPMCDME-13354)

**Date**: 2026-07-09  
**Branch**: `EPMCDME-13354-teams-setting`  
**Ticket**: EPMCDME-13354  
**Feature**: Enable/disable assistants for project features (Teams integration)

---

## ⚠️ Breaking Changes

**None.** All existing endpoints are untouched. No response shapes, field names, or HTTP methods were modified. Safe to release without a major version bump.

---

## New Endpoints

### GET `/v1/assistants/projects/mapping`

List assistants enabled for a project feature.

**Auth**: Bearer token. Caller must be a project member or project admin for `project`.

**Query params**:
```
feature   string  required  — feature discriminator; currently only "teams"
project   string  required  — project name (application name)
page      number  optional  — 0-indexed page number, default 0
per_page  number  optional  — items per page, default 12, max 10000
```

**Response** — same paginated assistant list shape as `GET /v1/assistants`:
```typescript
{
  data: Assistant[],
  pagination: {
    page: number,      // 0-indexed
    per_page: number,
    total: number,
    pages: number,
  }
}
```

**Status codes**:
| Code | Meaning |
|------|---------|
| 200  | Success (empty `data` array when no assistants are enabled) |
| 400  | Invalid `feature` value |
| 403  | Caller is not a project member |
| 500  | Server error |

**Notes**:
- Results are scoped to what the calling user can normally access — a mapped assistant the user has lost access to is silently excluded.
- Pagination is 0-indexed (page 0 = first page).

---

### POST `/v1/assistants/{assistantId}/projects/mapping`

Enable an assistant for a project feature. **Idempotent** — calling it when the mapping already exists returns 200 with no error.

**Auth**: Bearer token. Caller must be project admin for `project_name`.

**Path params**:
```
assistantId  string  required  — UUID of the assistant
```

**Request body** (`Content-Type: application/json`):
```typescript
{
  project_name: string,           // required — project identifier
  feature: "teams"                // required — AssistantProjectFeature enum value
}
```

**Response**:
```typescript
{
  message: string   // "Assistant enabled for project feature successfully"
}
```

**Status codes**:
| Code | Meaning |
|------|---------|
| 200  | Enabled (or already was enabled) |
| 400  | Invalid `feature` value |
| 403  | Caller is not project admin |
| 404  | Assistant not found, or project not found / deleted |
| 500  | Server error |

---

### DELETE `/v1/assistants/{assistantId}/projects/mapping`

Disable an assistant for a project feature. Returns 404 if the mapping did not exist.

**Auth**: Bearer token. Caller must be project admin for `project`.

**Path params**:
```
assistantId  string  required  — UUID of the assistant
```

**Query params**:
```
project  string  required  — project name
feature  string  required  — feature discriminator; currently only "teams"
```

**Response**:
```typescript
{
  message: string   // "Assistant disabled for project feature successfully"
}
```

**Status codes**:
| Code | Meaning |
|------|---------|
| 200  | Mapping removed |
| 400  | Invalid `feature` value |
| 403  | Caller is not project admin |
| 404  | Mapping not found (was not enabled) |
| 500  | Server error |

---

## New / Changed Data Shapes

### `AssistantProjectFeature`

```typescript
type AssistantProjectFeature = "teams";
```

This enum will grow over time as more features are gated. Treat unrecognized values as unknown rather than erroring — forward compatibility.

---

## Streaming / Real-time Changes

**None.** No new event types or WebSocket frames.

---

## What Requires No SDK Changes

- Database migration (`assistant_project_mapping` table) — fully transparent.
- Feature flag guard (`features:teamsBotIntegration` in `customer-config.yaml`) — returns 403 at the HTTP level; the SDK should surface it as a standard error, no special handling needed.
- Service-layer internals (stale-project JOIN, race-condition handling, circular-import workaround) — invisible to SDK consumers.
- Router registration order fix in `main.py` — no API surface change.

---

## SDK Action Checklist

```
- [ ] Add type AssistantProjectFeature = "teams" (handle unknown values gracefully)

- [ ] Add type AssistantProjectMappingRequest:
        { project_name: string; feature: AssistantProjectFeature }

- [ ] Add type AssistantProjectMappingResponse:
        { message: string }

- [ ] Add client method: listProjectAssistants(params: {
        feature: AssistantProjectFeature;
        project: string;
        page?: number;
        per_page?: number;
      }) => Promise<PaginatedAssistantList>
      — GET /v1/assistants/projects/mapping

- [ ] Add client method: enableAssistantForProject(
        assistantId: string,
        body: AssistantProjectMappingRequest
      ) => Promise<AssistantProjectMappingResponse>
      — POST /v1/assistants/{assistantId}/projects/mapping

- [ ] Add client method: disableAssistantForProject(
        assistantId: string,
        params: { project: string; feature: AssistantProjectFeature }
      ) => Promise<AssistantProjectMappingResponse>
      — DELETE /v1/assistants/{assistantId}/projects/mapping

- [ ] Handle 404 on disableAssistantForProject — mapping was already gone;
      callers should treat this as a no-op if desired

- [ ] Export all three methods and the new types from the SDK's public entry point

- [ ] Add/update OpenAPI spec or code-gen source if the SDK is generated
      (new tag: "Assistant Project Mappings")
```
