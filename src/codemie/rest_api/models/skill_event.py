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

"""SQL + API models for `codemie skill *` lifecycle events.

Persistent record of every wrapper-emitted event (one row per skill targeted
by the operation). Lets us count installs / popularity / per-user activity
durably — the existing Elastic metric path retains data for only a few
months, while these rows live forever.

Schema is intentionally permissive (free-form TEXT for `command` / `status`
/ `scope`, JSONB `attributes` escape hatch) so adding a new command (e.g.
`find`, `pin`, `share`) requires only an API-layer Literal change, never a
database migration.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlmodel import Field

from codemie.rest_api.models.base import BaseModelWithSQLSupport


# ---------------------------------------------------------------------------
# Pydantic enums (validated at the API layer; DB stays flexible TEXT)
# ---------------------------------------------------------------------------

# Adding a new command requires only adding a Literal value here — no
# DB migration. `find` is included from day 1 even though the v1 CLI
# wrapper does not emit it; backend support is forward-looking so the
# UI/catalog can record discovery events without a backend change.
SkillCommand = Literal["add", "update", "remove", "list", "find"]
SkillInstallCommand = Literal["add", "remove"]
SkillStatus = Literal["started", "completed", "failed"]
SkillScope = Literal["global", "project", "unknown"]
AgentSelectionMode = Literal["explicit", "auto_detected", "prompted", "upstream"]


# ---------------------------------------------------------------------------
# REST request/response shapes
# ---------------------------------------------------------------------------

SESSION_ID_MAX_LENGTH = 128
AGENT_MAX_LENGTH = 64
AGENT_VERSION_MAX_LENGTH = 64
REPOSITORY_MAX_LENGTH = 512
BRANCH_MAX_LENGTH = 256
PROJECT_MAX_LENGTH = 256
ERROR_CODE_MAX_LENGTH = 128
SOURCE_MAX_LENGTH = 512
SKILL_SLUG_MAX_LENGTH = 256
SKILL_ID_MAX_LENGTH = 1024


class SkillEventRequest(BaseModel):
    """Body for `POST /v1/skills/events`.

    A single event = one lifecycle step (started/completed/failed) for ONE
    skill (or null skill for ops with no specific target — bare `list`,
    `find`, or interactive `add` with no `--skill`).

    The CLI fans out multi-skill operations into multiple POSTs.
    """

    # Lifecycle
    session_id: str = PydanticField(
        ...,
        max_length=SESSION_ID_MAX_LENGTH,
        description="CLI invocation UUID; groups events of one operation.",
    )
    command: SkillCommand
    status: SkillStatus
    scope: Optional[SkillScope] = None
    error_code: Optional[str] = PydanticField(default=None, max_length=ERROR_CODE_MAX_LENGTH)
    agent_selection_mode: Optional[AgentSelectionMode] = None
    target_agents: Optional[List[str]] = None

    # Skill identity. Server fills the missing pair member from skill_name +
    # source if only one of slug/id is provided. All three may be null for
    # ops with no specific skill target (e.g. bare `list`).
    source: Optional[str] = PydanticField(default=None, max_length=SOURCE_MAX_LENGTH)
    skill_name: Optional[str] = None
    skill_slug: Optional[str] = PydanticField(default=None, max_length=SKILL_SLUG_MAX_LENGTH)
    skill_id: Optional[str] = PydanticField(default=None, max_length=SKILL_ID_MAX_LENGTH)

    # Context (best-effort; CLI populates what it can)
    agent: Optional[str] = PydanticField(default="codemie-skills", max_length=AGENT_MAX_LENGTH)
    agent_version: Optional[str] = PydanticField(default=None, max_length=AGENT_VERSION_MAX_LENGTH)
    repository: Optional[str] = PydanticField(default=None, max_length=REPOSITORY_MAX_LENGTH)
    branch: Optional[str] = PydanticField(default=None, max_length=BRANCH_MAX_LENGTH)
    project: Optional[str] = PydanticField(default=None, max_length=PROJECT_MAX_LENGTH)

    # Forward-compat escape hatch for any future field
    attributes: Optional[Dict[str, Any]] = None


class SkillEventResponse(BaseModel):
    id: str
    success: bool = True
    message: str = "Skill event recorded"


class SkillEventLogItem(BaseModel):
    """One item in the paginated event-log response (GET /v1/skills/events)."""

    skill_slug: Optional[str] = None
    source: Optional[str] = None
    target_agents: List[str] = []
    date: datetime  # maps to SkillEvent.created_at; serialized as ISO 8601
    command: SkillInstallCommand
    user_id: str
    user_email: Optional[str] = None


class SkillStatsResponse(BaseModel):
    """Per-skill aggregated install / removal stats (GET /v1/skills/events/{slug}/stats)."""

    installs: int
    removals: int
    by_agent: Dict[str, int]
    by_source: Dict[str, int] = {}


class SkillStatsListItem(BaseModel):
    """One item in the paginated all-skills aggregated stats response (GET /v1/skills/events/stats)."""

    skill_slug: Optional[str] = None
    installs: int
    removals: int
    by_agent: Dict[str, int]
    by_source: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# SQL model
# ---------------------------------------------------------------------------


class SkillEvent(BaseModelWithSQLSupport, table=True):
    """One row per (lifecycle event, skill).

    `command`, `status`, `scope`, `agent_selection_mode` are stored as plain
    TEXT (no DB CHECK constraint) so adding a new value never requires a
    migration. API-layer Pydantic Literals validate input.
    """

    __tablename__ = "skill_events"

    # Override CommonBaseModel.id to ensure non-null UUID generation.
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # Identity / context
    user_id: str = Field(index=True)
    user_email: Optional[str] = Field(default=None, max_length=320)
    session_id: str = Field(index=True, max_length=SESSION_ID_MAX_LENGTH)
    agent: str = Field(default="codemie-skills", max_length=AGENT_MAX_LENGTH)
    agent_version: Optional[str] = Field(default=None, max_length=AGENT_VERSION_MAX_LENGTH)
    client_type: Optional[str] = Field(default=None, max_length=64)
    cli_version: Optional[str] = Field(default=None, max_length=64)
    repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH)
    branch: Optional[str] = Field(default=None, max_length=BRANCH_MAX_LENGTH)
    project: Optional[str] = Field(default=None, max_length=PROJECT_MAX_LENGTH)

    # Lifecycle (free-form TEXT; API-level validation only)
    command: str = Field(index=True, max_length=64)
    status: str = Field(index=True, max_length=32)
    scope: Optional[str] = Field(default=None, max_length=32)
    error_code: Optional[str] = Field(default=None, max_length=ERROR_CODE_MAX_LENGTH)
    agent_selection_mode: Optional[str] = Field(default=None, max_length=32)

    # Per-operation list (JSONB for codebase-wide consistency with ai_kata.tags etc.)
    target_agents: List[str] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(JSONB)),
    )

    # Skill identity (one row per skill; null for ops with no targeted skill)
    source: Optional[str] = Field(default=None, max_length=SOURCE_MAX_LENGTH)
    skill_slug: Optional[str] = Field(default=None, index=True, max_length=SKILL_SLUG_MAX_LENGTH)
    skill_id: Optional[str] = Field(default=None, index=True, max_length=SKILL_ID_MAX_LENGTH)

    # Forward-compat
    attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )

    __table_args__ = (
        Index("ix_skill_events_user_created", "user_id", "created_at"),
        Index("ix_skill_events_command_created", "command", "created_at"),
    )
