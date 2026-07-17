# Activity Events Read API — Design Spec

**Ticket:** EPMCDME-13275 (extension)
**Date:** 2026-07-15
**Status:** Approved

---

## 1. Goal

Expose two maintainer-only REST endpoints that allow the UI to display the `activity_events` audit log:

1. `GET /v1/admin/activity-events` — paginated, filterable, sortable event list with enriched actor info.
2. `GET /v1/admin/activity-events/filter-options` — distinct values for each filter dropdown. Adding a new event type to the backend automatically surfaces it in the UI with no frontend change.

---

## 2. Auth

Both endpoints require:
- `Depends(authenticate)` — standard session auth.
- `Depends(maintainer_access_only)` — same dependency already used by budget endpoints in `user_management_router.py`. Returns 403 for non-maintainers.

---

## 3. Endpoints

### 3.1 `GET /v1/admin/activity-events`

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `actor_id` | `str` | — | Filter by actor UUID |
| `domain` | `str` | — | Filter by domain string (e.g. `user_management`) |
| `event_type` | `str` | — | Filter by event type string (e.g. `user.created`) |
| `entity_type` | `str` | — | Filter by entity type string (e.g. `user`) |
| `entity_id` | `str` | — | Filter by entity UUID string |
| `from` | `datetime` | — | Inclusive lower bound on `created_at` |
| `to` | `datetime` | — | Inclusive upper bound on `created_at` |
| `sort_dir` | `"asc"` \| `"desc"` | `"desc"` | Sort direction on `created_at` |
| `limit` | `int` 1–1000 | `50` | Page size |
| `offset` | `int` ≥ 0 | `0` | Page offset |

All filters are optional and combinable. Omitting a filter means "no restriction on that field."

**Response:** `PaginatedListResponse[ActivityEventListItem]`

```python
class ActivityEventListItem(BaseModel):
    id: str
    domain: str
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    actor_id: Optional[str]
    actor_email: Optional[str]   # from LEFT JOIN users; null if actor_id is null or user deleted
    actor_name: Optional[str]    # from LEFT JOIN users; null if no name on record
    attributes: Optional[Dict[str, Any]]
    created_at: datetime
```

### 3.2 `GET /v1/admin/activity-events/filter-options`

No query parameters.

**Response:** `ActivityEventFilterOptions`

```python
class ActivityEventFilterOptions(BaseModel):
    domains: list[str]       # sorted, non-null distinct values of activity_events.domain
    event_types: list[str]   # sorted, non-null distinct values of activity_events.event_type
    entity_types: list[str]  # sorted, non-null distinct values of activity_events.entity_type
```

Backed by three `SELECT DISTINCT ... ORDER BY` queries. When a new domain or event type is first written to the DB, the next call to this endpoint returns the new value automatically.

---

## 4. Repository Changes

**File:** `src/codemie/service/activity/activity_repository.py`

### 4.1 `ActivityEventRow` dataclass

A lightweight struct returned by `find_all`. Defined at module level in `activity_repository.py`.

```python
from dataclasses import dataclass

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

### 4.2 New abstract methods on `ActivityEventRepository`

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
    """Return enriched events matching all supplied filters plus total count."""

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

### 4.3 `SQLActivityEventRepository` implementation

**`find_all`** builds the query:

```python
from sqlalchemy import func, asc, desc
from codemie.rest_api.models.user_management import UserDB

