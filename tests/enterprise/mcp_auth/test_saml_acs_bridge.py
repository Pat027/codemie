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
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codemie.enterprise.mcp_auth import dependencies as mcp_auth_dependencies


def _build_enabled_client() -> TestClient:
    from codemie.enterprise.mcp_auth.router import enabled_router

    app = FastAPI()
    app.include_router(enabled_router)
    return TestClient(app)


def _build_disabled_client() -> TestClient:
    from codemie.enterprise.mcp_auth.router import router as disabled_router

    app = FastAPI()
    app.include_router(disabled_router)
    return TestClient(app)


def _build_auth_config() -> dict[str, object]:
    return {
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


def _build_mcp_config(
    *,
    name: str = "Demo MCP Server",
    auth_config: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="mcp-config-1",
        name=name,
        config=SimpleNamespace(
            url="https://mcp.example.com/server",
            auth_config=auth_config or _build_auth_config(),
        ),
    )


def _build_state_payload(*, ts: int = 4_102_444_800) -> SimpleNamespace:
    return SimpleNamespace(
        auth_config_id="auth-config-1",
        user_id="user-1",
        session_binding_hash="a" * 64,
        ts=ts,
    )


def _build_store_payload(**overrides: object) -> SimpleNamespace:
    payload = {
        "authn_request_id": "request-123",
        "user_id": "user-1",
        "auth_config_id": "auth-config-1",
        "session_binding_hash": "a" * 64,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _install_fake_enterprise_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    class SAMLACSError(Exception):
        pass

    class SAMLAssertionVerificationError(SAMLACSError):
        pass

    class SAMLAssertionExpiredError(SAMLACSError):
        pass

    class SAMLConfigurationError(SAMLACSError):
        pass

    class SAMLACSRuntimeError(SAMLACSError):
        pass

    fake_module = SimpleNamespace(
        SAMLACSError=SAMLACSError,
        SAMLAssertionVerificationError=SAMLAssertionVerificationError,
        SAMLAssertionExpiredError=SAMLAssertionExpiredError,
        SAMLConfigurationError=SAMLConfigurationError,
        SAMLACSRuntimeError=SAMLACSRuntimeError,
    )
    monkeypatch.setitem(sys.modules, "codemie_enterprise", SimpleNamespace(mcp_auth=fake_module))
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_module)


def _set_default_bridge_state(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock, MagicMock]:
    relay_state_store = MagicMock()
    tms = MagicMock()
    consume_acs = MagicMock(
        return_value=SimpleNamespace(subject="user@example.com", attributes={"mail": ["user@example.com"]})
    )

    monkeypatch.setattr(mcp_auth_dependencies, "_redis_encryption", SimpleNamespace(signing_key=b"s" * 32))
    monkeypatch.setattr(mcp_auth_dependencies, "_saml_relay_state_store", relay_state_store)
    monkeypatch.setattr(mcp_auth_dependencies, "_tms", tms)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_decode_and_verify_saml_callback_state",
        lambda relay_state, signing_key: _build_state_payload(),
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_load_callback_mcp_config",
        MagicMock(return_value=_build_mcp_config()),
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_validate_callback_saml_auth_config",
        lambda raw_auth_config, server_name, auth_config_id: SimpleNamespace(**raw_auth_config),
    )
    monkeypatch.setattr(mcp_auth_dependencies, "_consume_saml_acs_response", consume_acs)
    monkeypatch.setattr(
        mcp_auth_dependencies, "build_saml_acs_url", lambda: "https://codemie.example.com/v1/mcp-auth/saml/acs"
    )
    monkeypatch.setattr(mcp_auth_dependencies.config, "FRONTEND_URL", "https://frontend.example.com/app")
    relay_state_store.consume.return_value = _build_store_payload()
    _install_fake_enterprise_exceptions(monkeypatch)

    return relay_state_store, tms, consume_acs


def _assert_has_callback_script(response_text: str) -> None:
    assert '<script src="/v1/mcp-auth/oauth2/callback-page.js"></script>' in response_text
    assert "<script>" not in response_text


def test_disabled_acs_path_preserves_story_1_4_payload() -> None:
    client = _build_disabled_client()

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay"})

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "feature": "MCP Authorization",
        "state": "inactive — enterprise package not installed or MCP_AUTH_ENABLED not set",
        "action": "Enable MCP_AUTH_ENABLED and install the enterprise package",
    }


def test_enabled_acs_keeps_form_fields_optional_and_returns_html() -> None:
    client = _build_enabled_client()

    response = client.post("/v1/mcp-auth/saml/acs")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/html")
    assert "Authentication session could not be verified. Return to CodeMie and try again." in response.text
    _assert_has_callback_script(response.text)


