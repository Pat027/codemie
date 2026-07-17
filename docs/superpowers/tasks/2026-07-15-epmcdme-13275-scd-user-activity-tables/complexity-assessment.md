# Complexity Assessment: database models migration activity events audit tracking SCD user budget

**Task**: Create SCD tables for user activity event tracking across user management and budget management domains, delivering a new SQLModel table, Alembic migration, repository class, alembic/env.py update, and optional service-layer instrumentation.
**Generated**: 2026-07-15T00:00:00Z

---

## Dimension Scores

| Dimension            | Score | Label |
|----------------------|-------|-------|
| Component Scope      | 4     | L     |
| Requirements Clarity | 4     | L     |
| Technical Risk       | 4     | L     |
| File Change Estimate | 4     | L     |
| Dependencies         | 1     | XS    |
| Affected Layers      | 4     | L     |

**Total: 21/36 — L**

---

## Key Reasoning

- **Component Scope (L)**: Spans DB-Persistence (new `user_activity_events` SQLModel table), Repository (new abstract+concrete repository following `SkillEventRepository` pattern), Service (instrumentation in `user_management_service.py`, `registration_service.py`, `authentication_service.py`, `budget_service.py`, `project_budget_service.py`), and `alembic/env.py`. Four distinct components across three layers with a new shared infrastructure pattern that both domains will depend on.

- **Requirements Clarity (L)**: The highest-priority design decision — single-table discriminator (as in `ProjectSpendTracking` with `spend_subject_type`) versus per-domain tables (as in `skill_events`) — is explicitly unresolved. FK strategy for heterogeneous entity types (nullable multi-column vs. single nullable column) is open. Service instrumentation scope is marked "optional." These gaps risk rework if assumptions are wrong.

- **Technical Risk (L)**: Greenfield SCD audit infrastructure for user and budget domains — no prior art for this specific combination in the codebase. `ProjectSpendTracking` is the closest multi-domain precedent but serves cost tracking, not audit. The multi-domain discriminator architectural decision must be made and documented before implementation. Red flag applied: "Changes database schema significantly" bumped Technical Risk from M to L.

- **File Change Estimate (L)**: Core deliverables alone reach ~4 files (1 new model module, 1 new migration, 1 new repository module, 1 modified `alembic/env.py`). With service instrumentation: 4–5 additional service file touches, totalling 8–9 files across `service/user/`, `service/budget/`, `service/activity/` (or `rest_api/models/`), `external/alembic/versions/`, and `external/alembic/`. Spans 4+ directories.

- **Affected Layers (L)**: DB-Persistence + Repository + Service = three layers. Red flag applied: "Changes database schema significantly" bumped Affected Layers from M to L.

- **Red flags applied**: "Changes database schema significantly" — bumped both Technical Risk (M→L) and Affected Layers (M→L).

---

## Routing

superpowers:brainstorming
