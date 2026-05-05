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

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from codemie.rest_api.models.skill_event import SkillEvent, SkillEventRequest
from codemie.rest_api.security.user import User
from codemie.service.skill_event_service import (
    SKILL_COMMAND_METRIC,
    SkillEventService,
    derive_skill_identity,
    to_skill_slug,
)


class FakeSkillEventRepository:
    def __init__(self) -> None:
        self.inserted: SkillEvent | None = None

    def insert(self, event: SkillEvent) -> SkillEvent:
        self.inserted = event
        event.id = "event-1"
        return event

    def find_by_id(self, event_id: str) -> SkillEvent | None:
        return self.inserted if self.inserted and self.inserted.id == event_id else None


def _user(email: str = "user@example.com") -> User:
    return User(id="user-1", username="user", email=email)


def test_to_skill_slug_matches_cli_normalization_rules() -> None:
    assert to_skill_slug("  Team_SKILL: v2!!  ") == "team-skill-v2"


@pytest.mark.parametrize(
    ("source", "skill_name", "skill_slug", "skill_id", "expected"),
    (
        ("github.com/org", "Skill Name", None, None, ("skill-name", "github.com/org/skill-name")),
        (None, "Skill Name", None, None, ("skill-name", "skill-name")),
        ("github.com/org", None, None, None, (None, None)),
        ("github.com/org", "Skill Name", "explicit-slug", "custom/id", ("explicit-slug", "custom/id")),
    ),
)
def test_derive_skill_identity_fills_only_missing_identity_parts(
    source: str | None,
    skill_name: str | None,
    skill_slug: str | None,
    skill_id: str | None,
    expected: tuple[str | None, str | None],
) -> None:
    assert derive_skill_identity(source, skill_name, skill_slug, skill_id) == expected


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("session_id", "s" * 129),
        ("error_code", "e" * 129),
        ("source", "s" * 513),
        ("skill_slug", "s" * 257),
        ("skill_id", "s" * 1025),
        ("agent", "a" * 65),
        ("agent_version", "v" * 65),
        ("repository", "r" * 513),
        ("branch", "b" * 257),
        ("project", "p" * 257),
    ),
)
def test_skill_event_request_rejects_values_longer_than_db_columns(field_name: str, value: str) -> None:
    payload = {
        "session_id": "session-1",
        "command": "add",
        "status": "completed",
        field_name: value,
    }

    with pytest.raises(ValidationError) as exc_info:
        SkillEventRequest(**payload)

    assert exc_info.value.errors()[0]["loc"] == (field_name,)


def test_record_persists_enriched_event_and_mirrors_flat_metric() -> None:
    repository = FakeSkillEventRepository()
    service = SkillEventService(repository=repository)
    request = SkillEventRequest(
        session_id="session-1",
        command="add",
        status="completed",
        scope="project",
        source="github.com/org",
        skill_name="Code Review",
        agent_version="1.2.3",
        repository="org/repo",
        branch="main",
        project="demo",
        target_agents=["codex", "claude"],
        attributes={"duration_ms": 123},
    )

    with patch("codemie.service.skill_event_service.send_log_metric") as send_log_metric:
        event = service.record(
            request=request,
            user=_user(),
            x_codemie_cli="codemie-cli/1.0.0",
            x_codemie_client="cli",
        )

    assert event is repository.inserted
    assert event.id == "event-1"
    assert event.user_id == "user-1"
    assert event.user_email == "user@example.com"
    assert event.client_type == "cli"
    assert event.cli_version == "codemie-cli/1.0.0"
    assert event.skill_slug == "code-review"
    assert event.skill_id == "github.com/org/code-review"
    assert event.target_agents == ["codex", "claude"]
    assert event.attributes == {"duration_ms": 123}
    send_log_metric.assert_called_once_with(
        SKILL_COMMAND_METRIC,
        {
            "agent": "codemie-skills",
            "agent_version": "1.2.3",
            "session_id": "session-1",
            "command": "add",
            "status": "completed",
            "scope": "project",
            "target_agents": ["codex", "claude"],
            "source": "github.com/org",
            "skill_slug": "code-review",
            "skill_id": "github.com/org/code-review",
            "repository": "org/repo",
            "branch": "main",
            "project": "demo",
            "user_id": "user-1",
            "user_email": "user@example.com",
        },
    )


def test_record_returns_persisted_event_when_metric_mirror_fails() -> None:
    repository = FakeSkillEventRepository()
    service = SkillEventService(repository=repository)
    request = SkillEventRequest(
        session_id="session-1",
        command="remove",
        status="failed",
        error_code="not_found",
        skill_slug="missing-skill",
    )

    with patch(
        "codemie.service.skill_event_service.send_log_metric",
        side_effect=RuntimeError("shipper unavailable"),
    ):
        event = service.record(request=request, user=_user(email=""))

    assert event is repository.inserted
    assert event.id == "event-1"
    assert event.user_email is None
    assert event.skill_slug == "missing-skill"
    assert event.skill_id == "missing-skill"
