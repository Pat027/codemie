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

from fastapi import FastAPI, Response, status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from codemie.core.exceptions import ExtendedHTTPException
from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies
from codemie.rest_api.main import extended_http_exception_handler
from codemie.rest_api.models.mcp_config import MCPConfig


def _build_enabled_app() -> tuple[FastAPI, TestClient]:
    from codemie.enterprise.mcp_auth.router import enabled_router

    app = FastAPI()
    app.include_router(enabled_router)
    app.add_exception_handler(ExtendedHTTPException, extended_http_exception_handler)
    return app, TestClient(app)


def _build_disabled_client() -> TestClient:
    from codemie.enterprise.mcp_auth.router import router as disabled_router

    app = FastAPI()
    app.include_router(disabled_router)
    return TestClient(app)


def _build_saml_auth_config(**overrides: object) -> dict[str, object]:
    payload = {
        "id": "auth-config-1",
        "auth_type": "saml",
        "sso_url": "https://idp.example.com/sso",
        "entity_id": "urn:codemie:test:sp",
        "idp_entity_id": "https://idp.example.com/metadata",
        "idp_x509cert": "CERTDATA",
        "saml_credential_attribute": "mail",
        "saml_session_ttl": 3600,
        "token_delivery": {"method": "header"},
    }
    payload.update(overrides)
    return payload


def _build_mcp_config(auth_config: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id="mcp-config-1",
        name="Demo MCP Server",
        config=SimpleNamespace(auth_config=auth_config),
    )


def test_disabled_metadata_route_preserves_story_1_4_payload() -> None:
    client = _build_disabled_client()

    response = client.get("/v1/mcp-auth/saml/metadata")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "feature": "MCP Authorization",
        "state": "inactive — enterprise package not installed or MCP_AUTH_ENABLED not set",
        "action": "Enable MCP_AUTH_ENABLED and install the enterprise package",
    }


def test_enabled_metadata_route_is_public_and_delegates_optional_query_param(monkeypatch) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    _, client = _build_enabled_app()
    captured: dict[str, object] = {}

    def fake_build_saml_metadata_response(*, auth_config_id: str | None) -> Response:
        captured["auth_config_id"] = auth_config_id
        return Response("<EntityDescriptor/>", media_type="application/samlmetadata+xml")

    monkeypatch.setattr(mcp_auth_router, "build_saml_metadata_response", fake_build_saml_metadata_response)

    response = client.get("/v1/mcp-auth/saml/metadata")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("application/samlmetadata+xml")
    assert response.text == "<EntityDescriptor/>"
    assert captured == {"auth_config_id": None}


def test_enabled_metadata_route_returns_400_for_missing_query_param() -> None:
    _, client = _build_enabled_app()

    response = client.get("/v1/mcp-auth/saml/metadata")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["message"] == "Invalid MCP auth configuration"
    assert (
        response.json()["error"]["details"]
        == "Query parameter auth_config_id is required for SAML metadata generation."
    )


def test_enabled_metadata_route_returns_400_for_whitespace_only_query_param(monkeypatch) -> None:
    _, client = _build_enabled_app()
    lookup_called = False

    def fake_get_by_auth_config_id(auth_config_id: str):
        nonlocal lookup_called
        lookup_called = True
        return None

    monkeypatch.setattr(MCPConfig, "get_by_auth_config_id", fake_get_by_auth_config_id)

    response = client.get("/v1/mcp-auth/saml/metadata", params={"auth_config_id": "   "})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["message"] == "Invalid MCP auth configuration"
    assert (
        response.json()["error"]["details"]
        == "Query parameter auth_config_id is required for SAML metadata generation."
    )
    assert lookup_called is False


