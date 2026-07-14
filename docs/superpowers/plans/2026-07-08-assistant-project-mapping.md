# Assistant Project Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `assistant_project_mapping` table and three endpoints so project admins can enable/disable which assistants appear in the Teams feature for their project, and project members can list those assistants.

**Architecture:** New table (presence = enabled, absence = disabled) with a `feature` discriminator for future expansion. A dedicated repository, service, and router follow the exact pattern of `assistant_user_mapping`. The GET listing delegates to the existing `AssistantRepository.query(scope=ALL)` to enforce per-user access control on top of the mapping table.

**Tech Stack:** Python 3.11+, FastAPI, SQLModel, SQLAlchemy, Alembic, pytest, unittest.mock

## Global Constraints

- Python version: ≥ 3.11 (use `X | Y` union syntax, `match`, etc.)
- All new files must carry the Apache 2.0 copyright header (copy from any existing file in `src/codemie/`).
- `feature` column stores `AssistantProjectFeature` string values; new feature values may be added later without a migration.
- `assistant_project_mapping.assistant_id` → FK to `assistants.id` with `ondelete="CASCADE"`.
- No FK from `project_name` to `applications` — soft-deleted projects are filtered at query time via a JOIN.
- Composite unique constraint `(assistant_id, project_name, feature)` named `uix_assistant_project_mapping`.
- The GET `/v1/assistants/projects/mapping` router MUST be registered in `main.py` **before** `assistant.router` to prevent FastAPI from matching the literal path segment `"projects"` as `{assistant_id}`.
- Do not commit `.env` or `config/customer/customer-config.yaml` — those are pre-existing dirty files unrelated to this ticket.
- Tests: no real DB, no real session — mock `Session` and `AssistantProjectMappingSQL.get_engine()` exactly as in `test_assistant_user_mapping_repository.py`.

---

### Task 1: Data model + Alembic migration

**Files:**
- Create: `src/codemie/rest_api/models/usage/assistant_project_mapping.py`
- Create: `src/external/alembic/versions/a1b2c3d4e5f6_create_assistant_project_mapping.py`

**Interfaces:**
- Produces: `AssistantProjectFeature`, `AssistantProjectMappingSQL`, `AssistantProjectMappingRequest`, `AssistantProjectMappingResponse` — consumed by Tasks 2, 3, 4.

- [ ] **Step 1: Write the model file**

```python
# src/codemie/rest_api/models/usage/assistant_project_mapping.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Models for assistant project feature mappings."""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField

from codemie.rest_api.models.base import BaseModelWithSQLSupport, CommonBaseModel


class AssistantProjectFeature(str, Enum):
    TEAMS = "teams"


class AssistantProjectMappingSQL(BaseModelWithSQLSupport, table=True):
    __tablename__ = "assistant_project_mapping"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    assistant_id: str = SQLField(foreign_key="assistants.id", index=True, ondelete="CASCADE")
    project_name: str = SQLField(index=True)
    feature: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(UTC))
    updated_by: str

    __table_args__ = (
        UniqueConstraint(
            "assistant_id", "project_name", "feature",
            name="uix_assistant_project_mapping",
        ),
    )


class AssistantProjectMappingRequest(CommonBaseModel):
    project_name: str
    feature: AssistantProjectFeature


class AssistantProjectMappingResponse(CommonBaseModel):
    id: str
    assistant_id: str
    project_name: str
    feature: str
    created_at: Optional[datetime] = None
    updated_by: str

    @classmethod
    def from_db_model(cls, db_model: AssistantProjectMappingSQL) -> "AssistantProjectMappingResponse":
        return cls(
            id=db_model.id,
            assistant_id=db_model.assistant_id,
            project_name=db_model.project_name,
            feature=db_model.feature,
            created_at=db_model.created_at,
            updated_by=db_model.updated_by,
        )
```

- [ ] **Step 2: Write the Alembic migration**

