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

"""Repository for assistant project feature mappings."""

from abc import ABC, abstractmethod
from uuid import uuid4

from sqlmodel import Session, select

from codemie.clients.postgres import PostgresClient
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
        with Session(PostgresClient.get_engine()) as session:
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
        with Session(PostgresClient.get_engine()) as session:
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

        with Session(PostgresClient.get_engine()) as session:
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
        with Session(PostgresClient.get_engine()) as session:
            return (
                session.exec(
                    select(AssistantProjectMappingSQL).where(
                        AssistantProjectMappingSQL.assistant_id == assistant_id,
                        AssistantProjectMappingSQL.project_name == project_name,
                        AssistantProjectMappingSQL.feature == feature,
                    )
                ).first()
                is not None
            )


AssistantProjectMappingRepositoryImpl = SQLAssistantProjectMappingRepository
