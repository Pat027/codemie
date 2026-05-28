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

from langchain_core.messages import HumanMessage, ImageContentBlock, TextContentBlock, ToolMessage


def _extract_image_blocks(artifact: list) -> list[ImageContentBlock]:
    return [
        ImageContentBlock(type="image", base64=item["data"], mime_type=item["mime_type"])
        for item in artifact
        if isinstance(item, dict) and "data" in item and "mime_type" in item
    ]


def _make_image_message(blocks: list[ImageContentBlock]) -> HumanMessage:
    return HumanMessage(
        content=[
            TextContentBlock(type="text", text="[Attached images from the tool response above]"),
            *blocks,
        ]
    )


def image_artifact_pre_model_hook(state: dict) -> dict:
    """Inject images from ToolMessage.artifact right after the tool group that produced them."""
    messages = state.get("messages", [])
    result: list = []
    pending: list[ImageContentBlock] = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            artifact = getattr(msg, "artifact", None)
            if isinstance(artifact, list):
                pending.extend(_extract_image_blocks(artifact))
        else:
            if pending:
                result.append(_make_image_message(pending))
                pending = []
        result.append(msg)

    if pending:
        result.append(_make_image_message(pending))

    return {"llm_input_messages": result}