```python
# src/external/alembic/versions/a1b2c3d4e5f6_create_assistant_project_mapping.py
"""create assistant_project_mapping

Revision ID: a1b2c3d4e5f6
Revises: r2s3t4u5v6w7
Create Date: 2026-07-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "r2s3t4u5v6w7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_project_mapping",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("assistant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("feature", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assistant_id"],
            ["assistants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_id", "project_name", "feature", name="uix_assistant_project_mapping"),
    )
    op.create_index(
        op.f("ix_assistant_project_mapping_assistant_id"),
        "assistant_project_mapping",
        ["assistant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_project_mapping_project_name"),
        "assistant_project_mapping",
        ["project_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_project_mapping_feature"),
        "assistant_project_mapping",
        ["feature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_project_mapping_feature"), table_name="assistant_project_mapping")
    op.drop_index(op.f("ix_assistant_project_mapping_project_name"), table_name="assistant_project_mapping")
    op.drop_index(op.f("ix_assistant_project_mapping_assistant_id"), table_name="assistant_project_mapping")
    op.drop_table("assistant_project_mapping")
```

- [ ] **Step 3: Verify the model imports cleanly**

```bash
cd /path/to/repo
python -c "from codemie.rest_api.models.usage.assistant_project_mapping import AssistantProjectMappingSQL, AssistantProjectFeature, AssistantProjectMappingRequest, AssistantProjectMappingResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/codemie/rest_api/models/usage/assistant_project_mapping.py \
        src/external/alembic/versions/a1b2c3d4e5f6_create_assistant_project_mapping.py
git commit -m "feat(EPMCDME-13354): add assistant_project_mapping model and migration"
```

---

### Task 2: Repository

**Files:**
- Create: `src/codemie/repository/assistants/assistant_project_mapping_repository.py`
- Create: `tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py`

**Interfaces:**
- Consumes: `AssistantProjectMappingSQL` from Task 1; `Application` from `codemie.core.models`.
- Produces:
  - `AssistantProjectMappingRepository` (ABC) with: `create(assistant_id, project_name, feature, updated_by) -> AssistantProjectMappingSQL`, `delete(assistant_id, project_name, feature) -> bool`, `get_assistant_ids(project_name, feature) -> list[str]`, `exists(assistant_id, project_name, feature) -> bool`.
  - `AssistantProjectMappingRepositoryImpl = SQLAssistantProjectMappingRepository` — consumed by Task 3.

- [ ] **Step 1: Write the failing test for `create`**

```python
# tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# ... (Apache 2.0 header)

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC

from codemie.rest_api.models.usage.assistant_project_mapping import AssistantProjectMappingSQL
from codemie.repository.assistants.assistant_project_mapping_repository import (
    SQLAssistantProjectMappingRepository,
)


@pytest.fixture
def repo():
    return SQLAssistantProjectMappingRepository()


def test_create_inserts_row(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        repo.create("asst-1", "proj-x", "teams", "user-1")

        mock_session.assert_called_once_with("mock_engine")
        mock_instance.add.assert_called_once()
        mock_instance.commit.assert_called_once()
        created = mock_instance.add.call_args[0][0]
        assert isinstance(created, AssistantProjectMappingSQL)
        assert created.assistant_id == "asst-1"
        assert created.project_name == "proj-x"
        assert created.feature == "teams"
        assert created.updated_by == "user-1"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
python -m pytest tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py::test_create_inserts_row -v
```

Expected: `FAILED` with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Write the repository**

