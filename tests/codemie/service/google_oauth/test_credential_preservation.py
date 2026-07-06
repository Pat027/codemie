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

"""Unit tests for GoogleOAuthSettingsService.get_preserved_credential_keys()."""

import pytest

from codemie.rest_api.models.settings import CredentialValues
from codemie.service.google_oauth.settings_service import GoogleOAuthSettingsService


@pytest.fixture
def service():
    """GoogleOAuthSettingsService instance."""
    return GoogleOAuthSettingsService()


class TestGetPreservedCredentialKeys:
    """Test credential preservation logic for updates."""

    def test_preserves_oauth_tokens_when_not_in_update(self, service):
        """Should preserve access_token, refresh_token, expires_at from existing credentials."""
        existing = [
            CredentialValues(key="access_token", value="encrypted_access"),
            CredentialValues(key="refresh_token", value="encrypted_refresh"),
            CredentialValues(key="expires_at", value="123456"),
            CredentialValues(key="email", value="test@example.com"),
        ]

        # Update only changes alias - no OAuth tokens in prepared_creds
        prepared_cred_keys = ["email", "other_field"]

        preserved_keys = service.get_preserved_credential_keys(existing, prepared_cred_keys)

        # Should include prepared keys + OAuth token keys from existing
        assert "email" in preserved_keys
        assert "other_field" in preserved_keys
        assert "access_token" in preserved_keys
        assert "refresh_token" in preserved_keys
        assert "expires_at" in preserved_keys

    def test_does_not_duplicate_keys_when_oauth_tokens_in_prepared(self, service):
        """Should not duplicate keys when OAuth tokens are in prepared_creds."""
        existing = [
            CredentialValues(key="access_token", value="old_encrypted_access"),
            CredentialValues(key="refresh_token", value="old_encrypted_refresh"),
            CredentialValues(key="expires_at", value="123456"),
            CredentialValues(key="email", value="old@example.com"),
        ]

        # Re-authentication: new OAuth tokens in prepared_creds
        prepared_cred_keys = ["access_token", "refresh_token", "expires_at", "email"]

        preserved_keys = service.get_preserved_credential_keys(existing, prepared_cred_keys)

        # Should have each key only once
        assert preserved_keys.count("access_token") == 1
        assert preserved_keys.count("refresh_token") == 1
        assert preserved_keys.count("expires_at") == 1
        assert preserved_keys.count("email") == 1

    def test_preserves_only_oauth_keys_that_exist_in_existing(self, service):
        """Should only preserve OAuth keys that actually exist in existing credentials."""
        existing = [
            CredentialValues(key="access_token", value="encrypted_access"),
            # refresh_token missing
            CredentialValues(key="email", value="test@example.com"),
        ]

        prepared_cred_keys = ["email"]

        preserved_keys = service.get_preserved_credential_keys(existing, prepared_cred_keys)

        # Should preserve access_token (exists) but not refresh_token (doesn't exist)
        assert "access_token" in preserved_keys
        assert "refresh_token" not in preserved_keys
        assert "expires_at" not in preserved_keys

    def test_returns_list_when_existing_empty(self, service):
        """Should handle empty existing credentials gracefully."""
        existing = []
        prepared_cred_keys = ["email", "other_field"]

        preserved_keys = service.get_preserved_credential_keys(existing, prepared_cred_keys)

        # Should only have prepared keys, no OAuth tokens to preserve
        assert preserved_keys == prepared_cred_keys

    def test_preserves_all_three_oauth_token_keys(self, service):
        """Should preserve all three OAuth token keys: access_token, refresh_token, expires_at."""
        existing = [
            CredentialValues(key="access_token", value="encrypted_access"),
            CredentialValues(key="refresh_token", value="encrypted_refresh"),
            CredentialValues(key="expires_at", value="123456"),
            CredentialValues(key="email", value="test@example.com"),
            CredentialValues(key="unrelated", value="value"),
        ]

        prepared_cred_keys = ["email"]

        preserved_keys = service.get_preserved_credential_keys(existing, prepared_cred_keys)

        # Should preserve exactly the 3 OAuth token keys + email
        oauth_keys_in_preserved = [k for k in preserved_keys if k in {"access_token", "refresh_token", "expires_at"}]
        assert len(oauth_keys_in_preserved) == 3
        assert "unrelated" not in preserved_keys  # Other keys should not be preserved automatically
