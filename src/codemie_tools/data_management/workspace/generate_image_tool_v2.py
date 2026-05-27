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

import base64
import io
import re
from datetime import datetime, timezone
from typing import Any, Type

import requests
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from codemie.configs.logger import logger
from codemie.core.exceptions import ValidationException
from codemie_tools.data_management.workspace.tools import BaseWorkspaceTool
from codemie_tools.data_management.workspace.tools_vars import GENERATE_WORKSPACE_IMAGE_TOOL_V2

_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xX:]\s*(\d+(?:[.,]\d+)?)\s*$")
_PNG_MIME_TYPE = "image/png"
_HTTP_TIMEOUT_SECONDS = 30
_BACKGROUND_VALUES = {"light", "dark"}
_MIN_DIMENSION = 1024
_MAX_DIMENSION = 1536
_BOUNDING_BOXES = {
    "landscape": (_MAX_DIMENSION, _MIN_DIMENSION),
    "square": (_MIN_DIMENSION, _MIN_DIMENSION),
    "portrait": (_MIN_DIMENSION, _MAX_DIMENSION),
}
_OUTPUT_FORMAT = "png"


class GenerateWorkspaceImageToolV2Input(BaseModel):
    image_description: str = Field(
        description="Detailed image description or detailed user ask for generating an image."
    )
    size: str = Field(
        description="Requested image size in the format 'widthxheight', for example '1920x1080'. Or you can simple specify aspect ratio like '5:12'"
    )
    background: str = Field(
        default="light",
        description="Background hint for the generated image. Allowed values: 'light' or 'dark'.",
    )


class GenerateWorkspaceImageToolV2(BaseWorkspaceTool):
    name: str = GENERATE_WORKSPACE_IMAGE_TOOL_V2.name
    description: str = GENERATE_WORKSPACE_IMAGE_TOOL_V2.description or ""
    args_schema: Any = GenerateWorkspaceImageToolV2Input
    image_generator: Any | None = Field(default=None, exclude=True)

    def execute(self, image_description: str, size: str, background: str = "light") -> str:
        if not self.image_generator:
            raise ValidationException("Image generation is not configured.")

        requested_width, requested_height = parse_size_string(size)
        normalized_background = validate_background(background)
        canvas_width, canvas_height = get_canvas_dimensions(requested_width, requested_height)
        target_width, target_height = calculate_target_dimensions(requested_width, requested_height)

        prompt = build_image_prompt(
            description=image_description,
            background=normalized_background,
            target_width=target_width,
            target_height=target_height,
        )

        try:
            output_bytes = generate_workspace_image_bytes(
                image_generator=self.image_generator,
                prompt=prompt,
                background=normalized_background,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                target_width=target_width,
                target_height=target_height,
            )
        except ValidationException as exc:
            image_generator_type = type(self.image_generator).__name__
            logger.info(f"Image generation validation error for image_generator={image_generator_type}: {exc}")
            raise ValidationException(f"{exc} (image_generator={image_generator_type})") from exc

        workspace_id = self._get_workspace_id()
        file_path = build_workspace_image_path()
        self.workspace_service.upsert_binary_file(workspace_id, file_path, output_bytes, self.user)
        sandbox_url = self.workspace_service.get_file_sandbox_url(workspace_id, file_path, self.user)

        return self._dump_json(
            {
                "workspace_path": file_path,
                "sandbox_url": sandbox_url,
                "mime_type": _PNG_MIME_TYPE,
                "width": target_width,
                "height": target_height,
            }
        )


def parse_size_string(size: str) -> tuple[float, float]:
    match = _SIZE_PATTERN.match(size or "")
    if not match:
        raise ValidationException(
            f"Invalid size format '{size}'. Expected format: 'widthxheight' (for example, '1920x1080')."
        )

    width = float(match.group(1).replace(",", "."))
    height = float(match.group(2).replace(",", "."))
    if width <= 0 or height <= 0:
        raise ValidationException(f"Invalid dimensions: {width}x{height}. Both width and height must be positive.")
    return width, height


def validate_background(background: str) -> str:
    normalized_background = (background or "light").strip().lower()
    if normalized_background not in _BACKGROUND_VALUES:
        allowed = ", ".join(sorted(_BACKGROUND_VALUES))
        raise ValidationException(f"Invalid background '{background}'. Must be one of: {allowed}")
    return normalized_background


