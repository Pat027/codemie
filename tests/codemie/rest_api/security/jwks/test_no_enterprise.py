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

"""OSS-compatibility tests: JWKS behaviour when codemie-enterprise is absent.

All tests patch `HAS_IDP=False` directly on the runtime module so they run
correctly in both environments — enterprise installed or not. The real
installed state of the package is irrelevant.

Key patching note: `runtime.py` imports `HAS_IDP` by value at module level
(`from codemie.enterprise.loader import HAS_IDP`), so the patch target must
be `codemie.rest_api.security.jwks.runtime.HAS_IDP`, not the loader module.
"""

from __future__ import annotations

import pytest

from codemie.rest_api.security.idp.factory import IdpFactory
from codemie.rest_api.security.jwks import runtime


_RUNTIME_HAS_IDP = "codemie.rest_api.security.jwks.runtime.HAS_IDP"
_JWKS_ENABLED = "codemie.configs.config.JWKS_VALIDATION_ENABLED"


class TestJwksWithoutEnterprise:
    """Guarantees when codemie-enterprise is absent (HAS_IDP patched to False)."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        monkeypatch.setattr(_RUNTIME_HAS_IDP, False)
        runtime.reset_for_tests()
        yield
        runtime.reset_for_tests()

    @pytest.mark.asyncio
    async def test_warmup_is_noop_when_jwks_disabled(self, monkeypatch):
        """JWKS_VALIDATION_ENABLED=False → warmup is a no-op even without enterprise."""
        monkeypatch.setattr(_JWKS_ENABLED, False)

        await runtime.jwks_warmup()

        assert runtime._get_singletons.cache_info().currsize == 0

    @pytest.mark.asyncio
    async def test_warmup_logs_error_and_does_not_crash(self, monkeypatch):
        """JWKS_VALIDATION_ENABLED=True but no enterprise → log error, do not crash.

        We monkeypatch the module-level logger so we can assert on the error
        message without depending on how the custom structured logger routes output.
        """
        from unittest.mock import MagicMock

        mock_logger = MagicMock()
        monkeypatch.setattr("codemie.rest_api.security.jwks.runtime.logger", mock_logger)
        monkeypatch.setattr(_JWKS_ENABLED, True)
        monkeypatch.setattr("codemie.configs.config.JWKS_TRUSTED_ISSUERS", "[]")

        await runtime.jwks_warmup()

        assert runtime._get_singletons.cache_info().currsize == 0
        mock_logger.error.assert_called_once()
        logged_message = mock_logger.error.call_args[0][0]
        assert "codemie-enterprise" in logged_message

    def test_get_global_validator_raises_runtime_error(self, monkeypatch):
        """get_global_validator() raises RuntimeError with a clear message."""
        monkeypatch.setattr(_JWKS_ENABLED, True)
        monkeypatch.setattr("codemie.configs.config.JWKS_TRUSTED_ISSUERS", "[]")

        with pytest.raises(RuntimeError, match="codemie-enterprise"):
            runtime.get_global_validator()

    def test_get_global_jwks_client_raises_runtime_error(self, monkeypatch):
        """get_global_jwks_client() raises RuntimeError with a clear message."""
        monkeypatch.setattr(_JWKS_ENABLED, True)
        monkeypatch.setattr("codemie.configs.config.JWKS_TRUSTED_ISSUERS", "[]")

        with pytest.raises(RuntimeError, match="codemie-enterprise"):
            runtime.get_global_jwks_client()

    def test_jwks_package_type_exports_are_none(self):
        """codemie.rest_api.security.jwks re-exports are None when enterprise absent."""
        import codemie.rest_api.security.jwks as jwks_pkg

        assert jwks_pkg.JwksClient is None
        assert jwks_pkg.TokenSignatureValidator is None
        assert jwks_pkg.TrustedIssuer is None
        assert jwks_pkg.JwksError is None
        assert jwks_pkg.JwksFetchError is None
        assert jwks_pkg.KidNotFoundError is None

    def test_no_jwks_idp_variants_registered(self):
        """IdpFactory has no jwks-* providers when enterprise is absent."""
        providers = IdpFactory.get_registered_providers()
        jwks_variants = [p for p in providers if p.startswith("jwks-")]
        assert jwks_variants == [], f"Unexpected jwks-* providers: {jwks_variants}"
