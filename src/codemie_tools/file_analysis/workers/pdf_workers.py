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

"""PDF workers for multiprocessing."""

import io

from codemie_tools.utils.image_processor import ImageProcessor
import pdfplumber


ERROR_NO_PDF_LOADED = "No PDF document is loaded"
ERROR_NO_PDF_LOADED_DETAIL = "No PDF document is loaded. Please provide a valid PDF."


def _ensure_pdf_object(pdf_document: pdfplumber.PDF | bytes) -> tuple[pdfplumber.PDF, bool]:
    """Ensure we have a pdfplumber.PDF object.

    Args:
        pdf_document: PDF object or bytes

    Returns:
        Tuple of (pdf_object, should_close)
    """
    if isinstance(pdf_document, pdfplumber.PDF):
        return pdf_document, False
    if isinstance(pdf_document, bytes):
        try:
            return pdfplumber.open(io.BytesIO(pdf_document)), True
        except Exception as e:
            raise ValueError(f"Failed to open PDF document: {str(e)}")
    raise ValueError("Object pdf_document should be instace of `bytes` or `pdfplumber.PDF` ")


def _get_pages_to_process(pdf_obj: pdfplumber.PDF, pages: list[int] | None = None) -> list[int] | range:
    """Get the range of pages to process.

    Args:
        pdf_obj: pdfplumber PDF object
        pages: Optional list of 1-based page numbers

    Returns:
        List of 0-based page indices or range object
    """
    if pages is None:
        return range(len(pdf_obj.pages))
    return [p - 1 for p in pages]


def extract_pdf_markdown(pdf_file: bytes | pdfplumber.PDF, pages: list[int] | None, page_chunks: bool = False) -> str:
    """
    Extract PDF as markdown with tables.

    Args:
        pdf_bytes: PDF file content as bytes
        zero_based_pages: List of 0-based page indices
        page_chunks: Include page headers in output

    Returns:
        Markdown-formatted text
    """
    try:
        # Track if we opened the PDF (caller didn't)
        should_close = False
        pdf_obj, should_close = _ensure_pdf_object(pdf_file)
        if not pdf_obj:
            raise ValueError(ERROR_NO_PDF_LOADED_DETAIL)
        pages_to_process = _get_pages_to_process(pdf_obj, pages)
        zero_based_pages = list(pages_to_process) if not isinstance(pages_to_process, list) else pages_to_process

        markdown_parts = []
        for page_idx in zero_based_pages:
            if page_idx >= len(pdf_obj.pages):
                continue
            page = pdf_obj.pages[page_idx]

            parts = []
            if page_chunks:
                parts.append(f"\n## Page {page_idx + 1}\n")

            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)

            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                if table:
                    table_md = _table_to_markdown(table)
                    parts.append(f"\n**Table {table_idx + 1}:**\n{table_md}\n")

            markdown_parts.extend(parts)

        # Only close if we opened it
        if should_close:
            pdf_obj.close()
        return "\n\n".join(markdown_parts)
    except Exception as e:
        raise e


def _table_to_markdown(table) -> str:
    """Helper for table markdown conversion."""
    if not table or not any(table):
        return ""

    md_lines = []
    for i, row in enumerate(table):
        if not row:
            continue
        cells = [str(cell or "").strip() for cell in row]
        md_lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(md_lines)
