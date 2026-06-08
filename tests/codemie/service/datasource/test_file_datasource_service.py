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

"""Tests for FileDatasourceService and _validate_json_file."""

import json

import pytest
from elasticsearch.exceptions import NotFoundError
from fastapi import status
from unittest.mock import MagicMock, patch

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.security.user import User
from codemie.service.datasource.file_datasource_service import FileDatasourceService, _validate_json_file


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = "user1"
    user.username = "user1@example.com"
    user.name = "User One"
    return user


@pytest.fixture
def mock_index():
    index = MagicMock()
    index.uploaded_files = ["existing_file.txt"]
    index.created_by = MagicMock()
    index.created_by.id = "original_owner"
    return index


# ---------------------------------------------------------------------------
# find_or_raise
# ---------------------------------------------------------------------------


class TestFindOrRaise:
    def test_returns_first_index_when_found(self, mock_index):
        with patch(
            "codemie.service.datasource.file_datasource_service.KnowledgeBaseIndexInfo.filter_by_project_and_repo",
            return_value=[mock_index],
        ):
            result = FileDatasourceService.find_or_raise("project", "name")
        assert result is mock_index

    def test_raises_404_when_not_found(self):
        with patch(
            "codemie.service.datasource.file_datasource_service.KnowledgeBaseIndexInfo.filter_by_project_and_repo",
            return_value=[],
        ):
            with pytest.raises(ExtendedHTTPException) as exc_info:
                FileDatasourceService.find_or_raise("project", "name")
        assert exc_info.value.code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# parse_uploaded_files
# ---------------------------------------------------------------------------


class TestParseUploadedFiles:
    def test_returns_json_parsed_list_when_provided(self, mock_index):
        result = FileDatasourceService.parse_uploaded_files('["file1.txt", "file2.txt"]', mock_index)
        assert result == ["file1.txt", "file2.txt"]

    def test_returns_existing_uploaded_files_when_none(self, mock_index):
        result = FileDatasourceService.parse_uploaded_files(None, mock_index)
        assert result == ["existing_file.txt"]

    def test_raises_400_on_invalid_json(self, mock_index):
        with pytest.raises(ExtendedHTTPException) as exc_info:
            FileDatasourceService.parse_uploaded_files("not-valid-json", mock_index)
        assert exc_info.value.code == status.HTTP_400_BAD_REQUEST

    def test_returns_empty_list_when_index_uploaded_files_is_none(self):
        index = MagicMock()
        index.uploaded_files = None
        result = FileDatasourceService.parse_uploaded_files(None, index)
        assert result == []


# ---------------------------------------------------------------------------
# parse_guardrail_assignments
# ---------------------------------------------------------------------------


class TestParseGuardrailAssignments:
    def test_returns_none_when_none_passed(self):
        result = FileDatasourceService.parse_guardrail_assignments(None)
        assert result is None

    def test_returns_none_when_empty_string(self):
        result = FileDatasourceService.parse_guardrail_assignments("")
        assert result is None

    def test_returns_empty_list_when_empty_json_array(self):
        result = FileDatasourceService.parse_guardrail_assignments("[]")
        assert result == []

    def test_raises_400_on_invalid_json(self):
        with pytest.raises(ExtendedHTTPException) as exc_info:
            FileDatasourceService.parse_guardrail_assignments("not-valid-json")
        assert exc_info.value.code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# compute_file_changes
# ---------------------------------------------------------------------------


class TestComputeFileChanges:
    def test_no_changes_when_same_files_no_new(self, mock_index):
        mock_index.uploaded_files = ["file1.txt"]
        result = FileDatasourceService.compute_file_changes(None, ["file1.txt"], mock_index)
        assert not result.has_file_changes
        assert result.removed_files == set()

    def test_detects_removed_files(self, mock_index):
        mock_index.uploaded_files = ["file1.txt", "file2.txt"]
        result = FileDatasourceService.compute_file_changes(None, ["file1.txt"], mock_index)
        assert result.has_file_changes
        assert result.removed_files == {"file2.txt"}

    def test_detects_new_files(self, mock_index):
        mock_index.uploaded_files = ["file1.txt"]
        new_files = [MagicMock()]
        result = FileDatasourceService.compute_file_changes(new_files, ["file1.txt"], mock_index)
        assert result.has_file_changes
        assert result.removed_files == set()

    def test_uploaded_files_none_treated_as_empty(self):
        index = MagicMock()
        index.uploaded_files = None
        result = FileDatasourceService.compute_file_changes(None, [], index)
        assert not result.has_file_changes


