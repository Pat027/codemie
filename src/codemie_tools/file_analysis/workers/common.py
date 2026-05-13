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

"""Common helpers for file-analysis tools to reduce code duplication."""

from typing import Callable, Iterable, Optional, Any

from codemie_tools.base.constants import (
    SOURCE_DOCUMENT_KEY,
    SOURCE_FIELD_KEY,
    FILE_CONTENT_FIELD_KEY,
)
from codemie_tools.base.file_object import FileObject


def process_files_with_worker(
    files: Iterable[FileObject],
    worker: Callable[[FileObject], Any],
    *,
    to_text: Optional[Callable[[Any], str]] = None,
    header_builder: Optional[Callable[[FileObject], str]] = None,
) -> str:
    """
    Process files with a per-file worker and assemble LLM-friendly output.

    The worker is responsible for any heavy lifting (including use of process
    pools if necessary). This helper only orchestrates per-file calls and
    constructs a consistent output format that agents can consume.

    Args:
        files: Sequence of FileObject to process
        worker: Function that receives a FileObject and returns a result (any type)
        to_text: Optional converter for non-string results; defaults to str(result)
        header_builder: Optional function that builds header text per file

    Returns:
        Single string containing all file blocks.
    """

    result_parts: list[str] = []

    for file_obj in files:
        value = worker(file_obj)
        text = to_text(value) if to_text is not None else str(value)

        if header_builder is not None:
            header = header_builder(file_obj)
            result_parts.append(header)
        else:
            result_parts.append(f"\n{SOURCE_DOCUMENT_KEY}\n")
            result_parts.append(f"{SOURCE_FIELD_KEY} {file_obj.name}\n")
            result_parts.append(f"{FILE_CONTENT_FIELD_KEY} \n")

        result_parts.append(f"{text}\n")

    return "".join(result_parts)
