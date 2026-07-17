# Activity Events Read API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose two maintainer-only REST endpoints — a paginated filterable event list with actor enrichment, and a data-driven filter-options endpoint — on top of the existing `activity_events` table.

**Architecture:** New `ActivityEventService` wraps a new `find_all` repository method that does a `LEFT JOIN users` in a single query. A second `get_filter_options` service method returns distinct field values via three `SELECT DISTINCT` queries. Both endpoints live in a new `activity_events_router` under `/v1/admin/activity-events` and are gated by `maintainer_access_only`.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy core (`session.execute`), Pydantic v2, pytest + `unittest.mock`

---

## File Map

| File | Action |
|---|---|
| `src/codemie/rest_api/models/activity_event.py` | Create — `ActivityEventListItem`, `ActivityEventFilterOptions` |
| `src/codemie/service/activity/activity_repository.py` | Edit — `ActivityEventRow` dataclass, `find_all`, `get_distinct_domains/event_types/entity_types` on ABC + impl |
| `src/codemie/service/activity/activity_event_service.py` | Create — `ActivityEventService`, `activity_event_service` singleton |
| `src/codemie/rest_api/routers/activity_events_router.py` | Create — `GET /filter-options`, `GET ""` |
| `src/codemie/rest_api/main.py` | Edit — register new router |
| `tests/codemie/rest_api/models/test_activity_event_models.py` | Create — model validation tests |
| `tests/codemie/service/activity/test_activity_repository.py` | Edit — add `find_all` + distinct tests |
| `tests/codemie/service/activity/test_activity_event_service.py` | Create — service unit tests |
| `tests/codemie/rest_api/routers/test_activity_events_router.py` | Create — handler unit tests |

---

## Task 1: REST Response Models

**Files:**
- Create: `src/codemie/rest_api/models/activity_event.py`
- Create: `tests/codemie/rest_api/models/test_activity_event_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/codemie/rest_api/models/test_activity_event_models.py
from datetime import datetime, timezone
from codemie.rest_api.models.activity_event import ActivityEventListItem, ActivityEventFilterOptions


class TestActivityEventListItem:
    def test_all_fields_present(self):
        item = ActivityEventListItem(
            id="evt-1",
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id="u-1",
            actor_id="a-1",
            actor_email="admin@test.com",
            actor_name="Admin",
            attributes={"key": "val"},
            created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        assert item.id == "evt-1"
        assert item.actor_email == "admin@test.com"

    def test_optional_fields_default_to_none(self):
        item = ActivityEventListItem(
            id="evt-2",
            domain="budget_management",
            event_type="budget.created",
            created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        assert item.entity_type is None
        assert item.actor_id is None
        assert item.actor_email is None
        assert item.actor_name is None
        assert item.attributes is None


class TestActivityEventFilterOptions:
    def test_all_lists_populated(self):
        opts = ActivityEventFilterOptions(
            domains=["budget_management", "user_management"],
            event_types=["budget.created", "user.created"],
            entity_types=["budget", "user"],
        )
        assert "user_management" in opts.domains
        assert len(opts.event_types) == 2

    def test_empty_lists_valid(self):
        opts = ActivityEventFilterOptions(domains=[], event_types=[], entity_types=[])
        assert opts.domains == []
```

