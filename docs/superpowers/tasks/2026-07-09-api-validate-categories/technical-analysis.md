# Technical Research

**Task**: assistants marketplace publishing validation categories
**Generated**: 2026-07-09T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

API does not validate presence of categories when publishing assistant to marketplace; should reject if categories are missed. Currently only UI enforces category selection. Backend API does not perform validation and will process requests without categories. This creates inconsistency. Need to add API validation to reject publishing requests lacking categories, with clear error response.

---

## 2. Codebase Findings

### Existing Implementations

- `src/codemie/rest_api/routers/assistant.py` — main FastAPI router; contains `publish_assistant_to_marketplace` (POST `/v1/assistants/{id}/marketplace/publish`), `_validate_publish_marketplace`, `PublishToMarketplaceRequest`, `CategoriesRequest`; root location of the gap
- `src/codemie/rest_api/models/assistant.py` — `Assistant` (SQLModel), `AssistantBase`, `AssistantRequest`, `SubAssistantPublishSettings`, `PublishValidationResponse`, `PublishValidationErrorResponse`; `AssistantBase._check_categories()` already validates IDs but returns `None` when `not self.categories` (no presence enforcement)
- `src/codemie/service/assistant/category_service.py` — `DatabaseCategoryService` singleton (`category_service`); exposes `validate_category_ids`, `filter_valid_category_ids`, `enrich_categories`; `validate_category_ids()` is a no-op on empty input — cannot be reused for presence check
- `src/codemie/rest_api/models/category.py` — `Category` (SQLModel, `categories` table), `CategoryResponse`, `CategoryCreateRequest`
- `src/codemie/rest_api/routers/category.py` — category CRUD router (separate from assistant router)
- `src/codemie/repository/category_repository.py` — repository for category persistence
- `src/codemie/core/exceptions.py` — `ExtendedHTTPException(code, message, details, help)` and `ValidationException` — standard error classes used across all validation rejections
- `src/codemie/rest_api/models/workflow_marketplace.py` — `PublishWorkflowToMarketplaceRequest.categories: list[str] = Field(min_length=1, max_length=3)` — the reference implementation that already enforces required non-empty categories
- `src/codemie/service/workflow_config/workflow_marketplace_service.py` — `_validate_categories()` method (lines 45–50) wraps `category_service.validate_category_ids()` in `ValidationException`; direct reference pattern for the fix
- `config/categories/assistant-categories.yaml` — defines the 18 canonical marketplace category records (id + name + description) seeded into the `categories` table by Alembic migration `f7a9b2c4d5e6_create_categories_table.py`

### Architecture and Layers Affected

- **API/Router** (`src/codemie/rest_api/routers/assistant.py`): `PublishToMarketplaceRequest` model definition (co-located in the router file), `_validate_publish_marketplace()` helper (line ~1606), `publish_assistant_to_marketplace()` endpoint (line ~1324), `_apply_sub_assistant_settings()` (line ~1491)
- **Models/Schema** (`src/codemie/rest_api/models/assistant.py`): `AssistantBase.categories` field (`list[str]`, JSONB, no non-empty constraint); `AssistantRequest.categories` (`max_length=3` but not required non-empty)
- **Service** (`src/codemie/service/assistant/category_service.py`): `validate_category_ids()` — called for ID existence check; no change required to the service itself

### Integration Points

- `publish_assistant_to_marketplace` → `_validate_publish_marketplace` → `_check_user_can_access_assistant` + `_validate_remote_entities_and_raise`
- `AssistantBase._check_categories()` → `category_service.validate_category_ids()` — ID validation only; not called in the publish path at the time categories would be resolved
- `publish_assistant_to_marketplace` → `_index_marketplace_assistant` (background task) → Elasticsearch datasource `PLATFORM_MARKETPLACE_DATASOURCE_NAME`; an unpopulated categories field breaks search/filter in the index
- `DatabaseCategoryService` → `Category` model → PostgreSQL `categories` table (populated from `config/categories/assistant-categories.yaml` via migration)

### Patterns and Conventions

- **Request model field constraint (preferred)**: Workflow marketplace uses `categories: list[str] = Field(min_length=1, max_length=3)` on `PublishWorkflowToMarketplaceRequest`. This triggers HTTP 422 (`RequestValidationError`) automatically via the registered Pydantic handler before the endpoint body runs. This is the primary fix location.
- **Domain validation helper**: `_validate_*` private helpers in `assistant.py` encapsulate pre-condition checks. The ID-existence check belongs here, wrapping `category_service.validate_category_ids()` in `ValidationException`, following `workflow_marketplace_service._validate_categories()` (lines 45–50).
- **Exception types and HTTP codes**:
  - `ValidationException` → HTTP 400: `{"error": {"message": "<str(exc)>", "details": null, "help": null}}`
  - `ExtendedHTTPException(code, message, details, help)` → HTTP `code`
  - Pydantic `RequestValidationError` (Field constraint violation) → HTTP 422: `{"error": {"message": "...", "details": [...]}}`
