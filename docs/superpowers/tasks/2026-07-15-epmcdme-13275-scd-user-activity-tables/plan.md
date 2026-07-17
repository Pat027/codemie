# Activity Events — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, append-only `activity_events` table and repository to record audit events across the user management and budget management domains, with service-layer instrumentation emitting events transactionally alongside each mutation.

**Architecture:** Single Postgres table with `domain` + `entity_type` + `entity_id` generic references (no per-domain FK columns), three composite indexes for the three stated query shapes, a sync+async repository, and thin emit-calls in each service method. The event row is written in the same DB transaction as the mutation — if the mutation rolls back, the event rolls back too.

**Tech Stack:** SQLModel, SQLAlchemy (JSONB, TIMESTAMP, Index), Alembic, Pydantic v2, pytest, unittest.mock

---

## File Map

| File | Action |
|---|---|
| `src/codemie/service/activity/__init__.py` | Create (empty) |
| `src/codemie/service/activity/activity_models.py` | Create — SQLModel table, constants, Pydantic input model |
| `src/codemie/service/activity/activity_repository.py` | Create — abstract + concrete repository, singleton |
| `src/external/alembic/versions/<hash>_create_activity_events_table.py` | Create — migration |
| `src/codemie/service/user/user_management_service.py` | Edit — emit events in create_local_user, update_user, deactivate_user |
| `src/codemie/service/user/authentication_service.py` | Edit — emit user.login in authenticate_and_login |
| `src/codemie/rest_api/routers/local_auth_router.py` | Edit — emit user.logout in /logout endpoint |
| `src/codemie/service/budget/budget_service.py` | Edit — emit events in create_budget, update_budget, assign_budget_to_user |
| `src/codemie/service/budget/project_budget_service.py` | Edit — emit events in create_project_budget, delete_project_budget |
| `tests/codemie/service/activity/__init__.py` | Create (empty) |
| `tests/codemie/service/activity/test_activity_models.py` | Create — tests for Pydantic validator |
| `tests/codemie/service/activity/test_activity_repository.py` | Create — unit tests for repository methods |
| `tests/codemie/service/user/test_user_management_service.py` | Create — tests for event emission in user service |
| `tests/codemie/service/user/test_authentication_service.py` | Edit — add login/logout event emission assertions |
| `tests/codemie/service/budget/test_budget_service_activity.py` | Create — tests for event emission in budget service |

---

## Task 1: Activity module — model, constants, input model

**Files:**
- Create: `src/codemie/service/activity/__init__.py`
- Create: `src/codemie/service/activity/activity_models.py`
- Create: `tests/codemie/service/activity/__init__.py`
- Create: `tests/codemie/service/activity/test_activity_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/codemie/service/activity/test_activity_models.py
import pytest
from pydantic import ValidationError
from codemie.service.activity.activity_models import ActivityEventCreate


def test_entity_pair_both_set_is_valid():
    e = ActivityEventCreate(
        domain="user_management",
        event_type="user.created",
        entity_type="user",
        entity_id="abc-123",
    )
    assert e.entity_type == "user"
    assert e.entity_id == "abc-123"


def test_entity_pair_both_none_is_valid():
    e = ActivityEventCreate(domain="user_management", event_type="user.login")
    assert e.entity_type is None
    assert e.entity_id is None


def test_entity_type_set_without_entity_id_raises():
    with pytest.raises(ValidationError, match="entity_type and entity_id"):
        ActivityEventCreate(
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id=None,
        )


def test_entity_id_set_without_entity_type_raises():
    with pytest.raises(ValidationError, match="entity_type and entity_id"):
        ActivityEventCreate(
            domain="user_management",
            event_type="user.created",
            entity_type=None,
            entity_id="abc-123",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/repo
python -m pytest tests/codemie/service/activity/test_activity_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'codemie.service.activity'`

- [ ] **Step 3: Create `src/codemie/service/activity/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `src/codemie/service/activity/activity_models.py`**

```python
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Activity event model, constants, and input model.

Append-only audit log table. One row per domain action.
Generic entity references (entity_type + entity_id) keep the table
extensible to future domains without schema migrations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, model_validator
from sqlalchemy import Column, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel
from sqlalchemy import VARCHAR, ForeignKey
from sqlalchemy import TIMESTAMP


