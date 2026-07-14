# Design: Assistant Project Feature Mapping (EPMCDME-13354)

**Date**: 2026-07-08
**Ticket**: EPMCDME-13354
**Branch**: EPMCDME-13354-teams-setting
**Status**: Approved

## Goal

Allow project admins to control which assistants are enabled for a specific project under a named feature (currently only `"teams"`). Provide a project-member-facing listing endpoint and project-admin-facing enable/disable endpoints.

---

## Data Model

### New table: `assistant_project_mapping`

**File**: `src/codemie/rest_api/models/usage/assistant_project_mapping.py`

```python
class AssistantProjectFeature(str, Enum):
    TEAMS = "teams"


class AssistantProjectMappingSQL(BaseModelWithSQLSupport, table=True):
    __tablename__ = "assistant_project_mapping"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    assistant_id: str = SQLField(
        foreign_key="assistants.id", index=True, ondelete="CASCADE"
    )
    project_name: str = SQLField(index=True)
    feature: str = SQLField(index=True)          # AssistantProjectFeature value
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(UTC))
    updated_by: str                               # user_id of caller

    __table_args__ = (
        UniqueConstraint(
            "assistant_id", "project_name", "feature",
            name="uix_assistant_project_mapping",
        ),
    )
```

**Key properties:**
- One row = assistant is enabled for a project under a feature. No row = disabled.
- `foreign_key="assistants.id", ondelete="CASCADE"`: hard-deleting an assistant automatically removes all its mappings at DB level. Follows the same pattern as `AssistantConfiguration` (line 1165 of `assistant.py`).
- `project_name` has no DB-level FK to `applications` (projects are soft-deleted, not hard-deleted). Stale project mappings are filtered at query time instead (see GET filtering below).
- API validates `feature` values against `AssistantProjectFeature` enum at the boundary — unknown strings return 400 before touching the DB.

**Pydantic models** (same file):
- `AssistantProjectMappingRequest`: `{"project_name": str}`
- `AssistantProjectMappingResponse`: `{id, assistant_id, project_name, feature, created_at, updated_by}`

### Migration

New Alembic revision: `create_assistant_project_mapping`. Creates the table and the `uix_assistant_project_mapping` composite unique index. No changes to existing tables.

---

## API Contract

All three endpoints live in a new router: `src/codemie/rest_api/routers/assistant_project_mapping.py`.  
Registered in `main.py` alongside the existing `assistant_mapping` router.

### GET `/v1/assistants/projects/mapping`

**Query params**: `feature` (required), `project` (required), `page` (default 0), `per_page` (default 12)  
**Auth**: project member or project admin for the given `project`  
**Returns**: paginated `AssistantListResponse` list (same shape as `GET /v1/assistants`)

**Filtering (two-step):**

Step 1 — mapping table:
```sql
SELECT assistant_id FROM assistant_project_mapping
JOIN applications ON applications.name = project_name
  AND applications.deleted_at IS NULL
WHERE project_name = :project AND feature = :feature
```

Step 2 — hand off to `AssistantRepository`:
```python
AssistantRepository().query(
    user=user,
    scope=AssistantScope.ALL,          # includes global + all project-visible assistants
    filters={"id": assistant_ids},     # list value → compose_term_filter uses .in_()
    page=page, per_page=per_page,
)
```

`AssistantScope.ALL` runs `_filter_for_regular_user_visibility(include_global=True)`, which enforces:
- Shared assistants in the user's projects
- Assistants in projects the user administers
- Assistants created by the user
- Global/marketplace assistants

Admins see everything in the mapping. Regular users only see what they are normally allowed to access — mappings for assistants they've lost access to silently drop from results. Soft-deleted assistants are filtered by the existing `deleted_at IS NULL` logic inside `AssistantRepository`.

**Note**: register this route **before** `/v1/assistants/{assistant_id}/...` in the router to prevent FastAPI from matching `"projects"` as an `assistant_id` path param.

