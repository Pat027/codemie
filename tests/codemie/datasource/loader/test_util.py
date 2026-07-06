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
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from codemie.datasource.exceptions import ConnectionException, UnauthorizedException
from codemie.datasource.loader.util import AssistantKBGoogleDocToJsonParser


class TestAssistantKBGoogleDocToJsonParser:
    @pytest.fixture
    def mock_parser(self):
        return AssistantKBGoogleDocToJsonParser(document_id="test_id1", access_token="test_token")

    @pytest.fixture
    def mock_elements(self):
        return [
            {
                "paragraph": {
                    "elements": [{"textRun": {"content": "1.1.2. Title"}}],
                    "paragraphStyle": {"namedStyleType": "heading_1"},
                }
            },
            {"paragraph": {"elements": [{"textRun": {"content": "content1"}}]}},
        ]

    def test_get_element_text(self, mock_parser, mock_elements):
        result = mock_parser.get_element_text(mock_elements[0])

        assert result == "1.1.2. Title"

    def test_get_element_style(self, mock_parser, mock_elements):
        result = mock_parser.get_element_style(mock_elements[0])

        assert result == "heading_1"

    def test_get_articles(self, mock_parser, mock_elements):
        result = mock_parser.get_articles(mock_elements)

        assert result == [{"title": "Title", "content": "content1", "instructions": "", "reference": "1.1.2."}]

    def test_get_titles(self, mock_parser, mock_elements):
        result = mock_parser.get_titles(mock_elements)

        assert result == ["1.1.2. Title"]

    def test_check_document_accessible_success(self, mock_parser):
        mock_service = MagicMock()
        mock_execute = MagicMock(return_value={"documentId": "test_id1"})
        mock_service.documents.return_value.get.return_value.execute = mock_execute

        with patch("codemie.datasource.loader.util.build", return_value=mock_service):
            mock_parser.check_document_accessible()

        mock_service.documents.return_value.get.assert_called_once_with(documentId="test_id1", fields="documentId")
        mock_execute.assert_called_once_with()

    def test_check_document_accessible_raises_on_api_error(self, mock_parser):
        mock_service = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 403
        http_error = HttpError(resp=mock_resp, content=b"Access denied")
        mock_service.documents.return_value.get.return_value.execute.side_effect = http_error

        with patch("codemie.datasource.loader.util.build", return_value=mock_service):
            with pytest.raises(UnauthorizedException, match="Access denied.*don't have permission"):
                mock_parser.check_document_accessible()


class TestHandleGoogleApiError:
    @pytest.fixture
    def mock_parser(self):
        return AssistantKBGoogleDocToJsonParser(document_id="test_doc_id", access_token="test_token")

    def test_handle_403_raises_unauthorized_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 403
        http_error = HttpError(resp=mock_resp, content=b"Forbidden")

        with pytest.raises(UnauthorizedException, match="Access denied.*don't have permission"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_handle_401_raises_unauthorized_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 401
        http_error = HttpError(resp=mock_resp, content=b"Unauthorized")

        with pytest.raises(UnauthorizedException, match="Authentication failed.*credentials are invalid"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_handle_404_raises_connection_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 404
        http_error = HttpError(resp=mock_resp, content=b"Not found")

        with pytest.raises(ConnectionException, match="Document not found.*test_doc_id.*does not exist"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_handle_500_raises_connection_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 500
        http_error = HttpError(resp=mock_resp, content=b"Internal server error")

        with pytest.raises(ConnectionException, match="temporarily unavailable.*try again later"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_handle_503_raises_connection_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 503
        http_error = HttpError(resp=mock_resp, content=b"Service unavailable")

        with pytest.raises(ConnectionException, match="temporarily unavailable.*try again later"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_handle_other_status_raises_connection_exception(self, mock_parser):
        mock_resp = MagicMock()
        mock_resp.status = 429
        http_error = HttpError(resp=mock_resp, content=b"Too many requests")

        with pytest.raises(ConnectionException, match="API request failed \\(HTTP 429\\)"):
            mock_parser._handle_google_api_error(http_error, "test_doc_id", "fetch document")

    def test_get_document_wraps_http_error(self, mock_parser):
        mock_service = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 403
        http_error = HttpError(resp=mock_resp, content=b"Forbidden")
        mock_service.documents.return_value.get.return_value.execute.side_effect = http_error

        with pytest.raises(UnauthorizedException):
            mock_parser.get_document(mock_service, "test_doc_id")
