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

"""Service for managing assistant project feature mappings."""

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from codemie.configs import logger
from codemie.core.models import Application
from codemie.repository.application_repository import application_repository
from codemie.repository.assistants.assistant_project_mapping_repository import (
    AssistantProjectMappingRepository,
    AssistantProjectMappingRepositoryImpl,
)
from codemie.rest_api.models.base import PaginatedListResponse, PaginationData
from codemie.rest_api.security.user import User
from codemie.service.assistant.assistant_repository import AssistantRepository, AssistantScope


class AssistantProjectMappingNotFound(Exception):
    """Raised when a required resource (project or mapping) does not exist."""

    def __init__(self, resource_id: str, resource_type: str):
        self.resource_id = resource_id
        self.resource_type = resource_type
        super().__init__(f"{resource_type} '{resource_id}' not found")


class AssistantProjectMappingForbidden(Exception):
    """Raised when the caller lacks permission for the requested action."""

    def __init__(self, action: str):
        self.action = action
        super().__init__(f"Forbidden: {action}")


class AssistantProjectMappingService:
    """Manages which assistants are enabled for a project feature (e.g. Teams bot)."""

    def __init__(self, repository: Optional[AssistantProjectMappingRepository] = None):
        self.repository = repository if repository else AssistantProjectMappingRepositoryImpl()

    def list(
        self,
        project_name: str,
        feature: str,
        user: User,
        page: int = 0,
        per_page: int = 12,
    ) -> PaginatedListResponse:
        """Return paginated assistants enabled for a project feature. Caller must be a project member."""
        self._require_project_access(user, project_name)

        assistant_ids = self.repository.get_assistant_ids(project_name, feature)

        if not assistant_ids:
            return PaginatedListResponse(
                data=[],
                pagination=PaginationData(page=page, per_page=per_page, total=0, pages=0),
            )

        result = AssistantRepository().query(
            user=user,
            scope=AssistantScope.ALL,
            filters={"id": assistant_ids},
            page=page,
            per_page=per_page,
        )

        return PaginatedListResponse(
            data=result["data"],
            pagination=PaginationData(**result["pagination"]),
        )

    def enable(self, assistant_id: str, project_name: str, feature: str, user: User) -> None:
        """Enable an assistant for a project feature. Idempotent — no-op if already enabled."""
        self._require_project_admin(user, project_name)
        self._validate_project_exists(project_name)

        if self.repository.exists(assistant_id, project_name, feature):
            logger.debug(f"Mapping already exists: assistant={assistant_id} project={project_name} feature={feature}")
            return

        try:
            self.repository.create(assistant_id, project_name, feature, user.id)
            logger.debug(f"Mapping created: assistant={assistant_id} project={project_name} feature={feature}")
        except IntegrityError:
            logger.debug(
                f"Concurrent enable — mapping already exists: assistant={assistant_id} "
                f"project={project_name} feature={feature}"
            )

    def disable(self, assistant_id: str, project_name: str, feature: str, user: User) -> None:
        """Disable an assistant for a project feature. Raises if the mapping does not exist."""
        self._require_project_admin(user, project_name)

        found = self.repository.delete(assistant_id, project_name, feature)
        if not found:
            raise AssistantProjectMappingNotFound(
                resource_id=f"{assistant_id}/{project_name}/{feature}",
                resource_type="Mapping",
            )

    def _validate_project_exists(self, project_name: str) -> None:
        """Raise AssistantProjectMappingNotFound if the project does not exist or is deleted."""
        with Session(Application.get_engine()) as session:
            app = application_repository.get_by_name(session, project_name)

        if not app or app.deleted_at is not None:
            raise AssistantProjectMappingNotFound(resource_id=project_name, resource_type="Project")

    def _require_project_admin(self, user: User, project_name: str) -> None:
        """Raise AssistantProjectMappingForbidden if the user is not a project admin or global maintainer."""
        if not (user.is_application_admin(project_name) or user.is_admin_or_maintainer):
            raise AssistantProjectMappingForbidden("manage assistant feature mappings for this project")

    def _require_project_access(self, user: User, project_name: str) -> None:
        """Raise AssistantProjectMappingForbidden if the user has no access to the project."""
        if not user.has_access_to_application(project_name):
            raise AssistantProjectMappingForbidden("list assistant mappings for this project")