def test_enabled_acs_uses_form_binding_and_shared_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import router as mcp_auth_router

    client = _build_enabled_client()
    captured: dict[str, object] = {}

    def fake_build_saml_callback_response(**kwargs):
        captured.update(kwargs)
        return mcp_auth_dependencies._build_success_callback_response("Demo MCP Server", "auth-config-1")

    monkeypatch.setattr(mcp_auth_router, "build_saml_callback_response", fake_build_saml_callback_response)

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response-blob", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert captured == {"saml_response": "response-blob", "relay_state": "relay-state"}


def test_enabled_acs_invalid_relay_state_returns_secure_error_without_server_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_enabled_client()
    relay_state_store, tms, consume_acs = _set_default_bridge_state(monkeypatch)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_decode_and_verify_saml_callback_state",
        lambda relay_state, signing_key: (_ for _ in ()).throw(
            mcp_auth_dependencies.CallbackPageError(
                "Authentication session could not be verified. Return to CodeMie and try again."
            )
        ),
    )

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "bad-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "Authentication session could not be verified. Return to CodeMie and try again." in response.text
    assert "MCP server:" not in response.text
    assert relay_state_store.consume.call_count == 0
    assert consume_acs.call_count == 0
    assert tms.store.call_count == 0


def test_enabled_acs_expired_relay_state_short_circuits_before_store_consume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_enabled_client()
    relay_state_store, _, consume_acs = _set_default_bridge_state(monkeypatch)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_decode_and_verify_saml_callback_state",
        lambda relay_state, signing_key: _build_state_payload(ts=0),
    )

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "expired-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "Authentication session could not be verified. Return to CodeMie and try again." in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-bridge-error-code="verification_failed"' in response.text
    assert relay_state_store.consume.call_count == 0
    assert consume_acs.call_count == 0


def test_enabled_acs_consumed_relay_state_returns_verification_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_enabled_client()
    relay_state_store, _, consume_acs = _set_default_bridge_state(monkeypatch)
    relay_state_store.consume.return_value = None

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "Authentication session could not be verified. Return to CodeMie and try again." in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-bridge-error-code="verification_failed"' in response.text
    assert consume_acs.call_count == 0


def test_enabled_acs_enforces_relay_state_store_equality_before_enterprise_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_enabled_client()
    relay_state_store, _, consume_acs = _set_default_bridge_state(monkeypatch)
    relay_state_store.consume.return_value = _build_store_payload(user_id="other-user")

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "Authentication session could not be verified. Return to CodeMie and try again." in response.text
    assert consume_acs.call_count == 0


def test_enabled_acs_redis_unavailable_returns_service_message(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_enabled_client()
    _, _, consume_acs = _set_default_bridge_state(monkeypatch)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_consume_saml_relay_state",
        lambda relay_state_store, relay_state, auth_config_id: (_ for _ in ()).throw(
            mcp_auth_dependencies.CallbackPageError(
                "Authentication session could not be verified. Return to CodeMie and try again when the service is available.",
                auth_config_id=auth_config_id,
                bridge_error_code="runtime_error",
            )
        ),
    )

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "try again when the service is available" in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-bridge-error-code="runtime_error"' in response.text
    assert consume_acs.call_count == 0


def test_enabled_acs_missing_config_returns_trusted_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_enabled_client()
    relay_state_store, _, consume_acs = _set_default_bridge_state(monkeypatch)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_load_callback_mcp_config",
        lambda auth_config_id: (_ for _ in ()).throw(
            mcp_auth_dependencies.CallbackPageError(
                "Authentication could not be completed because the MCP server configuration is invalid. "
                "Contact your administrator if the problem persists.",
                auth_config_id=auth_config_id,
                bridge_error_code="configuration_error",
            )
        ),
    )

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "MCP server configuration is invalid" in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-bridge-error-code="configuration_error"' in response.text
    relay_state_store.consume.assert_called_once_with("relay-state")
    assert consume_acs.call_count == 0


def test_enabled_acs_wrong_auth_type_returns_trusted_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_enabled_client()
    relay_state_store, _, consume_acs = _set_default_bridge_state(monkeypatch)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_load_callback_mcp_config",
        MagicMock(return_value=_build_mcp_config(auth_config={"auth_type": "oauth2"})),
    )

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert "MCP server configuration is invalid" in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-bridge-error-code="configuration_error"' in response.text
    relay_state_store.consume.assert_called_once_with("relay-state")
    assert consume_acs.call_count == 0


