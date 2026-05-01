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

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codemie.core.exceptions import MCPAuthenticationRequiredException
from codemie.rest_api.main import mcp_auth_required_handler


app = FastAPI()
app.add_exception_handler(MCPAuthenticationRequiredException, mcp_auth_required_handler)


@app.get("/requires-auth")
def requires_auth() -> None:
    raise MCPAuthenticationRequiredException(
        {
            "error": "authentication_required",
            "servers": [
                {
                    "mcp_config_id": "mcp-1",
                    "mcp_config_name": "GitHub",
                    "mcp_server_name": "GitHub",
                    "auth_config_id": "auth-1",
                    "auth_type": "oauth2",
                    "as_hostname": "login.example.com",
                    "status": "authentication_required",
                    "error_context": None,
                    "initiate_url": "/v1/mcp-auth/oauth2/initiate",
                }
            ],
        }
    )


client = TestClient(app)


def test_mcp_auth_required_handler_returns_payload_with_explicit_401() -> None:
    response = client.get("/requires-auth")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "error": "authentication_required",
        "servers": [
            {
                "mcp_config_id": "mcp-1",
                "mcp_config_name": "GitHub",
                "mcp_server_name": "GitHub",
                "auth_config_id": "auth-1",
                "auth_type": "oauth2",
                "as_hostname": "login.example.com",
                "status": "authentication_required",
                "error_context": None,
                "initiate_url": "/v1/mcp-auth/oauth2/initiate",
            }
        ],
    }
