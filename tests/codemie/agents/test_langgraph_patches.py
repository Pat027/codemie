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

import pytest
from unittest.mock import MagicMock, patch as mock_patch

from langchain_core.messages import AIMessage, HumanMessage

from codemie.agents.langgraph_patches import (
    _make_prefill_safe_afunc,
    _make_prefill_safe_func,
    _patch_generate_structured_response_node,
    _rewrap_trailing_ai_message,
)


def _ai(content: str = "agent response", tool_calls=None) -> AIMessage:
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


def _human(content: str = "user question") -> HumanMessage:
    return HumanMessage(content=content)


def _make_mock_graph(with_node: bool = True, afunc=None):
    """Build a minimal MagicMock that looks like a compiled LangGraph graph."""
    original_func = MagicMock(return_value={"structured_response": "result"})
    node = MagicMock()
    node.bound.func = original_func
    node.bound.afunc = afunc
    graph = MagicMock()
    if with_node:
        graph.nodes = {"generate_structured_response": node}
    else:
        graph.nodes = {}
    return graph, node, original_func


class TestRewrapTrailingAiMessage:
    def test_empty_list_unchanged(self):
        assert _rewrap_trailing_ai_message([]) == []

    def test_no_trailing_ai_unchanged(self):
        messages = [_human(), _ai(tool_calls=[{"name": "t", "args": {}, "id": "c1", "type": "tool_call"}])]
        assert _rewrap_trailing_ai_message(messages) is messages

    def test_trailing_human_unchanged(self):
        messages = [_ai(), _human()]
        assert _rewrap_trailing_ai_message(messages) is messages

    def test_trailing_plain_ai_rewrapped_as_human(self):
        messages = [_human("q"), _ai("my answer")]
        result = _rewrap_trailing_ai_message(messages)
        assert result is not messages
        assert len(result) == 2
        assert isinstance(result[-1], HumanMessage)

    def test_rewrapped_content_uses_template(self):
        messages = [_ai("the agent said this")]
        result = _rewrap_trailing_ai_message(messages)
        assert "The previous response was:" in result[-1].content
        assert "the agent said this" in result[-1].content
        assert "Continue from this point." in result[-1].content

    def test_preceding_messages_preserved(self):
        messages = [_human("q"), _ai("mid"), _ai("final")]
        result = _rewrap_trailing_ai_message(messages)
        assert result[0] == messages[0]
        assert result[1] == messages[1]

    def test_trailing_ai_with_tool_calls_not_rewrapped(self):
        tool_calls = [{"name": "search", "args": {}, "id": "call_1", "type": "tool_call"}]
        messages = [_human(), _ai(tool_calls=tool_calls)]
        assert _rewrap_trailing_ai_message(messages) is messages


class TestMakePrefillSafeFunc:
    def test_rewraps_trailing_ai_before_delegation(self):
        captured = {}

        def original(state, runtime, config):
            captured["state"] = state
            return {"structured_response": "done"}

        wrapped = _make_prefill_safe_func(original)
        state = {"messages": [_human("q"), _ai("answer")]}
        wrapped(state, "runtime", "config")

        last = captured["state"]["messages"][-1]
        assert isinstance(last, HumanMessage)
        assert "answer" in last.content

    def test_no_rewrap_when_not_needed(self):
        captured = {}

        def original(state, runtime, config):
            captured["state"] = state
            return {}

        wrapped = _make_prefill_safe_func(original)
        messages = [_human()]
        state = {"messages": messages}
        wrapped(state, None, None)

        assert captured["state"]["messages"] is messages

    def test_passes_runtime_and_config_through(self):
        captured = {}

        def original(state, runtime, config):
            captured["runtime"] = runtime
            captured["config"] = config
            return {}

        wrapped = _make_prefill_safe_func(original)
        wrapped({"messages": []}, "my_runtime", "my_config")

        assert captured["runtime"] == "my_runtime"
        assert captured["config"] == "my_config"

    def test_returns_original_result(self):
        def original(state, runtime, config):
            return {"structured_response": {"answer": 42}}

        wrapped = _make_prefill_safe_func(original)
        result = wrapped({"messages": []}, None, None)
        assert result == {"structured_response": {"answer": 42}}