```python
# src/codemie/repository/assistants/assistant_project_mapping_repository.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# ... (Apache 2.0 header)

"""Repository for assistant project feature mappings."""

from abc import ABC, abstractmethod
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, select

from codemie.rest_api.models.usage.assistant_project_mapping import AssistantProjectMappingSQL


class AssistantProjectMappingRepository(ABC):

    @abstractmethod
    def create(self, assistant_id: str, project_name: str, feature: str, updated_by: str) -> AssistantProjectMappingSQL:
        pass

    @abstractmethod
    def delete(self, assistant_id: str, project_name: str, feature: str) -> bool:
        pass

    @abstractmethod
    def get_assistant_ids(self, project_name: str, feature: str) -> list[str]:
        pass

    @abstractmethod
    def exists(self, assistant_id: str, project_name: str, feature: str) -> bool:
        pass


class SQLAssistantProjectMappingRepository(AssistantProjectMappingRepository):

    def create(self, assistant_id: str, project_name: str, feature: str, updated_by: str) -> AssistantProjectMappingSQL:
        with Session(AssistantProjectMappingSQL.get_engine()) as session:
            mapping = AssistantProjectMappingSQL(
                id=str(uuid4()),
                assistant_id=assistant_id,
                project_name=project_name,
                feature=feature,
                updated_by=updated_by,
            )
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            return mapping

    def delete(self, assistant_id: str, project_name: str, feature: str) -> bool:
        with Session(AssistantProjectMappingSQL.get_engine()) as session:
            mapping = session.exec(
                select(AssistantProjectMappingSQL).where(
                    AssistantProjectMappingSQL.assistant_id == assistant_id,
                    AssistantProjectMappingSQL.project_name == project_name,
                    AssistantProjectMappingSQL.feature == feature,
                )
            ).first()
            if mapping is None:
                return False
            session.delete(mapping)
            session.commit()
            return True

    def get_assistant_ids(self, project_name: str, feature: str) -> list[str]:
        from codemie.core.models import Application

        with Session(AssistantProjectMappingSQL.get_engine()) as session:
            rows = session.exec(
                select(AssistantProjectMappingSQL.assistant_id)
                .join(Application, Application.name == AssistantProjectMappingSQL.project_name)
                .where(
                    AssistantProjectMappingSQL.project_name == project_name,
                    AssistantProjectMappingSQL.feature == feature,
                    Application.deleted_at.is_(None),
                )
            ).all()
            return list(rows)

    def exists(self, assistant_id: str, project_name: str, feature: str) -> bool:
        with Session(AssistantProjectMappingSQL.get_engine()) as session:
            return session.exec(
                select(AssistantProjectMappingSQL).where(
                    AssistantProjectMappingSQL.assistant_id == assistant_id,
                    AssistantProjectMappingSQL.project_name == project_name,
                    AssistantProjectMappingSQL.feature == feature,
                )
            ).first() is not None


AssistantProjectMappingRepositoryImpl = SQLAssistantProjectMappingRepository
```

- [ ] **Step 4: Run `test_create_inserts_row` — expect PASS**

```bash
python -m pytest tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py::test_create_inserts_row -v
```

Expected: `PASSED`

- [ ] **Step 5: Write remaining repository tests**

Append to `tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py`:

```python
def test_delete_returns_true_when_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    existing = MagicMock(spec=AssistantProjectMappingSQL)
    mock_instance.exec.return_value.first.return_value = existing

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        result = repo.delete("asst-1", "proj-x", "teams")

        assert result is True
        mock_instance.delete.assert_called_once_with(existing)
        mock_instance.commit.assert_called_once()


def test_delete_returns_false_when_not_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = None

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        result = repo.delete("asst-1", "proj-x", "teams")

        assert result is False
        mock_instance.delete.assert_not_called()


def test_exists_returns_true_when_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = MagicMock()

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        assert repo.exists("asst-1", "proj-x", "teams") is True


def test_exists_returns_false_when_not_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = None

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        assert repo.exists("asst-1", "proj-x", "teams") is False


def test_get_assistant_ids_returns_list(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.all.return_value = ["asst-1", "asst-2"]

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.join.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch.object(AssistantProjectMappingSQL, "get_engine", return_value="mock_engine"),
    ):
        result = repo.get_assistant_ids("proj-x", "teams")

        assert result == ["asst-1", "asst-2"]
```

- [ ] **Step 6: Run all repository tests — expect all PASS**

```bash
python -m pytest tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py -v
```

Expected: all `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/codemie/repository/assistants/assistant_project_mapping_repository.py \
        tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py
git commit -m "feat(EPMCDME-13354): add AssistantProjectMappingRepository"
```

---

### Task 3: Service

**Files:**
- Create: `src/codemie/service/assistant/assistant_project_mapping_service.py`
- Create: `tests/codemie/service/assistant/test_assistant_project_mapping_service.py`

**Interfaces:**
- Consumes:
  - `AssistantProjectMappingRepository` from Task 2.
  - `AssistantProjectMappingRepositoryImpl` from Task 2.
  - `AssistantRepository`, `AssistantScope` from `codemie.service.assistant.assistant_repository`.
  - `Application` from `codemie.core.models`.
  - `Assistant` from `codemie.rest_api.models.assistant`.
  - `ExtendedHTTPException` from `codemie.core.exceptions`.
  - `User` from `codemie.rest_api.security.user`.
- Produces: `AssistantProjectMappingService` with `enable(assistant_id, project_name, feature, user)`, `disable(assistant_id, project_name, feature, user)`, `list(project_name, feature, user, page, per_page) -> dict`; singleton `assistant_project_mapping_service` — consumed by Task 4.

