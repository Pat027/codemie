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

"""Tests for AssistantProjectMappingService."""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import IntegrityError

from codemie.repository.assistants.assistant_project_mapping_repository import AssistantProjectMappingRepository
from codemie.service.assistant.assistant_project_mapping_service import (
    AssistantProjectMappingForbidden,
    AssistantProjectMappingNotFound,
    AssistantProjectMappingService,
)


@pytest.fixture
def mock_repo():
    return MagicMock(spec=AssistantProjectMappingRepository)


@pytest.fixture
def service(mock_repo):
    return AssistantProjectMappingService(repository=mock_repo)


@pytest.fixture
def project_admin_user():
    user = MagicMock()
    user.id = "user-1"
    user.is_application_admin.return_value = True
    user.is_admin_or_maintainer = False
    user.has_access_to_application.return_value = True
    return user


@pytest.fixture
def regular_user():
    user = MagicMock()
    user.id = "user-2"
    user.is_application_admin.return_value = False
    user.is_admin_or_maintainer = False
    user.has_access_to_application.return_value = True
    return user


def test_enable_creates_mapping(service, mock_repo, project_admin_user):
    mock_repo.exists.return_value = False

    with patch.object(service, "_validate_project_exists"):
        service.enable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.create.assert_called_once_with("asst-1", "proj-x", "teams", "user-1")


def test_enable_is_idempotent(service, mock_repo, project_admin_user):
    mock_repo.exists.return_value = True

    with patch.object(service, "_validate_project_exists"):
        service.enable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.create.assert_not_called()


def test_enable_raises_403_for_non_admin(service, mock_repo, regular_user):
    with pytest.raises(AssistantProjectMappingForbidden):
        service.enable("asst-1", "proj-x", "teams", regular_user)
    mock_repo.create.assert_not_called()


def test_disable_calls_delete(service, mock_repo, project_admin_user):
    mock_repo.delete.return_value = True

    service.disable("asst-1", "proj-x", "teams", project_admin_user)

    mock_repo.delete.assert_called_once_with("asst-1", "proj-x", "teams")


def test_disable_raises_404_when_not_found(service, mock_repo, project_admin_user):
    mock_repo.delete.return_value = False

    with pytest.raises(AssistantProjectMappingNotFound):
        service.disable("asst-1", "proj-x", "teams", project_admin_user)


def test_list_returns_empty_when_no_mappings(service, mock_repo, regular_user):
    mock_repo.get_assistant_ids.return_value = []

    result = service.list("proj-x", "teams", regular_user)

    assert result.data == []
    assert result.pagination.total == 0
    mock_repo.get_assistant_ids.assert_called_once_with("proj-x", "teams")


def test_list_delegates_to_assistant_repository(service, mock_repo, regular_user):
    mock_repo.get_assistant_ids.return_value = ["asst-1", "asst-2"]
    mock_assistant = MagicMock()
    repo_result = {"data": [mock_assistant], "pagination": {"page": 0, "per_page": 12, "total": 1, "pages": 1}}

    with patch("codemie.service.assistant.assistant_project_mapping_service.AssistantRepository") as mock_repo_cls:
        mock_repo_cls.return_value.query.return_value = repo_result
        result = service.list("proj-x", "teams", regular_user, page=0, per_page=12)

    assert result.pagination.total == 1
    assert result.pagination.page == 0
    mock_repo_cls.return_value.query.assert_called_once()
    call_kwargs = mock_repo_cls.return_value.query.call_args[1]
    assert call_kwargs["filters"] == {"id": ["asst-1", "asst-2"]}


def test_list_raises_403_for_non_member(service, mock_repo):
    non_member = MagicMock()
    non_member.has_access_to_application.return_value = False

    with pytest.raises(AssistantProjectMappingForbidden):
        service.list("proj-x", "teams", non_member)


def test_enable_handles_concurrent_insert(service, mock_repo, project_admin_user):
    mock_repo.exists.return_value = False
    mock_repo.create.side_effect = IntegrityError("concurrent insert", None, None)

    with patch.object(service, "_validate_project_exists"):
        service.enable("asst-1", "proj-x", "teams", project_admin_user)  # must not raise
