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

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.skill_event import SkillEvent, SkillEventRequest
from codemie.rest_api.routers.skill_events import record_skill_event
from codemie.rest_api.security.user import User


def _user() -> User:
    return User(id="user-1", username="user", email="user@example.com")


def _request() -> SkillEventRequest:
    return SkillEventRequest(
        session_id="session-1",
        command="add",
        status="completed",
        skill_slug="code-review",
    )


def test_record_skill_event_returns_persisted_event_id() -> None:
    event = SkillEvent(
        id="event-1",
        user_id="user-1",
        session_id="session-1",
        command="add",
        status="completed",
    )

    with patch("codemie.rest_api.routers.skill_events.skill_event_service.record", return_value=event) as record:
        response = record_skill_event(
            request=_request(),
            user=_user(),
            x_codemie_cli="codemie-cli/1.0.0",
            x_codemie_client="cli",
        )

    assert response.id == "event-1"
    assert response.success is True
    assert response.message == "Skill event 'add/completed' recorded"
    record.assert_called_once()
    assert record.call_args.kwargs["x_codemie_cli"] == "codemie-cli/1.0.0"
    assert record.call_args.kwargs["x_codemie_client"] == "cli"


def test_record_skill_event_preserves_service_http_errors() -> None:
    original = ExtendedHTTPException(code=409, message="duplicate event")

    with patch("codemie.rest_api.routers.skill_events.skill_event_service.record", side_effect=original):
        with pytest.raises(ExtendedHTTPException) as exc_info:
            record_skill_event(request=_request(), user=_user())

    assert exc_info.value is original


def test_record_skill_event_wraps_unexpected_service_errors() -> None:
    with patch(
        "codemie.rest_api.routers.skill_events.skill_event_service.record",
        side_effect=RuntimeError("database unavailable"),
    ):
        with pytest.raises(ExtendedHTTPException) as exc_info:
            record_skill_event(request=_request(), user=_user())

    assert exc_info.value.code == 500
    assert exc_info.value.message == "Failed to record skill event"
    assert "command=add status=completed" in exc_info.value.details