def find_all(self, *, actor_id, domain, event_type, entity_type, entity_id,
             from_dt, to_dt, sort_dir, limit, offset, session):
    stmt = (
        select(
            ActivityEvent,
            UserDB.email.label("actor_email"),
            UserDB.name.label("actor_name"),
        )
        .outerjoin(UserDB, ActivityEvent.actor_id == UserDB.id)
    )
    if actor_id is not None:
        stmt = stmt.where(ActivityEvent.actor_id == actor_id)
    if domain is not None:
        stmt = stmt.where(ActivityEvent.domain == domain)
    if event_type is not None:
        stmt = stmt.where(ActivityEvent.event_type == event_type)
    if entity_type is not None:
        stmt = stmt.where(ActivityEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ActivityEvent.entity_id == entity_id)
    if from_dt is not None:
        stmt = stmt.where(ActivityEvent.created_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(ActivityEvent.created_at <= to_dt)

    order = desc(ActivityEvent.created_at) if sort_dir == "desc" else asc(ActivityEvent.created_at)
    stmt = stmt.order_by(order)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.exec(count_stmt).one()

    rows = session.exec(stmt.offset(offset).limit(limit)).all()
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
```

**Distinct methods** — one implementation pattern, three methods:

```python
def get_distinct_domains(self, session: Session) -> list[str]:
    stmt = (
        select(ActivityEvent.domain)
        .distinct()
        .where(ActivityEvent.domain.is_not(None))
        .order_by(ActivityEvent.domain)
    )
    return [r for (r,) in session.exec(stmt).all()]
```

`get_distinct_event_types` and `get_distinct_entity_types` follow the same pattern on their respective columns.

---

## 5. Service Layer

**File:** `src/codemie/service/activity/activity_event_service.py` (new)

```python
from codemie.clients.postgres import get_sync_session  # or PostgresClient.get_engine()
from codemie.service.activity.activity_repository import activity_event_repository, ActivityEventRow
from codemie.rest_api.models.activity_event import ActivityEventListItem, ActivityEventFilterOptions

class ActivityEventService:
    def list_events(
        self,
        *,
        actor_id, domain, event_type, entity_type, entity_id,
        from_dt, to_dt, sort_dir, limit, offset,
    ) -> tuple[list[ActivityEventListItem], int]:
        with Session(PostgresClient.get_engine()) as session:
            rows, total = activity_event_repository.find_all(
                actor_id=actor_id, domain=domain, event_type=event_type,
                entity_type=entity_type, entity_id=entity_id,
                from_dt=from_dt, to_dt=to_dt,
                sort_dir=sort_dir, limit=limit, offset=offset,
                session=session,
            )
        items = [
            ActivityEventListItem(
                id=r.id, domain=r.domain, event_type=r.event_type,
                entity_type=r.entity_type, entity_id=r.entity_id,
                actor_id=r.actor_id, actor_email=r.actor_email,
                actor_name=r.actor_name, attributes=r.attributes,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, total

    def get_filter_options(self) -> ActivityEventFilterOptions:
        with Session(PostgresClient.get_engine()) as session:
            return ActivityEventFilterOptions(
                domains=activity_event_repository.get_distinct_domains(session),
                event_types=activity_event_repository.get_distinct_event_types(session),
                entity_types=activity_event_repository.get_distinct_entity_types(session),
            )

activity_event_service = ActivityEventService()
```

---

## 6. Router

**File:** `src/codemie/rest_api/routers/activity_events_router.py` (new)

```python
router = APIRouter(
    tags=["activity-events"],
    prefix="/v1/admin/activity-events",
    dependencies=[Depends(authenticate)],
)

@router.get("/filter-options", response_model=ActivityEventFilterOptions)
def get_filter_options(
    _: None = Depends(maintainer_access_only),
) -> ActivityEventFilterOptions:
    ...

# NOTE: /filter-options must be declared before "" so FastAPI resolves
# the static path before the paginated list route.
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
    ...
```

**`main.py`:** `app.include_router(activity_events_router.router)` added alongside the existing admin routers.

---

## 7. File Manifest

| File | Action |
|---|---|
| `src/codemie/rest_api/models/activity_event.py` | New — `ActivityEventListItem`, `ActivityEventFilterOptions` |
| `src/codemie/service/activity/activity_event_service.py` | New — `ActivityEventService`, `activity_event_service` singleton |
| `src/codemie/service/activity/activity_repository.py` | Edit — `ActivityEventRow` dataclass, `find_all`, `get_distinct_*` on ABC + impl |
| `src/codemie/rest_api/routers/activity_events_router.py` | New — two GET endpoints |
| `src/codemie/rest_api/main.py` | Edit — register router |

---

## 8. Out of Scope

- Write / delete endpoints (audit log is append-only).
- Actor dropdown population (served by existing `GET /v1/admin/users`).
- Caching of filter-options results (first iteration; add if query becomes slow).
- Export / CSV download.
