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

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from codemie.rest_api.models.mcp_config import MCPConfigCreateRequest, MCPConfigUpdateRequest, MCPServerConfigData
from codemie.service.mcp_config_service import MCPConfigService


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.name = "Test User"
    user.username = "test-user"
    return user


def _build_confidential_auth_config(**overrides: Any) -> dict[str, Any]:
    payload = {
        "auth_type": "oauth2",
        "authorization_url": "https://auth.example.com/authorize",
        "token_url": "https://auth.example.com/token",
        "client_id": "client-id",
        "client_type": "confidential",
        "scopes": ["openid"],
        "token_delivery": {"method": "env", "key": "ACCESS_TOKEN"},
    }
    payload.update(overrides)
    return payload


def _build_public_auth_config(**overrides: Any) -> dict[str, Any]:
    payload = _build_confidential_auth_config(client_type="public")
    payload.update(overrides)
    return payload


def _build_create_request(auth_config: dict[str, Any]) -> MCPConfigCreateRequest:
    return MCPConfigCreateRequest(
        name="server-name",
        description=None,
        server_home_url=None,
        source_url=None,
        logo_url=None,
        categories=[],
        config=MCPServerConfigData(auth_config=auth_config),
        required_env_vars=[],
        is_public=False,
    )


def _build_update_request(config: MCPServerConfigData | None = None, **kwargs: Any) -> MCPConfigUpdateRequest:
    return MCPConfigUpdateRequest(config=config, **kwargs)


def _build_response_payload(auth_config: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": "cfg-1",
        "name": "server-name",
        "description": None,
        "server_home_url": None,
        "source_url": None,
        "logo_url": None,
        "categories": [],
        "config": MCPServerConfigData(auth_config=auth_config) if auth_config is not None else None,
        "required_env_vars": [],
        "user_id": "user-1",
        "is_public": True,
        "is_system": True,
        "created_by": None,
        "usage_count": 0,
        "is_active": True,
        "date": None,
        "update_date": None,
    }


def _make_existing_config(auth_config: dict[str, Any] | None) -> MagicMock:
    existing = MagicMock()
    existing.id = "cfg-1"
    existing.name = "server-name"
    existing.user_id = "user-1"
    existing.config = MCPServerConfigData(auth_config=auth_config) if auth_config is not None else None
    existing.model_dump.return_value = _build_response_payload(auth_config)
    return existing


