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

from typing import TypedDict, TypeGuard


class ImageDocumentMetadata(TypedDict):
    """Metadata stored on image documents — both fields are always set together."""

    image_encoded_url: str
    image_mime_type: str


def is_image_document_metadata(meta: dict) -> TypeGuard[ImageDocumentMetadata]:
    return "image_encoded_url" in meta and "image_mime_type" in meta