class TestMakePrefillSafeAfunc:
    @pytest.mark.asyncio
    async def test_rewraps_trailing_ai_before_delegation(self):
        captured = {}

        async def original(state, runtime, config):
            captured["state"] = state
            return {"structured_response": "done"}

        wrapped = _make_prefill_safe_afunc(original)
        state = {"messages": [_human("q"), _ai("async answer")]}
        await wrapped(state, None, None)

        last = captured["state"]["messages"][-1]
        assert isinstance(last, HumanMessage)
        assert "async answer" in last.content

    @pytest.mark.asyncio
    async def test_no_rewrap_when_not_needed(self):
        captured = {}

        async def original(state, runtime, config):
            captured["state"] = state
            return {}

        wrapped = _make_prefill_safe_afunc(original)
        messages = [_human()]
        state = {"messages": messages}
        await wrapped(state, None, None)

        assert captured["state"]["messages"] is messages

    @pytest.mark.asyncio
    async def test_returns_original_result(self):
        async def original(state, runtime, config):
            return {"structured_response": "async_result"}

        wrapped = _make_prefill_safe_afunc(original)
        result = await wrapped({"messages": []}, None, None)
        assert result == {"structured_response": "async_result"}


class TestPatchGenerateStructuredResponseNode:
    def test_patches_func_in_place(self):
        graph, node, original_func = _make_mock_graph()
        _patch_generate_structured_response_node(graph)
        assert node.bound.func is not original_func

    def test_patches_afunc_when_present(self):
        original_afunc = MagicMock()
        graph, node, _ = _make_mock_graph(afunc=original_afunc)
        _patch_generate_structured_response_node(graph)
        assert node.bound.afunc is not original_afunc

    def test_leaves_afunc_none_when_absent(self):
        graph, node, _ = _make_mock_graph(afunc=None)
        _patch_generate_structured_response_node(graph)
        assert node.bound.afunc is None

    def test_no_op_when_node_absent(self):
        graph, _, _ = _make_mock_graph(with_node=False)
        # Should not raise
        _patch_generate_structured_response_node(graph)

    def test_patched_func_rewraps_on_call(self):
        """End-to-end: patched func rewraps trailing AIMessage before delegating."""
        captured = {}

        def original_func(state, runtime, config):
            captured["state"] = state
            return {}

        node = MagicMock()
        node.bound.func = original_func
        node.bound.afunc = None
        graph = MagicMock()
        graph.nodes = {"generate_structured_response": node}

        _patch_generate_structured_response_node(graph)

        state = {"messages": [_human("q"), _ai("final answer")]}
        graph.nodes["generate_structured_response"].bound.func(state, None, None)

        last = captured["state"]["messages"][-1]
        assert isinstance(last, HumanMessage)
        assert "final answer" in last.content


class TestSmartReactAgentCallSitesPatch:
    """Verify smart_react_agent.py applies the patch at both create_react_agent call sites."""

    def _make_compiled_graph_mock(self):
        original_func = MagicMock(return_value={})
        node = MagicMock()
        node.bound.func = original_func
        node.bound.afunc = None
        graph = MagicMock()
        graph.nodes = {"generate_structured_response": node}
        return graph, node, original_func

    def test_create_standard_react_agent_patches_node(self):
        from codemie.agents.smart_react_agent import _create_standard_react_agent

        compiled, node, original_func = self._make_compiled_graph_mock()
        with mock_patch("codemie.agents.smart_react_agent.create_react_agent", return_value=compiled):
            result = _create_standard_react_agent(
                model=MagicMock(),
                tools=[],
                prompt=None,
                response_format=MagicMock(),
                name=None,
                parallel_tool_calls=None,
            )
        assert result is compiled
        assert node.bound.func is not original_func

    def test_create_sub_agent_patches_node(self):
        from codemie.agents.smart_react_agent import _create_sub_agent

        compiled, node, original_func = self._make_compiled_graph_mock()
        with mock_patch("codemie.agents.smart_react_agent.create_react_agent", return_value=compiled):
            result = _create_sub_agent(
                model=MagicMock(),
                available_tools=[],
                prompt=None,
                response_format=MagicMock(),
                name=None,
                parallel_tool_calls=None,
            )
        assert result is compiled
        assert node.bound.func is not original_func

    def test_no_patch_when_node_absent(self):
        from codemie.agents.smart_react_agent import _create_standard_react_agent

        graph_no_node = MagicMock()
        graph_no_node.nodes = {}
        with mock_patch("codemie.agents.smart_react_agent.create_react_agent", return_value=graph_no_node):
            result = _create_standard_react_agent(
                model=MagicMock(),
                tools=[],
                prompt=None,
                response_format=None,
                name=None,
                parallel_tool_calls=None,
            )
        assert result is graph_no_node
