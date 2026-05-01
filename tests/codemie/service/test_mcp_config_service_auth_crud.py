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
from sqlalchemy.exc import IntegrityError

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.mcp_config import MCPConfigCreateRequest, MCPConfigUpdateRequest, MCPServerConfigData
from codemie.service.mcp_config_service import MCPConfigService, _AUTH_CONFIG_ID_INDEX


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.name = "Test User"
    user.username = "test-user"
    return user


def _build_valid_oauth2_auth_config(**overrides: Any) -> dict[str, Any]:
    payload = {
        "auth_type": "oauth2",
        "authorization_url": "https://auth.example.com/authorize",
        "token_url": "https://auth.example.com/token",
        "client_id": "client-id",
        "client_type": "public",
        "scopes": ["openid", "profile"],
        "token_delivery": {"method": "env", "key": "ACCESS_TOKEN"},
    }
    payload.update(overrides)
    return payload


def _build_create_request(auth_config: dict[str, Any] | None = None) -> MCPConfigCreateRequest:
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


def _build_response_payload(config: MCPServerConfigData | None = None) -> dict[str, Any]:
    return {
        "id": "cfg-1",
        "name": "server-name",
        "description": None,
        "server_home_url": None,
        "source_url": None,
        "logo_url": None,
        "categories": [],
        "config": config,
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


def _make_existing_config(config: MCPServerConfigData | None = None) -> MagicMock:
    existing = MagicMock()
    existing.id = "cfg-1"
    existing.name = "server-name"
    existing.user_id = "user-1"
    existing.config = config or MCPServerConfigData()
    existing.model_dump.return_value = _build_response_payload(existing.config)
    return existing


def _make_auth_config_integrity_error() -> IntegrityError:
    orig = Exception(f'duplicate key value violates unique constraint "{_AUTH_CONFIG_ID_INDEX}"')
    return IntegrityError("INSERT INTO mcp_configs ...", {}, orig)


def _get_stored_auth_config(config: MCPServerConfigData | dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None

    if isinstance(config, dict):
        auth_config = config.get("auth_config")
        return auth_config if isinstance(auth_config, dict) else None

    return config.auth_config


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4", return_value="generated-id")
def test_create_generates_missing_auth_config_id(mock_uuid4: MagicMock, mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    request = _build_create_request(_build_valid_oauth2_auth_config())
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(request.config)
    mock_mcp_config_class.return_value = mock_instance

    MCPConfigService.create(request, _make_user())

    assert request.config.auth_config is not None
    assert request.config.auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()
    mock_instance.save.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4")
def test_create_generates_blank_auth_config_id(mock_uuid4: MagicMock, mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    request = _build_create_request(_build_valid_oauth2_auth_config(id="   "))
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(request.config)
    mock_mcp_config_class.return_value = mock_instance
    mock_uuid4.return_value = "generated-id"

    MCPConfigService.create(request, _make_user())

    assert request.config.auth_config is not None
    assert request.config.auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4", return_value="generated-id")
def test_create_generates_empty_string_auth_config_id(mock_uuid4: MagicMock, mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    request = _build_create_request(_build_valid_oauth2_auth_config(id=""))
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(request.config)
    mock_mcp_config_class.return_value = mock_instance

    MCPConfigService.create(request, _make_user())

    assert request.config.auth_config is not None
    assert request.config.auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4", return_value="generated-id")
def test_create_generates_none_auth_config_id(mock_uuid4: MagicMock, mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    request = _build_create_request(_build_valid_oauth2_auth_config(id=None))
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(request.config)
    mock_mcp_config_class.return_value = mock_instance

    MCPConfigService.create(request, _make_user())

    assert request.config.auth_config is not None
    assert request.config.auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4")
def test_create_preserves_custom_auth_config_id(mock_uuid4: MagicMock, mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    request = _build_create_request(_build_valid_oauth2_auth_config(id="custom-id"))
    mock_instance.save.return_value = MagicMock(id="cfg-1")
    mock_instance.model_dump.return_value = _build_response_payload(request.config)
    mock_mcp_config_class.return_value = mock_instance

    MCPConfigService.create(request, _make_user())

    assert request.config.auth_config is not None
    assert request.config.auth_config["id"] == "custom-id"
    mock_uuid4.assert_not_called()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config", return_value=True)
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=True)
def test_update_rejects_auth_config_id_change_when_credentials_exist(
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="old-id")))
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="new-id")))

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.update("cfg-1", request)

    assert exc_info.value.code == 422
    assert exc_info.value.message == "auth_config.id cannot be changed after credentials have been stored"
    mock_has_credentials.assert_called_once_with("old-id")
    existing.update.assert_not_called()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config", return_value=False)
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=True)
def test_update_allows_auth_config_id_change_when_no_credentials_exist(
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="new-id"))
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="old-id")))
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    response = MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    assert response.id == "cfg-1"
    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["id"] == "new-id"
    mock_has_credentials.assert_called_once_with("old-id")
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
def test_update_translates_duplicate_auth_config_id_to_409(mock_mcp_config_class: MagicMock) -> None:
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="dup-id"))
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="old-id")))
    mock_mcp_config_class.find_by_id.return_value = existing
    existing.update.side_effect = _make_auth_config_integrity_error()

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    assert exc_info.value.code == 409
    assert exc_info.value.message == "auth_config.id already in use"


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config")
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=True)
def test_update_preserves_existing_auth_config_id_without_immutability_check_when_id_matches(
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    auth_config = _build_valid_oauth2_auth_config(id="stable-id")
    existing = _make_existing_config(MCPServerConfigData(auth_config=auth_config.copy()))
    existing.model_dump.return_value = _build_response_payload(existing.config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(MCPServerConfigData(auth_config=auth_config.copy())))

    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["id"] == "stable-id"
    mock_has_credentials.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config")
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=True)
def test_update_restores_existing_auth_config_id_when_request_omits_it(
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="stable-id")))
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config())
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["id"] == "stable-id"
    mock_has_credentials.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.uuid.uuid4", return_value="generated-id")
