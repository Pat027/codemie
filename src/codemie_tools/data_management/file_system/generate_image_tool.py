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

import base64
import io
import uuid
from typing import Any, Optional, Protocol, Type

from langchain_core.messages import AIMessage, HumanMessage
from openai import AzureOpenAI
from pydantic import BaseModel, Field

from codemie_tools.base.codemie_tool import CodeMieTool
from codemie_tools.data_management.file_system.tools_vars import GENERATE_IMAGE_TOOL


class LiteLLMImageConfig(BaseModel):
    api_base: str
    api_key: str
    api_version: str
    model_id: str
    timeout: float = 60.0


def _resolve_image_url(url: str) -> tuple[str | None, str | None]:
    """Return (url, b64_data). Splits inline data-URLs into raw b64."""
    if url.startswith("data:image"):
        return None, url.split(",", 1)[1]
    return url, None


class ImageGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Generate an image from a prompt. Returns (url, b64_data)."""
        ...

    def edit(
        self,
        prompt: str,
        image: bytes,
        mask: bytes | None = None,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Edit or inpaint an image. Returns (url, b64_data)."""
        ...


class LiteLLMImageGenerator:
    """Calls an AzureOpenAI-compatible image endpoint for generations and edits."""

    def __init__(self, config: LiteLLMImageConfig) -> None:
        self._model_id = config.model_id
        self._client = AzureOpenAI(
            azure_endpoint=config.api_base,
            api_key=config.api_key,
            api_version=config.api_version,
            timeout=config.timeout,
        )

    def generate(
        self,
        prompt: str,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        request: dict[str, Any] = {"model": self._model_id, "prompt": prompt, "n": 1}
        if size:
            request["size"] = size
        if output_format:
            request["output_format"] = output_format

        item = self._client.images.generate(**request).data[0]
        if item.url:
            return _resolve_image_url(item.url)
        return None, item.b64_json

    def edit(
        self,
        prompt: str,
        image: bytes,
        mask: bytes | None = None,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        image_file = ("image.png", io.BytesIO(image), "image/png")
        request: dict[str, Any] = {
            "model": self._model_id,
            "image": image_file,
            "prompt": prompt,
        }
        if mask is not None:
            request["mask"] = ("mask.png", io.BytesIO(mask), "image/png")
        if size:
            request["size"] = size
        if output_format:
            request["output_format"] = output_format

        item = self._client.images.edit(**request).data[0]
        if item.url:
            return _resolve_image_url(item.url)
        return None, item.b64_json


class ChatModelImageGenerator:
    """Calls ChatVertexAI (or any LangChain wrapper) via invoke() based on model."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def generate(
        self,
        prompt: str,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        response: AIMessage = self._model.invoke([HumanMessage(content=prompt)])
        if isinstance(response.content, list):
            for part in response.content:
                if isinstance(part, dict):
                    if url := part.get("image_url", {}).get("url"):
                        return _resolve_image_url(url)
                    if b64 := part.get("data"):
                        return None, b64
        return None, None

    def edit(
        self,
        prompt: str,
        image: bytes,
        mask: bytes | None = None,
        size: str | None = None,
        output_format: str | None = None,
    ) -> tuple[str | None, str | None]:
        raise NotImplementedError("This image generator does not support inpainting or image edits.")


class GenerateImagesToolInput(BaseModel):
    image_description: str = Field(
        description="Detailed image description or detailed user ask for generating an image."
    )


class GenerateImageTool(CodeMieTool):
    name: str = GENERATE_IMAGE_TOOL.name
    description: str = GENERATE_IMAGE_TOOL.description or ""
    args_schema: Any = GenerateImagesToolInput
    image_generator: Optional[Any] = Field(exclude=True, default=None)
    file_repository: Optional[Any] = Field(exclude=True, default=None)
    user_id: str = ""

    def execute(self, image_description: str, *args, **kwargs) -> Any:
        if not self.image_generator:
            raise ValueError("Image generation is not configured.")
        url, b64_data = self.image_generator.generate(image_description)
        return self._resolve_output(url, b64_data)

    def _resolve_output(self, url: str | None, b64_data: str | None) -> str:
        if not url and not b64_data:
            raise ValueError("Image generation returned no image data.")
        if b64_data:
            return self._store_b64_image(b64_data)
        if url is None:
            raise ValueError("Image generation returned no image data.")
        return url

    def _store_b64_image(self, b64_data: str) -> str:
        if not self.file_repository:
            raise ValueError("Image generation returned base64 data but no file repository is configured.")
        filename = f"{uuid.uuid4()}.png"
        stored_file = self.file_repository.write_file(
            name=filename,
            mime_type="image/png",
            content=base64.b64decode(b64_data),
            owner=self.user_id,
        )
        return f"sandbox:/v1/files/{stored_file.to_encoded_url()}"
