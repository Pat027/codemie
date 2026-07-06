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

"""Google OAuth constants and configuration values."""


class GoogleOAuthStatus:
    """OAuth flow status constants."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    NOT_FOUND = "not_found"


TOKEN_REFRESH_BUFFER = 5 * 60  # Refresh tokens 5 minutes before expiry

# Google OAuth scopes
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/documents.readonly",
]

GOOGLE_OAUTH_ERROR_DESCRIPTIONS = {
    "access_denied": (
        "Authorization was declined or required permissions were not granted. "
        "Please try again and ensure you grant access to all requested scopes (email and Google Docs)."
    ),
    "invalid_grant": "The authorization code is invalid or expired.",
    "invalid_client": "The application is not configured correctly. Contact your administrator.",
    "redirect_uri_mismatch": "Redirect URI does not match. Contact your administrator.",
    "admin_policy_enforced": "Your organization's administrator policies prevent this authorization.",
    "org_internal": "This application is restricted to specific organization accounts.",
    "deleted_client": "The OAuth application has been deleted. Contact your administrator.",
    "disallowed_useragent": "Authorization cannot be completed in this browser context.",
    "invalid_request": "The authorization request is malformed. Please try again.",
}