def test_update_generates_id_when_adding_auth_config_for_first_time(
    mock_uuid4: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config())
    existing = _make_existing_config(MCPServerConfigData())
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config")
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=False)
def test_update_allows_auth_config_id_change_when_enterprise_auth_unavailable(
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="new-id"))
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="old-id")))
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    mock_has_credentials.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_invalidates_credentials_before_persisting_when_auth_config_removed(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    call_order: list[str] = []

    def _record_invalidate(auth_config_id: str) -> None:
        assert auth_config_id == "remove-id"
        call_order.append("invalidate")

    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="remove-id")))
    existing.update.side_effect = lambda: call_order.append("update")
    existing.model_dump.return_value = _build_response_payload(MCPServerConfigData(auth_config=None))
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_invalidate.side_effect = _record_invalidate

    MCPConfigService.update("cfg-1", _build_update_request(MCPServerConfigData(auth_config=None)))

    assert call_order == ["invalidate", "update"]
    mock_invalidate.assert_called_once_with("remove-id")
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_invalidates_credentials_before_persisting_when_config_removed(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    call_order: list[str] = []

    def _record_invalidate(auth_config_id: str) -> None:
        assert auth_config_id == "remove-id"
        call_order.append("invalidate")

    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="remove-id")))
    existing.update.side_effect = lambda: call_order.append("update")
    existing.model_dump.return_value = _build_response_payload(None)
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_invalidate.side_effect = _record_invalidate

    MCPConfigService.update("cfg-1", MCPConfigUpdateRequest(config=None))

    assert call_order == ["invalidate", "update"]
    mock_invalidate.assert_called_once_with("remove-id")
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch(
    "codemie.service.mcp_config_service.invalidate_credentials_for_auth_config",
    side_effect=RuntimeError("boom"),
)
def test_update_rejects_auth_config_removal_when_invalidation_fails(
    _: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="remove-id")))
    mock_mcp_config_class.find_by_id.return_value = existing

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.update("cfg-1", _build_update_request(MCPServerConfigData(auth_config=None)))

    assert exc_info.value.code == 503
    assert exc_info.value.message == "Token invalidation failed. Configuration not saved. Please retry."
    existing.update.assert_not_called()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_rejects_config_removal_when_invalidation_fails(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="remove-id")))
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_invalidate.side_effect = RuntimeError("boom")

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.update("cfg-1", MCPConfigUpdateRequest(config=None))

    assert exc_info.value.code == 503
    assert exc_info.value.message == "Token invalidation failed. Configuration not saved. Please retry."
    existing.update.assert_not_called()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_invalidates_credentials_before_persisting_when_auth_config_changes(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    call_order: list[str] = []

    def _record_invalidate(auth_config_id: str) -> None:
        assert auth_config_id == "stable-id"
        call_order.append("invalidate")

    updated_config = MCPServerConfigData(
        auth_config=_build_valid_oauth2_auth_config(id="stable-id", scopes=["openid", "profile", "email"])
    )
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="stable-id")))
    existing.model_dump.return_value = _build_response_payload(updated_config)
    existing.update.side_effect = lambda: call_order.append("update")
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_invalidate.side_effect = _record_invalidate

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    assert call_order == ["invalidate", "update"]
    mock_invalidate.assert_called_once_with("stable-id")
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_skips_invalidation_when_no_previous_auth_config_id_exists(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config()))
    existing.model_dump.return_value = _build_response_payload(MCPServerConfigData(auth_config=None))
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(MCPServerConfigData(auth_config=None)))

    mock_invalidate.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_does_not_invalidate_credentials_for_noop_auth_config_save(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    unchanged_auth_config = _build_valid_oauth2_auth_config(id="stable-id")
    updated_config = MCPServerConfigData(auth_config=unchanged_auth_config.copy())
    existing = _make_existing_config(MCPServerConfigData(auth_config=unchanged_auth_config.copy()))
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    mock_invalidate.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
@patch("codemie.service.mcp_config_service.uuid.uuid4", return_value="generated-id")
def test_update_generates_id_for_first_auth_config_creation_without_invalidation(
    mock_uuid4: MagicMock,
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config())
    existing = _make_existing_config(MCPServerConfigData())
    existing.model_dump.return_value = _build_response_payload(updated_config)
    mock_mcp_config_class.find_by_id.return_value = existing

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["id"] == "generated-id"
    mock_uuid4.assert_called_once_with()
    mock_invalidate.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch(
    "codemie.service.mcp_config_service.invalidate_credentials_for_auth_config",
    side_effect=RuntimeError("boom"),
)
def test_update_rejects_auth_config_change_when_invalidation_fails(
    _: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    updated_config = MCPServerConfigData(
        auth_config=_build_valid_oauth2_auth_config(
            id="stable-id", token_delivery={"method": "header", "key": "Authorization"}
        )
    )
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="stable-id")))
    mock_mcp_config_class.find_by_id.return_value = existing

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    assert exc_info.value.code == 503
    assert exc_info.value.message == "Token invalidation failed. Configuration not saved. Please retry."
    existing.update.assert_not_called()