- [ ] **Step 2: Run tests — expect ImportError (file doesn't exist yet)**

```bash
cd /path/to/repo
poetry run pytest tests/codemie/rest_api/models/test_activity_event_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'codemie.rest_api.models.activity_event'`

- [ ] **Step 3: Create the models file**

```python
# src/codemie/rest_api/models/activity_event.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class ActivityEventListItem(BaseModel):
    id: str
    domain: str
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    created_at: datetime


class ActivityEventFilterOptions(BaseModel):
    domains: list[str]
    event_types: list[str]
    entity_types: list[str]
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
poetry run pytest tests/codemie/rest_api/models/test_activity_event_models.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/codemie/rest_api/models/activity_event.py \
        tests/codemie/rest_api/models/test_activity_event_models.py
git commit -m "feat: add ActivityEventListItem and ActivityEventFilterOptions REST models"
```

---

## Task 2: Repository `find_all` and Distinct Methods

**Files:**
- Modify: `src/codemie/service/activity/activity_repository.py`
- Modify: `tests/codemie/service/activity/test_activity_repository.py`

- [ ] **Step 1: Write the failing tests — append to the existing test file**

Open `tests/codemie/service/activity/test_activity_repository.py` and add the following at the end (keep all existing tests):

```python
# --- new imports needed at top of file ---
# from codemie.service.activity.activity_repository import ActivityEventRow
# (add to the existing import from activity_repository)


class TestFindAll:
    def _make_row(self, event_id="evt-1"):
        from codemie.service.activity.activity_models import ActivityEvent
        from datetime import datetime, timezone
        event = ActivityEvent(
            id=event_id,
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id="u-1",
            actor_id="a-1",
            created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        return (event, "admin@test.com", "Admin User")

    def test_find_all_returns_enriched_rows_and_count(self):
        session = MagicMock()
        row = self._make_row()
        # First execute() call = count query, second = data query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_result.all.return_value = [row]
        session.execute.side_effect = [count_result, data_result]

        results, total = _repo().find_all(limit=10, offset=0, session=session)

        assert total == 1
        assert len(results) == 1
        r = results[0]
        assert r.id == "evt-1"
        assert r.actor_email == "admin@test.com"
        assert r.actor_name == "Admin User"

    def test_find_all_with_no_results_returns_empty_list(self):
        session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        results, total = _repo().find_all(limit=10, offset=0, session=session)

        assert total == 0
        assert results == []

    def test_find_all_filters_are_passed_to_query(self):
        session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []
        session.execute.side_effect = [count_result, data_result]

        _repo().find_all(
            actor_id="a-1",
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id="u-1",
            limit=5,
            offset=0,
            session=session,
        )

        assert session.execute.call_count == 2

    def test_find_all_actor_email_is_none_when_actor_id_is_none(self):
        from codemie.service.activity.activity_models import ActivityEvent
        from datetime import datetime, timezone
        event = ActivityEvent(
            id="evt-2",
            domain="budget_management",
            event_type="budget.created",
            created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_result.all.return_value = [(event, None, None)]
        session.execute.side_effect = [count_result, data_result]

        results, _ = _repo().find_all(limit=10, offset=0, session=session)

        assert results[0].actor_email is None
        assert results[0].actor_name is None


class TestGetDistinctValues:
    def test_get_distinct_domains_returns_sorted_strings(self):
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            ("budget_management",),
            ("user_management",),
        ]
        result = _repo().get_distinct_domains(session)
        assert result == ["budget_management", "user_management"]

    def test_get_distinct_event_types_returns_sorted_strings(self):
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            ("budget.created",),
            ("user.created",),
            ("user.login",),
        ]
        result = _repo().get_distinct_event_types(session)
        assert result == ["budget.created", "user.created", "user.login"]

    def test_get_distinct_entity_types_returns_sorted_strings(self):
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            ("budget",),
            ("user",),
        ]
        result = _repo().get_distinct_entity_types(session)
        assert result == ["budget", "user"]

    def test_get_distinct_domains_returns_empty_list_when_table_empty(self):
        session = MagicMock()
        session.execute.return_value.all.return_value = []
        result = _repo().get_distinct_domains(session)
        assert result == []
```

- [ ] **Step 2: Run new tests — expect failures (methods not yet defined)**

```bash
poetry run pytest tests/codemie/service/activity/test_activity_repository.py::TestFindAll \
                  tests/codemie/service/activity/test_activity_repository.py::TestGetDistinctValues -v
```

Expected: `AttributeError: 'SQLActivityEventRepository' object has no attribute 'find_all'`

- [ ] **Step 3: Add `ActivityEventRow` dataclass and new abstract methods to repository**

Edit `src/codemie/service/activity/activity_repository.py`. Add these imports at the top (after the existing ones):

```python
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session as SASession
```

Add `ActivityEventRow` dataclass directly after the module docstring and before `class ActivityEventRepository`:

```python
@dataclass
class ActivityEventRow:
    id: str
    domain: str
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    actor_id: Optional[str]
    actor_email: Optional[str]
    actor_name: Optional[str]
    attributes: Optional[Dict[str, Any]]
    created_at: datetime
```

Add these abstract methods to `ActivityEventRepository` (after existing abstractmethods):

```python
@abstractmethod
def find_all(
    self,
    *,
    actor_id: Optional[str] = None,
    domain: Optional[str] = None,
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    sort_dir: str = "desc",
    limit: int,
    offset: int,
    session: Session,
) -> tuple[list[ActivityEventRow], int]:
    """Return enriched events matching filters plus total count for pagination."""

@abstractmethod
def get_distinct_domains(self, session: Session) -> list[str]:
    """Return sorted non-null distinct domain values."""

@abstractmethod
def get_distinct_event_types(self, session: Session) -> list[str]:
    """Return sorted non-null distinct event_type values."""

@abstractmethod
def get_distinct_entity_types(self, session: Session) -> list[str]:
    """Return sorted non-null distinct entity_type values."""
```

- [ ] **Step 4: Implement `find_all` and distinct methods on `SQLActivityEventRepository`**

Add these methods to `SQLActivityEventRepository` (after existing methods):

```python
def find_all(
    self,
    *,
    actor_id: Optional[str] = None,
    domain: Optional[str] = None,
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    sort_dir: str = "desc",
    limit: int,
    offset: int,
    session: Session,
) -> tuple[list[ActivityEventRow], int]:
    from codemie.rest_api.models.user_management import UserDB

    conditions = []
    if actor_id is not None:
        conditions.append(ActivityEvent.actor_id == actor_id)
    if domain is not None:
        conditions.append(ActivityEvent.domain == domain)
    if event_type is not None:
        conditions.append(ActivityEvent.event_type == event_type)
    if entity_type is not None:
        conditions.append(ActivityEvent.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(ActivityEvent.entity_id == entity_id)
    if from_dt is not None:
        conditions.append(ActivityEvent.created_at >= from_dt)
    if to_dt is not None:
        conditions.append(ActivityEvent.created_at <= to_dt)

    count_stmt = select(func.count(ActivityEvent.id))
    for c in conditions:
        count_stmt = count_stmt.where(c)
    total: int = session.execute(count_stmt).scalar_one()

    order = desc(ActivityEvent.created_at) if sort_dir == "desc" else asc(ActivityEvent.created_at)
    data_stmt = (
        select(
            ActivityEvent,
            UserDB.email.label("actor_email"),
            UserDB.name.label("actor_name"),
        )
        .outerjoin(UserDB, ActivityEvent.actor_id == UserDB.id)
    )
    for c in conditions:
        data_stmt = data_stmt.where(c)
    data_stmt = data_stmt.order_by(order).offset(offset).limit(limit)

    rows = session.execute(data_stmt).all()
    result = [
        ActivityEventRow(
            id=event.id,
            domain=event.domain,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_id=event.actor_id,
            actor_email=actor_email,
            actor_name=actor_name,
            attributes=event.attributes,
            created_at=event.created_at,
        )
        for event, actor_email, actor_name in rows
    ]
    return result, total

def get_distinct_domains(self, session: Session) -> list[str]:
    stmt = (
        select(ActivityEvent.domain)
        .distinct()
        .where(ActivityEvent.domain.is_not(None))
        .order_by(ActivityEvent.domain)
    )
    return [r for (r,) in session.execute(stmt).all()]

def get_distinct_event_types(self, session: Session) -> list[str]:
    stmt = (
        select(ActivityEvent.event_type)
        .distinct()
        .where(ActivityEvent.event_type.is_not(None))
        .order_by(ActivityEvent.event_type)
    )
    return [r for (r,) in session.execute(stmt).all()]

def get_distinct_entity_types(self, session: Session) -> list[str]:
    stmt = (
        select(ActivityEvent.entity_type)
        .distinct()
        .where(ActivityEvent.entity_type.is_not(None))
        .order_by(ActivityEvent.entity_type)
    )
    return [r for (r,) in session.execute(stmt).all()]
```

- [ ] **Step 5: Run all repository tests — expect PASS**

```bash
poetry run pytest tests/codemie/service/activity/test_activity_repository.py -v
```

Expected: all tests PASSED (existing 6 + new 8 = 14 total)

- [ ] **Step 6: Commit**

```bash
git add src/codemie/service/activity/activity_repository.py \
        tests/codemie/service/activity/test_activity_repository.py
git commit -m "feat: add find_all and get_distinct_* methods to ActivityEventRepository"
```

---

## Task 3: `ActivityEventService`

**Files:**
- Create: `src/codemie/service/activity/activity_event_service.py`
- Create: `tests/codemie/service/activity/test_activity_event_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/codemie/service/activity/test_activity_event_service.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from codemie.rest_api.models.activity_event import ActivityEventListItem, ActivityEventFilterOptions
from codemie.service.activity.activity_event_service import ActivityEventService
from codemie.service.activity.activity_repository import ActivityEventRow


def _row(**kwargs) -> ActivityEventRow:
    defaults = dict(
        id="evt-1",
        domain="user_management",
        event_type="user.created",
        entity_type="user",
        entity_id="u-1",
        actor_id="a-1",
        actor_email="admin@test.com",
        actor_name="Admin",
        attributes=None,
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return ActivityEventRow(**defaults)


class TestListEvents:
    @patch("codemie.service.activity.activity_event_service.activity_event_repository")
    @patch("codemie.service.activity.activity_event_service.Session")
    @patch("codemie.service.activity.activity_event_service.PostgresClient")
    def test_returns_paginated_items_and_total(self, mock_pg, mock_session_cls, mock_repo):
        mock_repo.find_all.return_value = ([_row()], 1)
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        svc = ActivityEventService()
        items, total = svc.list_events(limit=10, offset=0)

        assert total == 1
        assert len(items) == 1
        assert isinstance(items[0], ActivityEventListItem)
        assert items[0].id == "evt-1"
        assert items[0].actor_email == "admin@test.com"

    @patch("codemie.service.activity.activity_event_service.activity_event_repository")
    @patch("codemie.service.activity.activity_event_service.Session")
    @patch("codemie.service.activity.activity_event_service.PostgresClient")
    def test_passes_all_filters_to_repository(self, mock_pg, mock_session_cls, mock_repo):
        mock_repo.find_all.return_value = ([], 0)
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        from datetime import datetime, timezone
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 12, 31, tzinfo=timezone.utc)

        svc = ActivityEventService()
        svc.list_events(
            actor_id="a-1",
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id="u-1",
            from_dt=from_dt,
            to_dt=to_dt,
            sort_dir="asc",
            limit=25,
            offset=50,
        )

        call_kwargs = mock_repo.find_all.call_args.kwargs
        assert call_kwargs["actor_id"] == "a-1"
        assert call_kwargs["domain"] == "user_management"
        assert call_kwargs["sort_dir"] == "asc"
        assert call_kwargs["limit"] == 25
        assert call_kwargs["offset"] == 50

    @patch("codemie.service.activity.activity_event_service.activity_event_repository")
    @patch("codemie.service.activity.activity_event_service.Session")
    @patch("codemie.service.activity.activity_event_service.PostgresClient")
    def test_returns_empty_list_when_no_events(self, mock_pg, mock_session_cls, mock_repo):
        mock_repo.find_all.return_value = ([], 0)
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        svc = ActivityEventService()
        items, total = svc.list_events(limit=10, offset=0)

        assert items == []
        assert total == 0


class TestGetFilterOptions:
    @patch("codemie.service.activity.activity_event_service.activity_event_repository")
    @patch("codemie.service.activity.activity_event_service.Session")
    @patch("codemie.service.activity.activity_event_service.PostgresClient")
    def test_returns_distinct_values_from_repository(self, mock_pg, mock_session_cls, mock_repo):
        mock_repo.get_distinct_domains.return_value = ["budget_management", "user_management"]
        mock_repo.get_distinct_event_types.return_value = ["budget.created", "user.created"]
        mock_repo.get_distinct_entity_types.return_value = ["budget", "user"]
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        svc = ActivityEventService()
        opts = svc.get_filter_options()

        assert isinstance(opts, ActivityEventFilterOptions)
        assert opts.domains == ["budget_management", "user_management"]
        assert opts.event_types == ["budget.created", "user.created"]
        assert opts.entity_types == ["budget", "user"]

    @patch("codemie.service.activity.activity_event_service.activity_event_repository")
    @patch("codemie.service.activity.activity_event_service.Session")
    @patch("codemie.service.activity.activity_event_service.PostgresClient")
    def test_returns_empty_lists_when_table_has_no_events(self, mock_pg, mock_session_cls, mock_repo):
        mock_repo.get_distinct_domains.return_value = []
        mock_repo.get_distinct_event_types.return_value = []
        mock_repo.get_distinct_entity_types.return_value = []
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        svc = ActivityEventService()
        opts = svc.get_filter_options()

        assert opts.domains == []
        assert opts.event_types == []
        assert opts.entity_types == []
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
poetry run pytest tests/codemie/service/activity/test_activity_event_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'codemie.service.activity.activity_event_service'`

- [ ] **Step 3: Create the service**

```python
# src/codemie/service/activity/activity_event_service.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from codemie.clients.postgres import PostgresClient
from codemie.rest_api.models.activity_event import ActivityEventFilterOptions, ActivityEventListItem
from codemie.service.activity.activity_repository import activity_event_repository


class ActivityEventService:
    def list_events(
        self,
        *,
        actor_id: Optional[str] = None,
        domain: Optional[str] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityEventListItem], int]:
        with Session(PostgresClient.get_engine()) as session:
            rows, total = activity_event_repository.find_all(
                actor_id=actor_id,
                domain=domain,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                from_dt=from_dt,
                to_dt=to_dt,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
                session=session,
            )
        return [
            ActivityEventListItem(
                id=r.id,
                domain=r.domain,
                event_type=r.event_type,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                actor_id=r.actor_id,
                actor_email=r.actor_email,
                actor_name=r.actor_name,
                attributes=r.attributes,
                created_at=r.created_at,
            )
            for r in rows
        ], total

    def get_filter_options(self) -> ActivityEventFilterOptions:
        with Session(PostgresClient.get_engine()) as session:
            return ActivityEventFilterOptions(
                domains=activity_event_repository.get_distinct_domains(session),
                event_types=activity_event_repository.get_distinct_event_types(session),
                entity_types=activity_event_repository.get_distinct_entity_types(session),
            )


activity_event_service = ActivityEventService()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
poetry run pytest tests/codemie/service/activity/test_activity_event_service.py -v
```

Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/codemie/service/activity/activity_event_service.py \
        tests/codemie/service/activity/test_activity_event_service.py
git commit -m "feat: add ActivityEventService with list_events and get_filter_options"
```

---

## Task 4: Router and `main.py` Registration

**Files:**
- Create: `src/codemie/rest_api/routers/activity_events_router.py`
- Modify: `src/codemie/rest_api/main.py`
- Create: `tests/codemie/rest_api/routers/test_activity_events_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/codemie/rest_api/routers/test_activity_events_router.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.activity_event import ActivityEventFilterOptions, ActivityEventListItem
from codemie.rest_api.routers.activity_events_router import (
    get_filter_options,
    list_activity_events,
)
from codemie.rest_api.security.user import User


def _maintainer() -> User:
    return User(
        id="m-1",
        username="maintainer",
        email="maintainer@test.com",
        is_admin=True,
        is_maintainer=True,
    )


def _item() -> ActivityEventListItem:
    return ActivityEventListItem(
        id="evt-1",
        domain="user_management",
        event_type="user.created",
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )


class TestListActivityEvents:
    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_returns_paginated_response(self, mock_svc):
        mock_svc.list_events.return_value = ([_item()], 1)

        response = list_activity_events(
            actor_id=None, domain=None, event_type=None,
            entity_type=None, entity_id=None,
            from_=None, to=None, sort_dir="desc",
            limit=50, offset=0,
            _=None,
        )

        assert response.pagination.total == 1
        assert response.pagination.per_page == 50
        assert response.pagination.page == 0
        assert len(response.data) == 1
        assert response.data[0].id == "evt-1"

    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_passes_filters_to_service(self, mock_svc):
        mock_svc.list_events.return_value = ([], 0)

        list_activity_events(
            actor_id="a-1",
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id="u-1",
            from_=None, to=None,
            sort_dir="asc",
            limit=25, offset=100,
            _=None,
        )

        call_kwargs = mock_svc.list_events.call_args.kwargs
        assert call_kwargs["actor_id"] == "a-1"
        assert call_kwargs["domain"] == "user_management"
        assert call_kwargs["sort_dir"] == "asc"
        assert call_kwargs["limit"] == 25
        assert call_kwargs["offset"] == 100

    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_wraps_unexpected_exceptions_in_http_500(self, mock_svc):
        mock_svc.list_events.side_effect = RuntimeError("db error")

        with pytest.raises(ExtendedHTTPException) as exc_info:
            list_activity_events(
                actor_id=None, domain=None, event_type=None,
                entity_type=None, entity_id=None,
                from_=None, to=None, sort_dir="desc",
                limit=50, offset=0,
                _=None,
            )

        assert exc_info.value.code == 500

    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_propagates_extended_http_exceptions(self, mock_svc):
        original = ExtendedHTTPException(code=403, message="forbidden")
        mock_svc.list_events.side_effect = original

        with pytest.raises(ExtendedHTTPException) as exc_info:
            list_activity_events(
                actor_id=None, domain=None, event_type=None,
                entity_type=None, entity_id=None,
                from_=None, to=None, sort_dir="desc",
                limit=50, offset=0,
                _=None,
            )

        assert exc_info.value is original

    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_pagination_pages_calculated_correctly(self, mock_svc):
        items = [_item() for _ in range(10)]
        mock_svc.list_events.return_value = (items, 47)

        response = list_activity_events(
            actor_id=None, domain=None, event_type=None,
            entity_type=None, entity_id=None,
            from_=None, to=None, sort_dir="desc",
            limit=10, offset=20,
            _=None,
        )

        assert response.pagination.total == 47
        assert response.pagination.pages == 5    # ceil(47/10)
        assert response.pagination.page == 2     # offset(20) // limit(10)


class TestGetFilterOptions:
    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_returns_filter_options_from_service(self, mock_svc):
        mock_svc.get_filter_options.return_value = ActivityEventFilterOptions(
            domains=["user_management"],
            event_types=["user.created"],
            entity_types=["user"],
        )

        response = get_filter_options(_=None)

        assert response.domains == ["user_management"]
        assert response.event_types == ["user.created"]
        assert response.entity_types == ["user"]

    @patch("codemie.rest_api.routers.activity_events_router.activity_event_service")
    def test_wraps_unexpected_exception_in_http_500(self, mock_svc):
        mock_svc.get_filter_options.side_effect = RuntimeError("db error")

        with pytest.raises(ExtendedHTTPException) as exc_info:
            get_filter_options(_=None)

        assert exc_info.value.code == 500
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
poetry run pytest tests/codemie/rest_api/routers/test_activity_events_router.py -v
```

Expected: `ImportError: cannot import name 'get_filter_options' from 'codemie.rest_api.routers.activity_events_router'`

- [ ] **Step 3: Create the router**

```python
# src/codemie/rest_api/routers/activity_events_router.py
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.activity_event import ActivityEventFilterOptions, ActivityEventListItem
from codemie.rest_api.models.base import PaginatedListResponse, PaginationData
from codemie.rest_api.security.authentication import authenticate, maintainer_access_only
from codemie.service.activity.activity_event_service import activity_event_service


router = APIRouter(
    tags=["activity-events"],
    prefix="/v1/admin/activity-events",
    dependencies=[Depends(authenticate)],
)


@router.get("/filter-options", response_model=ActivityEventFilterOptions)
def get_filter_options(
    _: None = Depends(maintainer_access_only),
) -> ActivityEventFilterOptions:
    try:
        return activity_event_service.get_filter_options()
    except ExtendedHTTPException:
        raise
    except Exception as exc:
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve filter options",
            details=f"error={exc}",
        ) from exc