def test_enabled_metadata_route_returns_404_for_unknown_auth_config_id(monkeypatch) -> None:
    _, client = _build_enabled_app()
    monkeypatch.setattr(MCPConfig, "get_by_auth_config_id", lambda auth_config_id: None)

    response = client.get("/v1/mcp-auth/saml/metadata", params={"auth_config_id": "missing-auth-config"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["message"] == "MCP configuration not found"


def test_enabled_metadata_route_returns_exact_400_for_non_saml_config(monkeypatch) -> None:
    _, client = _build_enabled_app()
    monkeypatch.setattr(
        MCPConfig,
        "get_by_auth_config_id",
        lambda auth_config_id: _build_mcp_config(
            {
                "id": auth_config_id,
                "auth_type": "oauth2",
                "authorization_url": "https://idp.example.com/oauth2/authorize",
                "token_url": "https://idp.example.com/oauth2/token",
                "client_id": "client-1",
                "client_type": "public",
                "scopes": ["openid"],
                "token_delivery": {"method": "header"},
            }
        ),
    )

    response = client.get("/v1/mcp-auth/saml/metadata", params={"auth_config_id": "auth-config-1"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["message"] == "SP metadata is only available for SAML auth configurations"


def test_enabled_metadata_route_returns_400_for_missing_persisted_auth_config(monkeypatch) -> None:
    _, client = _build_enabled_app()
    monkeypatch.setattr(MCPConfig, "get_by_auth_config_id", lambda auth_config_id: _build_mcp_config(None))

    response = client.get("/v1/mcp-auth/saml/metadata", params={"auth_config_id": "auth-config-1"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["message"] == "Invalid MCP auth configuration"
    assert response.json()["error"]["details"] == "MCP configuration does not include a persisted auth_config."


def test_enabled_metadata_route_returns_400_for_invalid_saml_config(monkeypatch) -> None:
    class InvalidSAMLAuthConfig(BaseModel):
        sso_url: str

    _, client = _build_enabled_app()
    monkeypatch.setattr(
        MCPConfig,
        "get_by_auth_config_id",
        lambda auth_config_id: _build_mcp_config(
            {
                "id": auth_config_id,
                "auth_type": "saml",
                "entity_id": "urn:codemie:test:sp",
                "idp_entity_id": "https://idp.example.com/metadata",
                "idp_x509cert": "CERTDATA",
                "saml_credential_attribute": "mail",
                "saml_session_ttl": 3600,
                "token_delivery": {"method": "header"},
            }
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "codemie_enterprise.mcp_auth",
        SimpleNamespace(
            SAMLAuthConfig=SimpleNamespace(model_validate=lambda raw: InvalidSAMLAuthConfig.model_validate(raw)),
            build_saml_sp_metadata=lambda **kwargs: "<unused/>",
        ),
    )

    response = client.get("/v1/mcp-auth/saml/metadata", params={"auth_config_id": "auth-config-1"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["message"] == "Invalid MCP auth configuration"
    assert "Stored SAML auth_config is invalid" in response.json()["error"]["details"]


def test_build_saml_metadata_response_returns_xml_and_delegates_to_enterprise(monkeypatch) -> None:
    validated_auth_config = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        MCPConfig,
        "get_by_auth_config_id",
        lambda auth_config_id: _build_mcp_config(_build_saml_auth_config(id=auth_config_id)),
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "build_saml_acs_url",
        lambda: "https://codemie.example.com/v1/mcp-auth/saml/acs",
    )

    def fake_build_saml_sp_metadata(**kwargs):
        captured.update(kwargs)
        return "<EntityDescriptor/>"

    monkeypatch.setitem(
        sys.modules,
        "codemie_enterprise.mcp_auth",
        SimpleNamespace(
            SAMLAuthConfig=SimpleNamespace(model_validate=lambda raw: validated_auth_config),
            build_saml_sp_metadata=fake_build_saml_sp_metadata,
        ),
    )

    response = mcp_auth_dependencies.build_saml_metadata_response(auth_config_id="auth-config-1")

    assert response.status_code == status.HTTP_200_OK
    assert response.media_type == "application/samlmetadata+xml"
    assert response.body == b"<EntityDescriptor/>"
    assert captured == {
        "auth_config": validated_auth_config,
        "acs_url": "https://codemie.example.com/v1/mcp-auth/saml/acs",
    }


def test_build_saml_metadata_response_translates_generation_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        MCPConfig,
        "get_by_auth_config_id",
        lambda auth_config_id: _build_mcp_config(_build_saml_auth_config(id=auth_config_id)),
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "build_saml_acs_url",
        lambda: "https://codemie.example.com/v1/mcp-auth/saml/acs",
    )
    monkeypatch.setitem(
        sys.modules,
        "codemie_enterprise.mcp_auth",
        SimpleNamespace(
            SAMLAuthConfig=SimpleNamespace(model_validate=lambda raw: raw),
            build_saml_sp_metadata=lambda **kwargs: (_ for _ in ()).throw(ValueError("metadata invalid")),
        ),
    )

    try:
        mcp_auth_dependencies.build_saml_metadata_response(auth_config_id="auth-config-1")
    except ExtendedHTTPException as exc:
        assert exc.code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.message == "SP metadata generation failed"
        assert exc.details == "metadata invalid"
    else:
        raise AssertionError("Expected ExtendedHTTPException")
