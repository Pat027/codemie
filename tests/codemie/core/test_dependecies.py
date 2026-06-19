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

"""Tests for get_indexed_repo and get_repo_from_fields in dependecies.py."""

from unittest.mock import MagicMock, patch

import pytest

from codemie.core.constants import CodeIndexType
from codemie.core.dependecies import get_indexed_repo, get_repo_from_fields
from codemie.core.models import CodeFields


@pytest.fixture
def git_fields():
    return CodeFields(app_name="my-app", repo_name="my-repo", index_type=CodeIndexType.CODE, repo_type="git")


@pytest.fixture
def svn_fields():
    return CodeFields(app_name="my-app", repo_name="my-repo", index_type=CodeIndexType.CODE, repo_type="svn")


@pytest.fixture
def git_repo():
    repo = MagicMock()
    repo.name = "my-repo"
    repo.index_type = CodeIndexType.CODE
    repo.get_identifier.return_value = "my-app-my-repo-code"
    return repo


@pytest.fixture
def svn_repo():
    repo = MagicMock()
    repo.name = "my-repo"
    repo.index_type = CodeIndexType.CODE
    repo.get_identifier.return_value = "my-app-my-repo-svn-code"
    return repo


# --- get_indexed_repo ---


class TestGetIndexedRepo:
    def test_git_repo_type_returns_git_repo(self, git_fields, git_repo):
        with (
            patch("codemie.core.dependecies.GitRepo.find_by_id", return_value=git_repo),
            patch("codemie.core.dependecies.SVNRepo.find_by_id") as svn_find,
        ):
            result = get_indexed_repo(git_fields)

        assert result is git_repo
        svn_find.assert_not_called()

    def test_svn_repo_type_returns_svn_repo(self, svn_fields, svn_repo):
        with (
            patch("codemie.core.dependecies.SVNRepo.find_by_id", return_value=svn_repo),
            patch("codemie.core.dependecies.GitRepo.find_by_id") as git_find,
        ):
            result = get_indexed_repo(svn_fields)

        assert result is svn_repo
        git_find.assert_not_called()

    def test_git_repo_type_raises_when_not_found(self, git_fields):
        with (
            patch("codemie.core.dependecies.GitRepo.find_by_id", return_value=None),
            pytest.raises(KeyError, match="my-repo"),
        ):
            get_indexed_repo(git_fields)

    def test_svn_repo_type_raises_when_not_found(self, svn_fields):
        with (
            patch("codemie.core.dependecies.SVNRepo.find_by_id", return_value=None),
            pytest.raises(KeyError, match="my-repo"),
        ):
            get_indexed_repo(svn_fields)

    def test_git_identifier_used_for_git_lookup(self, git_fields, git_repo):
        with (
            patch("codemie.core.dependecies.GitRepo.identifier_from_fields", return_value="git-id") as git_id,
            patch("codemie.core.dependecies.GitRepo.find_by_id", return_value=git_repo),
        ):
            get_indexed_repo(git_fields)

        git_id.assert_called_once_with(app_id="my-app", name="my-repo", index_type=CodeIndexType.CODE)

    def test_svn_identifier_used_for_svn_lookup(self, svn_fields, svn_repo):
        with (
            patch("codemie.core.dependecies.SVNRepo.identifier_from_fields", return_value="svn-id") as svn_id,
            patch("codemie.core.dependecies.SVNRepo.find_by_id", return_value=svn_repo),
        ):
            get_indexed_repo(svn_fields)

        svn_id.assert_called_once_with(app_id="my-app", name="my-repo", index_type=CodeIndexType.CODE)

    def test_default_repo_type_is_git(self):
        fields = CodeFields(app_name="a", repo_name="r", index_type=CodeIndexType.CODE)
        assert fields.repo_type == "git"


# --- get_repo_from_fields ---


class TestGetRepoFromFields:
    def _make_application(self, name="my-app"):
        app = MagicMock()
        app.name = name
        return app

    def test_git_repo_type_returns_matching_git_repo(self, git_fields, git_repo):
        with (
            patch("codemie.core.dependecies.Application.get_by_id", return_value=self._make_application()),
            patch("codemie.core.dependecies.GitRepo.get_by_app_id", return_value=[git_repo]),
            patch("codemie.core.dependecies.SVNRepo.get_by_app_id") as svn_get,
        ):
            result = get_repo_from_fields(git_fields)

        assert result is git_repo
        svn_get.assert_not_called()

    def test_svn_repo_type_returns_matching_svn_repo(self, svn_fields, svn_repo):
        with (
            patch("codemie.core.dependecies.Application.get_by_id", return_value=self._make_application()),
            patch("codemie.core.dependecies.SVNRepo.get_by_app_id", return_value=[svn_repo]),
            patch("codemie.core.dependecies.GitRepo.get_by_app_id") as git_get,
        ):
            result = get_repo_from_fields(svn_fields)

        assert result is svn_repo
        git_get.assert_not_called()

    def test_git_repo_filtered_by_index_type(self, git_fields, git_repo):
        git_repo.index_type = CodeIndexType.SUMMARY  # mismatch

        with (
            patch("codemie.core.dependecies.Application.get_by_id", return_value=self._make_application()),
            patch("codemie.core.dependecies.GitRepo.get_by_app_id", return_value=[git_repo]),
        ):
            result = get_repo_from_fields(git_fields)

        assert result is None

    def test_svn_repo_filtered_by_index_type(self, svn_fields, svn_repo):
        svn_repo.index_type = CodeIndexType.SUMMARY  # mismatch

        with (
            patch("codemie.core.dependecies.Application.get_by_id", return_value=self._make_application()),
            patch("codemie.core.dependecies.SVNRepo.get_by_app_id", return_value=[svn_repo]),
        ):
            result = get_repo_from_fields(svn_fields)

        assert result is None

    def test_svn_repo_filtered_by_name(self, svn_fields):
        other_svn = MagicMock()
        other_svn.name = "other-repo"
        other_svn.index_type = CodeIndexType.CODE

        with (
            patch("codemie.core.dependecies.Application.get_by_id", return_value=self._make_application()),
            patch("codemie.core.dependecies.SVNRepo.get_by_app_id", return_value=[other_svn]),
        ):
            result = get_repo_from_fields(svn_fields)

        assert result is None