# ---------------------------------------------------------------------------
# validate_project_change
# ---------------------------------------------------------------------------


class TestValidateProjectChange:
    def test_no_op_when_new_project_is_none(self, mock_user):
        FileDatasourceService.validate_project_change(None, "project", "repo", mock_user)

    def test_no_op_when_same_project(self, mock_user):
        FileDatasourceService.validate_project_change("project", "project", "repo", mock_user)

    def test_raises_404_when_application_not_found_error(self, mock_user):
        with patch(
            "codemie.service.datasource.file_datasource_service.Application.get_by_id",
            side_effect=NotFoundError(MagicMock(), MagicMock(), MagicMock()),
        ):
            with pytest.raises(ExtendedHTTPException) as exc_info:
                FileDatasourceService.validate_project_change("new_project", "old_project", "repo", mock_user)
        assert exc_info.value.code == status.HTTP_404_NOT_FOUND

    def test_raises_404_when_application_key_error(self, mock_user):
        with patch(
            "codemie.service.datasource.file_datasource_service.Application.get_by_id",
            side_effect=KeyError(),
        ):
            with pytest.raises(ExtendedHTTPException) as exc_info:
                FileDatasourceService.validate_project_change("new_project", "old_project", "repo", mock_user)
        assert exc_info.value.code == status.HTTP_404_NOT_FOUND

    def test_raises_403_when_user_has_no_access(self, mock_user):
        mock_user.has_access_to_application.return_value = False
        with patch("codemie.service.datasource.file_datasource_service.Application.get_by_id"):
            with pytest.raises(ExtendedHTTPException) as exc_info:
                FileDatasourceService.validate_project_change("new_project", "old_project", "repo", mock_user)
        assert exc_info.value.code == status.HTTP_403_FORBIDDEN

    def test_raises_409_when_index_already_exists_in_target_project(self, mock_user):
        mock_user.has_access_to_application.return_value = True
        with (
            patch("codemie.service.datasource.file_datasource_service.Application.get_by_id"),
            patch(
                "codemie.service.datasource.file_datasource_service.IndexInfo.filter_by_project_and_repo",
                return_value=[MagicMock()],
            ),
        ):
            with pytest.raises(ExtendedHTTPException) as exc_info:
                FileDatasourceService.validate_project_change("new_project", "old_project", "repo", mock_user)
        assert exc_info.value.code == status.HTTP_409_CONFLICT

    def test_succeeds_when_all_checks_pass(self, mock_user):
        mock_user.has_access_to_application.return_value = True
        with (
            patch("codemie.service.datasource.file_datasource_service.Application.get_by_id"),
            patch(
                "codemie.service.datasource.file_datasource_service.IndexInfo.filter_by_project_and_repo",
                return_value=[],
            ),
        ):
            FileDatasourceService.validate_project_change("new_project", "old_project", "repo", mock_user)


# ---------------------------------------------------------------------------
# update_metadata_only
# ---------------------------------------------------------------------------


class TestUpdateMetadataOnly:
    def test_calls_update_index_on_the_index(self, mock_index, mock_user):
        FileDatasourceService.update_metadata_only(
            index=mock_index,
            user=mock_user,
            description="new desc",
            project_space_visible=True,
            new_project_name="new_project",
            guardrail_assignments=None,
        )
        mock_index.update_index.assert_called_once()

    def test_passes_description_and_visibility_to_update_index(self, mock_index, mock_user):
        FileDatasourceService.update_metadata_only(
            index=mock_index,
            user=mock_user,
            description="updated",
            project_space_visible=False,
            new_project_name=None,
            guardrail_assignments=None,
        )
        call_kwargs = mock_index.update_index.call_args.kwargs
        assert call_kwargs["description"] == "updated"
        assert call_kwargs["project_space_visible"] is False


# ---------------------------------------------------------------------------
# upload_and_prepare_files
# ---------------------------------------------------------------------------


