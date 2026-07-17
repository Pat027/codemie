# Technical Research

**Task**: database models migration activity events audit tracking SCD user budget
**Generated**: 2026-07-15T00:00:00Z

---

## 1. Original Context

Plan new SCD (Slowly Changing Dimension) tables that track user activity events related to user management and budget management. The tables must be extensible to other domains in the future (only user management and budget management domains are in scope now). The main challenge is the correct DB model — the database design needs extra depth. The goal is to produce a spec and plan for the data model and migration, not necessarily full implementation.

---

## 2. Codebase Findings

### Existing Implementations

No `user_activity_events`, `audit_log`, or SCD-style activity table exists anywhere in the codebase. This is a greenfield addition. There is, however, a directly analogous precedent — `skill_events` — which serves as the canonical pattern:

- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/rest_api/models/skill_event.py` — `SkillEvent` SQLModel table: append-only event log, one row per lifecycle step, with free-form TEXT for `command`/`status` (no DB CHECK constraints), a JSONB `attributes` escape hatch, composite indexes, and a `created_at` server-default. This model is the closest existing SCD-style event store in the project.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/repository/skill_event_repository.py` — `SkillEventRepository` (abstract) + `SQLSkillEventRepository` (concrete): insert, find-by-id, paginated query, aggregation stats. Uses sync `Session`. Declares a singleton `SkillEventRepositoryImpl`.
- `/Users/uladzislau_svetlakou/projects/codemie/src/external/alembic/versions/c4f2a8b6d1e9_create_skill_events_table.py` — migration that created `skill_events`; shows the expected migration form for an event table.

Existing domain models that will be referenced as FKs or described in events:

- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/rest_api/models/user_management.py` — `UserDB` (`users` table), `UserProject` (`user_projects`), `UserKnowledgeBase` (`user_knowledge_bases`), `EmailVerificationToken`, `UserEnrichment`.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/budget/budget_models.py` — `Budget` (`budgets`), `UserBudgetAssignment` (`user_budget_assignments`), `ProjectBudgetGroup` (`project_budget_groups`), `ProjectBudgetAssignment` (`project_budget_assignments`), `ProjectMemberBudgetAssignment` (`project_member_budget_assignments`).
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/spend_tracking/spend_models.py` — `ProjectSpendTracking` (`project_spend_tracking`): an existing SCD-style snapshot table using `spend_date` + cumulative/delta spend columns. Its repository (`project_spend_tracking_repository.py`) is the most technically complex in the repo, with multi-subject-type partitioning (`spend_subject_type` discriminator), partial unique indexes, and subquery-based "latest row" lookups.

Key service entry points that would generate events:

- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/user/user_management_service.py` — `UserManagementService`: `create_local_user`, `update`, `deactivate`, user project CRUD.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/user/registration_service.py` — registration and IDP user provisioning.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/user/authentication_service.py` — login/logout.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/budget/budget_service.py` — budget create/update/delete/sync. Already uses `budget_event=...` structured log keys internally; currently logs only, does not persist events to DB.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/service/budget/project_budget_service.py` — project budget group/assignment lifecycle.

### Architecture and Layers Affected

| Layer | Components Touched |
|---|---|
| DB-Persistence / Model | New `user_activity_events` table (SQLModel class), new Alembic migration |
| Repository | New repository class (following `SkillEventRepository` abstract+concrete pattern) |
| Service | `user_management_service.py`, `registration_service.py`, `authentication_service.py`, `budget_service.py`, `project_budget_service.py` — emit events after mutations |
| API (optional in spec phase) | Potential future read endpoints; not required for the data model spec |

The task is scoped to the Model + Migration + Repository layers. The service-layer instrumentation (calling the new repository) is the implementation phase.

### Integration Points

Internal module dependencies:

- New model will `foreign_key` reference `users.id` (from `user_management.py`) and optionally `budgets.budget_id` (from `budget_models.py`).
- The `UserEnrichment` table uses a separate `codemie` schema (`__table_args__ = {"schema": "codemie"}`). All other relevant tables (`users`, `budgets`, `user_budget_assignments`, `project_spend_tracking`) use the default `codemie` schema set in `env.py` via `SET search_path TO codemie, public`.
- `alembic/env.py` imports all SQLModel classes for autogenerate — the new model must be imported there when the migration is created.
- `ProjectSpendTracking` is the most mature SCD-like table in the repo: it uses a `spend_subject_type` discriminator string to multiplex multiple entity types into a single table, with partial unique indexes per subject type. This is the most directly relevant architectural precedent for a multi-domain activity event table.

