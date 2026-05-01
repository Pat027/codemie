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

from unittest.mock import MagicMock, patch

import pytest

from codemie.enterprise.mcp_auth.dependencies import decrypt_confidential_client_secret


def _build_auth_config(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "auth_type": "oauth2",
        "client_type": "confidential",
        "client_secret": "encrypted-secret",
    }
    payload.update(overrides)
    return payload


@patch("codemie.enterprise.mcp_auth.dependencies.encryption_service")
def test_decrypt_confidential_client_secret_returns_plaintext_for_confidential_oauth2(
    mock_encryption_service: MagicMock,
) -> None:
    mock_encryption_service.decrypt.return_value = "plain-secret"

    result = decrypt_confidential_client_secret(_build_auth_config())

    assert result == "plain-secret"
    mock_encryption_service.decrypt.assert_called_once_with("encrypted-secret")


@pytest.mark.parametrize(
    "auth_config",
    [
        _build_auth_config(auth_type="saml"),
        _build_auth_config(client_type="public"),
        _build_auth_config(client_secret=None),
        _build_auth_config(client_secret="   "),
    ],
)
@patch("codemie.enterprise.mcp_auth.dependencies.encryption_service")
def test_decrypt_confidential_client_secret_returns_none_when_no_decryption_is_needed(
    mock_encryption_service: MagicMock,
    auth_config: dict[str, object],
) -> None:
    assert decrypt_confidential_client_secret(auth_config) is None
    mock_encryption_service.decrypt.assert_not_called()


@patch("codemie.enterprise.mcp_auth.dependencies.encryption_service")
def test_decrypt_confidential_client_secret_propagates_decryption_failures_unchanged(
    mock_encryption_service: MagicMock,
) -> None:
    failure = RuntimeError("decrypt failed")
    mock_encryption_service.decrypt.side_effect = failure

    with pytest.raises(RuntimeError) as exc_info:
        decrypt_confidential_client_secret(_build_auth_config())

    assert exc_info.value is failure
