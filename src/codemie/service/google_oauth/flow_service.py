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

"""Google OAuth Flow Service - orchestrates OAuth flow and token lifecycle."""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from codemie.configs import config, logger
from codemie.core.exceptions import ExtendedHTTPException
from codemie.service.encryption.encryption_factory import EncryptionFactory
from codemie.service.google_oauth.constants import (
    GOOGLE_OAUTH_SCOPES,
    GOOGLE_OAUTH_ERROR_DESCRIPTIONS,
)
from codemie.service.google_oauth.state_store import GoogleOAuthStateStore


@dataclass
class CallbackResult:
    """Result of OAuth callback processing."""

    success: bool
    message: str
    status_code: int


class GoogleOAuthFlowService:
    """Orchestrates Google OAuth authorization flow.

    Delegates to specialized services:
    - GoogleOAuthStateStore for Redis state management
    - Handles OAuth callback processing and flow status
    """

    def __init__(self, state_store=None, encryption_service=None):
        """Initialize service with dependencies.

        Args:
            state_store: Optional state store (defaults to GoogleOAuthStateStore()).
            encryption_service: Optional encryption service (defaults to current encryption service).
        """
        self.state_store = state_store or GoogleOAuthStateStore()
        self.encryption_service = encryption_service or EncryptionFactory().get_current_encryption_service()

    @staticmethod
    def _generate_code_verifier() -> str:
        """Generate 96-byte random URL-safe string for PKCE."""
        return secrets.token_urlsafe(96)

    @staticmethod
    def _generate_code_challenge(verifier: str) -> str:
        """Generate SHA256 code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def _create_flow(self, client_id: str, redirect_uri: str, state: Optional[str] = None) -> Flow:
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=GOOGLE_OAUTH_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )

    def _get_error_message(self, error: str) -> str:
        """Map OAuth error code to user-friendly message."""
        return GOOGLE_OAUTH_ERROR_DESCRIPTIONS.get(error, f"Authentication failed: {error}")

    def _validate_granted_scopes(self, granted_scope: Optional[str]) -> Optional[str]:
        """Validate that all required scopes were granted by the user.

        Args:
            granted_scope: Space-delimited list of scopes from callback query param.

        Returns:
            Error message if scopes are missing, None if validation passes.
        """
        if not granted_scope:
            # If scope parameter is missing, we can't validate - let token exchange handle it
            return None

        granted_scopes = set(granted_scope.split())
        required_scopes = set(GOOGLE_OAUTH_SCOPES)
        missing_scopes = required_scopes - granted_scopes

        if missing_scopes:
            logger.warning(
                f"Google OAuth: user denied required scopes. "
                f"Required: {required_scopes}, Granted: {granted_scopes}, Missing: {missing_scopes}"
            )
            return (
                "Authorization requires all permissions: email access and Google Docs read access. "
                "Please try again and grant all requested permissions."
            )

        return None

    def _exchange_code_for_tokens(
        self, code: str, code_verifier: str, client_id: str, redirect_uri: str, state: str
    ) -> tuple[str, str | None, int]:
        """Exchange authorization code for tokens using Flow.

        Args:
            code: Authorization code.
            code_verifier: PKCE code verifier.
            client_id: Google OAuth client ID.
            redirect_uri: OAuth redirect URI.
            state: State token.

        Returns:
            Tuple of (access_token, refresh_token, expires_in).
            refresh_token may be None if user selected an already-authorized account.

        Raises:
            Exception: On token exchange failure.
        """
        flow = self._create_flow(client_id, redirect_uri, state)
        flow.fetch_token(code=code, code_verifier=code_verifier)
        credentials = flow.credentials

        access_token = credentials.token
        refresh_token = credentials.refresh_token

        if not access_token:
            raise ValueError("Google OAuth response missing access_token")

        if credentials.expiry:
            expiry = credentials.expiry.replace(tzinfo=UTC) if credentials.expiry.tzinfo is None else credentials.expiry
            expires_in = int((expiry - datetime.now(UTC)).total_seconds())
        else:
            expires_in = 3600

        return access_token, refresh_token, expires_in

    def _fetch_user_email(self, access_token: str) -> str:
        """Fetch authenticated user's email from Google userinfo endpoint.

        Args:
            access_token: Valid Google OAuth access token.

        Returns:
            User's email address, or empty string if unavailable.
        """
        try:
            credentials = Credentials(token=access_token)
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get("email", "")
        except HttpError as exc:
            logger.warning(
                f"Google OAuth: HTTP {exc.resp.status} fetching user email. "
                f"ErrorDetails={exc.error_details if hasattr(exc, 'error_details') else str(exc)}"
            )
            return ""
        except Exception as exc:
            logger.warning(f"Google OAuth: failed to fetch user email: {exc}")
            return ""

    def _find_existing_refresh_token(self, user_id: str, email: str) -> str | None:
        """Find refresh_token from existing GoogleOAuth integration for this email.

        Args:
            user_id: User ID to search settings for.
            email: Email address to match against.

        Returns:
            Decrypted refresh_token if found, None otherwise.
        """
        try:
            from codemie.rest_api.models.settings import Settings
            from codemie_tools.base.models import CredentialTypes

            # Get all GoogleOAuth settings for this user (raw from DB, not masked)
            google_settings = Settings.get_by_user_id(user_id, credential_type=CredentialTypes.GOOGLE_OAUTH)

            for setting in google_settings:
                # Check if email matches
                setting_email = next((c.value for c in setting.credential_values if c.key == "email"), None)
                if setting_email == email:
                    # Extract refresh_token (encrypted from DB)
                    encrypted_refresh = next(
                        (c.value for c in setting.credential_values if c.key == "refresh_token"), None
                    )
                    if encrypted_refresh:
                        return self.encryption_service.decrypt(encrypted_refresh)

            return None
        except Exception as exc:
            logger.warning(f"Google OAuth: failed to find existing refresh_token: {exc}")
            return None

    def initiate_flow(self, user_id: str, client_id: Optional[str] = None) -> dict:
        """Initiate Google OAuth flow with PKCE.

        Generates authorization URL and stores state in Redis.

        Args:
            user_id: Authenticated user's ID.
            client_id: Optional override for Google OAuth client ID.

        Returns:
            Dict with ``auth_url`` and ``state`` keys.

        Raises:
            ExtendedHTTPException: If state cannot be stored in Redis.
        """
        effective_client_id = client_id or config.GOOGLE_OAUTH_CLIENT_ID
        redirect_uri = config.google_oauth_redirect_uri

        # Generate PKCE parameters
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        state_data = {
            "code_verifier": code_verifier,
            "client_id": effective_client_id,
            "user_id": user_id,
        }
        self.state_store.store_state(state, state_data)

        # Generate authorization URL
        flow = self._create_flow(effective_client_id, redirect_uri)
        auth_url, _ = flow.authorization_url(
            state=state,
            access_type="offline",
            prompt="select_account",
            include_granted_scopes="true",
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

        return {"auth_url": auth_url, "state": state}

    def handle_callback(
        self,
        code: Optional[str],
        state: Optional[str],
        error: Optional[str],
        granted_scope: Optional[str] = None,
    ) -> CallbackResult:
        """Handle OAuth callback from Google.

        Validates state, checks granted scopes, exchanges code for tokens,
        fetches user email, and stores result in Redis for polling endpoint.

        Args:
            code: Authorization code from Google (absent on error).
            state: Opaque state value from initiate_flow.
            error: OAuth error code from Google, if any.
            granted_scope: Space-delimited list of scopes the user granted.

        Returns:
            CallbackResult indicating success or failure.
        """
        # Validate state parameter
        if not state:
            return CallbackResult(False, "Missing state parameter.", 400)

        state_data = self.state_store.consume_state(state)

        user_id = state_data.get("user_id", "") if state_data else ""

        if error:
            message = self._get_error_message(error)
            # Don't store result for access_denied - no token was issued, so no cleanup needed
            # The frontend will handle the error via the HTML page
            return CallbackResult(False, message, 200)

        if state_data is None:
            return CallbackResult(False, "Invalid or expired authentication state.", 400)

        # Validate granted scopes before attempting token exchange
        scope_error = self._validate_granted_scopes(granted_scope)
        if scope_error:
            # Don't store result - no token was issued, nothing to clean up
            return CallbackResult(False, scope_error, 200)

        # Exchange code for tokens
        client_id = state_data.get("client_id") or config.GOOGLE_OAUTH_CLIENT_ID
        code_verifier = state_data["code_verifier"]

        try:
            access_token, refresh_token, expires_in = self._exchange_code_for_tokens(
                code, code_verifier, client_id, config.google_oauth_redirect_uri, state
            )
        except Exception as exc:
            logger.error(f"Google OAuth: token exchange failed: {exc}")
            # Don't store result - if token exchange fails, no valid token was created
            return CallbackResult(False, "Failed to complete authentication. Please try again.", 200)

        email = self._fetch_user_email(access_token)

        # If no refresh_token, try to reuse from existing integration for this email
        if not refresh_token and email:
            refresh_token = self._find_existing_refresh_token(user_id, email)
            if not refresh_token:
                logger.warning(
                    f"Google OAuth: No refresh_token from Google and no existing integration found for {email}. "
                    "User may need to revoke access and re-authorize."
                )

        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "expires_in": expires_in,
        }
        encrypted_token_data = self.encryption_service.encrypt(json.dumps(token_data))

        if isinstance(encrypted_token_data, bytes):
            encrypted_token_data_str = encrypted_token_data.decode()
        else:
            encrypted_token_data_str = encrypted_token_data
        stored = self.state_store.store_result(
            state, "success", user_id, token_data=encrypted_token_data_str, email=email
        )
        if not stored:
            return CallbackResult(False, "Authentication service temporarily unavailable. Please try again.", 503)

        return CallbackResult(True, "Authentication successful.", 200)

    def get_status(self, state: str, user_id: str) -> dict:
        """Poll Redis for OAuth flow result.

        Checks result key first (flow completed), then state key (flow pending).
        Validates result belongs to requesting user.

        Args:
            state: Opaque state token from initiate_flow.
            user_id: Authenticated user's ID (for ownership check).

        Returns:
            Dict with ``status`` key:
            - ``{"status": "success", ...}`` – flow completed successfully.
            - ``{"status": "error", "message": "..."}`` – flow failed.
            - ``{"status": "pending"}`` – flow in progress.
            - ``{"status": "not_found"}`` – state unknown/expired.

        Raises:
            ExtendedHTTPException: 403 if result doesn't belong to user_id.
        """
        try:
            result = self.state_store.get_result(state)
        except Exception as exc:
            logger.error(f"Google OAuth: Redis unavailable reading result in get_status: {exc}")
            return {"status": "error", "message": "Authentication service temporarily unavailable."}

        if result is not None:
            result_user_id = result.get("user_id", "")
            if result_user_id and result_user_id != user_id:
                raise ExtendedHTTPException(403, "Access denied")
            return result

        try:
            state_data = self.state_store.get_pending_state(state)
        except Exception as exc:
            logger.error(f"Google OAuth: Redis unavailable reading state in get_status: {exc}")
            return {"status": "error", "message": "Authentication service temporarily unavailable."}

        if state_data is not None:
            state_user_id = state_data.get("user_id", "")
            if state_user_id and state_user_id != user_id:
                raise ExtendedHTTPException(403, "Access denied")
            return {"status": "pending"}

        return {"status": "not_found"}
