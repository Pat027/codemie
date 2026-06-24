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

from codemie_tools.core.project_management.xwiki.toolkit import (
    XWIKI_TOOLKIT_NAME,
    XWikiToolkit,
    XWikiToolkitUI,
)

EXPECTED_TOOL_NAMES = {
    # Wikis
    "xwiki_list_wikis",
    "xwiki_get_wiki",
    # Spaces
    "xwiki_list_spaces",
    "xwiki_get_space",
    # Pages
    "xwiki_list_pages",
    "xwiki_list_wiki_pages",
    "xwiki_list_page_children",
    "xwiki_get_page",
    "xwiki_create_page",
    "xwiki_modify_page",
    "xwiki_delete_page",
    # Tags
    "xwiki_list_wiki_tags",
    "xwiki_list_page_tags",
    "xwiki_set_page_tags",
    # Comments
    "xwiki_list_page_comments",
    "xwiki_get_page_comment",
    "xwiki_create_page_comment",
    # Attachments
    "xwiki_list_page_attachments",
    "xwiki_get_page_attachment",
    "xwiki_read_attachment_content",
    "xwiki_create_page_attachment",
    "xwiki_delete_page_attachment",
    # Search
    "xwiki_search_wiki",
    "xwiki_search_space",
}


class TestXWikiToolkit:
    def test_get_definition_returns_ui(self):
        result = XWikiToolkit.get_definition()
        assert isinstance(result, XWikiToolkitUI)

    def test_get_definition_toolkit_name(self):
        result = XWikiToolkit.get_definition()
        assert result.toolkit == XWIKI_TOOLKIT_NAME

    def test_get_definition_tool_count(self):
        result = XWikiToolkit.get_definition()
        assert len(result.tools) == 24

    def test_get_definition_label(self):
        result = XWikiToolkit.get_definition()
        assert result.label == "xWiki"

    def test_get_definition_settings_config_enabled(self):
        result = XWikiToolkit.get_definition()
        assert result.settings_config is True


class TestXWikiToolkitUI:
    def test_all_tool_names_present(self):
        ui = XWikiToolkitUI()
        tool_names = {tool.name for tool in ui.tools}
        assert tool_names == EXPECTED_TOOL_NAMES

    def test_no_duplicate_tool_names(self):
        ui = XWikiToolkitUI()
        names = [tool.name for tool in ui.tools]
        assert len(names) == len(set(names))

    def test_wiki_tools_present(self):
        ui = XWikiToolkitUI()
        tool_names = {tool.name for tool in ui.tools}
        assert {"xwiki_list_wikis", "xwiki_get_wiki"}.issubset(tool_names)

    def test_page_tools_present(self):
        ui = XWikiToolkitUI()
        tool_names = {tool.name for tool in ui.tools}
        page_tools = {
            "xwiki_list_pages",
            "xwiki_list_wiki_pages",
            "xwiki_list_page_children",
            "xwiki_get_page",
            "xwiki_create_page",
            "xwiki_modify_page",
            "xwiki_delete_page",
        }
        assert page_tools.issubset(tool_names)

    def test_attachment_tools_present(self):
        ui = XWikiToolkitUI()
        tool_names = {tool.name for tool in ui.tools}
        attachment_tools = {
            "xwiki_list_page_attachments",
            "xwiki_get_page_attachment",
            "xwiki_read_attachment_content",
            "xwiki_create_page_attachment",
            "xwiki_delete_page_attachment",
        }
        assert attachment_tools.issubset(tool_names)

    def test_search_tools_present(self):
        ui = XWikiToolkitUI()
        tool_names = {tool.name for tool in ui.tools}
        assert {"xwiki_search_wiki", "xwiki_search_space"}.issubset(tool_names)
