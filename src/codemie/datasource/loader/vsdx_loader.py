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

"""LangChain-compatible loader for modern Visio (.vsdx) diagrams.

Extracts the text of each shape, page by page, using the pure-Python ``vsdx`` library
(``.vsdx`` is an OPC/ZIP package, the same family as .docx/.xlsx). One Document is emitted
per page that contains text. The legacy binary ``.vsd`` format is not supported.
"""

from __future__ import annotations

import os
from typing import Iterator

from langchain_core.documents import Document

from codemie.configs import logger


class VsdxLoader:
    """Load a .vsdx file and yield one Document per page that contains shape text."""

    def __init__(self, file_path: str, **kwargs) -> None:
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        try:
            from vsdx import VisioFile
        except ImportError as import_error:
            logger.warning(f"vsdx library is not installed; cannot parse Visio file: {import_error}")
            return

        source = os.path.basename(self.file_path)
        try:
            with VisioFile(self.file_path) as visio:
                pages = list(visio.pages)
                for page_number, page in enumerate(pages, start=1):
                    document = self._page_to_document(page, page_number, source)
                    if document is not None:
                        yield document
        except Exception as error:
            # A malformed/unreadable diagram should be skipped, not abort datasource creation.
            logger.warning(f"Failed to parse Visio file {source}: {error}", exc_info=True)

    def _page_to_document(self, page, page_number: int, source: str) -> Document | None:
        page_name = getattr(page, "name", None) or f"Page-{page_number}"
        texts = []
        try:
            for shape in page.all_shapes:
                text = (getattr(shape, "text", None) or "").strip()
                if text:
                    texts.append(text)
        except Exception as error:
            logger.warning(f"Failed to read shapes on page '{page_name}' of {source}: {error}", exc_info=True)
            return None

        if not texts:
            return None

        content = f"# {page_name}\n\n" + "\n".join(texts)
        metadata = {
            "source": source,
            "file_name": source,
            "page_name": page_name,
            "page_number": page_number,
            "conversion_success": True,
        }
        return Document(page_content=content, metadata=metadata)