def classify_orientation(width: float, height: float) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def calculate_target_dimensions(width: float, height: float) -> tuple[int, int]:
    max_width, max_height = get_canvas_dimensions(width, height)
    scale = min(max_width / width, max_height / height)
    scaled_width = int(round(width * scale))
    scaled_height = int(round(height * scale))
    return scaled_width, scaled_height


def get_canvas_dimensions(width: float, height: float) -> tuple[int, int]:
    return _BOUNDING_BOXES[classify_orientation(width, height)]


def get_orientation_hint(orientation: str, target_width: int, target_height: int) -> str:
    orientation_hint = ""

    if orientation == "landscape":
        percentage = target_height / _MIN_DIMENSION
        if percentage < 0.80:
            percentage += 0.1  # to have some margin
            orientation_hint = f"Landscape composition, draw in a full-width vertically centered horizontal strip that is {percentage * 100:.2f}% of total height"

    if orientation == "portrait":
        percentage = target_width / _MIN_DIMENSION
        if percentage < 0.80:
            percentage += 0.1  # to have some margin
            orientation_hint = f"Portrait composition, draw in a full-height horizontally centered vertical strip that is {percentage * 100:.2f}% of total width"

    return orientation_hint


def build_image_prompt(description: str, background: str, target_width: int, target_height: int) -> str:
    orientation = classify_orientation(target_width, target_height)
    orientation_hint = get_orientation_hint(orientation, target_width, target_height)
    return f"{description}\n\n" "Additional constraints:\n" f"- Composition {orientation}.\n" f"{orientation_hint}"


def normalize_generated_image_bytes(url: str | None, b64_data: str | None) -> bytes:
    if b64_data:
        return base64.b64decode(b64_data)
    if not url:
        raise ValidationException("Image generation returned no image data.")
    if url.startswith("data:image"):
        return base64.b64decode(url.split(",", 1)[1])

    response = requests.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def generate_workspace_image_bytes(
    image_generator: Any,
    prompt: str,
    background: str,
    canvas_width: int,
    canvas_height: int,
    target_width: int,
    target_height: int,
) -> bytes:
    canvas_size = f"{canvas_width}x{canvas_height}"
    base_image, mask_image = create_base_and_mask_images(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        target_width=target_width,
        target_height=target_height,
        background=background,
    )
    url, b64_data = image_generator.edit(
        prompt=prompt,
        image=base_image,
        mask=mask_image,
        size=canvas_size,
        output_format=_OUTPUT_FORMAT,
    )

    image_bytes = normalize_generated_image_bytes(url=url, b64_data=b64_data)
    return crop_image_to_dimensions(image_bytes, canvas_width, canvas_height, target_width, target_height)


def resize_image_to_png(image_bytes: bytes, width: int, height: int) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as image:
        source_image = image.convert("RGBA") if image.mode in {"RGBA", "LA", "P"} else image.convert("RGB")
        resized = ImageOps.contain(source_image, (width, height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized.save(output, format="PNG")
        return output.getvalue()


def create_base_and_mask_images(
    canvas_width: int,
    canvas_height: int,
    target_width: int,
    target_height: int,
    background: str,
) -> tuple[bytes, bytes]:
    background_rgb = (255, 255, 255) if background == "light" else (0, 0, 0)
    base_image = Image.new("RGB", (canvas_width, canvas_height), background_rgb)
    mask_image = Image.new("RGBA", (canvas_width, canvas_height), background_rgb + (255,))

    left = (canvas_width - target_width) // 2
    top = (canvas_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height

    transparent_mask = Image.new("RGBA", (target_width, target_height), background_rgb + (0,))
    mask_image.paste(transparent_mask, (left, top, right, bottom))

    base_output = io.BytesIO()
    base_image.save(base_output, format="PNG")

    mask_output = io.BytesIO()
    mask_image.save(mask_output, format="PNG")

    return base_output.getvalue(), mask_output.getvalue()


def crop_image_to_dimensions(
    image_bytes: bytes,
    canvas_width: int,
    canvas_height: int,
    target_width: int,
    target_height: int,
) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as image:
        source_image = image.convert("RGBA") if image.mode in {"RGBA", "LA", "P"} else image.convert("RGB")
        left = (canvas_width - target_width) // 2
        top = (canvas_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height
        cropped = source_image.crop((left, top, right, bottom))

        output = io.BytesIO()
        cropped.save(output, format="PNG")
        return output.getvalue()


def build_workspace_image_path(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"images/{timestamp}.png"