- [ ] **Step 1: Write failing tests for `enable` (idempotency)**

```python
# tests/codemie/service/assistant/test_assistant_project_mapping_service.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# ... (Apache 2.0 header)

"""Tests for AssistantProjectMappingService."""

import pytest
from unittest.mock import MagicMock, patch

from codemie.repository.assistants.assistant_project_mapping_repository import AssistantProjectMappingRepository
from codemie.service.assistant.assistant_project_mapping_service import AssistantProjectMappingService


@pytest.fixture
def mock_repo():
    return MagicMock(spec=AssistantProjectMappingRepository)


@pytest.fixture
def service(mock_repo):
    return AssistantProjectMappingService(repository=mock_repo)


@pytest.fixture
def project_admin_user():
    user = MagicMock()
    user.id = "user-1"
    user.is_application_admin.return_value = True
    user.is_admin_or_maintainer = False
    user.has_access_to_application.return_value = True
    return user


@pytest.fixture
def regular_user():
    user = MagicMock()
    user.id = "user-2"
    user.is_application_admin.return_value = False
    user.is_admin_or_maintainer = False
    user.has_access_to_application.return_value = True
    return user


def test_enable_creates_mapping(service, mock_repo, project_admin_user):
    mock_repo.exists.return_value = False

    with (
        patch.object(service, "_validate_assistant_exists"),
        patch.object(service, "_validate_project_exists"),
    ):
        service.enable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.create.assert_called_once_with("asst-1", "proj-x", "teams", "user-1")


def test_enable_is_idempotent(service, mock_repo, project_admin_user):
    mock_repo.exists.return_value = True

    with (
        patch.object(service, "_validate_assistant_exists"),
        patch.object(service, "_validate_project_exists"),
    ):
        service.enable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.create.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/codemie/service/assistant/test_assistant_project_mapping_service.py::test_enable_creates_mapping tests/codemie/service/assistant/test_assistant_project_mapping_service.py::test_enable_is_idempotent -v
```

Expected: `FAILED` with `ImportError`.

- [ ] **Step 3: Write the service**

```python
# src/codemie/service/assistant/assistant_project_mapping_service.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# ... (Apache 2.0 header)

"""Service for managing assistant project feature mappings."""

from typing import Optional

from fastapi import status
from sqlmodel import Session, select

from codemie.configs import logger
from codemie.core.exceptions import ExtendedHTTPException
from codemie.repository.assistants.assistant_project_mapping_repository import (
    AssistantProjectMappingRepository,
    AssistantProjectMappingRepositoryImpl,
)
from codemie.rest_api.security.user import User


class AssistantProjectMappingService:

    def __init__(self, repository: Optional[AssistantProjectMappingRepository] = None):
        self.repository = repository if repository else AssistantProjectMappingRepositoryImpl()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_assistant_exists(self, assistant_id: str) -> None:
        from codemie.rest_api.models.assistant import Assistant

        asst = Assistant.find_by_id(assistant_id)
        if not asst:
            raise ExtendedHTTPException(
                code=status.HTTP_404_NOT_FOUND,
                message="Assistant not found",
                details=f"No assistant found with id '{assistant_id}'.",
                help="Check the assistant id.",
            )

    def _validate_project_exists(self, project_name: str) -> None:
        from codemie.core.models import Application

        with Session(Application.get_engine()) as session:
            app = session.exec(
                select(Application).where(
                    Application.name == project_name,
                    Application.deleted_at.is_(None),
                )
            ).first()
        if not app:
            raise ExtendedHTTPException(
                code=status.HTTP_404_NOT_FOUND,
                message="Project not found",
                details=f"No active project found with name '{project_name}'.",
                help="Check the project name.",
            )

    def _require_project_admin(self, user: User, project_name: str) -> None:
        if not (user.is_application_admin(project_name) or user.is_admin_or_maintainer):
            raise ExtendedHTTPException(
                code=status.HTTP_403_FORBIDDEN,
                message="Forbidden",
                details="You must be a project admin to manage assistant feature mappings.",
                help="Ask a project admin to perform this action.",
            )

    def _require_project_access(self, user: User, project_name: str) -> None:
        if not user.has_access_to_application(project_name):
            raise ExtendedHTTPException(
                code=status.HTTP_403_FORBIDDEN,
                message="Forbidden",
                details="You do not have access to this project.",
                help="Ask a project admin to add you to the project.",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enable(self, assistant_id: str, project_name: str, feature: str, user: User) -> None:
        self._require_project_admin(user, project_name)
        self._validate_assistant_exists(assistant_id)
        self._validate_project_exists(project_name)

        if self.repository.exists(assistant_id, project_name, feature):
            logger.debug(f"Mapping already exists: assistant={assistant_id} project={project_name} feature={feature}")
            return

        self.repository.create(assistant_id, project_name, feature, user.id)
        logger.debug(f"Mapping created: assistant={assistant_id} project={project_name} feature={feature}")

    def disable(self, assistant_id: str, project_name: str, feature: str, user: User) -> None:
        self._require_project_admin(user, project_name)
        self._validate_assistant_exists(assistant_id)

        found = self.repository.delete(assistant_id, project_name, feature)
        if not found:
            raise ExtendedHTTPException(
                code=status.HTTP_404_NOT_FOUND,
                message="Mapping not found",
                details=f"No mapping found for assistant '{assistant_id}' in project '{project_name}' feature '{feature}'.",
                help="The assistant may not be enabled for this project feature.",
            )

    def list(
        self,
        project_name: str,
        feature: str,
        user: User,
        page: int = 0,
        per_page: int = 12,
    ) -> dict:
        from codemie.service.assistant.assistant_repository import AssistantRepository, AssistantScope

        self._require_project_access(user, project_name)

        assistant_ids = self.repository.get_assistant_ids(project_name, feature)
        if not assistant_ids:
            return {"data": [], "pagination": {"page": page, "per_page": per_page, "total": 0, "pages": 0}}

        return AssistantRepository().query(
            user=user,
            scope=AssistantScope.ALL,
            filters={"id": assistant_ids},
            page=page,
            per_page=per_page,
        )


assistant_project_mapping_service = AssistantProjectMappingService()
```

