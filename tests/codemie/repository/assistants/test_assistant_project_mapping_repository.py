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

"""
Tests for the assistant project mapping repository.
"""

import pytest
from unittest.mock import patch, MagicMock

from codemie.rest_api.models.usage.assistant_project_mapping import AssistantProjectMappingSQL
from codemie.repository.assistants.assistant_project_mapping_repository import (
    SQLAssistantProjectMappingRepository,
)


@pytest.fixture
def repo():
    return SQLAssistantProjectMappingRepository()


def test_create_inserts_row(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        repo.create("asst-1", "proj-x", "teams", "user-1")

        mock_session.assert_called_once_with("mock_engine")
        mock_instance.add.assert_called_once()
        mock_instance.commit.assert_called_once()
        created = mock_instance.add.call_args[0][0]
        assert isinstance(created, AssistantProjectMappingSQL)
        assert created.assistant_id == "asst-1"
        assert created.project_name == "proj-x"
        assert created.feature == "teams"
        assert created.updated_by == "user-1"


def test_delete_returns_true_when_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    existing = MagicMock(spec=AssistantProjectMappingSQL)
    mock_instance.exec.return_value.first.return_value = existing

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        result = repo.delete("asst-1", "proj-x", "teams")

        assert result is True
        mock_instance.delete.assert_called_once_with(existing)
        mock_instance.commit.assert_called_once()


def test_delete_returns_false_when_not_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = None

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        result = repo.delete("asst-1", "proj-x", "teams")

        assert result is False
        mock_instance.delete.assert_not_called()


def test_exists_returns_true_when_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = MagicMock()

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        assert repo.exists("asst-1", "proj-x", "teams") is True


def test_exists_returns_false_when_not_found(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.first.return_value = None

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        assert repo.exists("asst-1", "proj-x", "teams") is False


def test_get_assistant_ids_returns_list(repo):
    mock_session = MagicMock()
    mock_instance = mock_session.return_value.__enter__.return_value
    mock_instance.exec.return_value.all.return_value = ["asst-1", "asst-2"]

    mock_select = MagicMock(return_value=MagicMock())
    mock_select.return_value.join.return_value.where.return_value = MagicMock()

    with (
        patch("codemie.repository.assistants.assistant_project_mapping_repository.Session", mock_session),
        patch("codemie.repository.assistants.assistant_project_mapping_repository.select", mock_select),
        patch(
            "codemie.repository.assistants.assistant_project_mapping_repository.PostgresClient.get_engine",
            return_value="mock_engine",
        ),
    ):
        result = repo.get_assistant_ids("proj-x", "teams")

        assert result == ["asst-1", "asst-2"]
