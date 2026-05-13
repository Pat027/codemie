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

"""
File processing workers for multiprocessing pools.

All workers are top-level functions that can be pickled and executed
in separate processes for CPU-intensive file parsing operations.
"""

from codemie_tools.file_analysis.workers.docx_workers import extract_docx_content, extract_docx_text
from codemie_tools.file_analysis.workers.markdown_workers import convert_file_to_markdown
from codemie_tools.file_analysis.workers.pdf_workers import extract_pdf_markdown
from codemie_tools.file_analysis.workers.xlsx_workers import load_xlsx, process_xlsx_to_markdown

__all__ = [
    "convert_file_to_markdown",
    "extract_pdf_markdown",
    "extract_docx_text",
    "extract_docx_content",
    "load_xlsx",
    "process_xlsx_to_markdown",
]
