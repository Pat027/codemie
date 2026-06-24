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

from codemie_tools.base.models import ToolMetadata
from codemie_tools.core.project_management.xwiki.models import XWikiConfig
from codemie_tools.core.project_management.xwiki.tools_vars import (
    CREATE_PAGE_ATTACHMENT_TOOL,
    CREATE_PAGE_COMMENT_TOOL,
    CREATE_PAGE_TOOL,
    DELETE_PAGE_ATTACHMENT_TOOL,
    DELETE_PAGE_TOOL,
    GET_PAGE_ATTACHMENT_TOOL,
    GET_PAGE_COMMENT_TOOL,
    GET_PAGE_TOOL,
    GET_SPACE_TOOL,
    GET_WIKI_TOOL,
    LIST_PAGE_ATTACHMENTS_TOOL,
    LIST_PAGE_CHILDREN_TOOL,
    LIST_PAGE_COMMENTS_TOOL,
    LIST_PAGE_TAGS_TOOL,
    LIST_PAGES_TOOL,
    LIST_SPACES_TOOL,
    LIST_WIKI_PAGES_TOOL,
    LIST_WIKI_TAGS_TOOL,
    LIST_WIKIS_TOOL,
    MODIFY_PAGE_TOOL,
    READ_PAGE_ATTACHMENT_CONTENT_TOOL,
    SEARCH_SPACE_TOOL,
    SEARCH_WIKI_TOOL,
    SET_PAGE_TAGS_TOOL,
)

ALL_TOOLS = [
    (LIST_WIKIS_TOOL, "xwiki_list_wikis", "List Wikis"),
    (GET_WIKI_TOOL, "xwiki_get_wiki", "Get Wiki"),
    (LIST_SPACES_TOOL, "xwiki_list_spaces", "List Spaces"),
    (GET_SPACE_TOOL, "xwiki_get_space", "Get Space"),
    (LIST_PAGES_TOOL, "xwiki_list_pages", "List Pages"),
    (LIST_WIKI_PAGES_TOOL, "xwiki_list_wiki_pages", "List Wiki Pages"),
    (LIST_PAGE_CHILDREN_TOOL, "xwiki_list_page_children", "List Page Children"),
    (GET_PAGE_TOOL, "xwiki_get_page", "Get Page"),
    (CREATE_PAGE_TOOL, "xwiki_create_page", "Create Page"),
    (MODIFY_PAGE_TOOL, "xwiki_modify_page", "Modify Page"),
    (DELETE_PAGE_TOOL, "xwiki_delete_page", "Delete Page"),
    (LIST_WIKI_TAGS_TOOL, "xwiki_list_wiki_tags", "List Wiki Tags"),
    (LIST_PAGE_TAGS_TOOL, "xwiki_list_page_tags", "List Page Tags"),
    (SET_PAGE_TAGS_TOOL, "xwiki_set_page_tags", "Set Page Tags"),
    (LIST_PAGE_COMMENTS_TOOL, "xwiki_list_page_comments", "List Page Comments"),
    (GET_PAGE_COMMENT_TOOL, "xwiki_get_page_comment", "Get Page Comment"),
    (CREATE_PAGE_COMMENT_TOOL, "xwiki_create_page_comment", "Create Page Comment"),
    (LIST_PAGE_ATTACHMENTS_TOOL, "xwiki_list_page_attachments", "List Page Attachments"),
    (GET_PAGE_ATTACHMENT_TOOL, "xwiki_get_page_attachment", "Get Page Attachment"),
    (READ_PAGE_ATTACHMENT_CONTENT_TOOL, "xwiki_read_attachment_content", "Read Page Attachment Content"),
    (CREATE_PAGE_ATTACHMENT_TOOL, "xwiki_create_page_attachment", "Create Page Attachment"),
    (DELETE_PAGE_ATTACHMENT_TOOL, "xwiki_delete_page_attachment", "Delete Page Attachment"),
    (SEARCH_WIKI_TOOL, "xwiki_search_wiki", "Search Wiki"),
    (SEARCH_SPACE_TOOL, "xwiki_search_space", "Search Space"),
]