- [ ] **Step 4: Run the two enable tests — expect PASS**

```bash
python -m pytest tests/codemie/service/assistant/test_assistant_project_mapping_service.py::test_enable_creates_mapping tests/codemie/service/assistant/test_assistant_project_mapping_service.py::test_enable_is_idempotent -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Write remaining service tests**

Append to `tests/codemie/service/assistant/test_assistant_project_mapping_service.py`:

```python
def test_enable_raises_403_for_non_admin(service, mock_repo, regular_user):
    with pytest.raises(Exception) as exc_info:
        service.enable("asst-1", "proj-x", "teams", regular_user)
    assert exc_info.value.code == 403
    mock_repo.create.assert_not_called()


def test_disable_calls_delete(service, mock_repo, project_admin_user):
    mock_repo.delete.return_value = True

    with patch.object(service, "_validate_assistant_exists"):
        service.disable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.delete.assert_called_once_with("asst-1", "proj-x", "teams")


def test_disable_raises_404_when_not_found(service, mock_repo, project_admin_user):
    mock_repo.delete.return_value = False

    with patch.object(service, "_validate_assistant_exists"):
        with pytest.raises(Exception) as exc_info:
            service.disable("asst-1", "proj-x", "teams", project_admin_user)
    assert exc_info.value.code == 404


def test_list_returns_empty_when_no_mappings(service, mock_repo, regular_user):
    mock_repo.get_assistant_ids.return_value = []

    result = service.list("proj-x", "teams", regular_user)

    assert result["data"] == []
    assert result["pagination"]["total"] == 0
    mock_repo.get_assistant_ids.assert_called_once_with("proj-x", "teams")


def test_list_delegates_to_assistant_repository(service, mock_repo, regular_user):
    mock_repo.get_assistant_ids.return_value = ["asst-1", "asst-2"]
    expected = {"data": [MagicMock()], "pagination": {"page": 0, "per_page": 12, "total": 1, "pages": 1}}

    with patch(
        "codemie.service.assistant.assistant_project_mapping_service.AssistantRepository"
    ) as MockRepo:
        MockRepo.return_value.query.return_value = expected
        result = service.list("proj-x", "teams", regular_user, page=0, per_page=12)

    assert result == expected
    MockRepo.return_value.query.assert_called_once()
    call_kwargs = MockRepo.return_value.query.call_args[1]
    assert call_kwargs["filters"] == {"id": ["asst-1", "asst-2"]}


