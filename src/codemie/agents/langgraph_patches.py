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

"""
Patch for LangGraph's generate_structured_response node to fix Bedrock compatibility.

When response_format is set, create_react_agent adds a generate_structured_response
node that calls the model with the full state["messages"] list. If the last message is
a plain AIMessage (no tool_calls), Bedrock raises HTTP 400:
  "This model does not support assistant message prefill."

This module provides _patch_generate_structured_response_node, which mutates the
compiled graph's node callable in-place. Call it immediately after create_react_agent
returns to make structured-output agents safe for Bedrock.

Relies on LangGraph 1.1.6 internals: compiled_graph.nodes[name].bound is a
RunnableCallable with replaceable .func and .afunc instance attributes.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

_REWRAP_TEMPLATE = "The previous response was:\n\n{content}\n\nContinue from this point."


def _rewrap_trailing_ai_message(messages: list) -> list:
    """Replace a trailing plain AIMessage with a HumanMessage that wraps its content."""
    if messages and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls:
        content = messages[-1].content
        return list(messages[:-1]) + [HumanMessage(content=_REWRAP_TEMPLATE.format(content=content))]
    return messages


def _make_prefill_safe_func(original_func: Callable[..., Any]) -> Callable[..., Any]:
    def patched(state, runtime, config):
        messages = state.get("messages", []) if hasattr(state, "get") else []
        rewrapped = _rewrap_trailing_ai_message(messages)
        if rewrapped is not messages:
            state = {**state, "messages": rewrapped}
        return original_func(state, runtime, config)

    return patched


def _make_prefill_safe_afunc(
    original_afunc: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    async def apatched(state, runtime, config):
        messages = state.get("messages", []) if hasattr(state, "get") else []
        rewrapped = _rewrap_trailing_ai_message(messages)
        if rewrapped is not messages:
            state = {**state, "messages": rewrapped}
        return await original_afunc(state, runtime, config)

    return apatched


def _patch_generate_structured_response_node(compiled_graph) -> None:
    """Mutate the generate_structured_response node in-place to fix Bedrock prefill rejection.

    No-op when the node is absent (i.e., response_format=None was passed to create_react_agent).
    """
    if "generate_structured_response" not in compiled_graph.nodes:
        return
    node = compiled_graph.nodes["generate_structured_response"]
    node.bound.func = _make_prefill_safe_func(node.bound.func)
    if node.bound.afunc is not None:
        node.bound.afunc = _make_prefill_safe_afunc(node.bound.afunc)
