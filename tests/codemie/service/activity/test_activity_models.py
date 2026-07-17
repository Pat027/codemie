# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
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

import pytest
from pydantic import ValidationError
from codemie.service.activity.activity_models import ActivityEventCreate


def test_entity_pair_both_set_is_valid():
    e = ActivityEventCreate(
        domain="user_management",
        event_type="user.created",
        entity_type="user",
        entity_id="abc-123",
    )
    assert e.entity_type == "user"
    assert e.entity_id == "abc-123"


def test_entity_pair_both_none_is_valid():
    e = ActivityEventCreate(domain="user_management", event_type="user.login")
    assert e.entity_type is None
    assert e.entity_id is None


def test_entity_type_set_without_entity_id_raises():
    with pytest.raises(ValidationError, match="entity_type and entity_id"):
        ActivityEventCreate(
            domain="user_management",
            event_type="user.created",
            entity_type="user",
            entity_id=None,
        )


def test_entity_id_set_without_entity_type_raises():
    with pytest.raises(ValidationError, match="entity_type and entity_id"):
        ActivityEventCreate(
            domain="user_management",
            event_type="user.created",
            entity_type=None,
            entity_id="abc-123",
        )
