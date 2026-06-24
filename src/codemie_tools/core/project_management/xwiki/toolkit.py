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

from typing import List

from codemie_tools.base.base_toolkit import DiscoverableToolkit
from codemie_tools.base.models import Tool, ToolKit

from .tools import (
    CreatePageAttachmentTool,
    CreatePageCommentTool,
    CreatePageTool,
    DeletePageAttachmentTool,
    DeletePageTool,
    GetPageAttachmentTool,
    GetPageCommentTool,
    GetPageTool,
    GetSpaceTool,
    GetWikiTool,
    ListPageAttachmentsTool,
    ListPageChildrenTool,
    ListPageCommentsTool,
    ListPageTagsTool,
    ListPagesTool,
    ListSpacesTool,
    ListWikiPagesTool,
    ListWikiTagsTool,
    ListWikisTool,
    ModifyPageTool,
    ReadPageAttachmentContentTool,
    SearchSpaceTool,
    SearchWikiTool,
    SetPageTagsTool,
)
from .tools_vars import (
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

XWIKI_TOOLKIT_NAME = "XWiki"


class XWikiToolkitUI(ToolKit):
    toolkit: str = XWIKI_TOOLKIT_NAME
    tools: List[Tool] = [
        # Wikis
        Tool.from_metadata(LIST_WIKIS_TOOL, tool_class=ListWikisTool),
        Tool.from_metadata(GET_WIKI_TOOL, tool_class=GetWikiTool),
        # Spaces
        Tool.from_metadata(LIST_SPACES_TOOL, tool_class=ListSpacesTool),
        Tool.from_metadata(GET_SPACE_TOOL, tool_class=GetSpaceTool),
        # Pages
        Tool.from_metadata(LIST_PAGES_TOOL, tool_class=ListPagesTool),
        Tool.from_metadata(LIST_WIKI_PAGES_TOOL, tool_class=ListWikiPagesTool),
        Tool.from_metadata(LIST_PAGE_CHILDREN_TOOL, tool_class=ListPageChildrenTool),
        Tool.from_metadata(GET_PAGE_TOOL, tool_class=GetPageTool),
        Tool.from_metadata(CREATE_PAGE_TOOL, tool_class=CreatePageTool),
        Tool.from_metadata(MODIFY_PAGE_TOOL, tool_class=ModifyPageTool),
        Tool.from_metadata(DELETE_PAGE_TOOL, tool_class=DeletePageTool),
        # Tags
        Tool.from_metadata(LIST_WIKI_TAGS_TOOL, tool_class=ListWikiTagsTool),
        Tool.from_metadata(LIST_PAGE_TAGS_TOOL, tool_class=ListPageTagsTool),
        Tool.from_metadata(SET_PAGE_TAGS_TOOL, tool_class=SetPageTagsTool),
        # Comments
        Tool.from_metadata(LIST_PAGE_COMMENTS_TOOL, tool_class=ListPageCommentsTool),
        Tool.from_metadata(GET_PAGE_COMMENT_TOOL, tool_class=GetPageCommentTool),
        Tool.from_metadata(CREATE_PAGE_COMMENT_TOOL, tool_class=CreatePageCommentTool),
        # Attachments
        Tool.from_metadata(LIST_PAGE_ATTACHMENTS_TOOL, tool_class=ListPageAttachmentsTool),
        Tool.from_metadata(GET_PAGE_ATTACHMENT_TOOL, tool_class=GetPageAttachmentTool),
        Tool.from_metadata(READ_PAGE_ATTACHMENT_CONTENT_TOOL, tool_class=ReadPageAttachmentContentTool),
        Tool.from_metadata(CREATE_PAGE_ATTACHMENT_TOOL, tool_class=CreatePageAttachmentTool),
        Tool.from_metadata(DELETE_PAGE_ATTACHMENT_TOOL, tool_class=DeletePageAttachmentTool),
        # Search
        Tool.from_metadata(SEARCH_WIKI_TOOL, tool_class=SearchWikiTool),
        Tool.from_metadata(SEARCH_SPACE_TOOL, tool_class=SearchSpaceTool),
    ]
    label: str = "xWiki"
    settings_config: bool = True


class XWikiToolkit(DiscoverableToolkit):
    @classmethod
    def get_definition(cls) -> XWikiToolkitUI:
        return XWikiToolkitUI()
