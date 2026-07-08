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

"""
Tests for the assistant user mapping service.
"""

from unittest.mock import MagicMock
import pytest

from codemie.rest_api.models.usage.assistant_user_mapping import AssistantUserMappingSQL, ToolConfig
from codemie.repository.assistants.assistant_user_mapping_repository import AssistantUserMappingRepository
from codemie.service.assistant.assistant_user_mapping_service import AssistantUserMappingService


@pytest.fixture
def mock_repository():
    repository = MagicMock(spec=AssistantUserMappingRepository)
    return repository


@pytest.fixture
def service(mock_repository):
    return AssistantUserMappingService(repository=mock_repository)


@pytest.fixture
def sample_mapping():
    return AssistantUserMappingSQL(
        id="test-id",
        assistant_id="test-assistant-id",
        user_id="test-user-id",
        tools_config=[
            ToolConfig(name="Git", integration_id="git-integration-id"),
            ToolConfig(name="JIRA", integration_id="jira-integration-id"),
        ],
    )


@pytest.fixture
def tools_config_list():
    return [
        {"name": "Git", "integration_id": "git-integration-id"},
        {"name": "JIRA", "integration_id": "jira-integration-id"},
    ]


def test_create_or_update_mapping(service, mock_repository, tools_config_list, sample_mapping):
    # Arrange
    assistant_id = "test-assistant-id"
    user_id = "test-user-id"
    mock_repository.get_mapping.return_value = None  # no existing mapping
    mock_repository.create_or_update_mapping.return_value = sample_mapping

    # Act
    result = service.create_or_update_mapping(assistant_id, user_id, tools_config_list)

    # Assert
    mock_repository.create_or_update_mapping.assert_called_once()
    assert result == sample_mapping

    # Check that the tools_config was properly converted
    args = mock_repository.create_or_update_mapping.call_args[0]
    assert args[0] == assistant_id
    assert args[1] == user_id
    saved = {tc.name: tc.integration_id for tc in args[2]}
    assert saved == {"Git": "git-integration-id", "JIRA": "jira-integration-id"}
    assert all(isinstance(tc, ToolConfig) for tc in args[2])


def test_create_or_update_mapping_clears_slot_reset_to_none(service, mock_repository, sample_mapping):
    """A slot sent with an empty integration_id is removed from the stored mapping."""
    # Arrange: existing mapping has Git + JIRA; user resets Git to "None".
    mock_repository.get_mapping.return_value = sample_mapping
    incoming = [{"name": "Git", "integration_id": ""}]

    # Act
    service.create_or_update_mapping("test-assistant-id", "test-user-id", incoming)

    # Assert: only JIRA remains; Git entry deleted.
    saved = {tc.name: tc.integration_id for tc in mock_repository.create_or_update_mapping.call_args[0][2]}
    assert saved == {"JIRA": "jira-integration-id"}


def test_create_or_update_mapping_leaves_untouched_slots(service, mock_repository, sample_mapping):
    """Slots absent from the payload are preserved; only the sent slot is upserted."""
    # Arrange: existing Git + JIRA; payload only updates Git.
    mock_repository.get_mapping.return_value = sample_mapping
    incoming = [{"name": "Git", "integration_id": "git-new-id"}]

    # Act
    service.create_or_update_mapping("test-assistant-id", "test-user-id", incoming)

    # Assert: Git updated, JIRA untouched.
    saved = {tc.name: tc.integration_id for tc in mock_repository.create_or_update_mapping.call_args[0][2]}
    assert saved == {"Git": "git-new-id", "JIRA": "jira-integration-id"}


def test_create_or_update_mapping_clears_last_slot_to_empty(service, mock_repository, sample_mapping):
    """Clearing the only remaining slot results in an empty stored tools_config."""
    # Arrange: existing has a single Git slot; user clears it.
    single = AssistantUserMappingSQL(
        id="test-id",
        assistant_id="test-assistant-id",
        user_id="test-user-id",
        tools_config=[ToolConfig(name="Git", integration_id="git-integration-id")],
    )
    mock_repository.get_mapping.return_value = single
    incoming = [{"name": "Git", "integration_id": ""}]

    # Act
    service.create_or_update_mapping("test-assistant-id", "test-user-id", incoming)

    # Assert
    assert mock_repository.create_or_update_mapping.call_args[0][2] == []


def test_get_mapping(service, mock_repository, sample_mapping):
    # Arrange
    assistant_id = "test-assistant-id"
    user_id = "test-user-id"
    mock_repository.get_mapping.return_value = sample_mapping

    # Act
    result = service.get_mapping(assistant_id, user_id)

    # Assert
    mock_repository.get_mapping.assert_called_once_with(assistant_id, user_id)
    assert result == sample_mapping


def test_get_mapping_not_found(service, mock_repository):
    # Arrange
    assistant_id = "test-assistant-id"
    user_id = "test-user-id"
    mock_repository.get_mapping.return_value = None

    # Act
    result = service.get_mapping(assistant_id, user_id)

    # Assert
    mock_repository.get_mapping.assert_called_once_with(assistant_id, user_id)
    assert result is None


def test_get_mappings_by_assistant(service, mock_repository):
    # Arrange
    assistant_id = "test-assistant-id"
    expected_mappings = [
        AssistantUserMappingSQL(
            id="test-id-1",
            assistant_id=assistant_id,
            user_id="user-1",
            tools_config=[ToolConfig(name="Git", integration_id="git-id-1")],
        ),
        AssistantUserMappingSQL(
            id="test-id-2",
            assistant_id=assistant_id,
            user_id="user-2",
            tools_config=[ToolConfig(name="Git", integration_id="git-id-2")],
        ),
    ]
    mock_repository.get_mappings_by_assistant.return_value = expected_mappings

    # Act
    result = service.get_mappings_by_assistant(assistant_id)

    # Assert
    mock_repository.get_mappings_by_assistant.assert_called_once_with(assistant_id)
    assert result == expected_mappings


def test_get_mappings_by_user(service, mock_repository):
    # Arrange
    user_id = "test-user-id"
    expected_mappings = [
        AssistantUserMappingSQL(
            id="test-id-1",
            assistant_id="assistant-1",
            user_id=user_id,
            tools_config=[ToolConfig(name="Git", integration_id="git-id-1")],
        ),
        AssistantUserMappingSQL(
            id="test-id-2",
            assistant_id="assistant-2",
            user_id=user_id,
            tools_config=[ToolConfig(name="Git", integration_id="git-id-2")],
        ),
    ]
    mock_repository.get_mappings_by_user.return_value = expected_mappings

    # Act
    result = service.get_mappings_by_user(user_id)

    # Assert
    mock_repository.get_mappings_by_user.assert_called_once_with(user_id)
    assert result == expected_mappings


def test_singleton_instance():
    from codemie.service.assistant.assistant_user_mapping_service import assistant_user_mapping_service

    # Ensure the singleton instance is an instance of the service
    assert isinstance(assistant_user_mapping_service, AssistantUserMappingService)