External dependencies:

- PostgreSQL (via `psycopg2-binary`, `sqlmodel`, `sqlalchemy`). The codebase uses `TIMESTAMP(timezone=True)`, `JSONB`, `Numeric`, and `PG_UUID` column types from `sqlalchemy.dialects.postgresql`. These are the expected column types for the new table.
- No external event bus or message queue is involved; writes are synchronous Postgres INSERT statements (same as `skill_events` and `project_spend_tracking`).

### Patterns and Conventions

**SQLModel table declaration:**
- Tables that belong to business domains (budgets, users, skills) are declared in `src/codemie/service/<domain>/` (e.g., `budget_models.py`) or `src/codemie/rest_api/models/` (e.g., `skill_event.py`, `user_management.py`).
- Tables extending `BaseModelWithSQLSupport` inherit `id`, `date`, `update_date` from `CommonBaseModel`. The `SkillEvent` model overrides `id` with `default_factory=lambda: str(uuid4())` to guarantee non-null UUIDs.
- Tables that are pure append-only logs (like `skill_events` and `project_spend_tracking`) use a dedicated `created_at` with `server_default=func.now()` / `sa.text("now()")` rather than relying on `CommonBaseModel.date`.
- `JSONB` columns named `attributes` or `provider_metadata` are used as forward-compatible escape hatches. This pattern appears in `SkillEvent.attributes`, `Budget.provider_metadata`, and `ProjectMemberBudgetAssignment.provider_metadata`.
- Partial unique indexes with `postgresql_where=` are used in `Budget` (active-only name uniqueness), `ProjectBudgetGroup`, and `project_spend_tracking` (subject-type-specific conflict targets). This is the pattern to follow for the new table's deduplication constraints.

**Discriminator / multi-domain design (most relevant precedent):**
The `ProjectSpendTracking` table uses `spend_subject_type` (a plain VARCHAR, not a PG ENUM) to distinguish `key`, `budget`, `project_budget`, and `member_budget` rows in a single table. Each subject type has its own partial unique index and repository method. This is the direct precedent for a `domain` (or `entity_type`) discriminator column in the new activity events table.

**Repository pattern:**
- `SkillEventRepository` uses abstract base class + `SQLSkillEventRepository` concrete implementation, with a singleton `SkillEventRepositoryImpl = SQLSkillEventRepository`.
- `BudgetRepository` and `ProjectSpendTrackingRepository` are async-only (use `AsyncSession`).
- `UserRepository` has both sync (`Session`) and async (`AsyncSession`) methods.
- The `skill_event_repository` uses sync `Session` — matching `SkillEvent` which extends `BaseModelWithSQLSupport`. A new activity event repository should follow the same sync/async choice consistently with how the calling service layers operate.

**Migration format:**
All migrations explicitly declare `revision`, `down_revision`, `branch_labels`, `depends_on`, and include both `upgrade()` and `downgrade()` functions with `op.create_table` / `op.drop_table` / `op.create_index` / `op.drop_index` pairs.

---

## 3. Documentation Findings

### Guides and Architecture Docs

The following guides from `.ai-run/guides/` are directly relevant:

- `/Users/uladzislau_svetlakou/projects/codemie/.ai-run/guides/data/database-patterns.md` — mandates Alembic in `src/external/alembic/versions/` for all schema changes; prohibits runtime schema creation for persistent tables.
- `/Users/uladzislau_svetlakou/projects/codemie/.ai-run/guides/data/repository-patterns.md` — repositories own data access; services must not call storage directly; factory/provider pattern for multi-provider repos.
- `/Users/uladzislau_svetlakou/projects/codemie/.ai-run/guides/data/database-optimization.md` — avoid unbounded queries; pagination and batch queries are required for list methods.
- `/Users/uladzislau_svetlakou/projects/codemie/.ai-run/guides/architecture/layered-architecture.md` — API → Service → Repository hierarchy; shared exceptions/config in `core/`.

