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

"""
Story 1.2 — AC #2 service-layer tests.

Verifies that MCPConfigService.create() and MCPConfigService.update() translate
an IntegrityError on ix_mcp_configs_auth_config_id into a deterministic 409
ExtendedHTTPException rather than surfacing an unhandled DB exception as a 500.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.mcp_config import MCPServerConfigData
from codemie.service.mcp_config_service import (
    MCPConfigService,
    _is_auth_config_id_conflict,
    _AUTH_CONFIG_ID_INDEX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUTH_CONFIG_CONSTRAINT = "ix_mcp_configs_auth_config_id"


def _make_auth_config_integrity_error() -> IntegrityError:
    """Construct an IntegrityError whose string representation contains the constraint name."""
    orig = Exception(f'duplicate key value violates unique constraint "{_AUTH_CONFIG_CONSTRAINT}"')
    return IntegrityError(
        "INSERT INTO mcp_configs ...",
        {},
        orig,
    )


def _make_unrelated_integrity_error() -> IntegrityError:
    """Construct an IntegrityError for a different constraint (e.g. name+user uniqueness)."""
    orig = Exception("duplicate key value violates unique constraint \"ix_mcp_configs_name_user\"")
    return IntegrityError("INSERT INTO mcp_configs ...", {}, orig)


def _make_mock_user(user_id: str = "user-1") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.name = "Test User"
    user.username = "testuser"
    return user


def _make_valid_auth_config() -> dict:
    return {
        "auth_type": "oauth2",
        "authorization_url": "https://auth.example.com/authorize",
        "token_url": "https://auth.example.com/token",
        "client_id": "client-id",
        "client_type": "public",
        "scopes": ["openid"],
        "token_delivery": {"method": "env", "key": "ACCESS_TOKEN"},
    }


def _make_create_request(name: str = "my-server") -> MagicMock:
    req = MagicMock()
    req.name = name
    req.description = None
    req.server_home_url = None
    req.source_url = None
    req.logo_url = None
    req.categories = []
    req.config = MCPServerConfigData()
    req.required_env_vars = []
    req.is_public = False
    return req


def _make_update_request(auth_config: dict | None = None) -> MagicMock:
    req = MagicMock()
    req.name = None
    req.model_dump.return_value = {"config": MCPServerConfigData(auth_config=auth_config)}
    return req


# ---------------------------------------------------------------------------
# create() — AC #2
# ---------------------------------------------------------------------------


class TestMCPConfigServiceCreateAuthConfigConflict:
    """create() raises 409 when a duplicate auth_config.id is detected."""

    @patch("codemie.service.mcp_config_service.MCPConfig")
    def test_create_raises_409_on_auth_config_id_duplicate(self, mock_mcp_config_class):
        """AC #2: duplicate auth_config.id → 409 CONFLICT with stable message."""
        mock_mcp_config_class.get_by_fields.return_value = None  # no name conflict
        mock_instance = MagicMock()
        mock_mcp_config_class.return_value = mock_instance
        mock_instance.save.side_effect = _make_auth_config_integrity_error()

        with pytest.raises(ExtendedHTTPException) as exc_info:
            MCPConfigService.create(_make_create_request(), _make_mock_user())

        exc = exc_info.value
        assert exc.code == 409
        assert "auth_config.id" in exc.message.lower() or "already in use" in exc.message.lower()

    @patch("codemie.service.mcp_config_service.MCPConfig")
    def test_create_re_raises_unrelated_integrity_error(self, mock_mcp_config_class):
        """Unrelated IntegrityError (e.g. name+user index) is not swallowed."""
        mock_mcp_config_class.get_by_fields.return_value = None
        mock_instance = MagicMock()
        mock_mcp_config_class.return_value = mock_instance
        mock_instance.save.side_effect = _make_unrelated_integrity_error()

        with pytest.raises(IntegrityError):
            MCPConfigService.create(_make_create_request(), _make_mock_user())

    @patch("codemie.service.mcp_config_service.MCPConfig")
    def test_create_succeeds_when_no_integrity_error(self, mock_mcp_config_class):
        """Successful create() returns a response without raising."""
        mock_mcp_config_class.get_by_fields.return_value = None
        mock_instance = MagicMock()
        mock_mcp_config_class.return_value = mock_instance
        mock_instance.save.return_value = MagicMock(id="new-id")
        mock_instance.model_dump.return_value = {
            "id": "new-id",
            "name": "my-server",
            "description": None,
            "server_home_url": None,
            "source_url": None,
            "logo_url": None,
            "categories": [],
            "config": None,
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

        result = MCPConfigService.create(_make_create_request(), _make_mock_user())

        assert result is not None
        mock_instance.save.assert_called_once()


# ---------------------------------------------------------------------------
# update() — AC #2
# ---------------------------------------------------------------------------


class TestMCPConfigServiceUpdateAuthConfigConflict:
    """update() raises 409 when a duplicate auth_config.id is detected."""

    @patch("codemie.service.mcp_config_service.MCPConfig")
    def test_update_raises_409_on_auth_config_id_duplicate(self, mock_mcp_config_class):
        """AC #2: duplicate auth_config.id on update → 409 CONFLICT."""
        existing = MagicMock()
        existing.id = "cfg-1"
        existing.name = "existing-name"
        existing.user_id = "user-1"
        mock_mcp_config_class.find_by_id.return_value = existing
        existing.update.side_effect = _make_auth_config_integrity_error()

        req = _make_update_request(auth_config={**_make_valid_auth_config(), "id": "ac-dup"})

        with pytest.raises(ExtendedHTTPException) as exc_info:
            MCPConfigService.update("cfg-1", req)

        exc = exc_info.value
        assert exc.code == 409
        assert "auth_config.id" in exc.message.lower() or "already in use" in exc.message.lower()

    @patch("codemie.service.mcp_config_service.MCPConfig")
    def test_update_re_raises_unrelated_integrity_error(self, mock_mcp_config_class):
        """Unrelated IntegrityError on update is not swallowed."""
        existing = MagicMock()
        existing.id = "cfg-1"
        existing.name = "existing-name"
        existing.user_id = "user-1"
        existing.config = None
        mock_mcp_config_class.find_by_id.return_value = existing
        existing.update.side_effect = _make_unrelated_integrity_error()

        req = MagicMock()
        req.name = None
        req.model_dump.return_value = {}

        with pytest.raises(IntegrityError):
            MCPConfigService.update("cfg-1", req)


# ---------------------------------------------------------------------------
# _is_auth_config_id_conflict() — driver-agnostic diag + string fallback paths
# ---------------------------------------------------------------------------


class TestIsAuthConfigIdConflict:
    """Unit tests for _is_auth_config_id_conflict() covering both detection paths.

    The implementation no longer uses a psycopg2 isinstance guard; it checks
    ``e.orig.diag.constraint_name`` generically so any DBAPI driver that exposes
    structured diagnostics (psycopg2, psycopg3, etc.) is handled without special-
    casing.  These tests verify the generic diag path and the string-fallback path
    independently, with no patches of driver-specific symbols.
    """

    def test_diag_constraint_name_matches_returns_true(self):
        """Primary path: any exception with diag.constraint_name == index name → True."""
        orig = Exception("dup key")
        orig.diag = MagicMock(constraint_name=_AUTH_CONFIG_ID_INDEX)
        e = IntegrityError("INSERT", {}, orig)
        assert _is_auth_config_id_conflict(e) is True

    def test_diag_constraint_name_mismatch_returns_false(self):
        """Primary path: diag.constraint_name for a different index → False."""
        orig = Exception("dup key")
        orig.diag = MagicMock(constraint_name="ix_mcp_configs_name_user")
        e = IntegrityError("INSERT", {}, orig)
        assert _is_auth_config_id_conflict(e) is False

    def test_diag_constraint_name_none_falls_back_to_string_match(self):
        """diag present but constraint_name=None → falls through to str(e) check."""
        orig = Exception(f'duplicate key violates unique constraint "{_AUTH_CONFIG_ID_INDEX}"')
        orig.diag = MagicMock(constraint_name=None)
        e = IntegrityError(f'duplicate key violates unique constraint "{_AUTH_CONFIG_ID_INDEX}"', {}, orig)
        assert _is_auth_config_id_conflict(e) is True

    def test_no_diag_attribute_falls_back_to_string_match(self):
        """Exception without diag attribute → string fallback → True when index name present."""
        orig = Exception(f'duplicate key violates unique constraint "{_AUTH_CONFIG_ID_INDEX}"')
        e = IntegrityError(f'duplicate key violates unique constraint "{_AUTH_CONFIG_ID_INDEX}"', {}, orig)
        # plain Exception has no .diag — should fall through to str(e) check
        assert not hasattr(orig, "diag")
        assert _is_auth_config_id_conflict(e) is True

    def test_no_diag_unrelated_constraint_returns_false(self):
        """Exception without diag and a different constraint in str(e) → False."""
        orig = Exception('duplicate key violates unique constraint "ix_mcp_configs_name_user"')
        e = IntegrityError('duplicate key violates unique constraint "ix_mcp_configs_name_user"', {}, orig)
        assert _is_auth_config_id_conflict(e) is False
