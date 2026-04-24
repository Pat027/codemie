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

from importlib import import_module

_DEPENDENCY_EXPORTS = {
    "is_langfuse_enabled",
    "initialize_langfuse_from_config",
    "get_global_langfuse_service",
    "set_global_langfuse_service",
    "get_langfuse_service",
    "get_langfuse_callback_handler",
    "require_langfuse_client",
    "get_langfuse_client_or_none",
}

_WORKFLOW_EXPORTS = {
    "create_workflow_trace_context",
    "get_workflow_trace_context",
    "clear_workflow_trace_context",
    "build_agent_metadata_with_workflow_context",
}

__all__ = sorted(_DEPENDENCY_EXPORTS | _WORKFLOW_EXPORTS)


def __getattr__(name: str):
    if name in _DEPENDENCY_EXPORTS:
        dependencies = import_module(f"{__name__}.dependencies")
        value = getattr(dependencies, name)
        globals()[name] = value
        return value
    if name in _WORKFLOW_EXPORTS:
        workflows = import_module(f"{__name__}.workflows")
        value = getattr(workflows, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