class ActivityDomain:
    USER_MANAGEMENT = "user_management"
    BUDGET_MANAGEMENT = "budget_management"


class ActivityEntityType:
    USER = "user"
    BUDGET = "budget"
    PROJECT_BUDGET_GROUP = "project_budget_group"
    USER_BUDGET_ASSIGNMENT = "user_budget_assignment"
    PROJECT_BUDGET_ASSIGNMENT = "project_budget_assignment"


class UserManagementEvent:
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"


class BudgetManagementEvent:
    BUDGET_CREATED = "budget.created"
    BUDGET_UPDATED = "budget.updated"
    USER_BUDGET_ASSIGNED = "budget.user_assignment.created"
    PROJECT_BUDGET_CREATED = "budget.project_budget.created"
    PROJECT_BUDGET_DELETED = "budget.project_budget.deleted"


class ActivityEvent(SQLModel, table=True):
    """Append-only audit event row. Never updated or deleted by application code."""

    __tablename__ = "activity_events"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    domain: str = Field(sa_column=Column(VARCHAR(64), nullable=False))
    event_type: str = Field(sa_column=Column(VARCHAR(128), nullable=False))

    entity_type: Optional[str] = Field(
        default=None, sa_column=Column(VARCHAR(64), nullable=True)
    )
    entity_id: Optional[str] = Field(
        default=None, sa_column=Column(VARCHAR(36), nullable=True)
    )

    actor_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            VARCHAR(36),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    attributes: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )

    created_at: datetime = Field(
        sa_column=Column(
            TIMESTAMP(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )

    __table_args__ = (
        Index(
            "ix_activity_events_entity_type_entity_id",
            "entity_type",
            "entity_id",
            postgresql_where=text("entity_id IS NOT NULL"),
        ),
        Index(
            "ix_activity_events_actor_id_created_at",
            "actor_id",
            "created_at",
            postgresql_where=text("actor_id IS NOT NULL"),
        ),
        Index(
            "ix_activity_events_domain_created_at",
            "domain",
            "created_at",
        ),
    )


class ActivityEventCreate(BaseModel):
    """Input model for emitting a new activity event.

    entity_type and entity_id are a pair: both set or both None.
    """

    domain: str
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    actor_id: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def entity_pair_must_be_complete(self) -> "ActivityEventCreate":
        if (self.entity_type is None) != (self.entity_id is None):
            raise ValueError("entity_type and entity_id must both be set or both be absent")
        return self
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/codemie/service/activity/test_activity_models.py -v
```
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/codemie/service/activity/__init__.py \
        src/codemie/service/activity/activity_models.py \
        tests/codemie/service/activity/__init__.py \
        tests/codemie/service/activity/test_activity_models.py
git commit -m "EPMCDME-13275: Add ActivityEvent model and constants"
```

---

## Task 2: Activity repository

**Files:**
- Create: `src/codemie/service/activity/activity_repository.py`
- Create: `tests/codemie/service/activity/test_activity_repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/codemie/service/activity/test_activity_repository.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from codemie.service.activity.activity_models import ActivityEventCreate, ActivityDomain, UserManagementEvent, ActivityEntityType
from codemie.service.activity.activity_repository import SQLActivityEventRepository


def _repo() -> SQLActivityEventRepository:
    return SQLActivityEventRepository()


def _create_dto(**kwargs) -> ActivityEventCreate:
    defaults = {
        "domain": ActivityDomain.USER_MANAGEMENT,
        "event_type": UserManagementEvent.USER_CREATED,
        "entity_type": ActivityEntityType.USER,
        "entity_id": "user-uuid-1",
        "actor_id": "actor-uuid-1",
    }
    defaults.update(kwargs)
    return ActivityEventCreate(**defaults)


def test_insert_adds_and_flushes_event():
    session = MagicMock()
    dto = _create_dto()

    result = _repo().insert(dto, session)

    session.add.assert_called_once()
    session.flush.assert_called_once()
    assert result.domain == ActivityDomain.USER_MANAGEMENT
    assert result.event_type == UserManagementEvent.USER_CREATED
    assert result.entity_type == ActivityEntityType.USER
    assert result.entity_id == "user-uuid-1"
    assert result.actor_id == "actor-uuid-1"


def test_insert_domain_level_event_with_no_entity():
    session = MagicMock()
    dto = _create_dto(entity_type=None, entity_id=None)

    result = _repo().insert(dto, session)

    assert result.entity_type is None
    assert result.entity_id is None


@pytest.mark.asyncio
async def test_async_insert_adds_and_flushes_event():
    session = AsyncMock()
    dto = _create_dto()

    result = await _repo().async_insert(dto, session)

    session.add.assert_called_once()
    session.flush.assert_called_once()
    assert result.domain == ActivityDomain.USER_MANAGEMENT


def test_find_by_entity_executes_query():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.exec.return_value = mock_result

    results = _repo().find_by_entity("user", "user-uuid-1", limit=10, offset=0, session=session)

    session.exec.assert_called_once()
    assert results == []


def test_find_by_actor_executes_query():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.exec.return_value = mock_result

    results = _repo().find_by_actor("actor-uuid-1", limit=10, offset=0, session=session)

    session.exec.assert_called_once()
    assert results == []


def test_find_by_domain_executes_query():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.exec.return_value = mock_result

    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 12, 31, tzinfo=timezone.utc)

    results = _repo().find_by_domain(
        "user_management", from_dt=from_dt, to_dt=to_dt, limit=20, offset=0, session=session
    )

    session.exec.assert_called_once()
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/codemie/service/activity/test_activity_repository.py -v
```
Expected: `ImportError: cannot import name 'SQLActivityEventRepository'`

- [ ] **Step 3: Create `src/codemie/service/activity/activity_repository.py`**

```python
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Repository for activity events.

insert() and async_insert() accept a caller-provided session so the event row
is committed in the same transaction as the business mutation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session, select

from codemie.configs import logger
from codemie.service.activity.activity_models import ActivityEvent, ActivityEventCreate


class ActivityEventRepository(ABC):
    """Abstract interface for activity event persistence."""

    @abstractmethod
    def insert(self, event: ActivityEventCreate, session: Session) -> ActivityEvent:
        """Persist a new event within the caller's sync transaction."""

    @abstractmethod
    def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        """Return events for a specific entity, most recent first."""

    @abstractmethod
    def find_by_actor(
        self,
        actor_id: str,
        *,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        """Return events performed by a specific actor, most recent first."""

    @abstractmethod
    def find_by_domain(
        self,
        domain: str,
        *,
        from_dt: datetime,
        to_dt: datetime,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        """Return events in a domain within a time range, most recent first."""


class SQLActivityEventRepository(ActivityEventRepository):
    """Postgres-backed implementation."""

    def insert(self, event: ActivityEventCreate, session: Session) -> ActivityEvent:
        row = ActivityEvent(**event.model_dump())
        session.add(row)
        session.flush()
        logger.debug(
            f"[activity_events] insert domain={row.domain!r} event_type={row.event_type!r} "
            f"entity_id={row.entity_id!r} actor_id={row.actor_id!r}"
        )
        return row

    async def async_insert(self, event: ActivityEventCreate, session: AsyncSession) -> ActivityEvent:
        """Persist a new event within the caller's async transaction."""
        row = ActivityEvent(**event.model_dump())
        session.add(row)
        await session.flush()
        logger.debug(
            f"[activity_events] async_insert domain={row.domain!r} event_type={row.event_type!r} "
            f"entity_id={row.entity_id!r} actor_id={row.actor_id!r}"
        )
        return row

    def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        stmt = (
            select(ActivityEvent)
            .where(ActivityEvent.entity_type == entity_type)
            .where(ActivityEvent.entity_id == entity_id)
            .order_by(ActivityEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(stmt).all())

    def find_by_actor(
        self,
        actor_id: str,
        *,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        stmt = (
            select(ActivityEvent)
            .where(ActivityEvent.actor_id == actor_id)
            .order_by(ActivityEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(stmt).all())

    def find_by_domain(
        self,
        domain: str,
        *,
        from_dt: datetime,
        to_dt: datetime,
        limit: int,
        offset: int,
        session: Session,
    ) -> list[ActivityEvent]:
        stmt = (
            select(ActivityEvent)
            .where(ActivityEvent.domain == domain)
            .where(ActivityEvent.created_at >= from_dt)
            .where(ActivityEvent.created_at <= to_dt)
            .order_by(ActivityEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(stmt).all())


ActivityEventRepositoryImpl: ActivityEventRepository = SQLActivityEventRepository()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/codemie/service/activity/test_activity_repository.py -v
```
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/activity/activity_repository.py \
        tests/codemie/service/activity/test_activity_repository.py
git commit -m "EPMCDME-13275: Add ActivityEventRepository with sync and async insert"
```

---

## Task 3: Alembic migration

**Files:**
- Create: `src/external/alembic/versions/<hash>_create_activity_events_table.py`

Note: The migration is handwritten (project convention — autogenerate is not used). The model does not need to be added to `alembic/env.py` because this codebase writes migrations by hand and the service-layer models (`Budget`, `SkillEvent`, `ProjectSpendTracking`) are likewise absent from env.py.

- [ ] **Step 1: Generate the migration file skeleton**

```bash
cd src/external/alembic
python -m alembic revision -m "create_activity_events_table"
```
This creates `versions/<hash>_create_activity_events_table.py`. Open that file and replace its contents with the migration below (substitute `<hash>` with the generated value and set `down_revision = "7ca305066800"`).

- [ ] **Step 2: Write the migration content**

Replace the generated file content with:

```python
"""create_activity_events_table

Revision ID: <hash>
Revises: 7ca305066800
Create Date: 2026-07-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "<hash>"
down_revision: Union[str, None] = "7ca305066800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create activity_events — append-only audit log, domain-extensible via discriminator."""
    op.create_table(
        "activity_events",
        sa.Column("id", sa.VARCHAR(36), nullable=False),
        sa.Column("domain", sa.VARCHAR(64), nullable=False),
        sa.Column("event_type", sa.VARCHAR(128), nullable=False),
        sa.Column("entity_type", sa.VARCHAR(64), nullable=True),
        sa.Column("entity_id", sa.VARCHAR(36), nullable=True),
        sa.Column(
            "actor_id",
            sa.VARCHAR(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_events_entity_type_entity_id"),
        "activity_events",
        ["entity_type", "entity_id"],
        postgresql_where=sa.text("entity_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_activity_events_actor_id_created_at"),
        "activity_events",
        ["actor_id", "created_at"],
        postgresql_where=sa.text("actor_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_activity_events_domain_created_at"),
        "activity_events",
        ["domain", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_events_domain_created_at"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_actor_id_created_at"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_entity_type_entity_id"), table_name="activity_events")
    op.drop_table("activity_events")
```

- [ ] **Step 3: Verify migration syntax**

```bash
python -m alembic check
```
Expected: no errors (or "Target database is not up to date" if DB is available but not migrated — both are fine).

- [ ] **Step 4: Commit**

```bash
git add src/external/alembic/versions/<hash>_create_activity_events_table.py
git commit -m "EPMCDME-13275: Add Alembic migration for activity_events table"
```

---

## Task 4: UserManagementService — event instrumentation

**Files:**
- Modify: `src/codemie/service/user/user_management_service.py`
- Create: `tests/codemie/service/user/test_user_management_service.py`

Three methods are instrumented: `create_local_user`, `update_user`, `deactivate_user`. Each already receives `session: Session`, so the event row is written in the same transaction.

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/service/user/test_user_management_service.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codemie.service.activity.activity_models import ActivityDomain, ActivityEntityType, UserManagementEvent
from codemie.service.user.user_management_service import UserManagementService


def _mock_user(user_id: str = "user-1") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.is_admin = False
    user.is_active = True
    return user


@patch("codemie.service.user.user_management_service.activity_event_repository_impl")
@patch("codemie.service.user.user_management_service.user_repository")
@patch("codemie.service.user.user_management_service.password_service")
def test_create_local_user_emits_user_created_event(mock_pw, mock_repo, mock_activity):
    session = MagicMock()
    mock_repo.exists_by_email.return_value = False
    mock_repo.exists_by_username.return_value = False
    created_user = _mock_user("new-user-id")
    mock_repo.create.return_value = created_user

    UserManagementService.create_local_user(
        session, email="a@b.com", username="auser", password="password123"
    )

    mock_activity.insert.assert_called_once()
    call_args = mock_activity.insert.call_args[0]
    event_dto = call_args[0]
    assert event_dto.domain == ActivityDomain.USER_MANAGEMENT
    assert event_dto.event_type == UserManagementEvent.USER_CREATED
    assert event_dto.entity_type == ActivityEntityType.USER
    assert event_dto.entity_id == "new-user-id"


@patch("codemie.service.user.user_management_service.activity_event_repository_impl")
@patch("codemie.service.user.user_management_service.user_repository")
def test_update_user_emits_user_updated_event(mock_repo, mock_activity):
    session = MagicMock()
    updated_user = _mock_user("user-1")
    mock_repo.update.return_value = updated_user

    UserManagementService.update_user(session, "user-1", actor_user_id="admin-1", name="New Name")

    mock_activity.insert.assert_called_once()
    call_args = mock_activity.insert.call_args[0]
    event_dto = call_args[0]
    assert event_dto.event_type == UserManagementEvent.USER_UPDATED
    assert event_dto.entity_id == "user-1"
    assert event_dto.actor_id == "admin-1"


@patch("codemie.service.user.user_management_service.activity_event_repository_impl")
@patch("codemie.service.user.user_management_service.user_repository")
def test_deactivate_user_emits_user_deactivated_event(mock_repo, mock_activity):
    session = MagicMock()
    user = _mock_user("user-1")
    mock_repo.get_by_id.side_effect = [user, user]  # first check, then return after soft delete

    UserManagementService.deactivate_user(session, "user-1", actor_user_id="admin-1")

    mock_activity.insert.assert_called_once()
    call_args = mock_activity.insert.call_args[0]
    event_dto = call_args[0]
    assert event_dto.event_type == UserManagementEvent.USER_DEACTIVATED
    assert event_dto.entity_id == "user-1"
    assert event_dto.actor_id == "admin-1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/codemie/service/user/test_user_management_service.py -v
```
Expected: 3 tests FAIL (attribute error or assertion — `insert` not called)

- [ ] **Step 3: Add import and emit calls to `user_management_service.py`**

At the top of `src/codemie/service/user/user_management_service.py`, add the import after the existing imports:

```python
from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    ActivityEventCreate,
    UserManagementEvent,
)
from codemie.service.activity.activity_repository import ActivityEventRepositoryImpl as activity_event_repository_impl
```

In `create_local_user`, after `user = user_repository.create(session, user)` and before `return user`:

```python
        activity_event_repository_impl.insert(
            ActivityEventCreate(
                domain=ActivityDomain.USER_MANAGEMENT,
                event_type=UserManagementEvent.USER_CREATED,
                entity_type=ActivityEntityType.USER,
                entity_id=user.id,
                actor_id=actor_user_id if "actor_user_id" in locals() else None,
            ),
            session,
        )
```

Wait — `create_local_user` does not receive an `actor_user_id` parameter. The actor for admin-created users is the admin who called the endpoint, but that ID is not passed to this method. Set `actor_id=None` for this event and note in a follow-up to pass actor context.

```python
        activity_event_repository_impl.insert(
            ActivityEventCreate(
                domain=ActivityDomain.USER_MANAGEMENT,
                event_type=UserManagementEvent.USER_CREATED,
                entity_type=ActivityEntityType.USER,
                entity_id=user.id,
            ),
            session,
        )
        return user
```

In `update_user`, after `if user:` block, after the existing logger.info call:

```python
        if user:
            # ... existing role_detail logging ...
            activity_event_repository_impl.insert(
                ActivityEventCreate(
                    domain=ActivityDomain.USER_MANAGEMENT,
                    event_type=UserManagementEvent.USER_UPDATED,
                    entity_type=ActivityEntityType.USER,
                    entity_id=user_id,
                    actor_id=actor_user_id,
                ),
                session,
            )
```

In `deactivate_user`, after `user_repository.soft_delete(session, user_id)` and after the existing `logger.info` call, before `return user_repository.get_by_id(...)`:

```python
        activity_event_repository_impl.insert(
            ActivityEventCreate(
                domain=ActivityDomain.USER_MANAGEMENT,
                event_type=UserManagementEvent.USER_DEACTIVATED,
                entity_type=ActivityEntityType.USER,
                entity_id=user_id,
                actor_id=actor_user_id,
            ),
            session,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/codemie/service/user/test_user_management_service.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Run existing user management tests to verify no regressions**

```bash
python -m pytest tests/codemie/service/user/ -v
```
Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/codemie/service/user/user_management_service.py \
        tests/codemie/service/user/test_user_management_service.py
git commit -m "EPMCDME-13275: Emit activity events in UserManagementService"
```

---

## Task 5: AuthenticationService + logout router — event instrumentation

**Files:**
- Modify: `src/codemie/service/user/authentication_service.py`
- Modify: `src/codemie/rest_api/routers/local_auth_router.py`
- Modify: `tests/codemie/service/user/test_authentication_service.py`

Login is emitted in `authenticate_and_login` (service level, async). Logout is emitted in the `/logout` router endpoint because there is no dedicated logout service method — token invalidation happens at the router layer.

- [ ] **Step 1: Write failing tests for login event**

Add to `tests/codemie/service/user/test_authentication_service.py` (add after the last existing test class):

```python
class TestActivityEventEmission:
    """Tests that authenticate_and_login emits a user.login event."""

    @pytest.mark.asyncio
    @patch("codemie.service.user.authentication_service.activity_event_repository_impl")
    @patch("codemie.service.user.authentication_service.AuthenticationService.authenticate_local")
    @patch("codemie.service.user.authentication_service.AuthenticationService.update_last_login")
    async def test_authenticate_and_login_emits_login_event(
        self, mock_update_login, mock_authenticate, mock_activity
    ):
        mock_activity.async_insert = AsyncMock()
        user = MagicMock()
        user.id = "user-1"
        user.email = "a@b.com"
        mock_authenticate.return_value = user
        mock_update_login.return_value = True

        with patch("codemie.service.user.authentication_service.AuthenticationService._build_security_user") as mock_build, \
             patch("codemie.service.user.authentication_service.create_access_token") as mock_token, \
             patch("codemie.service.user.authentication_service.Session"):
            mock_build.return_value = MagicMock(id="user-1")
            mock_token.return_value = "token-xyz"
            await AuthenticationService.authenticate_and_login("a@b.com", "pass123")

        mock_activity.async_insert.assert_called_once()
        call_kwargs = mock_activity.async_insert.call_args[0]
        event_dto = call_kwargs[0]
        assert event_dto.event_type == "user.login"
        assert event_dto.entity_id == "user-1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/codemie/service/user/test_authentication_service.py::TestActivityEventEmission -v
```
Expected: FAIL — `async_insert` not called

- [ ] **Step 3: Read `authenticate_and_login` method body**

```bash
grep -n "authenticate_and_login" src/codemie/service/user/authentication_service.py
```
Then read that method to find the right insertion point (after successful login, before return).

- [ ] **Step 4: Add import and login event to `authentication_service.py`**

Add to imports section:
```python
from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    ActivityEventCreate,
    UserManagementEvent,
)
from codemie.service.activity.activity_repository import ActivityEventRepositoryImpl as activity_event_repository_impl
```

In `authenticate_and_login`, after the user is authenticated and before the return statement, add (inside the existing `async with Session(...) as session:` block or use a standalone session if no session context exists):

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.USER_MANAGEMENT,
                event_type=UserManagementEvent.USER_LOGIN,
                entity_type=ActivityEntityType.USER,
                entity_id=user.id,
                actor_id=user.id,  # user logs in as themselves
            ),
            session,
        )
```

- [ ] **Step 5: Add logout event to `/logout` router endpoint in `local_auth_router.py`**

Add to imports in `local_auth_router.py`:
```python
from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    ActivityEventCreate,
    UserManagementEvent,
)
from codemie.service.activity.activity_repository import ActivityEventRepositoryImpl as activity_event_repository_impl
```

In the `logout` endpoint, after token invalidation and before the response, emit the event using a standalone session (consistent with how other routers create short-lived sessions for writes):

```python
@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response, _user: User = Depends(authenticate)):
    # ... existing token invalidation logic ...
    with Session(UserDB.get_engine()) as session:
        activity_event_repository_impl.insert(
            ActivityEventCreate(
                domain=ActivityDomain.USER_MANAGEMENT,
                event_type=UserManagementEvent.USER_LOGOUT,
                entity_type=ActivityEntityType.USER,
                entity_id=_user.id,
                actor_id=_user.id,
            ),
            session,
        )
        session.commit()
    # ... existing return ...
```

- [ ] **Step 6: Run all auth tests**

```bash
python -m pytest tests/codemie/service/user/test_authentication_service.py -v
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/codemie/service/user/authentication_service.py \
        src/codemie/rest_api/routers/local_auth_router.py \
        tests/codemie/service/user/test_authentication_service.py
git commit -m "EPMCDME-13275: Emit activity events for user login and logout"
```

---

## Task 6: BudgetService — event instrumentation

**Files:**
- Modify: `src/codemie/service/budget/budget_service.py`
- Create: `tests/codemie/service/budget/test_budget_service_activity.py`

Three methods: `create_budget`, `update_budget`, `assign_budget_to_user`. All are async with `session: AsyncSession`.

- [ ] **Step 1: Write failing tests**

```python
# tests/codemie/service/budget/test_budget_service_activity.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    BudgetManagementEvent,
)
from codemie.service.budget.budget_service import BudgetService


def _mock_budget(budget_id: str = "budget-1") -> MagicMock:
    b = MagicMock()
    b.budget_id = budget_id
    b.budget_category = "personal"
    return b


@pytest.mark.asyncio
@patch("codemie.service.budget.budget_service.activity_event_repository_impl")
@patch("codemie.service.budget.budget_service.budget_repository")
async def test_create_budget_emits_budget_created_event(mock_budget_repo, mock_activity):
    mock_activity.async_insert = AsyncMock()
    session = AsyncMock()
    mock_budget_repo.get_by_id = AsyncMock(return_value=None)
    created_budget = _mock_budget("bud-1")
    mock_budget_repo.create = AsyncMock(return_value=created_budget)

    data = MagicMock()
    data.budget_id = "bud-1"
    data.budget_category = MagicMock(value="personal")
    data.max_budget = 100.0
    data.soft_budget = 80.0
    data.budget_duration = "30d"

    with patch.object(BudgetService, "_validate_constraints"), \
         patch.object(BudgetService, "_sync_updated_global_budget", new_callable=AsyncMock):
        await BudgetService().create_budget(session, data, actor_id="admin-1")

    mock_activity.async_insert.assert_called_once()
    call_args = mock_activity.async_insert.call_args[0]
    event_dto = call_args[0]
    assert event_dto.domain == ActivityDomain.BUDGET_MANAGEMENT
    assert event_dto.event_type == BudgetManagementEvent.BUDGET_CREATED
    assert event_dto.entity_type == ActivityEntityType.BUDGET
    assert event_dto.entity_id == "bud-1"
    assert event_dto.actor_id == "admin-1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/codemie/service/budget/test_budget_service_activity.py::test_create_budget_emits_budget_created_event -v
```
Expected: FAIL — `async_insert` not called

- [ ] **Step 3: Add import and event calls to `budget_service.py`**

Add to imports:
```python
from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    ActivityEventCreate,
    BudgetManagementEvent,
)
from codemie.service.activity.activity_repository import ActivityEventRepositoryImpl as activity_event_repository_impl
```

In `create_budget`, after the budget is persisted (after `await budget_repository.create(...)`) and before `return budget`:

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.BUDGET_MANAGEMENT,
                event_type=BudgetManagementEvent.BUDGET_CREATED,
                entity_type=ActivityEntityType.BUDGET,
                entity_id=budget.budget_id,
                actor_id=actor_id,
            ),
            session,
        )
```