---

### POST `/v1/assistants/{assistant_id}/projects/mapping`

**Auth**: project admin for `project_name` in request body  
**Body**: `{"project_name": "xxx", "feature": "teams"}`  
**Returns**: 200 `BaseResponse` (idempotent — no error if mapping already exists)

Validation before insert:
1. Assistant exists and `deleted_at IS NULL`.
2. Project exists and `deleted_at IS NULL`.
3. Caller has `UserProject.is_project_admin = True` for `project_name`.
4. `feature` is a valid `AssistantProjectFeature` value.

---

### DELETE `/v1/assistants/{assistant_id}/projects/mapping`

**Auth**: project admin for `project` query param  
**Query params**: `project` (required), `feature` (required)  
**Returns**: 200 on success, 404 if mapping does not exist

Validation:
1. Assistant exists.
2. Caller has `UserProject.is_project_admin = True` for `project`.
3. `feature` is valid.

---

## Service Layer

**File**: `src/codemie/service/assistant/assistant_project_mapping_service.py`

```python
class AssistantProjectMappingService:
    def enable(self, assistant_id, project_name, feature, user) -> None
    def disable(self, assistant_id, project_name, feature, user) -> None
    def list(self, project_name, feature, user, page, per_page) -> dict
```

- `enable`: validates existence + project admin, then calls `repo.create()`. Idempotent: skips insert if `repo.exists()` is True.
- `disable`: validates + project admin, calls `repo.delete()`. Raises 404 if not found.
- `list`: validates project membership, calls `repo.get_assistant_ids()`, delegates to `AssistantRepository`.

---

## Repository Layer

**File**: `src/codemie/repository/assistants/assistant_project_mapping_repository.py`

Mirrors `assistant_user_mapping_repository.py`:

```python
class AssistantProjectMappingRepository(ABC):
    def create(self, assistant_id, project_name, feature, updated_by) -> AssistantProjectMappingSQL
    def delete(self, assistant_id, project_name, feature) -> bool      # False = not found
    def get_assistant_ids(self, project_name, feature) -> list[str]
    def exists(self, assistant_id, project_name, feature) -> bool

AssistantProjectMappingRepositoryImpl = SQLAssistantProjectMappingRepository
```

`get_assistant_ids` runs the Step 1 JOIN including the `applications.deleted_at IS NULL` guard.

---

## Error Handling

| Scenario | HTTP |
|---|---|
| `assistant_id` not found or soft-deleted | 404 |
| `project_name` not found or soft-deleted | 404 |
| `feature` not in `AssistantProjectFeature` | 400 |
| Caller not project admin (POST / DELETE) | 403 |
| Caller not project member (GET) | 403 |
| Mapping already exists (POST) | 200 (idempotent) |
| Mapping not found (DELETE) | 404 |
| DB / unexpected error | 500 via `ExtendedHTTPException` |

---

## Testing

- **Unit** (`AssistantProjectMappingService`): enable idempotency, disable 404, list filters stale records, list respects user access scope.
- **API** (three endpoints): auth paths (member vs non-member, project admin vs regular user), 400 on bad feature, 404 on missing assistant/project.
- **Repository**: cascade delete — verify mapping rows are gone after assistant deletion.

---

## Files Touched

| File | Change |
|---|---|
| `src/codemie/rest_api/models/usage/assistant_project_mapping.py` | New |
| `src/codemie/repository/assistants/assistant_project_mapping_repository.py` | New |
| `src/codemie/service/assistant/assistant_project_mapping_service.py` | New |
| `src/codemie/rest_api/routers/assistant_project_mapping.py` | New |
| `src/codemie/rest_api/main.py` | Register new router |
| `src/external/alembic/versions/<rev>_create_assistant_project_mapping.py` | New migration |
| `tests/unit/service/test_assistant_project_mapping_service.py` | New |
| `tests/api/test_assistant_project_mapping.py` | New |
