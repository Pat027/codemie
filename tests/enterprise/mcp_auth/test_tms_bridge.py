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

import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest


def _patch_tms_config(monkeypatch: pytest.MonkeyPatch, dependencies, **overrides: object) -> None:
    defaults: dict[str, object] = {
        "MCP_AUTH_TMS_ENABLED": True,
        "ENV": "local",
        "MCP_AUTH_TMS_KMS_KEY_ID": "test-key",
        "MCP_AUTH_TMS_ENCRYPTION_CONTEXT_PREFIX": "codemie-enterprise:mcp-auth:tms",
        "MCP_AUTH_TMS_REFRESH_TIMEOUT_SECONDS": 2.5,
        "MCP_AUTH_TMS_REDIS_LOCK_ENABLED": True,
        "MCP_AUTH_TMS_REDIS_LOCK_TTL_SECONDS": 10,
        "MCP_AUTH_TMS_AUDIT_REQUIRED": True,
        "MCP_AUTH_TMS_AUDIT_FALLBACK_ENABLED": False,
        "MCP_AUTH_TMS_AUDIT_FALLBACK_SINK_CONFIGURED": False,
        "MCP_AUTH_TMS_ALLOW_MOCK": False,
        "MCP_AUTH_HMAC_SECRET": "x" * 32,
        "ENCRYPTION_TYPE": "plain",
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(dependencies.config, name, value)


def test_initialize_mcp_auth_uses_postgres_tms_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.configs import config as runtime_config
    from codemie.enterprise.mcp_auth import dependencies
    from codemie.service.mcp.toolkit_service import MCPToolkitService

    class FakeResolver:
        def __init__(self, token_management_system, authentication_required_factory, audit_context_provider=None):
            self.token_management_system = token_management_system
            self.authentication_required_factory = authentication_required_factory
            self.audit_context_provider = audit_context_provider

    fake_tms = object()
    fake_service = MagicMock()
    fake_resolver = FakeResolver
    fake_audit_context_provider = object()
    fake_redis_client = MagicMock(close=MagicMock())
    fake_redis_encryption = MagicMock()

    monkeypatch.setattr(dependencies, "HAS_MCP_AUTH", True)
    monkeypatch.setattr(runtime_config, "MCP_AUTH_ENABLED", True)
    _patch_tms_config(monkeypatch, dependencies)

    def create_task(coroutine):
        coroutine.close()
        return MagicMock(done=lambda: False)

    monkeypatch.setattr(dependencies.asyncio, "get_running_loop", lambda: MagicMock(create_task=create_task))
    monkeypatch.setattr(dependencies, "create_redis_client", lambda: fake_redis_client)
    monkeypatch.setattr(MCPToolkitService, "register_auth_resolver", MagicMock())
    monkeypatch.setattr(
        dependencies,
        "_build_token_management_system",
        MagicMock(return_value=fake_tms),
    )

    fake_enterprise_module = MagicMock(
        ContextVarTMSAuditContextProvider=MagicMock(return_value=fake_audit_context_provider),
        DCRCredentialsCache=MagicMock(),
        DiscoveryMetadataCache=MagicMock(),
        MCPAuthResolver=fake_resolver,
        MCPAuthService=MagicMock(return_value=fake_service),
        MCPAuthServiceConfig=MagicMock(return_value=MagicMock()),
        RedisEncryption=MagicMock(return_value=fake_redis_encryption),
        RedisPKCEStore=MagicMock(),
        SAMLRelayStateStore=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_enterprise_module)

    dependencies._initialized = False
    dependencies._bridge_queue = None
    dependencies._bridge_task = None
    dependencies._bridge_loop = None
    dependencies._mcp_auth_service = None
    dependencies._redis_client = None
    dependencies._tms = None
    dependencies._tms_audit_context_provider = None
    dependencies._registered_resolver_types.clear()
    MCPToolkitService._auth_resolvers.clear()

    try:
        dependencies.initialize_mcp_auth()
    finally:
        MCPToolkitService._auth_resolvers.clear()
        dependencies._registered_resolver_types.clear()
        dependencies._initialized = False
        dependencies._bridge_queue = None
        dependencies._bridge_task = None
        dependencies._bridge_loop = None
        dependencies._mcp_auth_service = None
        dependencies._redis_client = None
        dependencies._tms = None
        dependencies._tms_audit_context_provider = None

    dependencies._build_token_management_system.assert_called_once_with(  # type: ignore[attr-defined]
        fake_redis_client,
        fake_audit_context_provider,
    )
    assert fake_service.initialize.call_count == 1


def test_build_token_management_system_creates_postgres_tms_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    fake_tms = object()
    fake_root_module = MagicMock()
    fake_root_module.AEADEnvelopeEncryption = MagicMock(return_value="encryption")
    fake_root_module.ExternalEncryptionServiceKeyManagementProvider = MagicMock()
    fake_root_module.MockTokenManagementSystem = MagicMock()
    fake_root_module.PostgresTokenManagementSystem = MagicMock(return_value=fake_tms)
    fake_root_module.RedisTMSRefreshLock = MagicMock(return_value="refresh-lock")
    fake_root_module.TMSConfig = _FakeTMSConfig
    fake_root_module.TMSRuntimeEnvironment = types.SimpleNamespace(PRODUCTION="production")
    fake_tms_crypto_module = MagicMock()
    fake_tms_crypto_module.LocalKeyManagementProvider = MagicMock(return_value="local-kms")

    _patch_tms_config(monkeypatch, dependencies, ENV="local")
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_root_module)
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth.tms_crypto", fake_tms_crypto_module)

    result = dependencies._build_token_management_system(MagicMock(), MagicMock())

    assert result is fake_tms
    fake_root_module.MockTokenManagementSystem.assert_not_called()
    fake_tms_crypto_module.LocalKeyManagementProvider.assert_called_once_with("x" * 32, "test-key")
    fake_root_module.PostgresTokenManagementSystem.assert_called_once()


