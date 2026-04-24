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

from types import SimpleNamespace

from codemie.service.llm_proxy.provider_registry import get_active_llm_proxy_provider, register_llm_proxy_provider


def test_noop_llm_proxy_provider_returns_safe_defaults(monkeypatch):
    import codemie.service.llm_proxy.provider_registry as provider_registry

    monkeypatch.setattr(provider_registry, "_active_provider", None)
    provider = get_active_llm_proxy_provider()

    provider.close()
    provider.clean_expired_customer_cache()
    provider.clean_expired_models_cache()
    provider.reload_models_cache()

    assert provider.is_available() is False
    assert provider.get_keys_info_by_alias(["alias-1"], include_details=False, page=2, size=10) == []
    assert provider.get_all_keys_spending(include_details=False, page=2, size=10) == []


def test_register_llm_proxy_provider_overrides_noop(monkeypatch):
    import codemie.service.llm_proxy.provider_registry as provider_registry

    monkeypatch.setattr(provider_registry, "_active_provider", None)
    custom_provider = SimpleNamespace(provider_name="custom")

    register_llm_proxy_provider(custom_provider)

    assert get_active_llm_proxy_provider() is custom_provider