- Categories stored as `list[str]` (JSONB column) of category IDs; max 3; enriched to full objects at read time via `_enriched_categories` transient attribute

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/development/error-handling.md` — defines `ValidationException` and `ExtendedHTTPException` as the two exception types; central handlers registered at `main.py:804`; how error responses are structured
- `.ai-run/guides/api/rest-api-patterns.md` — confirms raising shared exceptions, not ad hoc error dicts; `ValidationException` → 400 response
- `.ai-run/guides/api/endpoint-conventions.md` — typed request models under `src/codemie/rest_api/models/`; non-trivial logic in handlers/services, not the router function body
- `.ai-run/guides/architecture/layered-architecture.md` — routers delegate to services; shared exceptions from `codemie.core`

### Architectural Decisions

- No explicit ADR for marketplace categories validation. The workflow marketplace implementation at `src/codemie/rest_api/models/workflow_marketplace.py` constitutes the established pattern: `categories: list[str] = Field(min_length=1, max_length=3)`.
- The `MARKETPLACE_LLM_VALIDATION_ON_PUBLISH_ENABLED` flag and its `ignore_recommendations` bypass path are intentionally scoped to the LLM quality gate only. Categories validation must remain a hard block, not influenced by this flag or its bypass.

### Derived Conventions

- Required non-empty list fields on publish request models: use Pydantic `Field(min_length=1, max_length=N)` on the field declaration (not a custom validator).
- Category ID existence validation in the service layer: wrap `category_service.validate_category_ids()` in `ValidationException` and raise from a `_validate_*` helper in the router.
- All error responses follow the project envelope `{"error": {"message": ..., "details": ..., "help": ...}}`.

---

## 4. Testing Landscape

### Existing Coverage

- `tests/codemie/rest_api/routers/test_assistant_marketplace.py` — covers publish/unpublish/validate endpoints; tests credential validation, sub-assistant publishing with categories, access denial; **no test for missing/empty categories on publish**
- `tests/codemie/rest_api/routers/test_workflow_marketplace_router.py` — workflow marketplace publish; has explicit 422 tests for empty categories list, blank-string category, and duplicate categories (lines 444–477) — **direct reference for new tests**
- `tests/codemie/rest_api/routers/test_assistant_categories.py` — covers CRUD endpoints for the categories resource; includes 422 validation tests for invalid pagination params and missing required fields
- `tests/codemie/rest_api/models/test_assistant_request_validation.py` — Pydantic model-level validation for `AssistantRequest` (type, system_prompt, llm_model_type)
- `tests/codemie/service/assistant/test_category_service.py` — unit tests for `CategoryService` (get, validate, filter, enrich)
- `tests/codemie/repository/test_category_repository.py` — repository-level tests for category querying
- `tests/codemie/service/test_skill_service.py` — covers `SkillService.publish_to_marketplace` with and without categories

### Testing Framework and Patterns

- **Framework**: pytest 8.3.x, pytest-asyncio `^0.23.7`, pytest-mock `^3.14.0`, pytest-env `^1.1.3`, pytest-cov `^5.0.0`
- **HTTP testing**: `ASGITransport(app=app)` + `AsyncClient` (httpx `^0.28.1`) — in-process FastAPI testing, no real server
- **Auth injection**: `app.dependency_overrides[router.authenticate] = lambda: user`; cleared in yield fixture teardown
- **Mocking**: `unittest.mock.patch` (context manager form), `MagicMock()` for assistant/entity objects
- **Test organisation**: class-based (`class TestPublishAssistantToMarketplace:`) with `autouse=True` auth fixtures; `@pytest.mark.asyncio` on every async test
- **Fixtures**: session-scoped `mock_database_engine` patches `PostgresClient.get_engine` globally; routers `conftest.py` disables rate limiter and injects `request.state.uuid`

### Coverage Gaps

- No test for `POST /v1/assistants/{id}/marketplace/publish` with `categories=None` (field absent from body)
- No test for `POST /v1/assistants/{id}/marketplace/publish` with `categories=[]` (empty list)
- No test for `POST /v1/assistants/{id}/marketplace/publish` with invalid category IDs (non-existent IDs)
- No test for `PublishToMarketplaceRequest` Pydantic model validation (no equivalent of `test_assistant_request_validation.py` for this request model)
- The sub-assistant path (`_apply_sub_assistant_settings`) is not tested for categories-missing scenario

---

## 5. Configuration and Environment

### Environment Variables

- `MARKETPLACE_LLM_VALIDATION_ON_PUBLISH_ENABLED` (bool, default `True`) — toggles the LLM quality gate on publish; defined in `src/codemie/configs/config.py` line 696; categories validation must be independent and non-bypassable by this flag
- `PLATFORM_MARKETPLACE_DATASOURCE_NAME` (str, default `"marketplace_assistants"`) — Elasticsearch datasource name for published assistants; assistants indexed without categories will break marketplace search/filter by category

### Configuration Files

- `config/categories/assistant-categories.yaml` — 18 canonical marketplace categories (id + name + description); the authoritative source of valid category IDs; seeded by migration `f7a9b2c4d5e6_create_categories_table.py`
- `config/categories/kata-roles.yaml`, `config/categories/kata-tags.yaml` — kata classification; not relevant to this task

### Feature Flags and Deployment Concerns

- `MARKETPLACE_LLM_VALIDATION_ON_PUBLISH_ENABLED` with `ignore_recommendations=True` in `PublishToMarketplaceRequest` bypasses LLM gate only; categories check must NOT be bypassable via this path.
- **Data state risk**: Assistants already published without categories will not be retroactively blocked — no backfill required, but existing uncategorized published assistants will surface as invisible to category-based Elasticsearch filters. Consider a one-time re-index or data cleanup as a separate follow-up.
- **Migration dependency**: `category_service.validate_category_ids()` queries the `categories` table. If migration `f7a9b2c4d5e6_create_categories_table.py` has not run on the target environment, the validator will silently accept any ID. Migration must be confirmed before deployment.

---

## 6. Risk Indicators

- `PublishToMarketplaceRequest.categories` is `Optional[list[str]] = None` with no `min_length` constraint — the field is structurally valid when absent or empty; this is the primary fix location and must mirror `PublishWorkflowToMarketplaceRequest`
- `_validate_publish_marketplace()` (line ~1606 of `assistant.py`) has no categories check; all other publish pre-conditions are validated here — the categories presence and ID-validity check must be added here or in the endpoint body before `assistant.update()`
- `DatabaseCategoryService.validate_category_ids()` returns early (no-op) on an empty list — it cannot enforce presence; a separate `if not categories` guard is required before calling it
- Sub-assistant path in `_apply_sub_assistant_settings()` (line ~1491) uses `if settings.categories:` (truthy only) — same gap exists for orchestrator assistants that use sub-assistant publishing; must be addressed in the same change
- `MARKETPLACE_LLM_VALIDATION_ON_PUBLISH_ENABLED` + `ignore_recommendations=True` bypass — categories validation must be a hard block that does not participate in this bypass path; risk of inadvertently placing the check inside the LLM-gate conditional
- No existing test coverage for `categories=None` or `categories=[]` on `POST /v1/assistants/{id}/marketplace/publish` — new tests required; reference pattern exists in `test_workflow_marketplace_router.py` lines 444–477
- Existing published assistants in the database have no categories — deploying this change without a data migration will not block re-publishing attempts but leaves them visible in the marketplace without categories (Elasticsearch filter gap)
- `config/categories/assistant-categories.yaml` migration must be confirmed applied on target environment before deployment; otherwise the ID-existence check is vacuous

---

## 7. Summary for Complexity Assessment

This task is a targeted, well-precedented validation addition with a narrow file change surface. The primary change is in `src/codemie/rest_api/routers/assistant.py`: tightening the `categories` field on `PublishToMarketplaceRequest` from `Optional[list[str]] = None` to `list[str] = Field(min_length=1, max_length=3)` (mirroring the workflow marketplace model), and adding a category ID existence check inside `_validate_publish_marketplace()` that wraps `category_service.validate_category_ids()` in a `ValidationException` (following the `workflow_marketplace_service._validate_categories()` pattern). A secondary, smaller change is required in `_apply_sub_assistant_settings()` to close the same gap for the sub-assistant publishing path. No service, repository, or database schema changes are needed. Total estimated file changes: 1–2 files (`assistant.py` router, potentially a minor addition to `category_service.py` if a named helper is preferred over an inline check).

The task follows a fully established pattern. The workflow marketplace domain has already solved this exact problem and provides a line-for-line reference for both the request model constraint (`Field(min_length=1, max_length=3)`) and the service-layer validation wrapper (`ValidationException`). The error response format, HTTP status codes, and exception hierarchy are documented in `.ai-run/guides/development/error-handling.md` and confirmed by the workflow marketplace implementation. No novel patterns or new architectural layers are introduced.

Test coverage for the affected endpoint is the weakest risk factor. `test_assistant_marketplace.py` currently has no cases for missing or empty categories on publish. The workflow marketplace tests (`test_workflow_marketplace_router.py` lines 444–477) provide the exact test pattern to replicate: three cases — absent field, empty list, invalid IDs — using the same `ASGITransport` + `AsyncClient` + `dependency_overrides` fixture structure. New tests for `PublishToMarketplaceRequest` model-level validation should also be added to `tests/codemie/rest_api/models/`. The sub-assistant path and the `ignore_recommendations` bypass must be covered by dedicated test cases to prevent regression of the non-bypassability requirement.
