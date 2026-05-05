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

"""Repository for `codemie skill *` lifecycle events.

Persistent record (Postgres) of every wrapper-emitted event so install /
popularity counts survive Elastic retention. Read methods are intentionally
minimal in v1 — analytics handlers can be added in a follow-up PR.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlmodel import Session

from codemie.configs import logger
from codemie.rest_api.models.skill_event import SkillEvent


class SkillEventRepository(ABC):
    """Abstract interface for skill event persistence."""

    @abstractmethod
    def insert(self, event: SkillEvent) -> SkillEvent:
        """Persist a single skill event row.

        The row is expected to be fully prepared by the service layer
        (slug/id derivation, sanitization, user context attachment).
        """

    @abstractmethod
    def find_by_id(self, event_id: str) -> Optional[SkillEvent]:
        """Return the event with `event_id` or None."""


class SQLSkillEventRepository(SkillEventRepository):
    """Postgres-backed implementation."""

    def insert(self, event: SkillEvent) -> SkillEvent:
        with Session(SkillEvent.get_engine()) as session:
            session.add(event)
            session.commit()
            session.refresh(event)
            logger.debug(
                "[skill_events] inserted id=%s command=%s status=%s skill_id=%s",
                event.id,
                event.command,
                event.status,
                event.skill_id,
            )
            return event

    def find_by_id(self, event_id: str) -> Optional[SkillEvent]:
        with Session(SkillEvent.get_engine()) as session:
            return session.get(SkillEvent, event_id)


# Default implementation (mirrors KataUsageRepositoryImpl convention)
SkillEventRepositoryImpl = SQLSkillEventRepository