class TestUploadAndPrepareFiles:
    def _make_upload_file(self, filename, content=b"data", content_type="text/plain"):
        f = MagicMock()
        f.filename = filename
        f.file.read.return_value = content
        f.headers = {"content-type": content_type}
        return f

    def _make_file_object(self, name, owner="user1"):
        obj = MagicMock()
        obj.name = name
        obj.owner = owner
        return obj

    def test_uploads_new_files_and_includes_kept_files(self, mock_index, mock_user):
        upload_file = self._make_upload_file("new.txt")
        file_obj = self._make_file_object("new.txt")

        with patch(
            "codemie.service.datasource.file_datasource_service.FileRepositoryFactory.get_current_repository"
        ) as mock_repo:
            mock_repo.return_value.write_file.return_value = file_obj
            result = FileDatasourceService.upload_and_prepare_files(
                new_files=[upload_file],
                user=mock_user,
                uploaded_files_to_keep=["kept.txt"],
                index=mock_index,
            )

        assert "new.txt" in result.uploaded_files
        assert "kept.txt" in result.uploaded_files
        assert len(result.new_files_paths) == 1
        assert len(result.all_files_paths) == 2

    def test_uses_user_id_as_owner_when_created_by_is_none(self, mock_user):
        index = MagicMock()
        index.created_by = None
        upload_file = self._make_upload_file("new.txt")
        file_obj = self._make_file_object("new.txt", owner="user1")

        with patch(
            "codemie.service.datasource.file_datasource_service.FileRepositoryFactory.get_current_repository"
        ) as mock_repo:
            mock_repo.return_value.write_file.return_value = file_obj
            result = FileDatasourceService.upload_and_prepare_files(
                new_files=[upload_file],
                user=mock_user,
                uploaded_files_to_keep=[],
                index=index,
            )

        assert result.all_files_paths[0].owner == "user1"

    def test_kept_files_use_original_owner(self, mock_index, mock_user):
        mock_index.created_by.id = "original_owner"
        upload_file = self._make_upload_file("new.txt")
        file_obj = self._make_file_object("new.txt")

        with patch(
            "codemie.service.datasource.file_datasource_service.FileRepositoryFactory.get_current_repository"
        ) as mock_repo:
            mock_repo.return_value.write_file.return_value = file_obj
            result = FileDatasourceService.upload_and_prepare_files(
                new_files=[upload_file],
                user=mock_user,
                uploaded_files_to_keep=["kept.txt"],
                index=mock_index,
            )

        kept = next(p for p in result.all_files_paths if p.name == "kept.txt")
        assert kept.owner == "original_owner"

    def test_raises_422_when_json_file_has_invalid_content(self, mock_index, mock_user):
        upload_file = self._make_upload_file("data.json", content=b"not-json", content_type="application/json")
        file_obj = self._make_file_object("data.json")

        with (
            patch(
                "codemie.service.datasource.file_datasource_service.FileRepositoryFactory.get_current_repository"
            ) as mock_repo,
            pytest.raises(ExtendedHTTPException) as exc_info,
        ):
            mock_repo.return_value.write_file.return_value = file_obj
            FileDatasourceService.upload_and_prepare_files(
                new_files=[upload_file],
                user=mock_user,
                uploaded_files_to_keep=[],
                index=mock_index,
            )

        assert exc_info.value.code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_non_json_files_skip_validation(self, mock_index, mock_user):
        upload_file = self._make_upload_file("report.csv", content=b"a,b\n1,2")
        file_obj = self._make_file_object("report.csv")

        with patch(
            "codemie.service.datasource.file_datasource_service.FileRepositoryFactory.get_current_repository"
        ) as mock_repo:
            mock_repo.return_value.write_file.return_value = file_obj
            result = FileDatasourceService.upload_and_prepare_files(
                new_files=[upload_file],
                user=mock_user,
                uploaded_files_to_keep=[],
                index=mock_index,
            )

        assert "report.csv" in result.uploaded_files


# ---------------------------------------------------------------------------
# _validate_json_file
# ---------------------------------------------------------------------------


class TestValidateJsonFile:
    def test_valid_json_with_content_and_metadata_does_not_raise(self):
        content = json.dumps([{"content": "text", "metadata": {}}]).encode()
        _validate_json_file("file.json", content)

    def test_valid_json_with_multiple_documents_does_not_raise(self):
        content = json.dumps([{"content": "a", "metadata": {"k": 1}}, {"content": "b", "metadata": {}}]).encode()
        _validate_json_file("file.json", content)

    def test_raises_422_on_missing_content_key(self):
        content = json.dumps([{"metadata": {}}]).encode()
        with pytest.raises(ExtendedHTTPException) as exc_info:
            _validate_json_file("file.json", content)
        assert exc_info.value.code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_raises_422_on_missing_metadata_key(self):
        content = json.dumps([{"content": "text"}]).encode()
        with pytest.raises(ExtendedHTTPException) as exc_info:
            _validate_json_file("file.json", content)
        assert exc_info.value.code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_raises_422_on_invalid_json_bytes(self):
        with pytest.raises(ExtendedHTTPException) as exc_info:
            _validate_json_file("file.json", b"not-json-content")
        assert exc_info.value.code == status.HTTP_422_UNPROCESSABLE_ENTITY
