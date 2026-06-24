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

from langchain_core.tools import ToolException

from .models import XWikiConfig


def build_spaces_path(space: str) -> str:
    """Convert dot-separated space name to xWiki REST URL path segments.

    "Main"         -> "/spaces/Main"
    "Main.Sandbox" -> "/spaces/Main/spaces/Sandbox"
    """
    parts = [p.strip() for p in space.split(".") if p.strip()]
    return "".join(f"/spaces/{p}" for p in parts)


def validate_creds(config: XWikiConfig) -> None:
    if not config.url:
        raise ToolException("xWiki URL is required. Please configure the xWiki integration.")
    if not config.token:
        raise ToolException("xWiki token is required. Please configure the xWiki integration.")
