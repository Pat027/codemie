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
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField, SQLModel

from codemie.rest_api.models.base import CommonBaseModel


class AssistantProjectFeature(str, Enum):
    TEAMS = "teams"


class AssistantProjectMappingSQL(SQLModel, table=True):
    __tablename__ = "assistant_project_mapping"

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    assistant_id: str = SQLField(foreign_key="assistants.id", ondelete="CASCADE")
    project_name: str = SQLField(index=True)
    feature: str = SQLField()
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(UTC))
    updated_by: str

    __table_args__ = (
        UniqueConstraint(
            "assistant_id",
            "project_name",
            "feature",
            name="uix_assistant_project_mapping",
        ),
    )


class AssistantProjectMappingRequest(CommonBaseModel):
    project_name: str
    feature: AssistantProjectFeature
