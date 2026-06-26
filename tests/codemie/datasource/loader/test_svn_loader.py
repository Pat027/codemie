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

"""Tests for SVNBatchLoader."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from codemie.datasource.loader.svn_client import SVNClientError
from codemie.datasource.loader.svn_loader import SVNBatchLoader, _build_branch_url
from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


# --- _build_branch_url ---


@pytest.mark.parametrize(
    "base_url,branch,expected",
    [
        (
            "https://svn.example.com/repos/myproject",
            "trunk",
            "https://svn.example.com/repos/myproject/trunk",
        ),
        (
            "https://svn.example.com/repos/myproject/",
            "trunk",
            "https://svn.example.com/repos/myproject/trunk",
        ),
        (
            "https://svn.example.com/repos",
            "branches/feature-x",
            "https://svn.example.com/repos/branches/feature-x",
        ),
        (
            "https://svn.example.com/repos",
            "custom",
            "https://svn.example.com/repos/custom",
        ),
        (
            "https://svn.example.com/repos",
            "/trunk/",
            "https://svn.example.com/repos/trunk",
        ),
    ],
)
def test_build_branch_url(base_url, branch, expected):
    assert _build_branch_url(base_url, branch) == expected


# --- SvnClient SSH tunnel flags ---


# --- _is_unsupported_mime_type ---


class TestIsUnsupportedMimeType:
    def test_python_file_is_supported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("script.py") is False

    def test_text_file_is_supported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("readme.txt") is False

    def test_unknown_extension_is_supported(self):
        assert not SVNBatchLoader._is_unsupported_mime_type("file.unknown123")

    def test_pdf_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("document.pdf") is False

    def test_jpg_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("photo.jpg") is False

    def test_docx_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("report.docx") is False

    def test_mp4_video_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("video.mp4") is True

    def test_mp3_is_supported_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("audio.mp3") is False

    def test_tar_archive_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("archive.tar") is True

    def test_rar_archive_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("archive.rar") is True


# --- _decode_content ---


class TestDecodeContent:
    def test_valid_utf8_content_returns_string(self):
        content = "hello world".encode("utf-8")
        result = SVNBatchLoader._decode_content(content, "test.txt")
        assert result == "hello world"

    def test_utf8_with_invalid_bytes_uses_backslashreplace(self):
        content = b"valid \xff bytes"
        result = SVNBatchLoader._decode_content(content, "test.bin")
        assert result is not None
        assert isinstance(result, str)
        assert "valid" in result

    def test_empty_content_returns_empty_string(self):
        result = SVNBatchLoader._decode_content(b"", "empty.txt")
        assert result == ""


# --- Fixtures ---


@pytest.fixture
def basic_creds():
    return SVNCredentials(auth_type=SVNAuthType.BASIC, username="user", password="pass")


@pytest.fixture
def svn_repo_mock():
    repo = MagicMock()
    repo.link = "https://svn.example.com/repos/test"
    repo.branch = "trunk"
    repo.files_filter = ""
    return repo


@pytest.fixture
def loader(svn_repo_mock, basic_creds):
    return SVNBatchLoader(
        svn_repo=svn_repo_mock,
        creds=basic_creds,
        request_uuid="test-uuid",
        datasource_id="ds-123",
    )


# --- _should_skip ---


class TestShouldSkip:
    def test_oversized_file_is_skipped(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("bigfile.dat", 5001) is True

    def test_file_within_size_limit_is_not_skipped(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=True),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("main.py", 1.0) is False

    def test_unsupported_mime_type_is_skipped(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("clip.mp4", 100) is True

    def test_filtered_out_file_is_skipped(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=False),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("code.py", 10) is True

    def test_zero_size_file_is_not_skipped_by_size(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=True),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("empty.py", 0) is False


# --- _process_content ---


class TestProcessContent:
    def test_text_file_returns_document_with_correct_content(self, loader):
        docs = loader._process_content(b"def hello(): pass", "src/module.py", "module.py")
        assert len(docs) == 1
        assert docs[0].page_content == "def hello(): pass"

    def test_text_file_document_has_correct_metadata(self, loader):
        docs = loader._process_content(b"x = 1", "lib/util.py", "util.py")
        assert docs[0].metadata["source"] == "lib/util.py"
        assert docs[0].metadata["file_path"] == "lib/util.py"
        assert docs[0].metadata["file_name"] == "util.py"
        assert docs[0].metadata["file_type"] == ".py"

    def test_decode_returns_none_yields_empty_list(self, loader):
        with patch.object(SVNBatchLoader, "_decode_content", return_value=None):
            docs = loader._process_content(b"data", "bad.txt", "bad.txt")
        assert docs == []

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_pdf_file_routes_to_binary_extraction(self, mock_extract, loader):
        mock_extract.return_value = [Document(page_content="pdf text", metadata={})]
        docs = loader._process_content(b"%PDF-1.4 content", "docs/doc.pdf", "doc.pdf")
        mock_extract.assert_called_once()
        assert len(docs) == 1


# --- _process_binary_file ---


class TestProcessBinaryFile:
    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_sets_correct_metadata_for_pdf(self, mock_extract, loader):
        raw_doc = Document(page_content="extracted text", metadata={"source": "/tmp/tmpXXX.pdf"})
        mock_extract.return_value = [raw_doc]
        result = loader._process_binary_file(b"%PDF-1.4", "sub/report.pdf", "report.pdf")
        assert len(result) == 1
        assert result[0].metadata["source"] == "sub/report.pdf"
        assert result[0].metadata["file_path"] == "sub/report.pdf"
        assert result[0].metadata["file_name"] == "report.pdf"
        assert result[0].metadata["file_type"] == ".pdf"

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_extractor_returns_empty_list(self, mock_extract, loader):
        mock_extract.return_value = []
        assert loader._process_binary_file(b"data", "f.docx", "f.docx") == []

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_passes_correct_args_to_extractor(self, mock_extract, loader):
        mock_extract.return_value = []
        loader._process_binary_file(b"bytes", "sub/doc.docx", "doc.docx")
        mock_extract.assert_called_once_with(
            file_bytes=b"bytes",
            file_name="doc.docx",
            request_uuid="test-uuid",
            datasource_id="ds-123",
        )

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes", side_effect=Exception("parse error"))
    def test_exception_returns_empty_list(self, mock_extract, loader):
        result = loader._process_binary_file(b"bad data", "broken.pdf", "broken.pdf")
        assert result == []


# --- test_connection ---


# --- fetch_remote_stats ---


class TestFetchRemoteStats:
    def test_returns_head_revision(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 55
        with patch("codemie.datasource.loader.svn_loader.SvnClient") as mock_cls:
            mock_cls.svn_is_available.return_value = True
            mock_cls.return_value = mock_client
            result = loader.fetch_remote_stats()
        assert result[SVNBatchLoader.HEAD_REVISION_KEY] == 55

    def test_raises_on_svn_error(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.side_effect = Exception("Connection refused")
        with (
            patch("codemie.datasource.loader.svn_loader.SvnClient") as mock_cls,
            pytest.raises(Exception, match="Connection refused"),
        ):
            mock_cls.svn_is_available.return_value = True
            mock_cls.return_value = mock_client
            loader.fetch_remote_stats()

    def test_documents_count_is_zero(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 1
        with patch("codemie.datasource.loader.svn_loader.SvnClient") as mock_cls:
            mock_cls.svn_is_available.return_value = True
            mock_cls.return_value = mock_client
            result = loader.fetch_remote_stats()
        assert result[SVNBatchLoader.DOCUMENTS_COUNT_KEY] == 0

    def test_raises_runtime_error_when_svn_not_available(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SvnClient") as mock_cls,
            pytest.raises(SVNClientError, match="svn CLI is not installed"),
        ):
            mock_cls.svn_is_available.return_value = False
            loader.fetch_remote_stats()


# --- get_load_stats ---


class TestGetLoadStats:
    def test_initial_stats_are_zero(self, loader):
        stats = loader.get_load_stats()
        assert stats[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 0
        assert stats[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 0

    def test_skipped_count_increments_for_oversized_file(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 100
            loader._should_skip("big.dat", 200)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_skipped_count_increments_for_unsupported_mime(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            loader._should_skip("video.mp4", 10)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_skipped_count_increments_for_filtered_file(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=False),
        ):
            mock_cfg.max_file_size_kb = 5000
            loader._should_skip("excluded.py", 1)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_failed_count_increments_on_fetch_error(self, loader):
        mock_client = MagicMock()
        mock_client.get_file.side_effect = Exception("SVN error")
        loader._fetch_and_process(mock_client, "path/file.py", 1, "file.py", "file.py")
        assert loader.get_load_stats()[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 1

    def test_accumulates_multiple_skips_and_failures(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 100
            loader._should_skip("a.dat", 200)
            loader._should_skip("b.dat", 300)
        mock_client = MagicMock()
        mock_client.get_file.side_effect = Exception("err")
        loader._fetch_and_process(mock_client, "c.py", 1, "c.py", "c.py")
        stats = loader.get_load_stats()
        assert stats[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 2
        assert stats[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 1


# --- lazy_load ---


class TestLazyLoad:
    def test_raises_runtime_error_when_svn_not_available(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SvnClient") as mock_cls,
            pytest.raises(SVNClientError, match="svn CLI is not installed"),
        ):
            mock_cls.svn_is_available.return_value = False
            list(loader.lazy_load())