No guide document specifically covers SCD tables, event sourcing, or audit trails. The design must be derived from code patterns.

### Architectural Decisions

From migration history and inline comments:

1. **VARCHAR discriminators over PG ENUMs**: `spend_subject_type`, `budget_type`, `budget_origin_type`, `command`, `status` in `skill_events` are all plain VARCHAR. The alembic `env.py` patches `alembic_postgresql_enum` to work with the non-default schema, indicating PG ENUMs have caused operational pain. New discriminator columns should use VARCHAR with API-layer validation (Pydantic `Literal`) — not DB CHECK constraints.

2. **Partial unique indexes for conflict control**: `project_spend_tracking` uses four separate partial unique indexes, one per `spend_subject_type` value. This is the established pattern for multi-entity tables where uniqueness constraints differ per entity type.

3. **JSONB `attributes` escape hatch**: `skill_events.attributes` (JSONB, nullable) was included from day 1 precisely so new per-event fields can ship without a schema migration. The same escape hatch should be in any new activity event table.

4. **Soft-delete on reference tables, append-only on event tables**: `Budget`, `UserDB`, and `ProjectBudgetGroup` use `deleted_at` for soft-delete. Event/log tables (`skill_events`, `project_spend_tracking`) are pure append-only — rows are never updated or deleted by application code.

5. **`created_at` as the SCD timestamp**: `project_spend_tracking.created_at` and `skill_events.created_at` both use `server_default=func.now()`. The authoritative event time uses a dedicated `created_at` column separate from `CommonBaseModel.date`.

6. **Schema**: Tables go into the `codemie` schema (set via `SET search_path` in `alembic/env.py`). The `UserEnrichment` table is the only exception that explicitly declares `{"schema": "codemie"}` in `__table_args__` — all other tables inherit it through the search path.

### Derived Conventions

- Primary keys: `str` UUID via `default_factory=lambda: str(uuid4())` for new rows, or `UUID` with `PG_UUID(as_uuid=True)` for newer tables (`ProjectSpendTracking`). Both approaches coexist. The `skill_events` pattern (`str` UUID PK) is simpler and sufficient for an event log.
- Indexes follow the naming convention `ix_{table}_{column}` (single) and `ix_{table}_{col1}_{col2}` (composite), created via `op.create_index(op.f("ix_..."), ...)` in the migration.
- Foreign keys to `users.id` use the constant `USER_ID_FOREIGN_KEY = "users.id"` declared in `budget_models.py`. The new model should declare a similar constant.
- Budget domain models live in `src/codemie/service/budget/budget_models.py`. New activity event models should live in a parallel location, e.g., `src/codemie/service/activity/` or `src/codemie/rest_api/models/activity_event.py` (following `skill_event.py` precedent).

---

## 4. Testing Landscape

### Existing Coverage

Directly relevant test files:

- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/repository/test_skill_event_repository.py` — unit tests for `SQLSkillEventRepository` using `unittest.mock.patch` to mock `Session`. Tests cover `insert`, `find_by_id`, and would extend naturally to new activity event repository methods.
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/repository/test_budget_repository.py` — async repository testing patterns.
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/repository/test_project_spend_tracking_repository.py` — most complex repository tests; tests batched insert, subquery-based "latest row" logic.
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/repository/test_user_repository.py` — sync `Session` mocking pattern (also used by `skill_event_repository` tests).
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/migrations/test_k5l6m7n8o9p0_deprecate_python_repl.py` — pattern for testing data-transform logic inside a migration.
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/service/budget/` — 7 budget service test files, well-covered.
- `/Users/uladzislau_svetlakou/projects/codemie/tests/codemie/service/user/` — 11 user service test files; covers most service methods.

### Testing Framework and Patterns