@router.get("", response_model=PaginatedListResponse[ActivityEventListItem])
def list_activity_events(
    actor_id: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: None = Depends(maintainer_access_only),
) -> PaginatedListResponse[ActivityEventListItem]:
    try:
        items, total = activity_event_service.list_events(
            actor_id=actor_id,
            domain=domain,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            from_dt=from_,
            to_dt=to,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        pagination = PaginationData(
            page=offset // limit if limit else 0,
            per_page=limit,
            total=total,
            pages=math.ceil(total / limit) if limit else 0,
        )
        return PaginatedListResponse(data=items, pagination=pagination)
    except ExtendedHTTPException:
        raise
    except Exception as exc:
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve activity events",
            details=f"error={exc}",
        ) from exc
```

- [ ] **Step 4: Run router tests — expect PASS**

```bash
poetry run pytest tests/codemie/rest_api/routers/test_activity_events_router.py -v
```

Expected: 7 tests PASSED

- [ ] **Step 5: Register router in `main.py`**

Find the import block near the other admin router imports (around line 99–103 in main.py, where `user_management_router` is imported):

```python
# Add this import alongside the other admin router imports:
from codemie.rest_api.routers import activity_events_router
```

Find the `app.include_router(user_management_router.router)` line and add immediately after it:

```python
app.include_router(activity_events_router.router)
```

- [ ] **Step 6: Run the full activity test suite to confirm nothing broken**

```bash
poetry run pytest tests/codemie/service/activity/ \
                  tests/codemie/rest_api/models/test_activity_event_models.py \
                  tests/codemie/rest_api/routers/test_activity_events_router.py -v
```

Expected: all tests PASSED

- [ ] **Step 7: Run ruff**

```bash
make ruff
```

Expected: no errors. Common issues to watch for:
- `Literal` needs to be imported from `typing` (not `typing_extensions`)
- Unused imports
- Line length violations in long `select(...)` chains

- [ ] **Step 8: Run full test suite**

```bash
make test
```

Expected: same pass/fail ratio as before this change (the one pre-existing failure on `TestLoadUserForAuth::test_load_user_for_auth_found` is a known pre-existing failure unrelated to this work).

- [ ] **Step 9: Commit**

```bash
git add src/codemie/rest_api/routers/activity_events_router.py \
        src/codemie/rest_api/main.py \
        tests/codemie/rest_api/routers/test_activity_events_router.py
git commit -m "feat: add activity events read API endpoints for maintainers"
```