@patch.object(MCPConfigService, "encryption_service")
@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_does_not_invalidate_when_has_client_secret_echo_and_omitted_secret_normalize_unchanged(
    mock_invalidate: MagicMock,
    mock_mcp_config_class: MagicMock,
    mock_encryption_service: MagicMock,
) -> None:
    existing = _make_existing_config(
        MCPServerConfigData(
            auth_config=_build_valid_oauth2_auth_config(
                id="stable-id",
                client_type="confidential",
                client_secret="stored-secret",
            )
        )
    )
    mock_mcp_config_class.find_by_id.return_value = existing
    request = _build_update_request(
        MCPServerConfigData(
            auth_config=_build_valid_oauth2_auth_config(
                id="stable-id",
                client_type="confidential",
                has_client_secret=True,
            )
        )
    )

    MCPConfigService.update("cfg-1", request)

    stored_auth_config = _get_stored_auth_config(existing.config)
    assert stored_auth_config is not None
    assert stored_auth_config["client_secret"] == "stored-secret"
    mock_encryption_service.encrypt.assert_not_called()
    mock_invalidate.assert_not_called()
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.MCPConfig")
@patch("codemie.service.mcp_config_service.has_any_credentials_for_auth_config", return_value=False)
@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=True)
@patch("codemie.service.mcp_config_service.invalidate_credentials_for_auth_config")
def test_update_invalidates_previous_id_before_persisting_when_id_change_allowed(
    mock_invalidate: MagicMock,
    _: MagicMock,
    mock_has_credentials: MagicMock,
    mock_mcp_config_class: MagicMock,
) -> None:
    call_order: list[str] = []

    def _record_invalidate(auth_config_id: str) -> None:
        assert auth_config_id == "old-id"
        call_order.append("invalidate")

    updated_config = MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="new-id"))
    existing = _make_existing_config(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="old-id")))
    existing.model_dump.return_value = _build_response_payload(updated_config)
    existing.update.side_effect = lambda: call_order.append("update")
    mock_mcp_config_class.find_by_id.return_value = existing
    mock_invalidate.side_effect = _record_invalidate

    MCPConfigService.update("cfg-1", _build_update_request(updated_config))

    assert call_order == ["invalidate", "update"]
    mock_has_credentials.assert_called_once_with("old-id")
    mock_invalidate.assert_called_once_with("old-id")
    existing.update.assert_called_once_with()


@patch("codemie.service.mcp_config_service.is_mcp_auth_enabled", return_value=False)
def test_to_response_keeps_inactive_auth_warning_top_level(_: MagicMock) -> None:
    payload = _build_response_payload(MCPServerConfigData(auth_config=_build_valid_oauth2_auth_config(id="auth-id")))
    mcp_config = MagicMock()
    mcp_config.model_dump.return_value = payload

    response = MCPConfigService._to_response(mcp_config)

    assert response.warnings
    assert response.warnings[0].code == "inactive_auth_config"
    assert response.config is not None
    assert response.config.auth_config is not None
    assert "warnings" not in response.config.auth_config


@patch("codemie.service.mcp_config_service.MCPConfig")
def test_create_translates_duplicate_auth_config_id_to_409(mock_mcp_config_class: MagicMock) -> None:
    mock_mcp_config_class.get_by_fields.return_value = None
    mock_instance = MagicMock()
    mock_mcp_config_class.return_value = mock_instance
    mock_instance.save.side_effect = _make_auth_config_integrity_error()

    with pytest.raises(ExtendedHTTPException) as exc_info:
        MCPConfigService.create(_build_create_request(_build_valid_oauth2_auth_config(id="dup-id")), _make_user())

    assert exc_info.value.code == 409