def test_build_token_management_system_rejects_plain_crypto_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    fake_root_module = MagicMock()
    fake_root_module.TMSConfig = _FakeTMSConfig
    fake_root_module.TMSRuntimeEnvironment = types.SimpleNamespace(PRODUCTION="production")
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_root_module)
    _patch_tms_config(monkeypatch, dependencies, ENV="production", ENCRYPTION_TYPE="plain")

    with pytest.raises(RuntimeError, match="KMS-backed encryption provider"):
        dependencies._build_token_management_system(MagicMock(), MagicMock())


def test_build_token_management_system_rejects_mock_tms_when_disabled_without_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    fake_root_module = MagicMock()
    fake_root_module.TMSConfig = _FakeTMSConfig
    fake_root_module.TMSRuntimeEnvironment = types.SimpleNamespace(PRODUCTION="production")
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_root_module)
    _patch_tms_config(monkeypatch, dependencies, MCP_AUTH_TMS_ENABLED=False, MCP_AUTH_TMS_ALLOW_MOCK=False)

    with pytest.raises(RuntimeError, match="production MCP auth requires TMS enabled"):
        dependencies._build_token_management_system(MagicMock(), MagicMock())


def test_build_token_management_system_rejects_mock_tms_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    fake_root_module = MagicMock()
    fake_root_module.MockTokenManagementSystem = MagicMock()
    fake_root_module.TMSConfig = MagicMock(side_effect=AssertionError("TMSConfig should not be constructed"))
    fake_root_module.TMSRuntimeEnvironment = types.SimpleNamespace(PRODUCTION="production")
    monkeypatch.setitem(sys.modules, "codemie_enterprise.mcp_auth", fake_root_module)
    _patch_tms_config(
        monkeypatch,
        dependencies,
        MCP_AUTH_TMS_ENABLED=False,
        ENV="production",
        MCP_AUTH_TMS_ALLOW_MOCK=True,
    )

    with pytest.raises(RuntimeError, match="production"):
        dependencies._build_token_management_system(MagicMock(), MagicMock())
    fake_root_module.TMSConfig.assert_not_called()
    fake_root_module.MockTokenManagementSystem.assert_not_called()


def test_store_callback_token_uses_audit_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    entered: list[tuple[str, str | None]] = []

    @contextmanager
    def audit_context(source: str, correlation_id: str | None = None):
        entered.append((source, correlation_id))
        yield

    tms = MagicMock()
    monkeypatch.setattr(dependencies, "_tms_audit_context", audit_context)

    dependencies._store_callback_token(
        user_id="user-1",
        auth_config_id="auth-1",
        token_data=MagicMock(),
        server_name="server",
        tms=tms,
        audit_source="oauth2_callback",
    )

    assert entered == [("oauth2_callback", "auth-1")]
    tms.store.assert_called_once()


def test_has_any_credentials_for_auth_config_uses_audit_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    entered: list[tuple[str, str | None]] = []

    @contextmanager
    def audit_context(source: str, correlation_id: str | None = None):
        entered.append((source, correlation_id))
        yield

    tms = MagicMock(has_any_credentials=MagicMock(return_value=True))
    dependencies._tms = tms
    monkeypatch.setattr(dependencies, "is_mcp_auth_enabled", lambda: True)
    monkeypatch.setattr(dependencies, "_tms_audit_context", audit_context)

    assert dependencies.has_any_credentials_for_auth_config("auth-1") is True
    assert entered == [("status_check", "auth-1")]


def test_invalidate_credentials_for_auth_config_uses_audit_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from codemie.enterprise.mcp_auth import dependencies

    entered: list[tuple[str, str | None]] = []

    @contextmanager
    def audit_context(source: str, correlation_id: str | None = None):
        entered.append((source, correlation_id))
        yield

    tms = MagicMock()
    dependencies._tms = tms
    monkeypatch.setattr(dependencies, "is_mcp_auth_enabled", lambda: True)
    monkeypatch.setattr(dependencies, "_tms_audit_context", audit_context)

    dependencies.invalidate_credentials_for_auth_config("auth-1")

    assert entered == [("admin_config_change", "auth-1")]
    tms.invalidate_by_config.assert_called_once_with("auth-1")


class _FakeTMSConfig:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)