def test_list_raises_403_for_non_member(service, mock_repo):
    non_member = MagicMock()
    non_member.has_access_to_application.return_value = False

    with pytest.raises(Exception) as exc_info:
        service.list("proj-x", "teams", non_member)
    assert exc_info.value.code == 403


def test_singleton_instance():
    from codemie.service.assistant.assistant_project_mapping_service import assistant_project_mapping_service as svc
    assert isinstance(svc, AssistantProjectMappingService)
```

- [ ] **Step 6: Run all service tests — expect all PASS**

```bash
python -m pytest tests/codemie/service/assistant/test_assistant_project_mapping_service.py -v
```

Expected: all `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/codemie/service/assistant/assistant_project_mapping_service.py \
        tests/codemie/service/assistant/test_assistant_project_mapping_service.py
git commit -m "feat(EPMCDME-13354): add AssistantProjectMappingService"
```

---

### Task 4: Router

**Files:**
- Create: `src/codemie/rest_api/routers/assistant_project_mapping.py`

**Interfaces:**
- Consumes:
  - `AssistantProjectMappingRequest`, `AssistantProjectMappingResponse`, `AssistantProjectFeature` from Task 1.
  - `assistant_project_mapping_service` singleton from Task 3.
  - `_get_assistant_by_id_or_raise` from `codemie.rest_api.routers.assistant`.
  - `authenticate` from `codemie.rest_api.security.authentication`.
  - `User` from `codemie.rest_api.security.user`.
  - `BaseResponse` from `codemie.core.models`.
  - `ExtendedHTTPException` from `codemie.core.exceptions`.
- Produces: `router` object (APIRouter) — consumed by Task 5.

**Route registration order within this file:**  
`GET /v1/assistants/projects/mapping` MUST be defined before the two `{assistant_id}` routes to avoid path-param collision inside this router. In `main.py` this router is registered before `assistant.router` for the same reason.

- [ ] **Step 1: Write the router**

```python
# src/codemie/rest_api/routers/assistant_project_mapping.py
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
# ... (Apache 2.0 header)

"""Router for assistant project feature mapping endpoints."""

from fastapi import APIRouter, Depends, Query, status

from codemie.configs import logger
from codemie.core.exceptions import ExtendedHTTPException
from codemie.core.models import BaseResponse
from codemie.rest_api.models.usage.assistant_project_mapping import (
    AssistantProjectFeature,
    AssistantProjectMappingRequest,
)
from codemie.rest_api.routers.assistant import _get_assistant_by_id_or_raise
from codemie.rest_api.security.authentication import authenticate
from codemie.rest_api.security.user import User
from codemie.service.assistant.assistant_project_mapping_service import assistant_project_mapping_service

router = APIRouter(
    tags=["Assistant Project Mappings"],
    prefix="/v1",
    dependencies=[],
)


# NOTE: this route MUST be defined before the {assistant_id} routes below
# to prevent FastAPI from matching "projects" as an assistant_id.
@router.get(
    "/assistants/projects/mapping",
    status_code=status.HTTP_200_OK,
    response_model_by_alias=True,
)
def list_project_assistants(
    feature: AssistantProjectFeature = Query(...),
    project: str = Query(...),
    page: int = Query(0, ge=0),
    per_page: int = Query(12, ge=1, le=100),
    user: User = Depends(authenticate),
):
    """List assistants enabled for a project feature. Accessible to project members."""
    try:
        return assistant_project_mapping_service.list(
            project_name=project,
            feature=feature.value,
            user=user,
            page=page,
            per_page=per_page,
        )
    except ExtendedHTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing project feature assistants: {e}", exc_info=True)
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to list assistants",
            details=str(e),
            help="Try again later.",
        ) from e


@router.post(
    "/assistants/{assistant_id}/projects/mapping",
    status_code=status.HTTP_200_OK,
    response_model=BaseResponse,
    response_model_by_alias=True,
)
def enable_assistant_for_project(
    assistant_id: str,
    request: AssistantProjectMappingRequest,
    user: User = Depends(authenticate),
):
    """Enable an assistant for a project feature. Requires project admin."""
    _get_assistant_by_id_or_raise(assistant_id)
    try:
        assistant_project_mapping_service.enable(
            assistant_id=assistant_id,
            project_name=request.project_name,
            feature=request.feature.value,
            user=user,
        )
        return BaseResponse(message="Assistant enabled for project feature successfully")
    except ExtendedHTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling assistant for project feature: {e}", exc_info=True)
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to enable assistant",
            details=str(e),
            help="Try again later.",
        ) from e


