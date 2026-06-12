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

"""DOCX loader that wraps markitdown with a resilient python-docx text fallback.

markitdown converts DOCX via mammoth, which raises ``AttributeError: 'TableCellUnmerged'
object has no attribute '_accept1'`` for documents whose table rows contain non-cell
elements (bookmarks, content controls / SDTs, comment ranges). Those constructs are common
in real-world documents, so a single such table would otherwise make the whole file fail to
index. When markitdown fails we fall back to extracting text directly with python-docx, which
does not rely on mammoth.
"""

from __future__ import annotations

import os
from typing import Iterator

from langchain_core.documents import Document
from langchain_markitdown import DocxLoader as MarkitdownDocxLoader

from codemie.configs import logger


class DocxLoader:
    """Load a DOCX file via markitdown, falling back to python-docx on conversion failure."""

    def __init__(self, file_path: str, **kwargs) -> None:
        self.file_path = file_path
        self._markitdown_loader = MarkitdownDocxLoader(file_path, **kwargs)

    def lazy_load(self) -> Iterator[Document]:
        try:
            documents = self._markitdown_loader.load()
        except Exception as primary_error:
            logger.warning(
                f"markitdown failed to convert DOCX {os.path.basename(self.file_path)}; "
                f"falling back to python-docx text extraction: {primary_error}",
                exc_info=True,
            )
            documents = self._fallback_load()
        yield from documents

    def _fallback_load(self) -> list[Document]:
        """Extract paragraphs and tables in document order using python-docx.

        Never raises: an unreadable file yields no documents so datasource creation
        skips it instead of failing, matching the existing best-effort extraction flow.
        """
        try:
            from docx import Document as DocxDocument

            doc = DocxDocument(self.file_path)
            parts = [block for block in (self._render_block(b) for b in self._iter_block_items(doc)) if block]
            content = "\n\n".join(parts)
        except Exception as fallback_error:
            logger.warning(
                f"python-docx fallback failed for DOCX {os.path.basename(self.file_path)}: {fallback_error}",
                exc_info=True,
            )
            return []

        if not content:
            # Nothing extractable: yield no documents rather than an empty chunk.
            return []

        metadata = {
            "source": self.file_path,
            "file_name": os.path.basename(self.file_path),
            "conversion_success": True,
            "conversion_fallback": "python-docx",
        }
        return [Document(page_content=content, metadata=metadata)]

    @staticmethod
    def _iter_block_items(parent):
        """Yield Paragraph and Table objects in their document order."""
        from docx.document import Document as _DocxDocumentType
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        parent_elm = parent.element.body if isinstance(parent, _DocxDocumentType) else parent.element
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    @classmethod
    def _render_block(cls, block) -> str:
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        if isinstance(block, Paragraph):
            return cls._render_paragraph(block)
        if isinstance(block, Table):
            return cls._render_table(block)
        return ""

    @staticmethod
    def _render_paragraph(paragraph) -> str:
        text = paragraph.text.strip()
        if not text:
            return ""
        style = (getattr(paragraph.style, "name", "") or "").lower()
        if style.startswith("heading"):
            digits = "".join(ch for ch in style if ch.isdigit())
            level = min(max(int(digits), 1), 6) if digits else 1
            return f"{'#' * level} {text}"
        if style == "title":
            return f"# {text}"
        return text

    @staticmethod
    def _escape_cell(text: str) -> str:
        """Collapse whitespace (so a cell stays on one line) and escape pipes (so it stays one column)."""
        return " ".join(text.split()).replace("|", r"\|")

    @staticmethod
    def _render_table(table) -> str:
        rows = []
        column_count = 0
        for row in table.rows:
            cells = [DocxLoader._escape_cell(cell.text) for cell in row.cells]
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
                if not column_count:
                    column_count = len(cells)
        if not rows:
            return ""
        if len(rows) > 1:
            separator = "| " + " | ".join(["---"] * column_count) + " |"
            rows.insert(1, separator)
        return "\n".join(rows)