- **Framework**: `pytest` with `pytest-mock` (via `mocker` fixture). Configuration in `pytest.ini`: `testpaths=tests`, `pythonpath=src`, `--import-mode=importlib`.
- **Database isolation**: Global `conftest.py` (`tests/conftest.py`) patches `PostgresClient.get_engine` session-scoped to prevent live DB connections. All repository tests mock `Session` or `AsyncSession` at the call site with `@patch("codemie.repository.<module>.Session")`.
- **Fixture style**: Factory functions (e.g., `_event(**kwargs)` in `test_skill_event_repository.py`) create minimal valid model instances with defaults. `pytest.fixture` is used for shared dependencies.
- **Async tests**: `pytest-asyncio` (implied by async test functions in budget/spend test files).
- **Assertion style**: `unittest.mock.assert_called_once_with` on mock objects for repository tests; `assert result is <expected>` for return value verification.

### Coverage Gaps

The new SCD activity event tables introduce the following untested areas:

1. **New `UserActivityEvent` model and table** — no tests exist because the model does not yet exist. Repository tests, model field validation tests, and migration tests all need to be written.
2. **Service-layer event emission** — `user_management_service.py`, `registration_service.py`, `budget_service.py`, and `project_budget_service.py` currently have no activity-event instrumentation. When instrumentation is added, tests for each mutation path (create user, update user, deactivate user, create budget, assign budget, etc.) will need to verify event rows are emitted.
3. **Multi-domain discriminator logic** — the `domain` / `entity_type` discriminator pattern (analogous to `spend_subject_type`) has no existing tests that cover it at the activity event level.
4. **Migration data correctness** — no migration test exists for the new table (consistent with the rarity of migration tests in this codebase, but the pattern exists in `tests/codemie/migrations/`).

---

## 5. Configuration and Environment

### Environment Variables

Relevant config variables from `src/codemie/configs/config.py`:

- `DEFAULT_DB_SCHEMA = "codemie"` (line 92) — all new tables go into this schema.
- `DB_INSERT_BATCH_SIZE = 1000` (line 98) — used by `ProjectSpendTrackingRepository` for bulk inserts; should be used by any bulk-insert method in the new repository.
- `DB_IN_CLAUSE_BATCH_SIZE = 500` (line 99) — used for batching IN-clause queries; relevant if the new repository needs batch lookups.
- `PG_URL` — set in `pytest.ini` test environment as `postgresql://pg:pg123@localhost:111/postgres`; production value from environment.

No feature flags or toggles gate the budget or user management domains at the database layer. The `enterprise` loader gates some optional enterprise features but does not affect core DB schema.

### Configuration Files

- `/Users/uladzislau_svetlakou/projects/codemie/src/external/alembic/alembic.ini` — Alembic configuration; `sqlalchemy.url` is read from environment.
- `/Users/uladzislau_svetlakou/projects/codemie/src/external/alembic/env.py` — imports all SQLModel models for autogenerate; the new model must be added here. Sets `search_path TO codemie, public` before running migrations.
- `/Users/uladzislau_svetlakou/projects/codemie/src/codemie/configs/config.py` — central Pydantic-settings config; add any new tuning parameters (e.g., activity event batch size) here.

### Feature Flags and Deployment Concerns

- No feature flags gate the user management or budget management DB layers.
- The new table adds a net-new `INSERT` call to service methods that are on the hot path (authentication, user CRUD, budget assignment). This is a write-amplification concern for high-traffic deployments. The `skill_events` table takes the same approach and was accepted without a toggle.
- Alembic migrations are applied via `make migrate` / deployment scripts; the migration chain must be extended from the current head (`r7s8t9u0v1w2` or any later merge-head). The chain currently has multiple active tips that are periodically merged via merge-head migrations (e.g., `8eb9522661cf`, `f9e8d7c6b5a4`). A new migration must correctly set `down_revision` to the current tip. If multiple feature branches are active, a merge-head migration may be needed.

---

## 6. Risk Indicators

- **No existing SCD activity/audit table in any domain** — the design is entirely greenfield. There is no prior art in this codebase for user or budget change-audit tables specifically. The `ProjectSpendTracking` table is the closest design analog (multi-subject discriminator, append-only snapshots) but serves cost tracking, not event audit.

- **Multi-domain extensibility design decision is unresolved** — the task explicitly requires the table to be extensible to domains beyond user management and budget management. Two competing designs exist in the codebase: (a) a single table with a `domain` discriminator column (as `ProjectSpendTracking` does with `spend_subject_type`), or (b) separate per-domain tables (as `skill_events` is a single-domain table). Choice (a) avoids schema migrations for new domains but produces a wide row with many nullable columns; choice (b) is cleaner per-domain but requires a new table per domain. This is the highest-priority design decision and has no existing ADR.