def test_enabled_acs_uses_reverse_lookup_and_stores_token(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_enabled_client()
    relay_state_store, tms, consume_acs = _set_default_bridge_state(monkeypatch)

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-security-policy"] == "default-src 'none'; script-src 'self'"
    assert response.headers["x-frame-options"] == "DENY"
    assert "Completing authentication..." in response.text
    assert "Authentication complete. Return to CodeMie to continue using the MCP server." in response.text
    assert "response" not in response.text
    assert "relay-state" not in response.text
    assert "user@example.com" not in response.text
    assert 'data-callback-result="success"' in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert 'data-target-origin="https://frontend.example.com"' in response.text
    _assert_has_callback_script(response.text)
    relay_state_store.consume.assert_called_once_with("relay-state")
    assert consume_acs.call_args.kwargs["request_id"] == "request-123"
    tms.store.assert_called_once()


def test_build_saml_callback_response_stores_token_for_same_verified_key(monkeypatch: pytest.MonkeyPatch) -> None:
    relay_state_store = MagicMock(name="relay_state_store")
    redis_encryption = SimpleNamespace(signing_key=b"s" * 32)
    tms = MagicMock(name="tms")
    state_payload = _build_state_payload()
    relay_state_data = _build_store_payload()
    mcp_config = _build_mcp_config()
    raw_auth_config = _build_auth_config()
    auth_config = SimpleNamespace(**raw_auth_config)
    token_data = SimpleNamespace(subject="user@example.com", attributes={"mail": ["user@example.com"]})
    validate_state_age = MagicMock(name="validate_state_age")
    validate_state_match = MagicMock(name="validate_state_match")
    consume_acs = MagicMock(name="consume_acs", return_value=token_data)

    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_require_initialized_saml_callback_dependencies",
        lambda: (relay_state_store, redis_encryption, tms),
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_decode_and_verify_saml_callback_state",
        lambda relay_state, signing_key: state_payload,
    )
    monkeypatch.setattr(mcp_auth_dependencies, "_validate_saml_callback_state_age", validate_state_age)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_consume_saml_relay_state",
        lambda relay_state_store_arg, relay_state, auth_config_id: relay_state_data,
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_validate_saml_callback_state_matches_store",
        validate_state_match,
    )
    monkeypatch.setattr(mcp_auth_dependencies, "_load_callback_mcp_config", lambda auth_config_id: mcp_config)
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_load_raw_callback_saml_config",
        lambda mcp_config_arg, auth_config_id: raw_auth_config,
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "_validate_callback_saml_auth_config",
        lambda raw_auth_config_arg, server_name, auth_config_id: auth_config,
    )
    monkeypatch.setattr(
        mcp_auth_dependencies,
        "build_saml_acs_url",
        lambda: "https://codemie.example.com/v1/mcp-auth/saml/acs",
    )
    monkeypatch.setattr(mcp_auth_dependencies, "_consume_saml_acs_response", consume_acs)
    monkeypatch.setattr(mcp_auth_dependencies.config, "FRONTEND_URL", "https://frontend.example.com/app")

    response = mcp_auth_dependencies._build_saml_callback_response(
        saml_response="response-blob",
        relay_state="relay-state",
    )

    assert response.status_code == status.HTTP_200_OK
    validate_state_age.assert_called_once_with(state_payload)
    validate_state_match.assert_called_once_with(state_payload, relay_state_data)
    consume_acs.assert_called_once_with(
        auth_config=auth_config,
        saml_response="response-blob",
        relay_state="relay-state",
        acs_url="https://codemie.example.com/v1/mcp-auth/saml/acs",
        request_id="request-123",
    )
    tms.store.assert_called_once_with("user-1", "auth-config-1", token_data)


@pytest.mark.parametrize(
    ("exception_name", "message", "bridge_error_code"),
    [
        (
            "SAMLAssertionVerificationError",
            "SAML assertion validation failed: invalid signature",
            "verification_failed",
        ),
        (
            "SAMLAssertionVerificationError",
            "SAML assertion validation failed: audience mismatch",
            "verification_failed",
        ),
        ("SAMLAssertionExpiredError", "SAML assertion validation failed: assertion expired", "session_expired"),
        ("SAMLConfigurationError", "ignored", "configuration_error"),
        ("SAMLACSError", "ignored", "runtime_error"),
        (
            "SAMLACSRuntimeError",
            "Authentication could not be completed. Return to CodeMie and try again.",
            "runtime_error",
        ),
    ],
)
def test_enabled_acs_maps_enterprise_failures_to_callback_copy(
    monkeypatch: pytest.MonkeyPatch,
    exception_name: str,
    message: str,
    bridge_error_code: str,
) -> None:
    client = _build_enabled_client()
    _, _, consume_acs = _set_default_bridge_state(monkeypatch)
    fake_module = sys.modules["codemie_enterprise.mcp_auth"]
    exception_type = getattr(fake_module, exception_name)
    consume_acs.side_effect = exception_type(message)

    response = client.post("/v1/mcp-auth/saml/acs", data={"SAMLResponse": "response", "RelayState": "relay-state"})

    assert response.status_code == status.HTTP_200_OK
    expected_message = (
        "Authentication could not be completed because the MCP server configuration is invalid. "
        "Contact your administrator if the problem persists."
        if exception_name == "SAMLConfigurationError"
        else "Authentication could not be completed. Return to CodeMie and try again."
        if exception_name == "SAMLACSError"
        else "Authentication could not be completed. Return to CodeMie and try again."
        if exception_name == "SAMLACSRuntimeError"
        else message
    )
    assert expected_message in response.text
    assert 'data-auth-config-id="auth-config-1"' in response.text
    assert f'data-bridge-error-code="{bridge_error_code}"' in response.text