def _assert_auth_config_matches_with_generated_id(
    actual_auth_config: dict[str, Any],
    expected_auth_config: dict[str, Any],
) -> None:
    assert actual_auth_config["id"]
    assert {key: value for key, value in actual_auth_config.items() if key != "id"} == expected_auth_config


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_create_encrypts_confidential_client_secret_and_strips_response_only_metadata(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(
        _build_confidential_auth_config(client_secret="encrypted-secret")
    )
    mock_mcp_config_class.return_value = mock_instance
    mock_encryption_service.encrypt.return_value = "encrypted-secret"
    request = _build_create_request(
        _build_confidential_auth_config(client_secret="plain-secret", has_client_secret=True)
    )

    MCPConfigService.create(request, _make_user())

    persisted_auth_config = mock_mcp_config_class.call_args.kwargs["config"].auth_config
    assert persisted_auth_config["client_secret"] == "encrypted-secret"
    assert "has_client_secret" not in persisted_auth_config
    mock_encryption_service.encrypt.assert_called_once_with("plain-secret")


@patch("codemie.service.mcp_config_service.validate_auth_config_on_save", return_value=[])
@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_create_strips_response_only_metadata_before_validation(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
    mock_validate: MagicMock,
) -> None:
    validated_auth_config: dict[str, Any] = {}

    def _capture_validation_input(raw_dict: dict[str, Any], transport: str) -> list[str]:
        validated_auth_config.update(raw_dict.copy())
        assert transport == "stdio"
        return []

    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(
        _build_confidential_auth_config(client_secret="encrypted-secret")
    )
    mock_mcp_config_class.return_value = mock_instance
    mock_encryption_service.encrypt.return_value = "encrypted-secret"
    mock_validate.side_effect = _capture_validation_input
    request = _build_create_request(
        _build_confidential_auth_config(client_secret="plain-secret", has_client_secret=True)
    )

    MCPConfigService.create(request, _make_user())

    mock_validate.assert_called_once()
    _assert_auth_config_matches_with_generated_id(
        validated_auth_config,
        _build_confidential_auth_config(client_secret="plain-secret"),
    )


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_preserves_existing_encrypted_secret_when_client_secret_is_omitted(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(
        MCPServerConfigData(auth_config=_build_confidential_auth_config(has_client_secret=True))
    )

    MCPConfigService.update("cfg-1", request)

    assert existing.config["auth_config"]["client_secret"] == "stored-secret"
    assert "has_client_secret" not in existing.config["auth_config"]
    mock_encryption_service.encrypt.assert_not_called()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_preserves_existing_encrypted_secret_when_config_is_absent_from_model_fields_set(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_mcp_config_class.get_by_fields.return_value = None
    request = MCPConfigUpdateRequest(name="renamed-server")

    MCPConfigService.update("cfg-1", request)

    assert existing.config.auth_config is not None
    assert existing.config.auth_config["client_secret"] == "stored-secret"
    mock_encryption_service.encrypt.assert_not_called()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
@pytest.mark.parametrize("client_secret", [None, "", "   "])
def test_update_preserves_existing_encrypted_secret_for_missing_value_variants(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
    client_secret: str | None,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(
        MCPServerConfigData(auth_config=_build_confidential_auth_config(client_secret=client_secret))
    )

    MCPConfigService.update("cfg-1", request)

    assert existing.config["auth_config"]["client_secret"] == "stored-secret"
    mock_encryption_service.encrypt.assert_not_called()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_removes_secret_when_auth_config_becomes_none(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(MCPServerConfigData(auth_config=None))

    MCPConfigService.update("cfg-1", request)

    assert existing.config["auth_config"] is None
    mock_encryption_service.encrypt.assert_not_called()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_skips_secret_transformation_when_config_is_explicitly_null(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = MCPConfigUpdateRequest(config=None)

    MCPConfigService.update("cfg-1", request)

    assert existing.config is None
    mock_encryption_service.encrypt.assert_not_called()
    existing.update.assert_called_once_with()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_replaces_existing_encrypted_secret_when_new_plaintext_is_provided(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_encryption_service.encrypt.return_value = "new-encrypted-secret"
    request = _build_update_request(
        MCPServerConfigData(auth_config=_build_confidential_auth_config(client_secret="new-plain-secret"))
    )

    MCPConfigService.update("cfg-1", request)

    assert existing.config["auth_config"]["client_secret"] == "new-encrypted-secret"
    mock_encryption_service.encrypt.assert_called_once_with("new-plain-secret")


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_removes_stored_secret_when_client_type_becomes_public(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(
        MCPServerConfigData(
            auth_config=_build_public_auth_config(client_secret="ignored-secret", has_client_secret=True)
        )
    )

    MCPConfigService.update("cfg-1", request)

    assert "client_secret" not in existing.config["auth_config"]
    assert "has_client_secret" not in existing.config["auth_config"]
    mock_encryption_service.encrypt.assert_not_called()


@patch("codemie.service.mcp_config_service.validate_auth_config_on_save")
@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_skips_secret_transformation_and_validation_when_config_is_unchanged(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
    mock_validate: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_mcp_config_class.get_by_fields.return_value = None
    request = _build_update_request(name="renamed-server")

    MCPConfigService.update("cfg-1", request)

    mock_validate.assert_not_called()
    mock_encryption_service.encrypt.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.validate_auth_config_on_save", return_value=[])
@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_strips_response_only_metadata_before_validation(
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
    mock_validate: MagicMock,
) -> None:
    existing = _make_existing_config(_build_confidential_auth_config(client_secret="stored-secret"))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(
        MCPServerConfigData(auth_config=_build_confidential_auth_config(has_client_secret=True))
    )

    MCPConfigService.update("cfg-1", request)

    validated_auth_config, transport = mock_validate.call_args.args
    assert transport == "stdio"
    _assert_auth_config_matches_with_generated_id(
        validated_auth_config,
        _build_confidential_auth_config(),
    )
    mock_encryption_service.encrypt.assert_not_called()


@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=False)
def test_to_response_strips_client_secret_adds_flag_and_does_not_mutate_source_payload(_: MagicMock) -> None:
    auth_config = _build_confidential_auth_config(client_secret="stored-secret")
    payload = _build_response_payload(auth_config)
    mcp_config = MagicMock()
    mcp_config.model_dump.return_value = payload

    response = MCPConfigService._to_response(mcp_config)

    assert response.config is not None
    assert response.config.auth_config == {**_build_confidential_auth_config(), "has_client_secret": True}
    assert payload["config"].auth_config["client_secret"] == "stored-secret"
    assert "has_client_secret" not in payload["config"].auth_config
    assert response.warnings[0].code == "inactive_auth_config"


@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=False)
def test_to_response_adds_has_client_secret_false_when_no_secret_is_stored(_: MagicMock) -> None:
    auth_config = _build_confidential_auth_config()
    payload = _build_response_payload(auth_config)
    mcp_config = MagicMock()
    mcp_config.model_dump.return_value = payload

    response = MCPConfigService._to_response(mcp_config)

    assert response.config is not None
    assert response.config.auth_config is not None
    assert response.config.auth_config["has_client_secret"] is False
    assert "client_secret" not in response.config.auth_config
