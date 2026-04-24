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

"""LLM proxy lifecycle provider registry.

Enterprise code registers a provider implementation at startup via
``register_llm_proxy_provider``.  Core code calls
``get_active_llm_proxy_provider`` to obtain the active provider (or the
noop fallback).
"""

from __future__ import annotations

from codemie.service.llm_proxy.provider import LLMProxyProvider

_NOOP_PROVIDER_NAME = "noop"

_active_provider: LLMProxyProvider | None = None


def register_llm_proxy_provider(provider: LLMProxyProvider) -> None:
    """Register the active LLM proxy provider.  Called once at startup by enterprise code."""
    global _active_provider
    _active_provider = provider


def get_active_llm_proxy_provider() -> LLMProxyProvider:
    """Return the registered provider, or the noop fallback if none is registered."""
    if _active_provider is not None:
        return _active_provider
    return _NOOP_PROVIDER


class _NoopLLMProxyProvider:
    """Noop provider used in non-enterprise / LiteLLM-disabled mode.

    All methods succeed without side effects so that core code never needs to
    branch on whether a real provider is registered.
    """

    provider_name: str = _NOOP_PROVIDER_NAME

    def is_available(self) -> bool:
        return False

    def close(self) -> None:
        # The noop provider does not acquire external resources.
        return None

    def clean_expired_customer_cache(self) -> None:
        # No caches are populated when the proxy integration is disabled.
        return None

    def clean_expired_models_cache(self) -> None:
        # No caches are populated when the proxy integration is disabled.
        return None

    def reload_models_cache(self) -> None:
        # No caches are populated when the proxy integration is disabled.
        return None

    def get_keys_info_by_alias(
        self,
        aliases: list[str],
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list:
        _ = (aliases, include_details, page, size)
        return []

    def get_all_keys_spending(
        self,
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list:
        _ = (include_details, page, size)
        return []


_NOOP_PROVIDER: LLMProxyProvider = _NoopLLMProxyProvider()  # type: ignore[assignment]
