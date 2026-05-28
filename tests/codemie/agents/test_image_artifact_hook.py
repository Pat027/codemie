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


from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from codemie.agents.image_artifact_hook import image_artifact_pre_model_hook as _image_artifact_pre_model_hook
from codemie.agents.langgraph_agent import _compose_pre_model_hooks


def _make_tool_message(content: str = "ok", artifact=None, **kwargs) -> ToolMessage:
    return ToolMessage(content=content, tool_call_id="call_1", artifact=artifact, **kwargs)


def _make_ai_message(content: str = "thinking...", tool_calls=None) -> AIMessage:
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


class TestHookNoOp:
    def test_empty_messages(self) -> None:
        result = _image_artifact_pre_model_hook({"messages": []})
        assert result["llm_input_messages"] == []

    def test_no_messages_key(self) -> None:
        result = _image_artifact_pre_model_hook({})
        assert result["llm_input_messages"] == []

    def test_no_artifacts(self) -> None:
        messages = [
            HumanMessage(content="Show me TEST-1"),
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="HTTP: GET ... 200 OK"),
        ]
        result = _image_artifact_pre_model_hook({"messages": messages})
        assert result["llm_input_messages"] == messages

    def test_artifact_is_none(self) -> None:
        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="text", artifact=None),
        ]
        result = _image_artifact_pre_model_hook({"messages": messages})
        assert result["llm_input_messages"] == messages

    def test_artifact_without_image_keys(self) -> None:
        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="text", artifact=[{"some": "data"}]),
        ]
        result = _image_artifact_pre_model_hook({"messages": messages})
        assert result["llm_input_messages"] == messages


class TestHookInjectsImages:
    def test_injects_single_image(self) -> None:
        artifact = [{"data": "base64data", "mime_type": "image/png", "filename": "err.png"}]
        messages = [
            HumanMessage(content="Fetch TEST-1"),
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="HTTP: GET ... 200 OK", artifact=artifact),
        ]

        result = _image_artifact_pre_model_hook({"messages": messages})
        llm_messages = result["llm_input_messages"]

        assert len(llm_messages) == len(messages) + 1
        injected = llm_messages[-1]
        assert isinstance(injected, HumanMessage)
        assert isinstance(injected.content, list)
        assert len(injected.content) == 2
        text_block = injected.content[0]
        image_block = injected.content[1]
        assert isinstance(text_block, dict)
        assert isinstance(image_block, dict)
        assert text_block["type"] == "text"
        assert image_block["type"] == "image"
        assert image_block["base64"] == "base64data"
        assert image_block["mime_type"] == "image/png"

    def test_injects_multiple_images_from_one_tool(self) -> None:
        artifact = [
            {"data": "img1", "mime_type": "image/png", "filename": "a.png"},
            {"data": "img2", "mime_type": "image/jpeg", "filename": "b.jpg"},
        ]
        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="ok", artifact=artifact),
        ]

        result = _image_artifact_pre_model_hook({"messages": messages})
        injected = result["llm_input_messages"][-1]

        assert len(injected.content) == 3  # 1 text + 2 images

    def test_does_not_modify_original_messages(self) -> None:
        artifact = [{"data": "x", "mime_type": "image/png"}]
        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="ok", artifact=artifact),
        ]
        original_len = len(messages)

        _image_artifact_pre_model_hook({"messages": messages})

        assert len(messages) == original_len  # original list not mutated


class TestHookScoping:
    def test_injects_images_inline_after_each_tool_group(self) -> None:
        """Images are placed right after the ToolMessage that produced them."""
        old_artifact = [{"data": "old_image", "mime_type": "image/png"}]
        new_artifact = [{"data": "new_image", "mime_type": "image/jpeg"}]

        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="round1", artifact=old_artifact),
            _make_ai_message(content="I analyzed the old image"),
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_2"}]),
            ToolMessage(content="round2", tool_call_id="call_2", artifact=new_artifact),
        ]

        result = _image_artifact_pre_model_hook({"messages": messages})
        output = result["llm_input_messages"]

        # Images from round 1 are injected after TM1 (before AI response)
        assert isinstance(output[2], HumanMessage)
        assert isinstance(output[2].content, list)
        block1 = output[2].content[1]
        assert isinstance(block1, dict)
        assert block1["base64"] == "old_image"
        # Images from round 2 are injected at the end (after TM2)
        assert isinstance(output[-1], HumanMessage)
        assert isinstance(output[-1].content, list)
        block2 = output[-1].content[1]
        assert isinstance(block2, dict)
        assert block2["base64"] == "new_image"

    def test_injection_persists_after_ai_response(self) -> None:
        """Images are injected inline even when AI has already responded."""
        artifact = [{"data": "img", "mime_type": "image/png"}]
        messages = [
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="ok", artifact=artifact),
            _make_ai_message(content="Done analyzing"),
        ]

        result = _image_artifact_pre_model_hook({"messages": messages})
        output = result["llm_input_messages"]
        # Image is placed after TM, before AI response
        assert isinstance(output[2], HumanMessage)
        assert isinstance(output[2].content, list)
        img_block = output[2].content[1]
        assert isinstance(img_block, dict)
        assert img_block["base64"] == "img"
        # AI response follows
        assert isinstance(output[3], AIMessage)


class TestComposePreModelHooks:
    def test_returns_none_when_no_hooks(self) -> None:
        assert _compose_pre_model_hooks() is None

    def test_runs_image_hook_on_compacted_messages(self) -> None:
        original_messages = [
            HumanMessage(content="older question"),
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_1"}]),
            _make_tool_message(content="round1", artifact=[{"data": "old", "mime_type": "image/png"}]),
        ]
        compacted_messages = [
            HumanMessage(content="latest question"),
            _make_ai_message(content="", tool_calls=[{"name": "jira", "args": {}, "id": "call_2"}]),
            _make_tool_message(content="round2", artifact=[{"data": "new", "mime_type": "image/jpeg"}]),
        ]

        def compaction_hook(state: dict) -> dict:
            assert state["messages"] == original_messages
            return {"llm_input_messages": compacted_messages}

        combined_hook = _compose_pre_model_hooks(compaction_hook, _image_artifact_pre_model_hook)
        assert combined_hook is not None

        result = combined_hook({"messages": original_messages})

        assert result["llm_input_messages"][:-1] == compacted_messages
        injected = result["llm_input_messages"][-1]
        assert isinstance(injected, HumanMessage)
        assert isinstance(injected.content, list)
        injected_block = injected.content[1]
        assert isinstance(injected_block, dict)
        assert injected_block["base64"] == "new"

    def test_preserves_other_hook_updates(self) -> None:
        def hook_one(_state: dict) -> dict:
            return {"custom": "value"}

        def hook_two(state: dict) -> dict:
            return {"llm_input_messages": state["messages"]}

        combined_hook = _compose_pre_model_hooks(hook_one, hook_two)
        assert combined_hook is not None

        assert combined_hook({"messages": [HumanMessage(content="hi")]}) == {
            "custom": "value",
            "llm_input_messages": [HumanMessage(content="hi")],
        }
