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

from unittest.mock import patch

import pytest

from codemie.datasource.loader.google_doc_loader import GoogleDocLoader


class TestGoogleDocLoaderCheckAccessible:
    def test_check_accessible_delegates_to_parser(self):
        loader = GoogleDocLoader(product_id="doc123")
        with patch.object(loader.kb_document_parser, "check_document_accessible") as mock_check:
            loader.check_accessible()
            mock_check.assert_called_once_with()

    def test_check_accessible_propagates_exception(self):
        loader = GoogleDocLoader(product_id="doc123")
        with patch.object(
            loader.kb_document_parser,
            "check_document_accessible",
            side_effect=Exception("not found"),
        ):
            with pytest.raises(Exception, match="not found"):
                loader.check_accessible()

    def test_fetch_remote_stats_still_calls_parse_doc(self):
        """fetch_remote_stats is unchanged — full parse still happens when called."""
        loader = GoogleDocLoader(product_id="doc123")
        articles = [{"content": "a"}]
        titles = ["t"]
        with patch.object(
            loader.kb_document_parser,
            "parse_doc",
            return_value=(articles, titles, "doc123"),
        ) as mock_parse:
            stats = loader.fetch_remote_stats()
            mock_parse.assert_called_once()
            assert stats[loader.DOCUMENTS_COUNT_KEY] == 1
