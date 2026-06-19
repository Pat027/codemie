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

"""Tests for SVNDatasourceProcessor."""

from unittest.mock import MagicMock, patch

import pytest

from codemie.core.constants import CodeIndexType
from codemie.datasource.svn.svn_datasource_processor import SVNDatasourceProcessor
from codemie.datasource.loader.svn_loader import SVNBatchLoader
from codemie.rest_api.security.user import User

_TEST_USER = User(id="user-1", username="test@example.com")


@pytest.fixture
def svn_repo():
    repo = MagicMock()
    repo.name = "test_repo"
    repo.index_type = CodeIndexType.CODE
    repo.app_id = "my_app"
    repo.last_indexed_revision = None
    repo.get_identifier.return_value = "my_app-test_repo-svn-code"
    return repo


@pytest.fixture
def mock_user():
    return _TEST_USER


@pytest.fixture
def processor(svn_repo, mock_user):
    with patch("codemie.datasource.base_datasource_processor.ElasticSearchClient.get_client"):
        return SVNDatasourceProcessor(repo=svn_repo, user=mock_user)


# --- create_processor ---


class TestCreateProcessor:
    def test_code_index_type_returns_svn_processor(self, svn_repo, mock_user):
        svn_repo.index_type = CodeIndexType.CODE
        with patch("codemie.datasource.base_datasource_processor.ElasticSearchClient.get_client"):
            result = SVNDatasourceProcessor.create_processor(svn_repo=svn_repo, user=mock_user)
        assert isinstance(result, SVNDatasourceProcessor)

    @patch(
        "codemie.datasource.code.code_summary_datasource_processor.CodeSummaryDatasourceProcessor.__init__",
        return_value=None,
    )
    def test_summary_index_type_returns_summary_processor(self, mock_init, svn_repo, mock_user):
        svn_repo.index_type = CodeIndexType.SUMMARY
        with patch("codemie.datasource.base_datasource_processor.ElasticSearchClient.get_client"):
            from codemie.datasource.code.code_summary_datasource_processor import CodeSummaryDatasourceProcessor

            result = SVNDatasourceProcessor.create_processor(svn_repo=svn_repo, user=mock_user)
        assert isinstance(result, CodeSummaryDatasourceProcessor)

    @patch(
        "codemie.datasource.code.code_summary_datasource_processor.CodeChunkSummaryDatasourceProcessor.__init__",
        return_value=None,
    )
    def test_chunk_summary_index_type_returns_chunk_processor(self, mock_init, svn_repo, mock_user):
        svn_repo.index_type = CodeIndexType.CHUNK_SUMMARY
        with patch("codemie.datasource.base_datasource_processor.ElasticSearchClient.get_client"):
            from codemie.datasource.code.code_summary_datasource_processor import CodeChunkSummaryDatasourceProcessor

            result = SVNDatasourceProcessor.create_processor(svn_repo=svn_repo, user=mock_user)
        assert isinstance(result, CodeChunkSummaryDatasourceProcessor)

    def test_unsupported_index_type_raises_not_implemented(self, svn_repo, mock_user):
        svn_repo.index_type = "unknown_type"
        with pytest.raises(NotImplementedError, match="Unsupported SVN index type"):
            SVNDatasourceProcessor.create_processor(svn_repo=svn_repo, user=mock_user)


# --- _index_name ---


class TestIndexName:
    def test_returns_repo_get_identifier(self, processor, svn_repo):
        assert processor._index_name == svn_repo.get_identifier()


# --- _processing_batch_size ---


class TestProcessingBatchSize:
    def test_returns_svn_config_loader_batch_size(self, processor):
        with patch("codemie.datasource.svn.svn_datasource_processor.SVN_CONFIG") as mock_cfg:
            mock_cfg.loader_batch_size = 10
            assert processor._processing_batch_size == 10


# --- _on_process_end ---


class TestOnProcessEnd:
    def test_updates_last_indexed_revision_from_loader_stats(self, processor, svn_repo):
        mock_loader = MagicMock()
        mock_loader.fetch_remote_stats.return_value = {SVNBatchLoader.HEAD_REVISION_KEY: 99}
        processor.loader = mock_loader
        processor._on_process_end()
        assert svn_repo.last_indexed_revision == 99

    def test_saves_repo_after_update(self, processor, svn_repo):
        mock_loader = MagicMock()
        mock_loader.fetch_remote_stats.return_value = {SVNBatchLoader.HEAD_REVISION_KEY: 42}
        processor.loader = mock_loader
        processor._on_process_end()
        svn_repo.save.assert_called()

    def test_does_not_update_revision_when_key_absent(self, processor, svn_repo):
        mock_loader = MagicMock()
        mock_loader.fetch_remote_stats.return_value = {}
        processor.loader = mock_loader
        svn_repo.last_indexed_revision = 50
        processor._on_process_end()
        assert svn_repo.last_indexed_revision == 50

    def test_no_loader_does_not_raise(self, processor, svn_repo):
        processor.loader = None
        processor._on_process_end()
        svn_repo.save.assert_called()

    def test_saves_repo_even_when_no_loader(self, processor, svn_repo):
        processor.loader = None
        processor._on_process_end()
        svn_repo.save.assert_called_once()