In `update_budget`, after the budget is updated in DB and before `return`, add:

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.BUDGET_MANAGEMENT,
                event_type=BudgetManagementEvent.BUDGET_UPDATED,
                entity_type=ActivityEntityType.BUDGET,
                entity_id=budget_id,
                actor_id=actor_id,
            ),
            session,
        )
```

In `assign_budget_to_user`, after the assignment is persisted, add:

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.BUDGET_MANAGEMENT,
                event_type=BudgetManagementEvent.USER_BUDGET_ASSIGNED,
                entity_type=ActivityEntityType.USER_BUDGET_ASSIGNMENT,
                entity_id=user_id,
                actor_id=actor_id if "actor_id" in locals() else None,
                attributes={"budget_id": budget_id, "category": category.value},
            ),
            session,
        )
```

- [ ] **Step 4: Run all budget tests**

```bash
python -m pytest tests/codemie/service/budget/ -v
```
Expected: all existing and new tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/budget/budget_service.py \
        tests/codemie/service/budget/test_budget_service_activity.py
git commit -m "EPMCDME-13275: Emit activity events in BudgetService"
```

---

## Task 7: ProjectBudgetService — event instrumentation

**Files:**
- Modify: `src/codemie/service/budget/project_budget_service.py`
- (tests inline with existing budget tests)

Two methods: `create_project_budget` and `delete_project_budget`. Both async with `session: AsyncSession`.

- [ ] **Step 1: Read the methods to find insertion points**

```bash
grep -n "def create_project_budget\|def delete_project_budget" \
  src/codemie/service/budget/project_budget_service.py