- **Foreign key strategy for `entity_id` columns** — if the table records, e.g., "user `X` was created", the `entity_id` could FK to `users.id`. But for heterogeneous entity types (users and budgets in the same table), referential integrity via FK is incompatible with a single column approach; the FK must be nullable or absent, matching how `project_spend_tracking` handles `budget_id`, `user_id`, and `key_hash` as independently nullable columns.

- **`ProjectSpendTracking` does not have ON DELETE CASCADE FKs on `budget_id` or `user_id`** — consistent with event/audit tables being independent of the lifecycle of the entities they reference (append-only history must survive entity deletion). The new table should follow this pattern (no cascade delete), but this needs to be an explicit decision.

- **Budget service already logs events as structured log lines** (e.g., `budget_event=budget_create_started`) but does not persist them to DB. Adding persistent DB writes to synchronous budget service methods introduces transactional coupling — a budget CREATE that also inserts an event row will roll back both if the transaction fails. This is correct behavior for audit fidelity but must be considered in the design.

- **Alembic migration chain has multiple active branch tips** — `r7s8t9u0v1w2` and `a1b3e5d7f9c2` and `c5d6e7f8a9b0` are among recent heads that have been merged. The new migration must correctly pick the current single head, which may require running `alembic heads` to verify.

- **No migration test coverage for budget or user management tables** — only one migration test exists (`test_k5l6m7n8o9p0_deprecate_python_repl.py`), covering a data-transform migration. A migration that creates a large new table with several indexes should have at least a structural test.

- **`TIMESTAMP(timezone=True)` vs naive `datetime`** — `UserDB` uses `date`/`update_date` as naive `datetime` via `CommonBaseModel`, while `Budget`, `SkillEvent`, and `ProjectSpendTracking` use timezone-aware `TIMESTAMP(timezone=True)`. New event tables must use `TIMESTAMP(timezone=True)` for `created_at`, consistent with the budget/spend_tracking pattern.

- **Schema location ambiguity for the new model file** — `SkillEvent` lives in `rest_api/models/`, `Budget` lives in `service/budget/`, `ProjectSpendTracking` lives in `service/spend_tracking/`. There is no single canonical location for domain event models. The choice should be consistent and the import must be added to `alembic/env.py`.

---

## 7. Summary for Complexity Assessment

The task is to design (not yet implement) a Slowly Changing Dimension table structure for tracking user activity events in the user management and budget management domains, with extensibility to future domains. Architecturally, this touches the DB-Persistence layer (new SQLModel table, new Alembic migration), the Repository layer (new repository class), and indirectly the Service layer (though service-layer instrumentation is deferred to implementation). The file change surface for the design spec deliverable is approximately 3–5 files: one new SQLModel module, one Alembic migration file, one repository module, and an update to `alembic/env.py`. If service instrumentation is included in scope, add 4–6 more service file touches.

The task introduces technical novelty in one critical dimension: the multi-domain extensibility architecture decision. The codebase has two competing patterns — single-table discriminator (`ProjectSpendTracking` with `spend_subject_type`) versus single-domain event tables (`skill_events`). Neither has been applied to a combined user+budget audit context. The design must choose one approach and document the rationale, as this decision will shape all future domain additions. The `ProjectSpendTracking` pattern is the stronger precedent for multi-domain use, but it introduces a wide nullable-column schema that is more complex to query and maintain. This is the single highest-risk design decision and warrants the most design depth in the spec.

Test coverage for the new area will be entirely absent until written — no `user_activity_events` table or activity event repository exists. The closely analogous `skill_event_repository` tests provide a complete template for unit testing the new repository using mock `Session` objects. The budget and user management service layers are well-tested (7 and 11 test files respectively), but none currently test event emission because no event emission exists. Adding event emission to service methods will require adding assertions for event insertion to the relevant test cases. Overall risk is moderate: the domain models being captured (user management, budget) are well-understood and well-tested; the novelty is concentrated in the SCD/multi-domain design decision and the absence of any existing event infrastructure for these two domains.
