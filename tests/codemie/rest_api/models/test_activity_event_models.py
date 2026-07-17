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
        assert item.entity_id is None
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
        assert len(opts.entity_types) == 2

    def test_empty_lists_valid(self):
        opts = ActivityEventFilterOptions(domains=[], event_types=[], entity_types=[])
        assert opts.domains == []