class TestAllToolsCommonProperties:
    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_is_tool_metadata(self, tool, expected_name, expected_label):
        assert isinstance(tool, ToolMetadata)

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_name(self, tool, expected_name, expected_label):
        assert tool.name == expected_name

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_label(self, tool, expected_name, expected_label):
        assert tool.label == expected_label

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_settings_config_is_false(self, tool, expected_name, expected_label):
        assert tool.settings_config is False

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_config_class_is_xwiki_config(self, tool, expected_name, expected_label):
        assert tool.config_class is XWikiConfig

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_description_is_non_empty(self, tool, expected_name, expected_label):
        assert tool.description and len(tool.description) > 20

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_user_description_is_non_empty(self, tool, expected_name, expected_label):
        assert tool.user_description and len(tool.user_description) > 10

    @pytest.mark.parametrize("tool, expected_name, expected_label", ALL_TOOLS)
    def test_name_has_xwiki_prefix(self, tool, expected_name, expected_label):
        assert tool.name.startswith("xwiki_")


class TestToolDescriptionContent:
    def test_list_wikis_describes_pagination(self):
        assert "number" in LIST_WIKIS_TOOL.description
        assert "start" in LIST_WIKIS_TOOL.description

    def test_get_space_describes_dot_notation(self):
        assert "dot" in GET_SPACE_TOOL.description.lower() or "." in GET_SPACE_TOOL.description

    def test_get_page_describes_is_markdown(self):
        assert "is_markdown" in GET_PAGE_TOOL.description or "markdown" in GET_PAGE_TOOL.description.lower()

    def test_create_page_describes_syntax_default(self):
        assert "xwiki/2.1" in CREATE_PAGE_TOOL.description

    def test_modify_page_mentions_optional_title(self):
        assert "title" in MODIFY_PAGE_TOOL.description.lower()

    def test_delete_page_warns_irreversible(self):
        assert "irreversible" in DELETE_PAGE_TOOL.description.lower()

    def test_set_page_tags_warns_replaces_all(self):
        desc = SET_PAGE_TAGS_TOOL.description.lower()
        assert "replace" in desc or "replaces" in desc

    def test_create_page_attachment_mentions_input_files(self):
        assert "input_files" in CREATE_PAGE_ATTACHMENT_TOOL.description

    def test_delete_page_attachment_warns_irreversible(self):
        assert "irreversible" in DELETE_PAGE_ATTACHMENT_TOOL.description.lower()

    def test_read_attachment_content_lists_file_types(self):
        desc = READ_PAGE_ATTACHMENT_CONTENT_TOOL.description.lower()
        assert "pdf" in desc
        assert "docx" in desc or "word" in desc

    def test_search_wiki_describes_scope_options(self):
        assert "scope" in SEARCH_WIKI_TOOL.description
        assert "content" in SEARCH_WIKI_TOOL.description

    def test_search_space_references_search_wiki(self):
        assert "xwiki_search_wiki" in SEARCH_SPACE_TOOL.description or "wiki" in SEARCH_SPACE_TOOL.description.lower()


class TestToolUserDescriptions:
    def test_all_user_descriptions_mention_credentials(self):
        # READ_PAGE_ATTACHMENT_CONTENT_TOOL uses a brief one-liner user_description by design
        skip = {READ_PAGE_ATTACHMENT_CONTENT_TOOL.name}
        for tool, _, _ in ALL_TOOLS:
            if tool.name in skip:
                continue
            desc = tool.user_description.lower()
            assert (
                "url" in desc or "token" in desc or "api" in desc
            ), f"{tool.name} user_description does not mention credentials"

    def test_create_page_attachment_mentions_input_files_in_user_desc(self):
        assert "input_files" in CREATE_PAGE_ATTACHMENT_TOOL.user_description
