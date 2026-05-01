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

from __future__ import annotations

import json
from unittest.mock import MagicMock

from codemie.core.exceptions import MCPAuthenticationRequiredException
from codemie.workflows.constants import END_NODE, NEXT_KEY
from codemie.workflows.nodes.base_node import BaseNode


class _AuthenticationRequiredNode(BaseNode[dict[str, object]]):
    def execute(self, state_schema: type[dict[str, object]], execution_context: dict) -> object:
        # Intentionally validates the flat bridge payload in isolation; Story 3.6 aggregation happens in core.
        raise MCPAuthenticationRequiredException(
            {
                "auth_config_id": "auth-1",
                "mcp_config_id": "mcp-1",
                "mcp_server_name": "server-1",
                "status": "session_expired",
                "auth_type": "oauth2",
                "error_context": None,
            }
        )

    def get_task(self, state_schema: type[dict[str, object]], *arg, **kwargs) -> str:
        return "authenticate"


class _SAMLSessionExpiredNode(BaseNode[dict[str, object]]):
    def execute(self, state_schema: type[dict[str, object]], execution_context: dict) -> object:
        raise MCPAuthenticationRequiredException(
            {
                "auth_config_id": "auth-2",
                "mcp_config_id": "mcp-2",
                "mcp_server_name": "server-2",
                "status": "session_expired",
                "auth_type": "saml",
                "error_context": "SAML session expired",
            }
        )

    def get_task(self, state_schema: type[dict[str, object]], *arg, **kwargs) -> str:
        return "authenticate"


def test_base_node_preserves_status_payload_through_json_boundary() -> None:
    workflow_execution_service = MagicMock()
    workflow_execution_service.start_state.return_value = "state-1"
    callback = MagicMock()
    node = _AuthenticationRequiredNode(
        callbacks=[callback],
        workflow_execution_service=workflow_execution_service,
        thought_queue=MagicMock(),
        node_name="Auth Node",
    )

    result = node({})

    workflow_execution_service.finish_state.assert_called_once()
    workflow_execution_service.mark_authentication_required.assert_called_once()

    finish_call = workflow_execution_service.finish_state.call_args.kwargs
    mark_call = workflow_execution_service.mark_authentication_required.call_args.kwargs
    assert finish_call["output"] == mark_call["output"]
    assert json.loads(mark_call["output"]) == {
        "auth_config_id": "auth-1",
        "mcp_config_id": "mcp-1",
        "mcp_server_name": "server-1",
        "status": "session_expired",
        "auth_type": "oauth2",
        "error_context": None,
        "node_name": "Auth Node",
    }
    callback.on_node_fail.assert_called_once()
    assert result == {NEXT_KEY: [END_NODE]}


def test_base_node_preserves_saml_session_expired_payload_through_json_boundary() -> None:
    workflow_execution_service = MagicMock()
    workflow_execution_service.start_state.return_value = "state-1"
    callback = MagicMock()
    node = _SAMLSessionExpiredNode(
        callbacks=[callback],
        workflow_execution_service=workflow_execution_service,
        thought_queue=MagicMock(),
        node_name="Auth Node",
    )

    result = node({})

    workflow_execution_service.finish_state.assert_called_once()
    workflow_execution_service.mark_authentication_required.assert_called_once()

    finish_call = workflow_execution_service.finish_state.call_args.kwargs
    mark_call = workflow_execution_service.mark_authentication_required.call_args.kwargs
    assert finish_call["output"] == mark_call["output"]
    assert json.loads(mark_call["output"]) == {
        "auth_config_id": "auth-2",
        "mcp_config_id": "mcp-2",
        "mcp_server_name": "server-2",
        "status": "session_expired",
        "auth_type": "saml",
        "error_context": "SAML session expired",
        "node_name": "Auth Node",
    }
    callback.on_node_fail.assert_called_once()
    assert result == {NEXT_KEY: [END_NODE]}
