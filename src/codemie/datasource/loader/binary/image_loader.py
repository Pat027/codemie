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

import logging
import os
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from langchain_community.document_loaders.parsers import BaseImageBlobParser
from langchain_core.document_loaders import BaseLoader
from langchain_core.document_loaders.blob_loaders import Blob
from langchain_core.documents import Document
from PIL import Image
from PIL.ExifTags import TAGS

from codemie.configs import config
from codemie.datasource.datasource_file_storage import DatasourceFileStorage
from codemie.datasource.exceptions import SkippedFileException
from codemie.datasource.loader.models import ImageDocumentMetadata

logger = logging.getLogger(__name__)


@dataclass
class ImageMetadata:
    """Structured image metadata extracted from a file via PIL.

    All fields except ``file_name`` and ``file_size`` are optional and populated
    best-effort — extraction continues even when PIL cannot open the file.
    """

    file_name: str
    file_size: int
    format: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mode: Optional[str] = None
    exif: dict[str, str] = field(default_factory=dict)

    def to_text(self) -> str:
        """Render metadata as human-readable lines, skipping unpopulated fields."""
        lines = [f"Image: {self.file_name}"]
        lines.append(f"File Size: {self.file_size} bytes")
        if self.format:
            lines.append(f"Format: {self.format}")
        if self.width and self.height:
            lines.append(f"Dimensions: {self.width}x{self.height}")
        if self.mode:
            lines.append(f"Mode: {self.mode}")
        lines.extend(f"{tag}: {value}" for tag, value in self.exif.items())
        return "\n".join(lines)


class ImageLoader(BaseLoader):
    """LangChain loader for raster image files (JPEG, PNG, GIF, etc.).

    Combines two extraction strategies:
    - **Structural metadata** via PIL (dimensions, format, EXIF tags) — always available.
    - **Semantic content** via an ``images_parser`` (LLM vision or Tesseract OCR) appended
      to the metadata text as ``doc.page_content``.

    Image bytes are uploaded to ``storage`` (a ``DatasourceFileStorage``) and the returned
    encoded URL is stored in ``doc.metadata["image_encoded_url"]`` for on-demand retrieval
    at query time via ``FileService.get_image_base64``.
    """

    _WANTED_EXIF_TAGS = frozenset(
        {
            "DateTimeOriginal",
            "DateTime",
            "Make",
            "Model",
            "ImageDescription",
        }
    )
    _MAX_SIZE_BYTES: int = config.IMAGE_INDEXING_MAX_SIZE_BYTES

    def __init__(
        self,
        file_path: str,
        images_parser: BaseImageBlobParser,
        storage: DatasourceFileStorage,
    ) -> None:
        self.file_path = file_path
        self.images_parser = images_parser
        self.storage = storage

    # ---------- Public API ----------

    def lazy_load(self) -> Iterator[Document]:
        """Yield documents extracted from the image file.

        Each document's ``page_content`` is the parser output (OCR / LLM description)
        followed by the PIL metadata summary. ``doc.metadata["file_path"]`` is set to
        ``self.file_path``; callers are expected to overwrite ``source`` with the
        original (non-temp) file name.
        """
        file_size = os.path.getsize(self.file_path)
        if file_size > self._MAX_SIZE_BYTES:
            file_name = Path(self.file_path).name
            reason = f"size {file_size} bytes exceeds IMAGE_INDEXING_MAX_SIZE_BYTES={self._MAX_SIZE_BYTES} bytes"
            logger.info(f"Skipping image {file_name}: {reason}")
            raise SkippedFileException(file_name=file_name, reason=reason)

        metadata = self._extract_image_metadata()
        metadata_text = metadata.to_text()
        blob = Blob.from_path(self.file_path)
        img_meta = self._store_image(blob, metadata)
        for doc in self.images_parser.lazy_parse(blob):
            doc.page_content = f"{doc.page_content}\n\n{metadata_text}".strip()
            doc.metadata["file_path"] = self.file_path
            if img_meta:
                doc.metadata.update(img_meta)
            yield doc

    # ---------- Metadata extraction ----------

    def _extract_image_metadata(self) -> ImageMetadata:
        """Extract image metadata using PIL. Best-effort: never raises on PIL errors."""
        file_name = Path(self.file_path).name
        file_size = os.path.getsize(self.file_path)
        meta = ImageMetadata(file_name=file_name, file_size=file_size)

        try:
            with Image.open(self.file_path) as img:
                meta.format = img.format or self._extension_fallback(file_name)
                meta.mime_type = img.get_format_mimetype() or mimetypes.guess_type(file_name)[0]
                meta.width = img.width
                meta.height = img.height
                meta.mode = img.mode
                meta.exif = self._extract_exif(img)
        except Exception as e:
            logger.warning(f"PIL metadata extraction failed for {file_name}: {e}")
            meta.format = meta.format or self._extension_fallback(file_name)

        return meta

    @classmethod
    def _extract_exif(cls, img: Image.Image) -> dict[str, str]:
        """Extract wanted EXIF tags as ``{tag_name: value}``, skipping non-string values."""
        return {
            tag_name: value
            for tag_id, value in img.getexif().items()
            if isinstance(value, str) and (tag_name := TAGS.get(tag_id, str(tag_id))) in cls._WANTED_EXIF_TAGS
        }

    @staticmethod
    def _extension_fallback(file_name: str) -> str:
        """Return the uppercased file extension, or ``'UNKNOWN'`` if there is none."""
        return Path(file_name).suffix.lstrip(".").upper() or "UNKNOWN"

    # ---------- File storage ----------

    def _store_image(self, blob: Blob, metadata: ImageMetadata) -> ImageDocumentMetadata | None:
        """Upload image bytes to file storage and return the URL reference metadata dict.

        Returns ``None`` (with a warning log) only when the upload raises an exception,
        so callers can skip the metadata update rather than crash indexing.
        """
        mime_type = metadata.mime_type or blob.mimetype or "image/jpeg"
        try:
            file_bytes = blob.as_bytes()
            file_obj = self.storage.write_file(
                name=metadata.file_name,
                mime_type=mime_type,
                content=file_bytes,
            )
            return {
                "image_encoded_url": file_obj.to_encoded_url(),
                "image_mime_type": mime_type,
            }
        except Exception as e:
            logger.warning(f"Failed to store image {metadata.file_name} in file repository: {e}")
            return None
