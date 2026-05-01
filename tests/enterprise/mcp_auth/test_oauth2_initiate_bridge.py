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

import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codemie.core.exceptions import ExtendedHTTPException
from codemie.enterprise.mcp_auth.router import authenticate as router_authenticate
from codemie.rest_api.main import extended_http_exception_handler
from codemie.rest_api.security.user import User


def _build_app():
    from codemie.enterprise.mcp_auth.router import enabled_router

    app = FastAPI()
    app.include_router(enabled_router)
    app.add_exception_handler(ExtendedHTTPException, extended_http_exception_handler)
    return app, TestClient(app)


def _build_user(**overrides: object) -> User:
    payload = {
        "id": "user-1",
        "name": "Test User",
        "auth_token": "Bearer token-123",
    }
    payload.update(overrides)
    user = User(**payload)
    user.is_admin = bool(payload.get("is_admin", False))
    user.is_maintainer = bool(payload.get("is_maintainer", False))
    return user


def _build_mcp_config(*, owner_id: str = "user-1", is_public: bool = False, url: str = "https://mcp.example.com/"):
    return SimpleNamespace(
        id="mcp-config-1",
        user_id=owner_id,
        is_public=is_public,
        config=SimpleNamespace(
            url=url,
            auth_config={
                "id": "auth-config-1",
                "auth_type": "oauth2",
                "authorization_url": "https://idp.example.com/oauth2/authorize",
                "token_url": "https://idp.example.com/oauth2/token",
                "client_id": "client-1",
                "client_type": "public",
                "scopes": ["openid", "profile"],
                "token_delivery": {"method": "header"},
            },
        ),
    )


@pytest.fixture
def app_client():
    return _build_app()


