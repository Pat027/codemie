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

"""Unit tests for Google OAuth token revocation."""

from unittest.mock import MagicMock, patch

import pytest

from codemie.service.google_oauth.token_manager import GoogleOAuthTokenManager
from codemie_tools.base.models import CredentialTypes


@pytest.fixture
def mock_encryption():
    """Mock encryption service."""
    mock_enc = MagicMock()
    mock_enc.decrypt.side_effect = lambda x: str(x).replace("encrypted_", "")
    return mock_enc


@pytest.fixture
def token_manager(mock_encryption):
    """GoogleOAuthTokenManager instance with mocked encryption."""
    return GoogleOAuthTokenManager(encryption_service=mock_encryption)


class TestRevokeToken:
    """Test revoke_token() method."""

    @patch("codemie.service.google_oauth.token_manager.Settings")
    @patch("requests.post")
    def test_revokes_refresh_token_via_google_api(self, mock_post, mock_settings_class, token_manager):
        """Should call Google's revocation endpoint with refresh token."""
        # Arrange
        mock_setting = MagicMock()
        mock_setting.id = "setting-123"
        mock_setting.credential_type = CredentialTypes.GOOGLE_OAUTH
        mock_setting.credential_values = [
            MagicMock(key="refresh_token", value="encrypted_refresh_xyz"),
        ]
        mock_settings_class.find_by_id.return_value = mock_setting

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Act
        token_manager.revoke_token("setting-123")

        # Assert
        mock_post.assert_called_once_with(
            "https://oauth2.googleapis.com/revoke",
            data={"token": "refresh_xyz"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    @patch("codemie.service.google_oauth.token_manager.Settings")
    def test_raises_404_when_setting_not_found(self, mock_settings_class, token_manager):
        """Should raise 404 when setting doesn't exist."""
        mock_settings_class.find_by_id.return_value = None

        with pytest.raises(Exception) as exc_info:
            token_manager.revoke_token("nonexistent")

        assert "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    @patch("codemie.service.google_oauth.token_manager.Settings")
    def test_raises_400_when_not_google_oauth(self, mock_settings_class, token_manager):
        """Should raise 400 when setting is not Google OAuth type."""
        mock_setting = MagicMock()
        mock_setting.credential_type = CredentialTypes.GIT
        mock_settings_class.find_by_id.return_value = mock_setting

        with pytest.raises(Exception) as exc_info:
            token_manager.revoke_token("git-setting")

        assert "400" in str(exc_info.value) or "not a Google OAuth" in str(exc_info.value)

    @patch("codemie.service.google_oauth.token_manager.Settings")
    @patch("requests.post")
    def test_handles_revocation_failure_gracefully(self, mock_post, mock_settings_class, token_manager):
        """Should log warning but not raise when revocation fails."""
        mock_setting = MagicMock()
        mock_setting.id = "setting-456"
        mock_setting.credential_type = CredentialTypes.GOOGLE_OAUTH
        mock_setting.credential_values = [
            MagicMock(key="refresh_token", value="encrypted_refresh_abc"),
        ]
        mock_settings_class.find_by_id.return_value = mock_setting

        # Google returns 400 for already-revoked or invalid tokens
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response

        # Should not raise - revocation is best-effort
        token_manager.revoke_token("setting-456")

    @patch("codemie.service.google_oauth.token_manager.Settings")
    @patch("requests.post")
    def test_handles_missing_refresh_token(self, mock_post, mock_settings_class, token_manager):
        """Should handle case when refresh_token is missing from credentials."""
        mock_setting = MagicMock()
        mock_setting.id = "setting-789"
        mock_setting.credential_type = CredentialTypes.GOOGLE_OAUTH
        mock_setting.credential_values = []  # No refresh token
        mock_settings_class.find_by_id.return_value = mock_setting

        # Should not call API or raise - nothing to revoke
        token_manager.revoke_token("setting-789")

        mock_post.assert_not_called()
