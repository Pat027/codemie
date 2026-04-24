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

from importlib import import_module

_DEPENDENCY_EXPORTS = {
    "is_litellm_enabled",
    "initialize_litellm_from_config",
    "get_global_litellm_service",
    "set_global_litellm_service",
    "get_litellm_service_or_none",
    "require_litellm_enabled",
    "ensure_predefined_budgets",
    "sync_budgets_from_litellm",
    "backfill_user_budget_assignments",
    "get_category_budget_id",
    "check_user_budget",
    "get_customer_spending",
    "get_key_spending_info",
    "get_available_models",
    "is_proxy_budget_enabled",
    "get_proxy_customer_spending",
    "get_proxy_username",
    "is_premium_models_enabled",
    "is_premium_model",
    "get_premium_username",
    "get_premium_customer_spending",
}

_CLIENT_EXPORTS = {
    "get_llm_proxy_client",
    "close_llm_proxy_client",
}

_MODEL_EXPORTS = {
    "map_litellm_to_llm_model",
    "get_user_allowed_models",
}

_CREDENTIAL_EXPORTS = {
    "get_litellm_credentials_for_user",
}

_LLM_FACTORY_EXPORTS = {
    "create_litellm_chat_model",
    "create_litellm_embedding_model",
    "generate_litellm_headers_from_context",
    "get_litellm_chat_model",
    "get_litellm_embedding_model",
}

_PROXY_ROUTER_EXPORTS = {
    "proxy_router",
    "register_proxy_endpoints",
}

_BUDGET_HELPER_EXPORTS = {
    "create_budget_in_litellm",
    "get_budget_reset_at",
    "list_budgets_from_litellm",
    "reset_customer_spending_in_litellm",
    "update_budget_in_litellm",
    "update_customer_budget_in_litellm",
}

__all__ = sorted(
    _DEPENDENCY_EXPORTS
    | _CLIENT_EXPORTS
    | _MODEL_EXPORTS
    | _CREDENTIAL_EXPORTS
    | _LLM_FACTORY_EXPORTS
    | _PROXY_ROUTER_EXPORTS
    | _BUDGET_HELPER_EXPORTS
)


def __getattr__(name: str):
    if name in _DEPENDENCY_EXPORTS:
        dependencies = import_module(f"{__name__}.dependencies")
        value = getattr(dependencies, name)
        globals()[name] = value
        return value
    if name in _CLIENT_EXPORTS:
        client = import_module(f"{__name__}.client")
        value = getattr(client, name)
        globals()[name] = value
        return value
    if name in _MODEL_EXPORTS:
        models = import_module(f"{__name__}.models")
        value = getattr(models, name)
        globals()[name] = value
        return value
    if name in _CREDENTIAL_EXPORTS:
        credentials = import_module(f"{__name__}.credentials")
        value = getattr(credentials, name)
        globals()[name] = value
        return value
    if name in _LLM_FACTORY_EXPORTS:
        llm_factory = import_module(f"{__name__}.llm_factory")
        value = getattr(llm_factory, name)
        globals()[name] = value
        return value
    if name in _PROXY_ROUTER_EXPORTS:
        proxy_router_module = import_module(f"{__name__}.proxy_router")
        value = getattr(proxy_router_module, name)
        globals()[name] = value
        return value
    if name in _BUDGET_HELPER_EXPORTS:
        budget_helpers = import_module(f"{__name__}.budget_helpers")
        value = getattr(budget_helpers, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
