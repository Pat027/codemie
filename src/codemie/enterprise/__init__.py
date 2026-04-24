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

"""Enterprise integration layer."""

from __future__ import annotations

from importlib import import_module

_LOADER_EXPORTS = {
    "HAS_IDP",
    "HAS_LANGFUSE",
    "HAS_LITELLM",
    "HAS_PLUGIN",
    "BudgetTable",
    "CustomerInfo",
    "KeySpendingInfo",
    "LangFuseConfig",
    "LangFuseService",
    "LangfuseContextManager",
    "LiteLLMAPIClient",
    "LiteLLMConfig",
    "LiteLLMService",
    "PluginConfig",
    "PluginCredentials",
    "PluginService",
    "PluginToolkit",
    "ToolConsumer",
    "SpanContext",
    "TraceContext",
    "build_agent_metadata",
    "build_workflow_metadata",
    "has_idp",
    "has_langfuse",
    "has_litellm",
    "has_plugin",
}

_LANGFUSE_EXPORTS = {
    "build_agent_metadata_with_workflow_context",
    "clear_workflow_trace_context",
    "create_workflow_trace_context",
    "get_global_langfuse_service",
    "get_langfuse_callback_handler",
    "get_langfuse_client_or_none",
    "get_langfuse_service",
    "get_workflow_trace_context",
    "initialize_langfuse_from_config",
    "is_langfuse_enabled",
    "require_langfuse_client",
    "set_global_langfuse_service",
}

_LITELLM_EXPORTS = {
    "check_user_budget",
    "close_llm_proxy_client",
    "create_litellm_chat_model",
    "create_litellm_embedding_model",
    "ensure_predefined_budgets",
    "get_category_budget_id",
    "generate_litellm_headers_from_context",
    "get_available_models",
    "get_customer_spending",
    "get_global_litellm_service",
    "get_key_spending_info",
    "get_litellm_chat_model",
    "get_litellm_credentials_for_user",
    "get_litellm_embedding_model",
    "get_litellm_service_or_none",
    "get_llm_proxy_client",
    "get_user_allowed_models",
    "initialize_litellm_from_config",
    "is_litellm_enabled",
    "map_litellm_to_llm_model",
    "proxy_router",
    "register_proxy_endpoints",
    "require_litellm_enabled",
    "set_global_litellm_service",
}

_PLUGIN_EXPORTS = {
    "get_global_plugin_service",
    "get_plugin_service_or_none",
    "get_plugin_tools_for_assistant",
    "initialize_plugin_from_config",
    "is_plugin_enabled",
    "set_global_plugin_service",
}

_IDP_EXPORTS = {
    "is_enterprise_idp_available",
    "register_enterprise_idps",
}

__all__ = sorted(_LOADER_EXPORTS | _LANGFUSE_EXPORTS | _LITELLM_EXPORTS | _PLUGIN_EXPORTS | _IDP_EXPORTS)


def __getattr__(name: str):
    if name in _LOADER_EXPORTS:
        loader = import_module(f"{__name__}.loader")
        value = getattr(loader, name)
        globals()[name] = value
        return value
    if name in _LANGFUSE_EXPORTS:
        langfuse = import_module(f"{__name__}.langfuse")
        value = getattr(langfuse, name)
        globals()[name] = value
        return value
    if name in _LITELLM_EXPORTS:
        litellm = import_module(f"{__name__}.litellm")
        value = getattr(litellm, name)
        globals()[name] = value
        return value
    if name in _PLUGIN_EXPORTS:
        plugin = import_module(f"{__name__}.plugin")
        value = getattr(plugin, name)
        globals()[name] = value
        return value
    if name in _IDP_EXPORTS:
        idp = import_module(f"{__name__}.idp")
        value = getattr(idp, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
