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

"""
Isolation between config-time pinned integration and use-time per-user mapping.

Invariant: a use-time (per-user) integration choice must never end up in the assistant
config (``MCPServerDetails.settings``) — it only shapes the runtime env for the current
user. A pinned integration always wins and is never replaced by a per-user override, and a
user without their own mapping entry gets no override (base config only).
"""

from unittest.mock import patch

from codemie_tools.base.models import CredentialTypes

from codemie.core.models import ToolConfig
from codemie.rest_api.models.assistant import MCPServerDetails
from codemie.rest_api.models.settings import SettingsBase
from codemie.service.mcp.models import MCPServerConfig
from codemie.service.mcp.toolkit_service import MCPToolkitService, MCP_TOOL_CONFIG_PREFIX


def _server_config() -> MCPServerConfig:
    return MCPServerConfig(command="npx", args=[], env={"BASE": "1"})


def test_use_time_override_never_writes_pinned_settings():
    """Applying the author's own use-time choice touches env only, never the pin field."""
    mcp_server = MCPServerDetails(name="srv")  # settings=None -> not pinned
    server_config = _server_config()
    tools_config = [ToolConfig(name=f"{MCP_TOOL_CONFIG_PREFIX}srv", integration_id="int-author")]

    with (
        patch.object(MCPToolkitService, "_current_user_can_use_integration", return_value=True),
        patch.object(MCPToolkitService, "_resolve_credentials_by_id", return_value={"OVERRIDE": "val"}),
    ):
        MCPToolkitService._apply_server_tools_config(server_config, mcp_server, tools_config, "author-user", "proj-a")

    # The choice is applied only to the runtime env; the assistant config stays non-pinned.
    assert mcp_server.settings is None
    assert server_config.env["OVERRIDE"] == "val"
    assert server_config.env["BASE"] == "1"


def test_pinned_server_ignores_use_time_override():
    """A pinned integration wins for everyone; a stray per-user mapping is skipped."""
    pinned = SettingsBase(
        project_name="proj-a", credential_type=CredentialTypes.ENVIRONMENT_VARS, user_id="author-user"
    )
    mcp_server = MCPServerDetails(name="srv", settings=pinned)
    server_config = _server_config()
    tools_config = [ToolConfig(name=f"{MCP_TOOL_CONFIG_PREFIX}srv", integration_id="int-other")]

    with patch.object(MCPToolkitService, "_resolve_credentials_by_id", return_value={"OVERRIDE": "val"}) as resolve:
        MCPToolkitService._apply_server_tools_config(server_config, mcp_server, tools_config, "other-user", "proj-a")

    resolve.assert_not_called()
    assert "OVERRIDE" not in server_config.env
    assert mcp_server.settings is pinned  # config unchanged


def test_other_user_without_mapping_entry_gets_no_override():
    """A different user whose per-user mapping has no entry for this server keeps base config."""
    mcp_server = MCPServerDetails(name="srv")  # not pinned
    server_config = _server_config()
    # Another user's mapping references a different server, not "srv".
    tools_config = [ToolConfig(name=f"{MCP_TOOL_CONFIG_PREFIX}other-server", integration_id="int-x")]

    with patch.object(MCPToolkitService, "_resolve_credentials_by_id", return_value={"OVERRIDE": "val"}) as resolve:
        MCPToolkitService._apply_server_tools_config(server_config, mcp_server, tools_config, "user-b", "proj-a")

    resolve.assert_not_called()
    assert "OVERRIDE" not in server_config.env


def test_use_time_override_skipped_when_user_lacks_access():
    """Defensive skip: no access under current user -> no override, base config preserved."""
    mcp_server = MCPServerDetails(name="srv")  # not pinned
    server_config = _server_config()
    tools_config = [ToolConfig(name=f"{MCP_TOOL_CONFIG_PREFIX}srv", integration_id="int-forbidden")]

    with (
        patch.object(MCPToolkitService, "_current_user_can_use_integration", return_value=False),
        patch.object(MCPToolkitService, "_resolve_credentials_by_id", return_value={"OVERRIDE": "val"}) as resolve,
    ):
        MCPToolkitService._apply_server_tools_config(server_config, mcp_server, tools_config, "user-b", "proj-a")

    resolve.assert_not_called()
    assert "OVERRIDE" not in server_config.env
    assert mcp_server.settings is None
