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

"""Tests for UpdateFileDatasourceUseCase.execute()."""

import pytest
from fastapi import BackgroundTasks, status
from unittest.mock import MagicMock, patch

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.security.user import User
from codemie.use_cases.datasource.update_file_datasource_use_case import UpdateFileDatasourceUseCase

_PROCESSOR_PATH = "codemie.use_cases.datasource.update_file_datasource_use_case.FileDatasourceUpdateProcessor"


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = "user1"
    user.username = "user1@example.com"
    user.name = "User One"
    return user


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.parse_uploaded_files.return_value = []
    service.parse_guardrail_assignments.return_value = None
    return service


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.project_name = "test_project"
    request.name = "test_ds"
    request.uploaded_files = None
    request.guardrail_assignments = None
    request.files = None
    request.description = None
    request.project_space_visible = None
    request.new_project_name = None
    return request


@pytest.fixture
def use_case(mock_service):
    return UpdateFileDatasourceUseCase(service=mock_service)


@pytest.fixture(autouse=True)
def _patch_ability():
    with patch("codemie.use_cases.datasource.update_file_datasource_use_case.Ability"):
        yield


# ---------------------------------------------------------------------------
# Metadata-only path (no file changes)
# ---------------------------------------------------------------------------


class TestExecuteMetadataOnlyPath:
    def test_returns_edit_successful_message(self, use_case, mock_service, mock_request, mock_user):
        mock_changes = MagicMock()
        mock_changes.has_file_changes = False
        mock_service.compute_file_changes.return_value = mock_changes

        result = use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        assert result.message == "Edit successful"

    def test_calls_update_metadata_only(self, use_case, mock_service, mock_request, mock_user):
        mock_changes = MagicMock()
        mock_changes.has_file_changes = False
        mock_service.compute_file_changes.return_value = mock_changes

        use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        mock_service.update_metadata_only.assert_called_once()

    def test_calls_all_service_resolution_methods(self, use_case, mock_service, mock_request, mock_user):
        mock_changes = MagicMock()
        mock_changes.has_file_changes = False
        mock_service.compute_file_changes.return_value = mock_changes

        use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        mock_service.find_or_raise.assert_called_once_with(mock_request.project_name, mock_request.name)
        mock_service.parse_uploaded_files.assert_called_once()
        mock_service.parse_guardrail_assignments.assert_called_once()
        mock_service.compute_file_changes.assert_called_once()
        mock_service.validate_project_change.assert_called_once()

    def test_does_not_call_upload_and_prepare_files(self, use_case, mock_service, mock_request, mock_user):
        mock_changes = MagicMock()
        mock_changes.has_file_changes = False
        mock_service.compute_file_changes.return_value = mock_changes

        use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        mock_service.upload_and_prepare_files.assert_not_called()


# ---------------------------------------------------------------------------
# File-changes path (processor scheduled)
# ---------------------------------------------------------------------------


class TestExecuteFileChangesPath:
    def _make_file_changes(self, has_changes=True):
        changes = MagicMock()
        changes.has_file_changes = has_changes
        changes.removed_files = set()
        return changes

    def _make_prepared(self):
        prepared = MagicMock()
        prepared.all_files_paths = []
        prepared.new_files_paths = []
        prepared.uploaded_files = []
        return prepared

    def test_returns_processor_started_message(self, use_case, mock_service, mock_request, mock_user):
        mock_service.compute_file_changes.return_value = self._make_file_changes()
        mock_service.upload_and_prepare_files.return_value = self._make_prepared()
        mock_processor = MagicMock()
        mock_processor.started_message = "Indexing has started"

        with patch(_PROCESSOR_PATH, return_value=mock_processor):
            result = use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        assert result.message == "Indexing has started"

    def test_calls_init_index_before_schedule(self, use_case, mock_service, mock_request, mock_user):
        mock_service.compute_file_changes.return_value = self._make_file_changes()
        mock_service.upload_and_prepare_files.return_value = self._make_prepared()
        mock_processor = MagicMock()
        mock_processor.started_message = "started"

        with patch(_PROCESSOR_PATH, return_value=mock_processor):
            use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        mock_processor.init_index.assert_called_once()
        mock_processor.schedule.assert_called_once()

    def test_upload_and_prepare_called_before_scheduling(self, use_case, mock_service, mock_request, mock_user):
        mock_service.compute_file_changes.return_value = self._make_file_changes()
        mock_service.upload_and_prepare_files.return_value = self._make_prepared()
        mock_processor = MagicMock()
        mock_processor.started_message = "started"

        with patch(_PROCESSOR_PATH, return_value=mock_processor):
            use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        mock_service.upload_and_prepare_files.assert_called_once()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestExecuteErrorPropagation:
    def test_propagates_404_from_find_or_raise(self, use_case, mock_service, mock_request, mock_user):
        mock_service.find_or_raise.side_effect = ExtendedHTTPException(
            code=status.HTTP_404_NOT_FOUND,
            message="Index not found",
            details="Not found",
            help="Check name",
        )

        with pytest.raises(ExtendedHTTPException) as exc_info:
            use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        assert exc_info.value.code == status.HTTP_404_NOT_FOUND

    def test_raises_403_when_ability_denies_write(self, use_case, mock_service, mock_request, mock_user):
        with patch("codemie.use_cases.datasource.update_file_datasource_use_case.Ability") as mock_ability_cls:
            mock_ability_cls.return_value.can.return_value = False

            with pytest.raises(ExtendedHTTPException) as exc_info:
                use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        assert exc_info.value.code == status.HTTP_403_FORBIDDEN

    def test_propagates_403_from_validate_project_change(self, use_case, mock_service, mock_request, mock_user):
        mock_changes = MagicMock()
        mock_changes.has_file_changes = False
        mock_service.compute_file_changes.return_value = mock_changes
        mock_service.validate_project_change.side_effect = ExtendedHTTPException(
            code=status.HTTP_403_FORBIDDEN,
            message="Access denied",
            details="...",
            help="...",
        )

        with pytest.raises(ExtendedHTTPException) as exc_info:
            use_case.execute(mock_request, mock_user, BackgroundTasks(), "req-uuid")

        assert exc_info.value.code == status.HTTP_403_FORBIDDEN