```
Read each method body to identify the point after the DB write succeeds and before `return`.

- [ ] **Step 2: Write failing tests**

Add to `tests/codemie/service/budget/test_budget_service_activity.py`:

```python
@pytest.mark.asyncio
@patch("codemie.service.budget.project_budget_service.activity_event_repository_impl")
async def test_create_project_budget_emits_project_budget_created_event(mock_activity):
    mock_activity.async_insert = AsyncMock()

    from codemie.service.budget.project_budget_service import ProjectBudgetService

    service = ProjectBudgetService()
    session = AsyncMock()

    data = MagicMock()
    data.project_name = "proj-1"
    data.budget_id = "bud-1"

    with patch.object(service, "_ensure_project_exists", new_callable=AsyncMock), \
         patch.object(service, "_upsert_child_budget", new_callable=AsyncMock), \
         patch.object(service, "_sync_created_project_budget", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = MagicMock(budget_id="proj-bud-1")
        await service.create_project_budget(session, data, actor_id="admin-1")

    mock_activity.async_insert.assert_called()
    event_dto = mock_activity.async_insert.call_args[0][0]
    assert event_dto.event_type == BudgetManagementEvent.PROJECT_BUDGET_CREATED
    assert event_dto.domain == ActivityDomain.BUDGET_MANAGEMENT
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/codemie/service/budget/test_budget_service_activity.py::test_create_project_budget_emits_project_budget_created_event -v
```
Expected: FAIL — `async_insert` not called

- [ ] **Step 4: Add import and event calls to `project_budget_service.py`**

Add to imports:
```python
from codemie.service.activity.activity_models import (
    ActivityDomain,
    ActivityEntityType,
    ActivityEventCreate,
    BudgetManagementEvent,
)
from codemie.service.activity.activity_repository import ActivityEventRepositoryImpl as activity_event_repository_impl
```

In `create_project_budget`, after the project budget is persisted, add:

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.BUDGET_MANAGEMENT,
                event_type=BudgetManagementEvent.PROJECT_BUDGET_CREATED,
                entity_type=ActivityEntityType.PROJECT_BUDGET_GROUP,
                entity_id=project_budget.budget_id,
                actor_id=actor_id if "actor_id" in locals() else None,
                attributes={"project_name": data.project_name},
            ),
            session,
        )
```

In `delete_project_budget`, after the rows are soft-deleted and before `return`, add:

```python
        await activity_event_repository_impl.async_insert(
            ActivityEventCreate(
                domain=ActivityDomain.BUDGET_MANAGEMENT,
                event_type=BudgetManagementEvent.PROJECT_BUDGET_DELETED,
                entity_type=ActivityEntityType.PROJECT_BUDGET_GROUP,
                entity_id=budget_id,
                actor_id=actor_id if "actor_id" in locals() else None,
            ),
            session,
        )
```

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/codemie/service/budget/ tests/codemie/service/user/ tests/codemie/service/activity/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Run quality gates**

```bash
make lint
```
Expected: no errors

- [ ] **Step 7: Final commit**

```bash
git add src/codemie/service/budget/project_budget_service.py \
        tests/codemie/service/budget/test_budget_service_activity.py
git commit -m "EPMCDME-13275: Emit activity events in ProjectBudgetService"
```

---

## Scope Notes

- **`USER_REACTIVATED`** was dropped — `UserManagementService` explicitly raises "Reactivation is not supported."
- **Logout event** is emitted at the router layer (`local_auth_router.py`) not in a service method, because logout is token-only and has no service-layer method.
- **`create_local_user` actor_id** is `None` because the method signature does not receive the calling admin's ID. This is a known gap — a follow-up can add `actor_user_id` to the method signature.
- **`assign_budget_to_user` actor_id** — read the method signature at implementation time and pass it if available; otherwise pass `None` with an `attributes` field for traceability.
- **`update_budget` actor_id** — check if `actor_id` is a parameter; the method signature was not fully read. Adjust at implementation time.
