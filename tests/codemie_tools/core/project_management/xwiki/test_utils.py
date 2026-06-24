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

import pytest
from langchain_core.tools import ToolException

from codemie_tools.core.project_management.xwiki.models import XWikiConfig
from codemie_tools.core.project_management.xwiki.utils import build_spaces_path, validate_creds


class TestBuildSpacesPath:
    def test_single_space(self):
        assert build_spaces_path("Main") == "/spaces/Main"

    def test_nested_space(self):
        assert build_spaces_path("Main.Sandbox") == "/spaces/Main/spaces/Sandbox"

    def test_three_levels(self):
        assert build_spaces_path("Main.Sandbox.Sub") == "/spaces/Main/spaces/Sandbox/spaces/Sub"

    def test_extra_whitespace_around_dots(self):
        assert build_spaces_path("Main . Sandbox") == "/spaces/Main/spaces/Sandbox"

    def test_empty_string(self):
        assert build_spaces_path("") == ""

    def test_single_dot_ignored(self):
        assert build_spaces_path(".Main.") == "/spaces/Main"


class TestValidateCreds:
    def test_valid_config(self, xwiki_config):
        validate_creds(xwiki_config)  # should not raise

    def test_missing_url_raises(self):
        config = XWikiConfig(url="", token="token")
        with pytest.raises(ToolException, match="xWiki URL is required"):
            validate_creds(config)

    def test_none_url_raises(self):
        config = XWikiConfig(token="token")
        config.url = None
        with pytest.raises(ToolException, match="xWiki URL is required"):
            validate_creds(config)

    def test_missing_token_raises(self):
        config = XWikiConfig(url="https://wiki.example.com", token="")
        with pytest.raises(ToolException, match="xWiki token is required"):
            validate_creds(config)

    def test_none_token_raises(self):
        config = XWikiConfig(url="https://wiki.example.com", token="placeholder")
        config.token = None
        with pytest.raises(ToolException, match="xWiki token is required"):
            validate_creds(config)