def test_initiate_route_authenticates_loads_config_and_rejects_client_auth_config_id(monkeypatch, app_client) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    app, client = app_client
    user = _build_user()
    mcp_config = _build_mcp_config()
    captured: dict[str, object] = {}

    def fake_build_oauth2_initiate_response(**kwargs):
        captured.update(kwargs)
        data = {
            "auth_url": "https://idp.example.com/oauth2/authorize?state=abc",
            "redirect_uri_hostname": "localhost:8080",
            "localhost_warning": True,
        }
        result = SimpleNamespace(**data)
        result.model_dump = lambda: data
        return result

    app.dependency_overrides[router_authenticate] = lambda: user
    monkeypatch.setattr(
        mcp_auth_router.MCPConfig, "find_by_id", lambda config_id: mcp_config if config_id == mcp_config.id else None
    )
    monkeypatch.setattr(mcp_auth_router, "build_oauth2_initiate_response", fake_build_oauth2_initiate_response)

    response = client.post(
        "/v1/mcp-auth/oauth2/initiate",
        json={"mcp_config_id": mcp_config.id, "auth_config_id": "client-controlled-value"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "auth_url": "https://idp.example.com/oauth2/authorize?state=abc",
        "redirect_uri_hostname": "localhost:8080",
        "localhost_warning": True,
    }
    assert captured["user"] == user
    assert captured["auth_config_id"] == "auth-config-1"
    assert captured["mcp_server_url"] == "https://mcp.example.com/"


def test_initiate_route_rejects_private_non_owned_config(monkeypatch, app_client) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    app, client = app_client
    app.dependency_overrides[router_authenticate] = lambda: _build_user(id="other-user", auth_token="Bearer token-123")
    monkeypatch.setattr(
        mcp_auth_router.MCPConfig, "find_by_id", lambda config_id: _build_mcp_config(owner_id="owner-user")
    )

    response = client.post("/v1/mcp-auth/oauth2/initiate", json={"mcp_config_id": "mcp-config-1"})

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["message"] == "Access denied"


def test_initiate_route_returns_not_found_for_missing_config(monkeypatch, app_client) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    app, client = app_client
    app.dependency_overrides[router_authenticate] = lambda: _build_user()
    monkeypatch.setattr(mcp_auth_router.MCPConfig, "find_by_id", lambda config_id: None)

    response = client.post("/v1/mcp-auth/oauth2/initiate", json={"mcp_config_id": "missing-config"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["message"] == "MCP configuration not found"


def test_initiate_route_fails_closed_when_auth_token_missing(monkeypatch, app_client) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies

    app, client = app_client
    app.dependency_overrides[router_authenticate] = lambda: _build_user(auth_token=None)
    monkeypatch.setattr(mcp_auth_router.MCPConfig, "find_by_id", lambda config_id: _build_mcp_config())
    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "http://localhost:8080")

    response = client.post("/v1/mcp-auth/oauth2/initiate", json={"mcp_config_id": "mcp-config-1"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        response.json()["error"]["details"]
        == "Authenticated MCP auth initiation requires a bearer token for session binding."
    )


def test_initiate_route_returns_redirect_hostname_and_localhost_warning(monkeypatch, app_client) -> None:
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    app, client = app_client
    app.dependency_overrides[router_authenticate] = lambda: _build_user()
    monkeypatch.setattr(mcp_auth_router.MCPConfig, "find_by_id", lambda config_id: _build_mcp_config())
    monkeypatch.setattr(mcp_auth_dependencies, "_pkce_store", SimpleNamespace())
    monkeypatch.setattr(mcp_auth_dependencies, "_redis_encryption", SimpleNamespace(signing_key=b"s" * 32))

    captured: dict[str, object] = {}

    def fake_build_oauth2_initiate_response(**kwargs):
        captured.update(kwargs)
        data = {
            "auth_url": "https://idp.example.com/oauth2/authorize?state=abc",
            "redirect_uri_hostname": kwargs["redirect_uri_hostname"],
            "localhost_warning": kwargs["localhost_warning"],
        }
        result = SimpleNamespace(**data)
        result.model_dump = lambda: data
        return result

    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "http://localhost:8080")
    monkeypatch.setitem(
        sys.modules,
        "codemie_enterprise.mcp_auth",
        SimpleNamespace(
            MCPAuthRedisUnavailable=RuntimeError,
            OAuth2AuthConfig=SimpleNamespace(model_validate=lambda raw: raw),
            build_oauth2_initiate_response=fake_build_oauth2_initiate_response,
        ),
    )

    response = client.post("/v1/mcp-auth/oauth2/initiate", json={"mcp_config_id": "mcp-config-1"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["redirect_uri_hostname"] == "localhost:8080"
    assert response.json()["localhost_warning"] is True
    assert captured["redirect_uri"] == "http://localhost:8080/v1/mcp-auth/oauth2/callback"


def test_build_redirect_uri_returns_full_netloc_for_non_default_https_port(monkeypatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies

    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "https://api.example.com:9443")

    redirect_uri, redirect_uri_hostname, localhost_warning = mcp_auth_dependencies.build_redirect_uri()

    assert redirect_uri == "https://api.example.com:9443/v1/mcp-auth/oauth2/callback"
    assert redirect_uri_hostname == "api.example.com:9443"
    assert localhost_warning is False


def test_build_redirect_uri_marks_normal_https_as_not_localhost(monkeypatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies

    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "https://api.example.com")

    redirect_uri, redirect_uri_hostname, localhost_warning = mcp_auth_dependencies.build_redirect_uri()

    assert redirect_uri == "https://api.example.com/v1/mcp-auth/oauth2/callback"
    assert redirect_uri_hostname == "api.example.com"
    assert localhost_warning is False


@pytest.mark.parametrize(
    ("callback_base_url", "expected_hostname"),
    [
        ("http://127.0.0.1:8080", "127.0.0.1:8080"),
        ("http://[::1]:8080", "[::1]:8080"),
    ],
)
def test_build_redirect_uri_marks_localhost_family_hosts(
    monkeypatch, callback_base_url: str, expected_hostname: str
) -> None:
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies

    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", callback_base_url)

    redirect_uri, redirect_uri_hostname, localhost_warning = mcp_auth_dependencies.build_redirect_uri()

    assert redirect_uri.endswith("/v1/mcp-auth/oauth2/callback")
    assert redirect_uri_hostname == expected_hostname
    assert localhost_warning is True


def test_build_redirect_uri_rejects_http_non_localhost(monkeypatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies

    monkeypatch.setattr(mcp_auth_dependencies.config, "CALLBACK_API_BASE_URL", "http://api.example.com:8080")

    with pytest.raises(ExtendedHTTPException) as exc_info:
        mcp_auth_dependencies.build_redirect_uri()

    assert exc_info.value.code == status.HTTP_400_BAD_REQUEST
    assert "Redirect URI must use HTTPS" in exc_info.value.details


def test_disabled_router_still_returns_story_1_4_payload(app_client) -> None:
    from codemie.enterprise.mcp_auth.router import router as disabled_router

    app = FastAPI()
    app.include_router(disabled_router)
    disabled_client = TestClient(app)

    response = disabled_client.post("/v1/mcp-auth/oauth2/initiate")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "feature": "MCP Authorization",
        "state": "inactive — enterprise package not installed or MCP_AUTH_ENABLED not set",
        "action": "Enable MCP_AUTH_ENABLED and install the enterprise package",
    }


def test_derive_resource_uri_normalizes_default_port_root_slash_and_query_fragment() -> None:
    from codemie.enterprise.mcp_auth.dependencies import derive_resource_uri

    assert derive_resource_uri("https://mcp.example.com:443/?q=1#frag") == "https://mcp.example.com"
    assert derive_resource_uri("https://MCP.Example.Com/path?q=1#frag") == "https://mcp.example.com/path"
    assert derive_resource_uri("https://mcp.example.com:8443/") == "https://mcp.example.com:8443"
