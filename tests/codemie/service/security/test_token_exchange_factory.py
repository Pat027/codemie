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

from datetime import UTC, datetime

import pytest
from unittest.mock import MagicMock, patch
from codemie.service.security.token_exchange_service import TokenExchangeService
from codemie.service.security.token_providers.base_provider import TokenProviderException
from codemie.rest_api.security.user import User


@pytest.fixture
def mock_cache():
    return MagicMock()


@pytest.fixture
def mock_context_provider():
    with patch("codemie.service.security.token_exchange_service.ContextTokenProvider") as mock:
        yield mock.return_value


@pytest.fixture
def factory(mock_cache, mock_context_provider):
    # Reset singleton for each test
    TokenExchangeService._instance = None
    factory = TokenExchangeService()
    factory._cache = mock_cache
    factory._default_provider = mock_context_provider
    return factory


@pytest.fixture
def current_user():
    user = MagicMock(spec=User)
    user.id = "test-user-id"
    return user


def test_singleton_pattern():
    TokenExchangeService._instance = None
    f1 = TokenExchangeService()
    f2 = TokenExchangeService()
    assert f1 is f2


@patch("codemie.service.security.token_exchange_service.get_current_user")
def test_get_token_no_user(mock_get_user, factory):
    mock_get_user.return_value = None
    token = factory.get_token_for_current_user()
    assert token is None


@patch("codemie.service.security.token_exchange_service.get_current_user")
def test_get_token_cache_hit(mock_get_user, factory, current_user, mock_cache):
    mock_get_user.return_value = current_user
    mock_cache.get.return_value = "cached-token"

    token = factory.get_token_for_current_user()

    assert token == "cached-token"
    mock_cache.get.assert_called_once_with(f"auth_token:{current_user.id}")
    factory._default_provider.get_token.assert_not_called()


@patch("codemie.service.security.token_exchange_service.get_current_user")
def test_get_token_cache_miss(mock_get_user, factory, current_user, mock_cache, mock_context_provider):
    mock_get_user.return_value = current_user
    mock_cache.get.return_value = None
    mock_context_provider.get_token.return_value = "new-token"

    token = factory.get_token_for_current_user()

    assert token == "new-token"
    mock_cache.get.assert_called_once_with(f"auth_token:{current_user.id}")
    mock_context_provider.get_token.assert_called_once()
    mock_cache.__setitem__.assert_called_once_with(f"auth_token:{current_user.id}", "new-token")


@patch("codemie.service.security.token_exchange_service.get_current_user")
def test_get_token_provider_error(mock_get_user, factory, current_user, mock_cache, mock_context_provider):
    mock_get_user.return_value = current_user
    mock_cache.get.return_value = None
    mock_context_provider.get_token.side_effect = TokenProviderException("Provider failed")

    with pytest.raises(TokenProviderException):
        factory.get_token_for_current_user()

    mock_cache.__setitem__.assert_not_called()


def test_clear_cache_specific_user(factory, mock_cache):
    user_id = "user-123"
    factory.clear_cache(user_id=user_id)
    mock_cache.pop.assert_called_once_with(f"auth_token:{user_id}", None)


def test_clear_cache_all(factory, mock_cache):
    factory.clear_cache()
    mock_cache.clear.assert_called_once()


def test_get_cache_stats(factory, mock_cache):
    mock_cache.__len__ = MagicMock(return_value=10)
    stats = factory.get_cache_stats()
    assert stats["cache_size"] == 10
    assert "cache_ttl" in stats


@patch("codemie.service.security.token_exchange_service.get_current_user")
def test_get_token_provider_returns_none(mock_get_user, factory, current_user, mock_cache, mock_context_provider):
    """Provider returns None → None returned, token not stored in cache."""
    mock_get_user.return_value = current_user
    mock_cache.get.return_value = None
    mock_context_provider.get_token.return_value = None

    token = factory.get_token_for_current_user()

    assert token is None
    mock_cache.__setitem__.assert_not_called()


# ---------------------------------------------------------------------------
# TMS integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tms_store():
    return MagicMock()


@pytest.fixture
def factory_with_tms(factory, mock_tms_store):
    TokenExchangeService._store = mock_tms_store
    yield factory
    TokenExchangeService._store = None


def test_get_token_returns_tms_cached_token(factory_with_tms, mock_tms_store, current_user):
    mock_tms_store.get.return_value = "tms-cached-jwt"

    with patch("codemie.service.security.token_exchange_service.get_current_user", return_value=current_user):
        result = factory_with_tms.get_token_for_current_user()

    assert result == "tms-cached-jwt"
    mock_tms_store.get.assert_called_once_with("test-user-id", "__idp_token__")


def test_get_token_tms_miss_calls_provider_and_stores(
    factory_with_tms, mock_tms_store, mock_context_provider, current_user
):
    mock_tms_store.get.return_value = None
    mock_context_provider.get_token.return_value = "fresh-jwt"

    with patch("codemie.service.security.token_exchange_service.get_current_user", return_value=current_user):
        with patch("codemie.service.security.token_exchange_service.parse_jwt_exp") as mock_parse:
            mock_parse.return_value = datetime(2025, 6, 1, tzinfo=UTC)
            result = factory_with_tms.get_token_for_current_user()

    assert result == "fresh-jwt"
    mock_tms_store.put.assert_called_once_with(
        "test-user-id",
        "__idp_token__",
        access_token="fresh-jwt",
        expires_at=datetime(2025, 6, 1, tzinfo=UTC),
    )


def test_get_token_no_store_uses_legacy_cache(factory, mock_context_provider, current_user, mock_cache):
    TokenExchangeService._store = None
    mock_cache.get.return_value = "legacy-cached"

    with patch("codemie.service.security.token_exchange_service.get_current_user", return_value=current_user):
        result = factory.get_token_for_current_user()

    assert result == "legacy-cached"


def test_clear_cache_user_calls_store_invalidate(factory_with_tms, mock_tms_store):
    factory_with_tms.clear_cache(user_id="test-user-id")

    mock_tms_store.invalidate.assert_called_once_with("test-user-id", "__idp_token__")


def test_clear_cache_none_does_not_call_store(factory_with_tms, mock_tms_store):
    factory_with_tms.clear_cache(user_id=None)

    mock_tms_store.invalidate.assert_not_called()
