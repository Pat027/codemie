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

"""Google OAuth Settings Service - integration bridge between OAuth flow and SettingsService."""

import json
import time

from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.settings import CredentialValues
from codemie.service.encryption.encryption_factory import EncryptionFactory


class GoogleOAuthSettingsService:
    """Bridge between Google OAuth flow and SettingsService.

    Provides methods that SettingsService calls to:
    - Extract credentials from completed OAuth flow
    - Preserve OAuth tokens during settings updates
    - Revoke old tokens when email changes
    """

    def __init__(self, flow_service=None, encryption_service=None, token_manager=None):
        """Initialize settings service.

        Args:
            flow_service: Optional flow service (defaults to importing at runtime to avoid circular imports).
            encryption_service: Optional encryption service (defaults to current encryption service).
            token_manager: Optional token manager (defaults to importing at runtime).
        """
        if flow_service is None:
            # Import at runtime to avoid circular import
            from codemie.service.google_oauth.flow_service import GoogleOAuthFlowService

            flow_service = GoogleOAuthFlowService()
        self.flow_service = flow_service
        self.encryption_service = encryption_service or EncryptionFactory().get_current_encryption_service()

        if token_manager is None:
            from codemie.service.google_oauth.token_manager import GoogleOAuthTokenManager

            token_manager = GoogleOAuthTokenManager()
        self.token_manager = token_manager

    @staticmethod
    def _get_credential_value(credentials: list[CredentialValues], key: str) -> str | None:
        return next((c.value for c in credentials if c.key == key), None)

    def populate_credentials_from_flow(
        self, oauth_state: str, user_id: str, existing_credentials: list[CredentialValues] | None = None
    ) -> list[CredentialValues]:
        """Get OAuth tokens from completed flow and return as credential values.

        Polls the OAuth flow status, validates completion, decrypts token data,
        and returns encrypted CredentialValues ready to store in Settings.

        Args:
            oauth_state: OAuth state token from initiate_flow.
            user_id: User ID for ownership validation.
            existing_credentials: Optional list of existing credentials from the integration being updated.
                Used to reuse refresh_token when authenticated email matches the existing integration.

        Returns:
            List of CredentialValues with encrypted tokens:
            - access_token (encrypted bytes)
            - refresh_token (encrypted bytes)
            - expires_at (string timestamp)
            - email (string)

        Raises:
            ExtendedHTTPException: 400 if flow not completed or failed.
            ExtendedHTTPException: 502 if token data missing or incomplete.
        """
        # Check flow status
        result = self.flow_service.get_status(oauth_state, user_id)

        if result.get("status") != "success":
            raise ExtendedHTTPException(
                400,
                "Google OAuth flow not completed",
                f"OAuth state status: {result.get('status')}. Please complete the OAuth flow first.",
            )

        # Extract and decrypt token_data
        encrypted_token_data = result.get("token_data")
        if not encrypted_token_data:
            raise ExtendedHTTPException(
                502, "OAuth token data missing", "The OAuth callback did not store token data properly."
            )

        token_data = json.loads(self.encryption_service.decrypt(encrypted_token_data))

        # Extract tokens from decrypted payload
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)
        email = result.get("email", "")

        if not access_token:
            raise ExtendedHTTPException(
                502,
                "OAuth access token missing",
                "The OAuth response did not include an access_token.",
            )

        # If no refresh_token from Google, try to reuse from existing integration if email matches
        if not refresh_token and existing_credentials:
            from codemie.configs import logger

            existing_email = self._get_credential_value(existing_credentials, "email")
            logger.info(
                f"Google OAuth: No refresh_token from Google. "
                f"Checking existing integration: existing_email={existing_email!r}, new_email={email!r}"
            )

            if existing_email and email and existing_email == email:
                # Same email - reuse existing refresh_token
                encrypted_refresh = self._get_credential_value(existing_credentials, "refresh_token")
                if encrypted_refresh:
                    refresh_token = self.encryption_service.decrypt(encrypted_refresh)
                    logger.info(f"Google OAuth: Reusing existing refresh_token for {email}")
                else:
                    logger.warning(
                        "Google OAuth: Email matches but no encrypted refresh_token found in existing_credentials"
                    )
            else:
                logger.warning(
                    f"Google OAuth: Email mismatch - existing={existing_email!r}, new={email!r}. "
                    "Cannot reuse refresh_token."
                )

        if not refresh_token:
            raise ExtendedHTTPException(
                502,
                "OAuth refresh token missing",
                f"No refresh token available for {email}. "
                "This can happen if you selected an account that was never authorized before. "
                "Please revoke access in your Google Account settings and try again.",
            )

        # Calculate expires_at timestamp
        expires_at = int(time.time()) + expires_in

        # Return as CredentialValues (PLAINTEXT - will be encrypted by SettingsService._encrypt_fields)
        return [
            CredentialValues(key="access_token", value=access_token),
            CredentialValues(key="refresh_token", value=refresh_token),
            CredentialValues(key="expires_at", value=str(expires_at)),
            CredentialValues(key="email", value=email),
        ]

    def revoke_old_credentials_if_email_changed(
        self,
        user_id: str,
        setting_id: str,
        existing_credentials: list[CredentialValues],
        new_credentials: list[CredentialValues],
    ) -> None:
        """Revoke old Google OAuth credentials if email changed.

        When updating an integration with a different email, we should revoke the old
        credentials if they're not being used by any other integration.

        Args:
            user_id: User ID for ownership check.
            setting_id: Setting ID being updated.
            existing_credentials: Current credentials before update.
            new_credentials: New credentials after OAuth flow.
        """
        from codemie.configs import logger

        old_email = self._get_credential_value(existing_credentials, "email")
        new_email = self._get_credential_value(new_credentials, "email")

        if not old_email or not new_email or old_email == new_email:
            return

        old_encrypted_refresh = self._get_credential_value(existing_credentials, "refresh_token")

        if not old_encrypted_refresh:
            return

        logger.info(
            f"Google OAuth: Email changed from {old_email} to {new_email} for setting {setting_id}, "
            f"checking if old credentials should be revoked"
        )

        # Delegate to token manager for actual revocation logic
        try:
            self.token_manager.revoke_token_from_credentials(
                user_id,
                setting_id,
                old_email,
                old_encrypted_refresh,
            )
        except Exception as exc:
            logger.warning(f"Google OAuth: Failed to revoke old credentials for setting {setting_id}: {exc}")

    @staticmethod
    def get_preserved_credential_keys(
        existing_credentials: list[CredentialValues], prepared_cred_keys: list[str]
    ) -> list[str]:
        """Get list of credential keys to preserve during update.

        For Google OAuth, we need to preserve access_token, refresh_token, and expires_at
        from existing credentials even when they're not in the update request. This ensures
        that updating other fields (alias, is_global, etc.) doesn't accidentally delete
        OAuth tokens.

        Args:
            existing_credentials: Current credentials from the Settings record.
            prepared_cred_keys: Keys from the update request after preparation.

        Returns:
            List of credential keys to preserve (prepared keys + OAuth token keys from existing).
        """
        # OAuth token keys that should be preserved if they exist
        oauth_token_keys = {"access_token", "refresh_token", "expires_at"}

        # Find which OAuth keys exist in current credentials AND are not already in prepared_creds
        existing_oauth_keys = [
            cred.key
            for cred in existing_credentials
            if cred.key in oauth_token_keys and cred.key not in prepared_cred_keys
        ]

        # Combine prepared keys with missing OAuth keys from existing
        return prepared_cred_keys + existing_oauth_keys
