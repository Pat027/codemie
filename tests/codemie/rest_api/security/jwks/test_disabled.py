# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
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

import pytest

from codemie.rest_api.security.idp.factory import IdpFactory
from codemie.rest_api.security.idp.local import LocalIdp
from codemie.rest_api.security.jwks import runtime


class TestJwksDisabled:
    """Backward-compat: all six guarantees when JWKS_VALIDATION_ENABLED=False."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        runtime.reset_for_tests()
        yield
        runtime.reset_for_tests()

    @pytest.mark.asyncio
    async def test_warmup_is_noop(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.JWKS_VALIDATION_ENABLED", False)

        await runtime.jwks_warmup()

        assert runtime._get_singletons.cache_info().currsize == 0

    @pytest.mark.asyncio
    async def test_warmup_does_not_raise_with_empty_issuers(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.JWKS_VALIDATION_ENABLED", False)
        monkeypatch.setattr("codemie.configs.config.JWKS_TRUSTED_ISSUERS", "")

        # Must not raise ValueError("JWKS validation is enabled but JWKS_TRUSTED_ISSUERS is empty")
        await runtime.jwks_warmup()

    def test_factory_has_no_jwks_variants(self):
        providers = IdpFactory.get_registered_providers()
        jwks_variants = [p for p in providers if p.startswith("jwks-")]
        assert jwks_variants == [], f"Expected no jwks-* providers, found: {jwks_variants}"

    def test_factory_returns_local_idp_unwrapped(self):
        idp = IdpFactory.create("local")

        assert isinstance(idp, LocalIdp)
        # Confirm no JWKS wrapper — the class name must be exactly LocalIdp
        assert type(idp).__name__ == "LocalIdp"

    def test_factory_wraps_non_local_idp_when_jwks_enabled(self, monkeypatch):
        from codemie.rest_api.security.idp.base import BaseIdp
        from codemie.rest_api.security.idp.jwks_validating import JwksValidatingIdp
        from unittest.mock import MagicMock

        monkeypatch.setattr("codemie.configs.config.JWKS_VALIDATION_ENABLED", True)

        stub_class = type(
            "StubIdp",
            (BaseIdp,),
            {
                "get_session_cookie": lambda self: "",
                "authenticate": lambda self, r: None,
            },
        )
        IdpFactory.register("stub-provider", stub_class)
        monkeypatch.setattr(
            "codemie.rest_api.security.jwks.runtime.get_global_validator",
            lambda: MagicMock(),
        )

        try:
            idp = IdpFactory.create("stub-provider")
            assert isinstance(idp, JwksValidatingIdp)
        finally:
            IdpFactory.unregister("stub-provider")

    def test_reset_for_tests_clears_singletons(self, monkeypatch):
        from unittest.mock import MagicMock

        # Populate the lru_cache by patching _build to return mocks directly.
        monkeypatch.setattr(runtime, "_build", lambda: (MagicMock(), MagicMock()))
        runtime._get_singletons()
        assert runtime._get_singletons.cache_info().currsize == 1

        runtime.reset_for_tests()

        assert runtime._get_singletons.cache_info().currsize == 0
