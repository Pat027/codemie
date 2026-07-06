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

"""Unit tests for Google OAuth integration deletion with token revocation."""

from unittest.mock import MagicMock, patch


from codemie.service.settings.settings import SettingsService
from codemie_tools.base.models import CredentialTypes


class TestDeleteGoogleOAuthIntegration:
    """Test that deleting Google OAuth settings revokes tokens."""

    @patch("codemie.service.google_oauth.token_manager.GoogleOAuthTokenManager")
    @patch("codemie.service.settings.settings.Settings")
    def test_revokes_token_before_deleting_google_oauth(self, mock_settings_class, mock_token_manager_class):
        """Should revoke token before deleting Google OAuth setting."""
        # Arrange
        mock_setting = MagicMock()
        mock_setting.id = "oauth-setting-123"
        mock_setting.credential_type = CredentialTypes.GOOGLE_OAUTH
        mock_setting.setting_type = MagicMock()  # SettingType.USER
        mock_setting.user_id = "user-456"
        mock_settings_class.get_by_id.return_value = mock_setting

        mock_token_manager = MagicMock()
        mock_token_manager_class.return_value = mock_token_manager

        # Act
        SettingsService.delete_setting(credential_id="oauth-setting-123", user_id="user-456")

        # Assert
        mock_token_manager.revoke_token.assert_called_once_with("oauth-setting-123")
        mock_settings_class.delete_setting.assert_called_once_with("oauth-setting-123")

    @patch("codemie.service.google_oauth.token_manager.GoogleOAuthTokenManager")
    @patch("codemie.service.settings.settings.Settings")
    def test_does_not_revoke_for_non_oauth_credentials(self, mock_settings_class, mock_token_manager_class):
        """Should not attempt revocation for non-OAuth credential types."""
        # Arrange
        mock_setting = MagicMock()
        mock_setting.id = "git-setting-789"
        mock_setting.credential_type = CredentialTypes.GIT
        mock_setting.setting_type = MagicMock()
        mock_setting.user_id = "user-456"
        mock_settings_class.get_by_id.return_value = mock_setting

        mock_token_manager = MagicMock()
        mock_token_manager_class.return_value = mock_token_manager

        # Act
        SettingsService.delete_setting(credential_id="git-setting-789", user_id="user-456")

        # Assert
        mock_token_manager.revoke_token.assert_not_called()
        mock_settings_class.delete_setting.assert_called_once_with("git-setting-789")

    @patch("codemie.service.google_oauth.token_manager.GoogleOAuthTokenManager")
    @patch("codemie.service.settings.settings.Settings")
    def test_deletes_setting_even_if_revocation_fails(self, mock_settings_class, mock_token_manager_class):
        """Should proceed with deletion even if token revocation fails."""
        # Arrange
        mock_setting = MagicMock()
        mock_setting.id = "oauth-setting-999"
        mock_setting.credential_type = CredentialTypes.GOOGLE_OAUTH
        mock_setting.setting_type = MagicMock()
        mock_setting.user_id = "user-456"
        mock_settings_class.get_by_id.return_value = mock_setting

        mock_token_manager = MagicMock()
        mock_token_manager.revoke_token.side_effect = Exception("Revocation failed")
        mock_token_manager_class.return_value = mock_token_manager

        # Act - should not raise, just log warning
        SettingsService.delete_setting(credential_id="oauth-setting-999", user_id="user-456")

        # Assert - deletion still happens
        mock_settings_class.delete_setting.assert_called_once_with("oauth-setting-999")