@router.delete(
    "/assistants/{assistant_id}/projects/mapping",
    status_code=status.HTTP_200_OK,
    response_model=BaseResponse,
    response_model_by_alias=True,
)
def disable_assistant_for_project(
    assistant_id: str,
    project: str = Query(...),
    feature: AssistantProjectFeature = Query(...),
    user: User = Depends(authenticate),
):
    """Disable an assistant for a project feature. Requires project admin."""
    _get_assistant_by_id_or_raise(assistant_id)
    try:
        assistant_project_mapping_service.disable(
            assistant_id=assistant_id,
            project_name=project,
            feature=feature.value,
            user=user,
        )
        return BaseResponse(message="Assistant disabled for project feature successfully")
    except ExtendedHTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling assistant for project feature: {e}", exc_info=True)
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to disable assistant",
            details=str(e),
            help="Try again later.",
        ) from e
```

- [ ] **Step 2: Verify the router imports cleanly**

```bash
python -c "from codemie.rest_api.routers.assistant_project_mapping import router; print(len(router.routes), 'routes')"
```

Expected: `3 routes`

- [ ] **Step 3: Commit**

```bash
git add src/codemie/rest_api/routers/assistant_project_mapping.py
git commit -m "feat(EPMCDME-13354): add assistant project mapping router"
```

---

### Task 5: Register router in main.py

**Files:**
- Modify: `src/codemie/rest_api/main.py`

**Interfaces:**
- Consumes: `router` from `codemie.rest_api.routers.assistant_project_mapping` (Task 4).

**Critical:** the new router must be registered **before** `assistant.router` so `GET /v1/assistants/projects/mapping` is matched before `GET /v1/assistants/{assistant_id}`.

- [ ] **Step 1: Add the import**

In `src/codemie/rest_api/main.py`, add `assistant_project_mapping` to the existing router import block (lines 49–93):

Find this line:
```python
    assistant_mapping,
```

Add after it:
```python
    assistant_project_mapping,
```

- [ ] **Step 2: Register the router before `assistant.router`**

Find this block in `main.py` (around line 743):
```python
app.include_router(a2a.router)
app.include_router(assistant.router)
```

Change it to:
```python
app.include_router(a2a.router)
app.include_router(assistant_project_mapping.router)
app.include_router(assistant.router)
```

- [ ] **Step 3: Verify the app starts without errors**

```bash
python -c "
import os; os.environ.setdefault('ENV', 'local')
from codemie.rest_api.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
assert any('/assistants/projects/mapping' in r for r in routes), 'Route not found'
print('Route registered OK')
"
```

Expected: `Route registered OK`

- [ ] **Step 4: Commit**

```bash
git add src/codemie/rest_api/main.py
git commit -m "feat(EPMCDME-13354): register assistant_project_mapping router"
```

---

### Task 6: Run quality gates

This task verifies the full implementation passes the project's CI checks.

**Files:** no changes — verification only.

- [ ] **Step 1: Run linting**

```bash
make lint
```

Expected: no errors. If `ruff` flags issues, fix them before proceeding.

- [ ] **Step 2: Run the full test suite for affected modules**

```bash
python -m pytest \
  tests/codemie/repository/assistants/test_assistant_project_mapping_repository.py \
  tests/codemie/service/assistant/test_assistant_project_mapping_service.py \
  -v
```

Expected: all `PASSED`, zero failures.

- [ ] **Step 3: Confirm migration chain is consistent**

```bash
grep -r "down_revision" src/external/alembic/versions/a1b2c3d4e5f6_create_assistant_project_mapping.py
```

Expected: `down_revision: Union[str, None] = "r2s3t4u5v6w7"` — matches the latest revision before this branch.

- [ ] **Step 4: Confirm no pre-existing dirty files in staged changes**

```bash
git diff --name-only HEAD
```

Expected: only the 7 files introduced by Tasks 1–5. Verify `.env` and `config/customer/customer-config.yaml` are NOT in the diff.

- [ ] **Step 5: Final commit (if any lint fixes were needed)**

```bash
git add -p   # stage only the lint-fix hunks
git commit -m "fix(EPMCDME-13354): apply ruff lint fixes"
```

Skip this step if lint passed clean in Step 1.
